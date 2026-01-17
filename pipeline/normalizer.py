import pandas as pd
from sklearn.preprocessing import StandardScaler
import numpy as np

def normalize_dataframe(df: pd.DataFrame, feature_cols: list) -> tuple:
    """
    Normalizes specific columns of a DataFrame using StandardScaler.

    Args:
        df: Input DataFrame.
        feature_cols: List of column names to normalize.

    Returns:
        tuple: (normalized_df, scaler)
            normalized_df: DataFrame with specified columns normalized.
            scaler: Fitted StandardScaler object.
    """
    # Create a copy to avoid settingWithCopyWarning or modifying original
    df_norm = df.copy()
    
    # Initialize and fit scaler
    scaler = StandardScaler()
    scaler.fit(df[feature_cols])
    
    # Transform data
    df_norm[feature_cols] = scaler.transform(df[feature_cols])
    
    return df_norm, scaler

if __name__ == "__main__":
    from pipeline.data_loader import load_and_label
    from pipeline.sensor_cleaner import remove_constant_sensors
    from pipeline.config import DATA_PATH, TRAIN_FILE
    import os

    # Construct path
    train_path = os.path.join(DATA_PATH, TRAIN_FILE)
    
    if os.path.exists(train_path):
        # 1. Load Data
        print(f"Loading data from {train_path}...")
        df = load_and_label(train_path)
        
        # 2. Clean Sensors
        print("\nCleaning sensors...")
        df_clean, kept_sensors = remove_constant_sensors(df)
        
        # 3. Normalize Data
        # We only normalize the sensor columns that were kept.
        # Check if kept_sensors contains any non-feature columns (like settings) if we wanted to normalize those too.
        # But generally we normalize sensors and maybe settings. 
        # The prompt implies normalizing "given feature columns". 
        # Usually settings (op1, op2, op3) and sensors (s1..s21) are features.
        # For this test, let's normalize the kept_sensors + op columns.
        
        # Identifying feature columns: settings + kept_sensors
        setting_cols = ['op1', 'op2', 'op3']
        features_to_normalize = setting_cols + kept_sensors
        
        # Ensure all features exist in df (some might have been dropped if constant? usually op aren't dropped by sensor cleaner unless we passed them)
        # sensor_cleaner only looked at "s" prefix by default, so op cols are safe.
        
        print(f"\nNormalizing {len(features_to_normalize)} features...")
        df_norm, scaler = normalize_dataframe(df_clean, features_to_normalize)
        
        print(f"Normalized DataFrame shape: {df_norm.shape}")
        
        # 4. Verify Normalization
        print("\nVerification (First 3 features):")
        subset_cols = features_to_normalize[:3]
        
        means = df_norm[subset_cols].mean()
        stds = df_norm[subset_cols].std()
        
        print("\nMeans (should be close to 0):")
        print(means)
        
        print("\nStandard Deviations (should be close to 1):")
        print(stds)
        
    else:
        print(f"Error: File not found at {train_path}")
