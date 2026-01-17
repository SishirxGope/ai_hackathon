import torch
import numpy as np
import matplotlib.pyplot as plt
import os
from pipeline.models.transformer_model import RULTransformer
from pipeline.models.train_transformer import load_seq_data, DEVICE

OUTPUT_DIR = "output/uncertainty"

def predict_uncertainty(model, X_seq, n_samples=50):
    """
    Runs MC Dropout inference.
    
    Args:
        model: PyTorch model
        X_seq: Input tensor (Batch, SeqLen, Feat)
        n_samples: Number of forward passes
        
    Returns:
        mean_preds, std_preds, all_preds
    """
    # Force model to train mode to keep dropout active
    model.train() 
    
    predictions = []
    
    with torch.no_grad():
        for _ in range(n_samples):
             # Move to device if not already (assuming X_seq is tensor on device or handled)
            out = model(X_seq)
            predictions.append(out.cpu().numpy())
            
    predictions = np.array(predictions) # Shape: (n_samples, batch_size)
    
    mean_preds = predictions.mean(axis=0)
    std_preds = predictions.std(axis=0)
    
    return mean_preds, std_preds, predictions

def run_uncertainty_analysis():
    print(f"--- Starting Track B: Uncertainty Analysis ---")
    
    # 1. Load Data
    # We want a few samples to test. 
    # load_seq_data() returns (X_train, y_train, X_val, y_val, input_dim). 
    X_train_np, y_train_np, X_val_np, y_val_np, input_dim = load_seq_data()
    
    # Use Validation set for this analysis to be fair
    target_X = X_val_np
    target_y = y_val_np
    
    print(f"Using Validation set for Uncertainty Analysis. Size: {target_X.shape}")
    
    # Pick 5 random sample indices or specific ones
    if len(target_X) > 5:
        # Fixed seed for reproducibility of example
        np.random.seed(42)
        indices = np.random.choice(len(target_X), 5, replace=False)
    else:
        indices = np.arange(len(target_X))
        
    X_sample = torch.tensor(target_X[indices], dtype=torch.float32).to(DEVICE)
    y_sample = target_y[indices]
    
    # 2. Load Model
    model_path = "pipeline/models/checkpoints/transformer.pt"
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    # Initialize model with same params as training
    model = RULTransformer(input_dim=input_dim, d_model=48, nhead=4, num_layers=1, dropout=0.1).to(DEVICE)
    model.load_state_dict(torch.load(model_path))
    
    # 3. Predict with Uncertainty
    print(f"\nRunning MC Dropout with 50 samples...")
    mean_rul, std_rul, all_preds = predict_uncertainty(model, X_sample, n_samples=50)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("\n--- Uncertainty Results (MC Dropout) ---")
    for i, idx in enumerate(indices):
        true_val = y_sample[i]
        pred_val = mean_rul[i]
        std_val = std_rul[i]
        
        # 95% Confidence Interval is approx mean +/- 1.96 * std
        ci_radius = 1.96 * std_val
        
        # Format: Predicted RUL = 52 ± 7 (95% CI)
        print(f"Sample {idx}: Predicted RUL = {pred_val:.0f} ± {ci_radius:.0f} (95% CI)")
        # Also showing True RUL for reference
        # print(f"  (True RUL: {true_val:.0f})")
        
        # Plot distribution for this sample
        plt.figure(figsize=(8, 4))
        plt.hist(all_preds[:, i], bins=15, alpha=0.7, color='skyblue', edgecolor='black')
        plt.axvline(true_val, color='green', linestyle='--', linewidth=2, label=f'True RUL: {true_val:.0f}')
        plt.axvline(pred_val, color='red', linestyle='-', linewidth=2, label=f'Mean Pred: {pred_val:.0f}')
        plt.title(f"Uncertainty Distribution (Sample {idx})\nPredicted RUL = {pred_val:.0f} ± {ci_radius:.0f} (95% CI)")
        plt.xlabel("RUL Prediction")
        plt.ylabel("Frequency")
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        save_path = os.path.join(OUTPUT_DIR, f"dist_sample_{idx}.png")
        plt.savefig(save_path)
        plt.close()
        
    print(f"\nSaved uncertainty plots to {OUTPUT_DIR}")

if __name__ == "__main__":
    # Test quickly if imports work
    run_uncertainty_analysis()
