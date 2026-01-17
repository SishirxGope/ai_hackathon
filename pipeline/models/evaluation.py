import os
import sys

# Update path to find 'pipeline' module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import pandas as pd
import torch
import numpy as np
from pipeline.models.xgb_baseline import XGBoostBaseline
from pipeline.utils import compute_metrics, plot_actual_vs_pred, plot_residuals
from pipeline.models.transformer_model import RULTransformer
from pipeline.dataset_builder import build_sequence_dataset
from pipeline.models.train_transformer import DEVICE

OUTPUT_DIR = "output"

def evaluate_track_a(model_path, X, y):
    """
    Evaluates the XGBoost baseline model.
    
    Args:
        model_path: Path to the saved model (.pkl)
        X: Feature DataFrame
        y: Target Series (RUL)
    """
    print(f"\n--- Evaluating Model from {model_path} ---")
    
    try:
        # 1. Load Model
        if not os.path.exists(model_path):
            print(f"Error: Model not found at {model_path}")
            return
            
        model = XGBoostBaseline.load(model_path)
        
        # Align columns
        expected = model.model.get_booster().feature_names
        X = X[expected]
        
        # 2. Predict
        preds = model.predict(X)
        
        # 3. MEtrics
        rmse, mae = compute_metrics(y, preds)
        print(f"Evaluation Results:")
        print(f"  RMSE: {rmse:.4f}")
        print(f"  MAE:  {mae:.4f}")
        
        # 4. Plots
        plot_actual_vs_pred(y, preds, 
                            title="XGBoost Baseline: Actual vs Predicted RUL",
                            save_path=os.path.join(OUTPUT_DIR, "xgb_actual_vs_pred.png"))
                            
        plot_residuals(y, preds, 
                       save_path=os.path.join(OUTPUT_DIR, "xgb_residuals.png"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRITICAL ERROR: {e}")


def evaluate_track_b(model_path, df, features):
    """
    Evaluates the Transformer model.
    """
    print(f"\n--- Evaluating Transformer from {model_path} ---")
    
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    # 1. Build Sequences
    # Ensure window matches training (50)
    window = 50
    print(f"Building sequences (Window={window})...")
    X_seq, y_seq = build_sequence_dataset(df, features, window=window)
    
    if len(X_seq) == 0:
        print("Error: No sequences built.")
        return
        
    input_dim = len(features)
    
    # 2. Load Model
    # Ensure config matches training (d_model=64, layers=2)
    model = RULTransformer(input_dim=input_dim, d_model=64, nhead=4, num_layers=2, dropout=0.1).to(DEVICE)
    model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    model.eval()
    
    # 3. Predict
    print("Predicting...")
    dataset = torch.utils.data.TensorDataset(
        torch.tensor(X_seq, dtype=torch.float32),
        torch.tensor(y_seq, dtype=torch.float32)
    )
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=False)
    
    preds = []
    targets = []
    
    with torch.no_grad():
        for X_batch, y_batch in dataloader:
            X_batch = X_batch.to(DEVICE)
            outputs = model(X_batch)
            preds.extend(outputs.cpu().numpy())
            targets.extend(y_batch.numpy())
            
    preds = np.array(preds)
    targets = np.array(targets)
    
    # 4. Metrics
    rmse, mae = compute_metrics(targets, preds)
    print(f"Transformer Results:")
    print(f"  RMSE: {rmse:.4f}")
    print(f"  MAE:  {mae:.4f}")
    
    # 5. Plots
    plot_actual_vs_pred(targets, preds, 
                        title="Transformer: Actual vs Predicted RUL",
                        save_path=os.path.join(OUTPUT_DIR, "transformer_actual_vs_pred.png"))
                        
    plot_residuals(targets, preds, 
                   save_path=os.path.join(OUTPUT_DIR, "transformer_residuals.png"))

if __name__ == "__main__":
    # Test run (requires data to be loaded)
    from pipeline.models.xgb_baseline import load_full_data
    
    df, features = load_full_data()
    X = df[features].copy()
    
    if "health_index" not in X.columns:
        X["health_index"] = df["health_index"]
    if "health_index_raw" not in X.columns:
        X["health_index_raw"] = df["health_index_raw"]

    y = df['RUL']
    
    model_path = "pipeline/models/checkpoints/xgb_model.pkl"
    evaluate_track_a(model_path, X, y)
    
    trans_path = "pipeline/models/checkpoints/transformer.pt"
    
    # Re-derive features to match training (includes health_index)
    exclude_cols = ['engine_id', 'cycle', 'RUL']
    features_all = [c for c in df.columns if c not in exclude_cols]
    
    evaluate_track_b(trans_path, df, features_all)
