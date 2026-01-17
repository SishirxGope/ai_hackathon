import pandas as pd
import numpy as np

def build_tabular_dataset(df: pd.DataFrame, feature_cols: list, target_col: str = "RUL") -> tuple:
    """
    Creates a tabular dataset using the last cycle of each engine.
    
    Args:
        df: Input DataFrame.
        feature_cols: List of feature columns to include.
        target_col: Name of the target column (default "RUL").
        
    Returns:
        tuple: (X, y)
            X: DataFrame containing features for the last cycle of each engine.
            y: Series containing the target value for the last cycle.
    """
    # Group by engine and take the last row
    last_rows = df.groupby('engine_id').last().reset_index()
    
    X = last_rows[feature_cols]
    y = last_rows[target_col]
    
    return X, y

def build_sequence_dataset(df: pd.DataFrame, feature_cols: list, window: int = 30, target_col: str = "RUL", max_samples: int = None) -> tuple:
    """
    Creates a sequence dataset (sliding window) for LSTM/RNN models.
    
    Args:
        df: Input DataFrame.
        feature_cols: List of feature columns to include.
        window: Size of the sliding window (default 30).
        target_col: Name of the target column (default "RUL").
        max_samples: Optional limit on number of samples to generate (for debugging).
        
    Returns:
        tuple: (X_seq, y_seq)
            X_seq: Numpy array of shape (num_samples, window, num_features).
            y_seq: Numpy array of shape (num_samples,).
    """
    X_seq = []
    y_seq = []
    
    # Process each engine independently to avoid mixing data across engines
    for engine_id, engine_df in df.groupby('engine_id'):
        
        # If max_samples reached, stop
        if max_samples is not None and len(X_seq) >= max_samples:
            break

        # If engine duration is shorter than window, we skip it (or zero-pad, but skipping is cleaner for quality)
        if len(engine_df) < window:
            continue
            
        data = engine_df[feature_cols].values
        targets = engine_df[target_col].values
        
        # Slide window
        # We want to go from index 0 -> window-1, 1 -> window, ...
        # Range of starting indices: 0 to len - window
        for i in range(len(engine_df) - window + 1):
            if max_samples is not None and len(X_seq) >= max_samples:
                break
                
            window_data = data[i : i + window]
            target = targets[i + window - 1] # Target at the last timestep of the window
            
            X_seq.append(window_data)
            y_seq.append(target)
            
    return np.array(X_seq), np.array(y_seq)

if __name__ == "__main__":
    from pipeline.data_loader import load_and_label
    from pipeline.sensor_cleaner import remove_constant_sensors
    from pipeline.normalizer import normalize_dataframe
    from pipeline.feature_engineering import add_degradation_features
    from pipeline.health_index import add_health_index
    from pipeline.config import DATA_PATH, TRAIN_FILE
    import os

    # Construct path
    train_path = os.path.join(DATA_PATH, TRAIN_FILE)
    
    if os.path.exists(train_path):
        print("Running full pipeline to prepare data...")
        
        # 1. Load
        df = load_and_label(train_path)
        
        # 2. Clean
        df_clean, kept_sensors = remove_constant_sensors(df)
        
        # 3. Normalize
        setting_cols = ['op1', 'op2', 'op3']
        features_to_normalize = setting_cols + kept_sensors
        df_norm, _ = normalize_dataframe(df_clean, features_to_normalize)
        
        # 4. Feature Engineering
        df_feat = add_degradation_features(df_norm, kept_sensors)
        
        # 5. Health Index
        # Using columns logic from previous health_index.py execution if available, 
        # or just letting the function filter internally as implemented in Step 327.
        # Ideally we pass all relevant columns or let it choose.
        # Let's pass the features from df_feat minus metadata.
        exclude_cols = ['engine_id', 'cycle', 'RUL']
        feature_cols_all = [c for c in df_feat.columns if c not in exclude_cols]
        df_final, _ = add_health_index(df_feat, feature_cols_all)
        
        print("\nBuilding datasets...")
        
        # Define features for the dataset (exclude ID, cycle, RUL, Health Index components if treated as target, etc.)
        # Usually we use the engineered features + kept sensors + settings.
        # And maybe we want to include health_index as a feature? Or is it a target? 
        # Prompt doesn't specify which features to use for the DATASET, just "feature_cols".
        # I'll use all feature columns available (excluding ID, RUL). 
        # I will include 'health_index' as a FEATURE potentially, or maybe just the physical features.
        # Given HI is a derived indicator, it might be a target or a feature. 
        # I'll stick to the "features" used for modeling RUL.
        # Let's effectively use `feature_cols_all` + maybe `health_index`.
        # I'll include `health_index` as it's a valuable high-level feature.
        
        dataset_features = feature_cols_all + ['health_index']
        # Remove health_index_raw if present as it is redundant/unscaled
        if 'health_index_raw' in dataset_features:
            dataset_features.remove('health_index_raw')
            
        print(f"Using {len(dataset_features)} features.")
        
        # Tabular
        X_tab, y_tab = build_tabular_dataset(df_final, dataset_features)
        print(f"X_tabular shape: {X_tab.shape}")
        print(f"y_tabular shape: {y_tab.shape}")
        
        # Sequence
        # Window size 30 is typical
        X_seq, y_seq = build_sequence_dataset(df_final, dataset_features, window=30)
        print(f"X_seq shape: {X_seq.shape}")
        print(f"y_seq shape: {y_seq.shape}")
        
    else:
        print(f"Error: File not found at {train_path}")
