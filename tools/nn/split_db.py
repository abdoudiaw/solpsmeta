import torch
import sklearn.metrics
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
#import _nn_learner
import nn_learner
import torch
from nn_learner import SOLVER_INDEXES
import collections

import sqlite3
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from utilities import insert_dataframe_to_db  # make sure this is available



if __name__=="__main__":
    print("PYTORCH VERSION",torch.__version__)
    DB_PATH = '../solps_diiid.db'
    TABLE_NAME = 'SOLPSDIIID'

    # Load full cleaned data into a DataFrame
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
    conn.close()

    print(f"📦 Loaded {len(df)} rows from cleaned database.")

    # Shuffle and split the dataset (80% train, 20% test)
    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)

    print(f"🧪 Split: {len(train_df)} training rows, {len(test_df)} testing rows")

    # Save to new databases
    insert_dataframe_to_db(train_df, 'solps_train.db', table='SOLPSDIIID')
    insert_dataframe_to_db(test_df, 'solps_test.db', table='SOLPSDIIID')
