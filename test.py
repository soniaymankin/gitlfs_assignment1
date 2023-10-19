import pandas as pd

def hello():
    df = pd.read_csv("/Users/soniamankin/Documents/mlops_2023/assignment_1/athletes.csv")
    return df.head()