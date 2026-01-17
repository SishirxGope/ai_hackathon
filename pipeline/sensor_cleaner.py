import pandas as pd
import numpy as np

def remove_constant_sensors(df: pd.DataFrame, sensor_prefix: str = "s", threshold: float = 1e-6):
    """
    Identifies and removes sensor columns with variance below a specified threshold.

    Args:
        df: Input DataFrame containing sensor data.
        sensor_prefix: Prefix of sensor column names (default "s").
        threshold: Variance threshold below which a sensor is considered constant (default 1e-6).

    Returns:
        tuple: (cleaned_df, kept_sensors)
            cleaned_df: The dataframe with constant sensors removed.
            kept_sensors: List of sensor column names that were retained.
    """
    
    # Identify sensor columns
    all_columns = df.columns
    sensor_cols = [col for col in all_columns if col.startswith(sensor_prefix)]
    
    # Compute variance for each sensor
    # We use var(ddof=1) which is unbiased sample variance, standard in pandas
    variances = df[sensor_cols].var()
    
    # Identify sensors to drop and keep
    drop_sensors = variances[variances < threshold].index.tolist()
    kept_sensors = variances[variances >= threshold].index.tolist()
    
    # Drop the constant sensors
    cleaned_df = df.drop(columns=drop_sensors)
    
    # Print statistics
    print(f"Original sensor count: {len(sensor_cols)}")
    print(f"Sensors removed: {len(drop_sensors)}")
    if drop_sensors:
        print(f"Removed sensors: {drop_sensors}")
    else:
        print("No sensors were removed.")
        
    return cleaned_df, kept_sensors

if __name__ == "__main__":
    from pipeline.data_loader import load_and_label
    from pipeline.config import DATA_PATH, TRAIN_FILE
    import os

    # Construct path
    # DATA_PATH = "data/"
    # TRAIN_FILE = "train_FD001.txt"
    train_path = os.path.join(DATA_PATH, TRAIN_FILE)
    
    if os.path.exists(train_path):
        print(f"Loading data from {train_path}...")
        df = load_and_label(train_path)
        
        print(f"\nOriginal DataFrame shape: {df.shape}")
        
        print("\nRunning remove_constant_sensors...")
        cleaned_df, kept_sensors = remove_constant_sensors(df)
        
        print(f"\nFinal DataFrame shape: {cleaned_df.shape}")
        print(f"Kept sensors: {kept_sensors}")
    else:
        print(f"Error: File not found at {train_path}")
