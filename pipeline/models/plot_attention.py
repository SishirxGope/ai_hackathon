import torch
import torch.nn as nn
import numpy as np
import matplotlib.pyplot as plt
import os
import sys

from pipeline.models.transformer_model import RULTransformer
from pipeline.models.xgb_baseline import load_full_data
from pipeline.dataset_builder import build_sequence_dataset
from pipeline.config import DATA_PATH
from pipeline.models.train_transformer import DEVICE

def plot_attention():
    print("--- Starting Attention Visualization ---")
    
    # 1. Load Data for Engine 1
    print("Loading data...")
    df, features = load_full_data()
    
    # Filter for Engine 1
    engine_id = 1
    df_engine = df[df['engine_id'] == engine_id]
    
    if df_engine.empty:
        print(f"Error: Engine {engine_id} not found in data.")
        return

    print(f"Engine {engine_id} data shape: {df_engine.shape}")
    
    exclude_cols = ['engine_id', 'cycle', 'RUL']
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # Build Sequence (just need one, but build all for this engine)
    print("Building sequences...")
    X_seq, y_seq = build_sequence_dataset(df_engine, feature_cols, window=30)
    
    if len(X_seq) == 0:
        print("Error: No sequences generated (data too short?).")
        return
        
    # Take the last sequence (closest to failure)
    sample_idx = len(X_seq) - 1
    # Add batch dimension: (1, SeqLen, Feat)
    X_sample = torch.tensor(X_seq[sample_idx:sample_idx+1], dtype=torch.float32).to(DEVICE)
    y_sample = y_seq[sample_idx]
    
    print(f"Selected sample {sample_idx}. Shape: {X_sample.shape}. True RUL: {y_sample}")
    
    # 2. Load Model
    model_path = "pipeline/models/checkpoints/transformer.pt"
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        # Try to find it in relative path if running from root
        return
        
    input_dim = len(feature_cols)
    model = RULTransformer(input_dim=input_dim, d_model=48, nhead=4, num_layers=1, dropout=0.1).to(DEVICE)
    model.load_state_dict(torch.load(model_path))
    model.eval()
    
    # 3. Inference
    print("Running inference...")
    with torch.no_grad():
        pred, attn_weights = model(X_sample, return_attention=True)
        
    print(f"Prediction: {pred.item():.2f}")
    print(f"Attention Weights Shape: {attn_weights.shape}") # (Batch, NHead, Seq, Seq)
    
    # 4. Plotting
    # Move to CPU numpy
    # Shape: (1, 4, 30, 30)
    attn = attn_weights[0].cpu().numpy()
    
    # Average across heads: (30, 30)
    attn_avg = np.mean(attn, axis=0)
    
    output_dir = "outputs/attention"
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, f"engine_{engine_id}.png")
    
    plt.figure(figsize=(10, 8))
    # Use 'viridis' or 'plasma' for heatmap
    plt.imshow(attn_avg, cmap='viridis', aspect='auto')
    plt.colorbar(label='Attention Weight')
    plt.title(f"Self-Attention Heatmap (Engine {engine_id}, Last Sequence)\nAvg across heads. True RUL: {y_sample:.1f}, Pred: {pred.item():.1f}")
    plt.xlabel("Time Step (Key)")
    plt.ylabel("Time Step (Query)")
    
    # Invert Y axis to match matrix convention or keep as is? 
    # Usually attention maps have 0 at top-left.
    # Time 0 to 29.
    
    plt.savefig(save_path)
    plt.close()
    
    print(f"Saved attention plot to {save_path}")

if __name__ == "__main__":
    plot_attention()
