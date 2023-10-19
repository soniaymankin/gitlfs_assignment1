# -*- coding: utf-8 -*-
"""MLOPS HW1.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1ErqEMufUP9YYO0-FHvDYdIhQ0hh4xPt6

## Packages
"""

# !pip install --upgrade tensorflow
# !pip install --upgrade tensorflow_privacy

import os
import io
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import Lasso
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
import tensorflow as tf
import warnings
warnings.filterwarnings('ignore')

"""## Data Cleaning"""

v1 = pd.read_csv('/content/athletes.csv')
# Remove not relevant columns
v1['total_lift'] = v1[['deadlift','candj','snatch','backsq']].sum(axis=1)
v1 = v1.dropna(subset=['region','age','weight','height','howlong','gender','eat', \
                            'train','background','experience','schedule','howlong', \
                            'deadlift','candj','snatch','backsq','experience',\
                            'background','schedule','howlong'])
v1 = v1.drop(columns=['affiliate','team','name','athlete_id','fran','helen','grace',\
                          'filthy50','fgonebad','run400','run5k','pullups','train'])
v1 = v1[v1['gender'] != '--']

def clean(data):
  # Remove Outliers
  data = data[data['weight'] < 1500]
  data = data[data['gender'] != '--']
  data = data[data['age'] >= 18]
  data = data[(data['height'] < 96) & (data['height'] > 48)]

  data = data[(data['deadlift'] > 0) & (data['deadlift'] <= 1105)|((data['gender'] == 'Female') \
                & (data['deadlift'] <= 636))]
  data = data[(data['candj'] > 0) & (data['candj'] <= 395)]
  data = data[(data['snatch'] > 0) & (data['snatch'] <= 496)]
  data = data[(data['backsq'] > 0) & (data['backsq'] <= 1069)]

  # Clean Survey Data

  decline_dict = {'Decline to answer|': np.nan}
  data = data.replace(decline_dict)
  data = data.dropna(subset=['background','experience','schedule','howlong','eat'])
  return data

v2 = clean(v1)
v2.head()

"""## EDA"""

def EDA(df):
  cat_col = ['region', 'gender']
  for col in cat_col:
      counts = df[col].value_counts()
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.pie(counts, labels=None, autopct='%1.1f%%', startangle=90, colors=sns.color_palette("pastel", len(counts)))
      ax.legend(title=col, labels=['%s: %d' % (label, value) for label, value in zip(counts.index, counts)], loc='center left', bbox_to_anchor=(1, 0.5))
      plt.title(f'Distribution of {col}')
      plt.show()
      plt.close()
  num_col = ['age', 'height', 'weight', 'candj', 'snatch', 'deadlift', 'backsq']
  if df is v2:
      summary = df[num_col].describe()
      print(summary)
      for col in num_col:
        plt.figure(figsize=(8, 5))
        sns.histplot(df[col], kde=True, bins=30)
        plt.title(f'Distribution of {col}')
        plt.xlabel(col)
        plt.ylabel('Frequency')
        plt.show()
  else:
    summary = df[num_col].describe()
    print(summary)

EDA(v1)

EDA(v2)

"""## ML Model"""

noise_multiplier = 1
num_microbatches = 1
l2_norm_clip = 0.5
learning_rate = 0.001
num_epochs = 10
def nonDP(df):
  X = df[['region', 'gender', 'age', 'height', 'weight']]
  y = df['total_lift']

  # One-hot encode categorical features and scale numeric features
  transformer = ColumnTransformer([
      ('cat', OneHotEncoder(), ['region', 'gender']),
      ('num', StandardScaler(), ['age', 'height', 'weight'])
  ])

  X = transformer.fit_transform(X)
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

  model = tf.keras.Sequential([
      tf.keras.layers.Input(shape=(X_train.shape[1],)),
      tf.keras.layers.Dense(1)
  ])

  # Define the loss function and optimizer
  loss_function = tf.keras.losses.MeanSquaredError()
  non_dp_optimizer = tf.keras.optimizers.SGD(learning_rate=learning_rate)

  # Training loop for non-DP model
  non_dp_model = tf.keras.models.clone_model(model)
  non_dp_model.build(X_train.shape)
  non_dp_model.compile(optimizer=non_dp_optimizer, loss=loss_function)
  non_dp_model.fit(X_train.toarray(), y_train, epochs=num_epochs, verbose=0)

  # Calculate metrics for non-DP model
  non_dp_y_pred = non_dp_model.predict(X_test.toarray())
  non_dp_mse = mean_squared_error(y_test, non_dp_y_pred)
  non_dp_r_squared = r2_score(y_test, non_dp_y_pred)

  print("\nNon-Differentially Private Model:")
  print(f"MSE: {non_dp_mse}")
  print(f"R-squared: {non_dp_r_squared}")

"""## Delta Lake
#### Documentation: https://delta.io/blog/2022-10-15-version-pandas-dataset/

Write out the pandas DataFrame to a Delta table
"""

# !pip install deltalake
from deltalake import DeltaTable
from deltalake.writer import write_deltalake
os.makedirs("MLops/HW1", exist_ok=True)
write_deltalake("MLops/HW1", v1)
dt1 = DeltaTable("MLops/HW1")
dt1.to_pandas()

"""Overwrite the contents of the Delta table with a new DataFrame v2."""

write_deltalake("MLops/HW1", v2, mode="overwrite", overwrite_schema = True)

DeltaTable("MLops/HW1").to_pandas().head()

DeltaTable("MLops/HW1", version=0).to_pandas().head()

nonDP(DeltaTable("MLops/HW1", version=0).to_pandas())

nonDP(DeltaTable("MLops/HW1").to_pandas())

"""## DP Model"""

tf.compat.v1.disable_v2_behavior()
from tensorflow_privacy.privacy.optimizers.dp_optimizer import DPGradientDescentGaussianOptimizer
from tensorflow_privacy.privacy.analysis.compute_dp_sgd_privacy_lib import compute_dp_sgd_privacy_statement

def DP(df):
  X = df[['region', 'gender', 'age', 'height', 'weight']]
  y = df['total_lift']

  # One-hot encode categorical features and scale numeric features
  transformer = ColumnTransformer([
      ('cat', OneHotEncoder(), ['region', 'gender']),
      ('num', StandardScaler(), ['age', 'height', 'weight'])
  ])

  X = transformer.fit_transform(X)
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

  model = tf.keras.Sequential([
      tf.keras.layers.Input(shape=(X_train.shape[1],)),
      tf.keras.layers.Dense(1)
  ])

  # Define the loss function and optimizer
  loss_function = tf.keras.losses.MeanSquaredError()
  dp_optimizer = DPGradientDescentGaussianOptimizer(
      l2_norm_clip=l2_norm_clip,
      noise_multiplier=noise_multiplier,
      num_microbatches=num_microbatches,
      learning_rate=learning_rate)

  # Training loop for DP model
  dp_model = tf.keras.models.clone_model(model)
  dp_model.build(X_train.shape)
  dp_model.compile(optimizer=dp_optimizer, loss=loss_function)
  dp_model.fit(X_train.toarray(), y_train, epochs=num_epochs, verbose=0)

  # Calculate metrics for DP model
  dp_y_pred = dp_model.predict(X_test.toarray())
  dp_mse = mean_squared_error(y_test, dp_y_pred)
  dp_r_squared = r2_score(y_test, dp_y_pred)

  print("\nDifferentially Private Model:")
  print(f"MSE: {dp_mse}")
  print(f"R-squared: {dp_r_squared}")

  # Calculate the epsilon
  epsilon = compute_dp_sgd_privacy_statement(
      number_of_examples=len(X_train.toarray()),
      batch_size=len(X_train.toarray()) // num_microbatches,
      noise_multiplier=noise_multiplier,
      num_epochs=num_epochs,
      delta=1e-5
  )
  print(f"Epsilon: {epsilon}")

DP(DeltaTable("MLops/HW1").to_pandas())