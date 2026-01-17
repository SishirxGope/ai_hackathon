import pandas as pd
import numpy as np

def load_and_label(filepath) -> pd.DataFrame:
    """
    Loads the NASA CMAPSS dataset, assigns column names, computes RUL, and returns a DataFrame.
    """
    # Define column names
    index_cols = ['engine_id', 'cycle']
    setting_cols = ['op1', 'op2', 'op3']
    sensor_cols = [f's{i}' for i in range(1, 22)]
    cols = index_cols + setting_cols + sensor_cols

    # Load data
    # The data is space-separated and header-less
    df = pd.read_csv(filepath, sep=r'\s+', header=None, names=cols)

    # Sort by engine_id and cycle
    df = df.sort_values(['engine_id', 'cycle'])

    # Compute RUL (Remaining Useful Life)
    # RUL = max_cycle_for_that_engine - current_cycle
    # We group by engine_id and get the max cycle for each group
    rul = df.groupby('engine_id')['cycle'].max().reset_index()
    rul.columns = ['engine_id', 'max_cycle']
    
    # Merge max_cycle back to the original dataframe
    df = df.merge(rul, on='engine_id', how='left')
    
    # Calculate RUL
    df['RUL'] = df['max_cycle'] - df['cycle']
    
    # Cap RUL at 125 (Piecewise Linear Degradation)
    df['RUL'] = df['RUL'].clip(upper=125)
    
    # Drop max_cycle as it's no longer needed, keeping RUL
    df = df.drop(columns=['max_cycle'])

    return df

if __name__ == "__main__":
    import os
    # Loading configuration to use path is a better practice but user asked for specific path in main block
    # so we will use the relative path as requested.
    train_file = "data/train_FD001.txt"
    
    if os.path.exists(train_file):
        print(f"Loading data from {train_file}...")
        df_train = load_and_label(train_file)
        
        print(f"\nNumber of unique engines: {df_train['engine_id'].nunique()}")
        print(f"Max cycle value: {df_train['cycle'].max()}")
        
        print("\nHead of dataframe:")
        print(df_train.head())

        # Confirm last cycle of each engine has RUL = 0
        # We process each engine to check the last row
        last_rows = df_train.groupby('engine_id').last()
        if (last_rows['RUL'] == 0).all():
             print("\nSUCCESS: Last cycle of each engine has RUL = 0.")
        else:
             print("\nWARNING: Some engines do not end with RUL = 0.")
             # Print engines where RUL != 0
             print(last_rows[last_rows['RUL'] != 0])

    else:
        print(f"Error: File {train_file} not found. Please run from project root.")
