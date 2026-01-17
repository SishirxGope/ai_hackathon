import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import numpy as np
import os
import copy
import sys
from pipeline.models.transformer_model import RULTransformer
from pipeline.config import DATA_PATH, TRAIN_FILE
# Import pipeline components to build dataset on the fly if needed
# But better to reuse specific functions or the run_pipeline variables if pass-able.
# Here we will re-run the dataset builder logic to be standalone.
from pipeline.models.xgb_baseline import load_full_data
from pipeline.dataset_builder import build_sequence_dataset
from pipeline.utils import compute_metrics
import plotext as plt

import time

DEBUG_FAST = False

BATCH_SIZE = 32
EPOCHS = 50 
LR = 1e-3
PATIENCE = 20 # Increased to force longer training
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"Imports done. Device: {DEVICE}")
sys.stdout.flush()

def load_seq_data():
    """
    Loads data and splits it by ENGINE ID to prevent leakage.
    Returns:
        X_train_seq, y_train_seq, X_val_seq, y_val_seq, input_dim
    """
    print("Loading full data...")
    sys.stdout.flush()
    df, features = load_full_data()
    print(f"Data loaded. Shape: {df.shape}.")
    sys.stdout.flush()
    
    exclude_cols = ['engine_id', 'cycle', 'RUL']
    # Ensure features match
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # --- SPLIT BY ENGINE ID ---
    engine_ids = df['engine_id'].unique()
    np.random.seed(42) # Fixed seed for reproducibility
    np.random.shuffle(engine_ids)
    
    split_idx = int(len(engine_ids) * 0.8)
    train_engines = engine_ids[:split_idx]
    val_engines = engine_ids[split_idx:]
    
    print(f"Total Engines: {len(engine_ids)}. Train: {len(train_engines)}, Val: {len(val_engines)}")
    
    # Filter DataFrames
    df_train = df[df['engine_id'].isin(train_engines)].copy()
    df_val = df[df['engine_id'].isin(val_engines)].copy()
    
    print(f"Building Sequence Datasets with {len(feature_cols)} features...")
    if DEBUG_FAST:
        print("DEBUG MODE: Using limit on samples (per split logic applied later, but here just warning)")
    sys.stdout.flush()
    
    # Pass max_samples to limit total sequences generated if needed
    max_samp = 2000 if DEBUG_FAST else None
    
    # Build Train Sequences
    print("Building Train Sequences...")
    X_train, y_train = build_sequence_dataset(df_train, feature_cols, window=50, max_samples=max_samp)
    
    # Build Val Sequences
    # Note: validation shouldn't strictly be limited by max_samp same as train if we want full validation, 
    # but for debug speed we limit it too.
    print("Building Val Sequences...")
    X_val, y_val = build_sequence_dataset(df_val, feature_cols, window=50, max_samples=max_samp)
    
    print(f"Sequences built.")
    print(f"Train: {X_train.shape}, Val: {X_val.shape}")
    sys.stdout.flush()
        
    return X_train, y_train, X_val, y_val, len(feature_cols)

def train_transformer():
    print("Using device:", DEVICE)
    print(f"--- Starting Track B: Transformer Training on {DEVICE} ---")
    if DEBUG_FAST:
        print("!!! DEBUG FAST MODE ENABLED !!!")
    
    # 1. Data
    X_train_np, y_train_np, X_val_np, y_val_np, input_dim = load_seq_data()
    
    # Tensor
    train_ds = TensorDataset(torch.tensor(X_train_np, dtype=torch.float32), torch.tensor(y_train_np, dtype=torch.float32))
    val_ds = TensorDataset(torch.tensor(X_val_np, dtype=torch.float32), torch.tensor(y_val_np, dtype=torch.float32))
    
    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0, pin_memory=True)
    val_dl = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0, pin_memory=True)
    
    # 2. Model
    model = RULTransformer(input_dim=input_dim, d_model=64, nhead=4, num_layers=2, dropout=0.1).to(DEVICE)

    # Resume if checkpoint exists
    ckpt_path = "pipeline/models/checkpoints/transformer.pt"
    if os.path.exists(ckpt_path):
        print(f"Resuming training from {ckpt_path}...")
        try:
            model.load_state_dict(torch.load(ckpt_path, map_location=DEVICE))
        except Exception as e:
            print(f"Could not load checkpoint: {e}")
            print("Starting from scratch...")
    
    optimizer = optim.AdamW(model.parameters(), lr=LR)
    # Using Huber Loss as it's robust to outliers which might happen in RUL
    criterion = nn.HuberLoss()
    
    best_rmse = float('inf')
    best_epoch = -1
    best_model_wts = copy.deepcopy(model.state_dict())
    patience_counter = 0
    
    # 3. Train Loop
    print("\nStarting Training Loop...")
    for epoch in range(EPOCHS):
        start_time = time.time()
        model.train()
        total_loss = 0
        
        for batch_idx, (X_batch, y_batch) in enumerate(train_dl):
            X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)
            
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item() * X_batch.size(0)
            
        avg_train_loss = total_loss / len(train_ds)
        
        # Validation
        model.eval()
        val_preds = []
        val_targets = []
        with torch.no_grad():
            for X_batch, y_batch in val_dl:
                X_batch = X_batch.to(DEVICE)
                outputs = model(X_batch)
                val_preds.extend(outputs.cpu().numpy())
                val_targets.extend(y_batch.numpy())
                
        rmse, mae = compute_metrics(np.array(val_targets), np.array(val_preds))
        
        epoch_time = time.time() - start_time
        
        print(f"[Time: {epoch_time:.2f}s] Epoch {epoch+1}/{EPOCHS} | Train Loss: {avg_train_loss:.4f} | Val RMSE: {rmse:.4f}")
        sys.stdout.flush()
            
        # Checkpointing & Early Stopping
        if rmse < best_rmse:
            best_rmse = rmse
            best_epoch = epoch + 1
            best_model_wts = copy.deepcopy(model.state_dict())
            patience_counter = 0 # Reset
            # Save immediately
            save_path = "pipeline/models/checkpoints/transformer.pt"
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save(best_model_wts, save_path)
        else:
            patience_counter += 1
            
        if patience_counter >= PATIENCE:
            print(f"\nEarly stopping triggered after {patience_counter} epochs without improvement.")
            break
            
    print(f"\n--- Training Finished ---")
    print(f"Best RMSE: {best_rmse:.4f} at Epoch {best_epoch}")
    print(f"Best model saved to pipeline/models/checkpoints/transformer.pt")
    
    # Load best weights into model just to be sure state is final
    model.load_state_dict(best_model_wts)

if __name__ == "__main__":
    train_transformer()
