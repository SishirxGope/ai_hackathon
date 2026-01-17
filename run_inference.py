import sys
import os
import torch
import numpy as np
import pandas as pd
import joblib

# Adjust path to ensure we can import pipeline
sys.path.append(os.getcwd())

from pipeline.data_loader import load_and_label
from pipeline.sensor_cleaner import remove_constant_sensors
from pipeline.normalizer import normalize_dataframe
from pipeline.feature_engineering import add_degradation_features
from pipeline.health_index import add_health_index
from pipeline.dataset_builder import build_sequence_dataset
from pipeline.models.transformer_model import RULTransformer
from pipeline.models.uncertainty import predict_uncertainty
from pipeline.models.train_transformer import DEVICE
from pipeline.utils import compute_health_percentage, infer_max_rul_from_training
from pipeline.config import DATA_PATH, TEST_FILE, TRAIN_FILE

def load_and_process_test_data():
    """
    Loads test data and applies the same preprocessing pipeline as training.
    Returns:
        df_final: Processed DataFrame with health_index
        feature_cols: List of feature column names
        scaler: Normalizer (for reference if needed)
        pca: PCA model (for reference if needed)
    """
    print("Loading test data...")
    test_file_path = os.path.join(DATA_PATH, TEST_FILE)
    
    # 1. Load Data
    df = load_and_label(test_file_path)
    print(f"Test data loaded. Shape: {df.shape}")
    
    # 2. Clean Sensors (use same logic as training)
    df_clean, kept_sensors = remove_constant_sensors(df)
    print(f"Shape after cleaning: {df_clean.shape}")
    
    # 3. Normalize Data
    setting_cols = ['op1', 'op2', 'op3']
    features_to_normalize = setting_cols + kept_sensors
    df_norm, scaler = normalize_dataframe(df_clean, features_to_normalize)
    print(f"Shape after normalization: {df_norm.shape}")
    
    # 4. Feature Engineering
    df_feat = add_degradation_features(df_norm, kept_sensors)
    print(f"Shape after feature engineering: {df_feat.shape}")
    
    # 5. Health Index
    print("Computing health index...")
    exclude_cols = ['engine_id', 'cycle', 'RUL']
    feature_cols = [c for c in df_feat.columns if c not in exclude_cols]
    
    df_final, pca = add_health_index(df_feat, feature_cols)
    print(f"Health Index computed. Min: {df_final['health_index'].min():.4f}, Max: {df_final['health_index'].max():.4f}")
    
    return df_final, feature_cols, scaler, pca

def load_models():
    """
    Loads the Transformer and XGBoost models.
    Returns:
        transformer: Loaded Transformer model
        xgb_model: Loaded XGBoost model
    """
    print("\nLoading models...")
    
    # Load Transformer
    trans_path = "pipeline/models/checkpoints/transformer.pt"
    if not os.path.exists(trans_path):
        raise FileNotFoundError(f"Transformer model not found at {trans_path}")
    
    # We need to infer input_dim from the test data
    # For now, use a placeholder and will be set when loading data
    transformer = None
    print(f"Transformer model found at {trans_path}")
    
    # Load XGBoost
    xgb_path = "pipeline/models/checkpoints/xgb_model.pkl"
    if not os.path.exists(xgb_path):
        raise FileNotFoundError(f"XGBoost model not found at {xgb_path}")
    
    xgb_model = joblib.load(xgb_path)
    print(f"XGBoost model loaded from {xgb_path}")
    
    return transformer, xgb_model

def run_inference():
    """
    Main inference pipeline:
    1. Load and process test data
    2. Build sequence dataset
    3. Load models
    4. For each engine: predict RUL, uncertainty, health_percentage
    5. Save results to CSV
    """
    print("=" * 60)
    print("Starting RUL Inference Pipeline")
    print("=" * 60)
    
    # 1. Load and process test data
    df_test, feature_cols, scaler, pca = load_and_process_test_data()
    
    # Get max_rul from training data for health percentage calculation
    print("\nInferring max_rul from training data...")
    train_file_path = os.path.join(DATA_PATH, TRAIN_FILE)
    df_train_raw = load_and_label(train_file_path)
    max_rul = infer_max_rul_from_training(df_train_raw)
    print(f"Max RUL from training: {max_rul:.2f}")
    
    # 2. Build sequence dataset per engine
    print("\nBuilding sequence dataset (window=30)...")
    X_seq, y_seq = build_sequence_dataset(df_test, feature_cols, window=30, max_samples=None)
    print(f"Sequence dataset shape: {X_seq.shape}")
    
    if len(X_seq) == 0:
        raise ValueError("No sequence samples generated. Check data.")
    
    input_dim = X_seq.shape[2]
    print(f"Input dimension: {input_dim}")
    
    # 3. Load models
    _, xgb_model = load_models()
    
    # Load Transformer now that we know input_dim
    trans_path = "pipeline/models/checkpoints/transformer.pt"
    transformer = RULTransformer(input_dim=input_dim, d_model=48, nhead=4, num_layers=1, dropout=0.1).to(DEVICE)
    transformer.load_state_dict(torch.load(trans_path))
    transformer.eval()
    print(f"Transformer model loaded successfully")
    
    # 4. Prepare results list
    results = []
    
    # Map sample index to engine_id by processing sequences
    # We need to track which engine each sequence belongs to
    engine_ids = []
    sample_idx = 0
    
    for engine_id in df_test['engine_id'].unique():
        engine_data = df_test[df_test['engine_id'] == engine_id]
        engine_features = engine_data[feature_cols].values
        
        # Build sequences for this engine
        num_samples = len(engine_features) - 30 + 1
        if num_samples > 0:
            for i in range(num_samples):
                engine_ids.append(engine_id)
    
    print(f"\nProcessing {len(X_seq)} samples for {df_test['engine_id'].nunique()} engines...")
    
    # 5. Run inference on each sample
    for i in range(len(X_seq)):
        engine_id = engine_ids[i]
        
        # Prepare sample
        sample_seq = torch.tensor(X_seq[i:i+1], dtype=torch.float32).to(DEVICE)
        
        # Predict RUL using Transformer (primary model)
        with torch.no_grad():
            pred_rul = transformer(sample_seq).item()
        
        # Predict uncertainty using MC Dropout
        mean_preds, std_preds, _ = predict_uncertainty(transformer, sample_seq, n_samples=30)
        uncertainty_std = std_preds[0]
        
        # Compute health percentage
        health_percent = compute_health_percentage(pred_rul, max_rul)
        
        results.append({
            'engine_id': int(engine_id),
            'predicted_rul': float(pred_rul),
            'health_percent': float(health_percent),
            'uncertainty_std': float(uncertainty_std)
        })
        
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} / {len(X_seq)} samples")
    
    # 6. Convert to DataFrame and save CSV
    results_df = pd.DataFrame(results)
    
    # Create output directory if needed
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "predictions.csv")
    results_df.to_csv(output_path, index=False)
    print(f"\nResults saved to {output_path}")
    
    # 7. Print summary
    print("\n" + "=" * 60)
    print("INFERENCE SUMMARY")
    print("=" * 60)
    print(f"Total predictions: {len(results_df)}")
    print(f"Number of engines: {results_df['engine_id'].nunique()}")
    print(f"\nPredicted RUL Statistics:")
    print(f"  Mean: {results_df['predicted_rul'].mean():.2f}")
    print(f"  Std: {results_df['predicted_rul'].std():.2f}")
    print(f"  Min: {results_df['predicted_rul'].min():.2f}")
    print(f"  Max: {results_df['predicted_rul'].max():.2f}")
    
    print(f"\nHealth Percentage Statistics:")
    print(f"  Mean: {results_df['health_percent'].mean():.2f}%")
    print(f"  Std: {results_df['health_percent'].std():.2f}%")
    print(f"  Min: {results_df['health_percent'].min():.2f}%")
    print(f"  Max: {results_df['health_percent'].max():.2f}%")
    
    print(f"\nUncertainty Std Statistics:")
    print(f"  Mean: {results_df['uncertainty_std'].mean():.4f}")
    print(f"  Std: {results_df['uncertainty_std'].std():.4f}")
    print(f"  Min: {results_df['uncertainty_std'].min():.4f}")
    print(f"  Max: {results_df['uncertainty_std'].max():.4f}")
    
    print(f"\nSample predictions:")
    print(results_df.head(10).to_string())
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Inference pipeline completed successfully!")
    print("=" * 60)
    
    return results_df

if __name__ == "__main__":
    try:
        results_df = run_inference()
    except Exception as e:
        print(f"\n[ERROR] Inference pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
