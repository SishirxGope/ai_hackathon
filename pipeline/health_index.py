import pandas as pd
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import re

def add_health_index(df: pd.DataFrame, feature_cols: list = None, n_components: int = 1) -> tuple:
    """
    Computes a Health Index (HI) using PCA with specific feature selection and smoothing.
    
    Args:
        df: Input DataFrame.
        feature_cols: Optional list of candidate features. If None, considers all columns.
                     Function applies internal filtering regardless.
        n_components: Number of PCA components (default 1).
        
    Returns:
        tuple: (df, pca_object)
            df: DataFrame with 'health_index_raw' and 'health_index' columns.
            pca_object: Fitted PCA object.
    """
    df_hi = df.copy()
    
    # Feature Selection Logic
    # Candidates: original sensors (sX), rolling means (sX_rmY), trends (sX_trend)
    # Exclude: delta, drift, op conditions
    
    # Identify all columns if feature_cols not provided
    candidates = feature_cols if feature_cols is not None else df_hi.columns
    
    selected_features = []
    
    for col in candidates:
        # Exclude specific patterns
        if 'delta' in col or 'drift' in col or col.startswith('op'):
            continue
        if col in ['engine_id', 'cycle', 'RUL', 'health_index', 'health_index_raw']:
            continue
            
        # Include patterns
        # 1. Original sensors: "s" followed by digits only
        is_original = bool(re.match(r'^s\d+$', col))
        # 2. Rolling mean: ends with _rm followed by digits
        is_rolling_mean = bool(re.search(r'_rm\d+$', col))
        # 3. Trend: ends with _trend
        is_trend = col.endswith('_trend')
        
        if is_original or is_rolling_mean or is_trend:
            selected_features.append(col)
            
    print(f"Selected {len(selected_features)} features for PCA out of {len(candidates)} candidates.")
    # print(f"Features: {selected_features}")

    if not selected_features:
        raise ValueError("No features selected for PCA. Check column names.")

    # Fit PCA
    pca = PCA(n_components=n_components)
    # Fit on the selected features
    df_hi['health_index_raw'] = pca.fit_transform(df_hi[selected_features])
    
    # Smoothing
    # For each engine, smooth health_index_raw using rolling mean (window=5)
    # We use transform to keep the index aligned
    df_hi['health_index_raw'] = df_hi.groupby('engine_id')['health_index_raw'].transform(
        lambda x: x.rolling(window=5, min_periods=1).mean()
    )
    
    # Normalize between 0 and 1 (Global min-max)
    scaler = MinMaxScaler()
    df_hi['health_index'] = scaler.fit_transform(df_hi[['health_index_raw']])
    
    # Determine direction
    # We want Healthy (early cycles) ~ 1 and Failing (late cycles) ~ 0
    # Check correlation with cycle
    correlation = df_hi['health_index'].corr(df_hi['cycle'])
    
    # If correlation is positive, HI increases with cycle (0 -> 1). We want 1 -> 0.
    if correlation > 0:
        df_hi['health_index'] = 1 - df_hi['health_index']
        
    return df_hi, pca

if __name__ == "__main__":
    from pipeline.data_loader import load_and_label
    from pipeline.sensor_cleaner import remove_constant_sensors
    from pipeline.normalizer import normalize_dataframe
    from pipeline.feature_engineering import add_degradation_features
    from pipeline.config import DATA_PATH, TRAIN_FILE
    import os

    # Construct path
    train_path = os.path.join(DATA_PATH, TRAIN_FILE)
    
    if os.path.exists(train_path):
        print("1. Loading...")
        df = load_and_label(train_path)
        
        print("2. Cleaning...")
        df_clean, kept_sensors = remove_constant_sensors(df)
        
        print("3. Normalizing...")
        setting_cols = ['op1', 'op2', 'op3']
        features_to_normalize = setting_cols + kept_sensors
        df_norm, _ = normalize_dataframe(df_clean, features_to_normalize)
        
        print("4. Feature Engineering...")
        df_feat = add_degradation_features(df_norm, kept_sensors)
        
        print("5. Health Index...")
        # We can pass all columns, the function filters internally
        df_final, pca = add_health_index(df_feat)
        
        print(f"HI Min: {df_final['health_index'].min():.4f}")
        print(f"HI Max: {df_final['health_index'].max():.4f}")
        
        print("Head of Health Index columns:")
        print(df_final[['engine_id', 'cycle', 'RUL', 'health_index']].head())
        
        # Plotting
        print("\nPlotting Health Index for Engine 1...")
        engine1 = df_final[df_final['engine_id'] == 1]
        
        plt.figure(figsize=(12, 6))
        plt.plot(engine1['cycle'], engine1['health_index'], label='Health Index', linewidth=2)
        plt.title('Health Index vs Cycle (Engine 1)')
        plt.xlabel('Cycle')
        plt.ylabel('Health Index (1=Healthy, 0=Failure)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Save plot
        output_plot = 'health_index_engine_1.png'
        plt.savefig(output_plot, dpi=150)
        print(f"Plot saved to {output_plot}")
        
    else:
        print(f"Error: File not found at {train_path}")
