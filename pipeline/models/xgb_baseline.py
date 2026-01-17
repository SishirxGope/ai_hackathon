import xgboost as xgb
import numpy as np
import pandas as pd
import joblib
import os
from sklearn.model_selection import GroupKFold
from pipeline.config import DATA_PATH, TRAIN_FILE
from pipeline.data_loader import load_and_label
from pipeline.sensor_cleaner import remove_constant_sensors
from pipeline.normalizer import normalize_dataframe
from pipeline.feature_engineering import add_degradation_features
from pipeline.health_index import add_health_index
from pipeline.utils import compute_metrics

METRICS_PATH = "pipeline/models/checkpoints"
XGB_MODEL_PATH = os.path.join(os.path.dirname(__file__), "checkpoints", "xgb_model.pkl")


class XGBoostBaseline:
    def __init__(self, n_estimators=300, max_depth=5, learning_rate=0.05, 
                 subsample=0.8, colsample_bytree=0.8, random_state=42):
        self.model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            objective='reg:squarederror', # standard squared error
            random_state=random_state,
            n_jobs=-1
        )
        
    def train(self, X, y):
        self.model.fit(X, y)
        
    def predict(self, X):
        return self.model.predict(X)
        
    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.model, path)
        print(f"Model saved to {path}")
        
    @staticmethod
    def load(path):
        model = joblib.load(path)
        xgb_instance = XGBoostBaseline()
        xgb_instance.model = model
        return xgb_instance



def load_full_data():
    """
    Runs the Phase 1 pipeline to get the fully processed DataFrame 
    (not just the last rows, but full trajectory).
    """
    file_path = os.path.join(DATA_PATH, TRAIN_FILE)
    print(f"Loading data from {file_path}...")
    
    # 1. Load
    df = load_and_label(file_path)
    
    # 2. Clean
    df_clean, kept_sensors = remove_constant_sensors(df)
    
    # 3. Normalize
    setting_cols = ['op1', 'op2', 'op3']
    features_to_normalize = setting_cols + kept_sensors
    df_norm, _ = normalize_dataframe(df_clean, features_to_normalize)
    
    # 4. Features
    df_feat = add_degradation_features(df_norm, kept_sensors)
    
    # 5. Health Index
    print("Computing Health Index...")
    exclude_cols = ['engine_id', 'cycle', 'RUL']
    # Select features usually used for modeling
    feature_cols = [c for c in df_feat.columns if c not in exclude_cols]
    
    df_final, _ = add_health_index(df_feat, feature_cols)
    
    print(f"Columns after processing: {df_final.columns.tolist()[:10]} ...")
    
    # Assert health_index is present
    assert "health_index" in df_final.columns, "CRITICAL FAIL: health_index missing!"
    
    return df_final, feature_cols

def train_xgb_baseline_model(df=None):
    print("--- Starting Track A: XGBoost Baseline Training ---")
    
    # 1. Get Data
    if df is None:
        df, feature_cols = load_full_data()
    else:
        # Recalculate feature cols if df is passed
        exclude_cols = ['engine_id', 'cycle', 'RUL']
        feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    X = df[feature_cols]
    y = df['RUL']
    groups = df['engine_id']
    
    print(f"Data Shape: {X.shape}, Features: {len(feature_cols)}")
    
    # 2. Cross Validation (GroupKFold)
    gkf = GroupKFold(n_splits=5)
    rmse_scores = []
    
    print("\nRunning 5-Fold CV (Grouped by Engine)...")
    
    fold = 1
    for train_idx, val_idx in gkf.split(X, y, groups):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        
        xgb_model = XGBoostBaseline()
        xgb_model.train(X_train, y_train)
        
        preds = xgb_model.predict(X_val)
        rmse, _ = compute_metrics(y_val, preds)
        rmse_scores.append(rmse)
        print(f"Fold {fold} RMSE: {rmse:.4f}")
        fold += 1
        
    mean_rmse = np.mean(rmse_scores)
    print(f"\nMean CV RMSE: {mean_rmse:.4f}")
    
    # 3. Final Model Training (Full Data)
    print("Training final model on full dataset...")
    final_model = XGBoostBaseline()
    final_model.train(X, y)
    
    # Evaluate on full data (just to see basic fit)
    final_preds = final_model.predict(X)
    final_rmse, _ = compute_metrics(y, final_preds)
    print(f"Final Model Train RMSE: {final_rmse:.4f}")
    
    # 4. Save
    # Use the constant path
    final_model.save(XGB_MODEL_PATH)
    
    return final_model, X, y


def load_xgb_model():
    if not os.path.exists(XGB_MODEL_PATH):
        raise FileNotFoundError(f"XGBoost model not found at {XGB_MODEL_PATH}")
    model = joblib.load(XGB_MODEL_PATH)
    print(f"Loaded XGBoost model from: {XGB_MODEL_PATH}")
    return model


if __name__ == "__main__":
    train_xgb_baseline_model()
