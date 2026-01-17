import sys
import os
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time

# Adjust path to ensure we can import pipeline
sys.path.append(os.getcwd())

# Imports
from pipeline.models.xgb_baseline import load_full_data, XGBoostBaseline
from pipeline.dataset_builder import build_tabular_dataset, build_sequence_dataset
from pipeline.models.transformer_model import RULTransformer
from pipeline.models.uncertainty import predict_uncertainty
from pipeline.models.train_transformer import DEVICE

def verify_system():
    print("Beginning System Verification...")
    results = {
        "Pipeline": "FAIL",
        "Dataset": "FAIL",
        "XGBoost": "FAIL",
        "Transformer": "FAIL",
        "Uncertainty": "FAIL",
        "Attention": "FAIL"
    }

    # Shared variables
    df = None
    features = None
    X_seq = None
    y_seq = None
    input_dim = 0
    
    # ---------------------------------------------------------
    # STEP 1 — Pipeline Sanity Check
    # ---------------------------------------------------------
    print("\nSTEP 1 — Pipeline Sanity Check")
    try:
        df, features = load_full_data()
        
        has_nans = df.isnull().sum().sum() > 0
        has_health = 'health_index' in df.columns
        has_rul = 'RUL' in df.columns
        feat_count = len(features)
        
        if not has_nans and has_health and has_rul and feat_count > 100:
            print("[PASS] Pipeline output sanity check")
            results["Pipeline"] = "PASS"
        else:
            print("[FAIL] Pipeline output sanity check")
            if has_nans: print(f"  - DataFrame contains NaNs")
            if not has_health: print("  - Missing 'health_index'")
            if not has_rul: print("  - Missing 'RUL'")
            if feat_count <= 100: print(f"  - Low feature count: {feat_count}")
    except Exception as e:
        print(f"[FAIL] Pipeline output sanity check. Error: {e}")

    # ---------------------------------------------------------
    # STEP 2 — Dataset Builder Check
    # ---------------------------------------------------------
    print("\nSTEP 2 — Dataset Builder Check")
    if results["Pipeline"] == "PASS":
        try:
            # Tabular
            # exclude health_index_raw if present in features for tabular X
            features_tab = [f for f in features if f != 'health_index_raw']
            
            X_tab, y_tab = build_tabular_dataset(df, features_tab)
            # Sequence
            X_seq, y_seq = build_sequence_dataset(df, features, window=30, max_samples=500)
            
            print(f"  X_tabular: {X_tab.shape}")
            print(f"  X_seq: {X_seq.shape}")
            
            if len(X_seq) > 0:
                input_dim = X_seq.shape[2]
            
            if len(X_tab) > 0 and len(X_seq) > 0 and X_seq.shape[1] == 30 and not np.isnan(X_seq).any():
                print("[PASS] Dataset builder check")
                results["Dataset"] = "PASS"
            else:
                print("[FAIL] Dataset builder check (Empty or NaNs or Wrong Shape)")
        except Exception as e:
            print(f"[FAIL] Dataset builder check. Error: {e}")
    else:
        print("[SKIP] Skipping Dataset check due to Pipeline fail")

    # ---------------------------------------------------------
    # STEP 3 — XGBoost Model Check (Track A)
    # ---------------------------------------------------------
    print("\nSTEP 3 — XGBoost Model Check (Track A)")
    try:
        from pipeline.models.xgb_baseline import load_xgb_model
        model = load_xgb_model()
        
        # Use X_tab for prediction test
        if len(X_tab) > 0:
            # Get expected feature names from model
            try:
                expected_features = model.get_booster().feature_names
            except:
                expected_features = model.feature_names_in_
            
            print(f"  Expected features: {len(expected_features)} features")
            
            # Prepare X_df: drop extra columns and reorder to match expected features
            X_df = X_tab.copy()
            
            # Before checking missing features, try to pull health_index or health_index_raw from df
            health_features = ['health_index', 'health_index_raw']
            for health_feat in health_features:
                if health_feat in expected_features and health_feat not in X_df.columns:
                    if health_feat in df.columns:
                        # Pull from df and align with X_df indices
                        X_df[health_feat] = df.loc[X_df.index, health_feat]
                        print(f"  Added '{health_feat}' from full dataframe")
            
            # Check if all expected features are present
            missing_features = set(expected_features) - set(X_df.columns)
            if missing_features:
                raise ValueError(f"Missing expected features: {missing_features}")
            
            # Strictly reorder X_df to match expected_features order (drop extra columns)
            expected_features_list = list(expected_features)
            X_df = X_df[expected_features_list]
            
            # Run prediction on first 5 samples
            samples = X_df.iloc[:5]
            preds = model.predict(samples)
            print(f"Sample XGBoost predictions: {preds}")
            
            # Check: Values are finite
            all_finite = np.all(np.isfinite(preds))
            # Check: Not all values are identical
            not_all_identical = len(np.unique(preds)) > 1
            
            if all_finite and not_all_identical:
                print("[PASS] XGBoost inference check")
                results["XGBoost"] = "PASS"
            else:
                if not all_finite:
                    print("[FAIL] XGBoost predictions contain NaN or Inf")
                if not not_all_identical:
                    print("[FAIL] XGBoost predictions are all identical")
        else:
            print("[FAIL] Cannot test XGBoost inference (Dataset empty)")
    except Exception as e:
        print(f"[FAIL] XGBoost check error: {e}")

    # ---------------------------------------------------------
    # STEP 4 — Transformer Forward Pass Check (Track B)
    # ---------------------------------------------------------
    print("\nSTEP 4 — Transformer Forward Pass Check (Track B)")
    trans_path = "pipeline/models/checkpoints/transformer.pt"
    model = None
    
    if os.path.exists(trans_path):
        try:
            # Recreate model structure
            # Must match training params: d_model=48, nhead=4, num_layers=1, dropout=0.1
            if input_dim == 0:
                print("[FAIL] Input dim is 0, cannot load model. Dataset build failing?")
            else:
                model = RULTransformer(input_dim=input_dim, d_model=48, nhead=4, num_layers=1, dropout=0.1).to(DEVICE)
                model.load_state_dict(torch.load(trans_path))
                model.eval()
                
                if X_seq is not None and len(X_seq) > 0:
                    # Take 1 sequence
                    sample_seq = torch.tensor(X_seq[0:1], dtype=torch.float32).to(DEVICE)
                    true_rul = y_seq[0]
                    
                    with torch.no_grad():
                        pred = model(sample_seq)
                    
                    pred_val = pred.item()
                    print(f"  Transformer single prediction: {pred_val:.2f}")
                    print(f"  Ground truth: {true_rul:.2f}")
                    
                    if np.isfinite(pred_val):
                        print("[PASS] Transformer forward pass check")
                        results["Transformer"] = "PASS"
                    else:
                        print("[FAIL] Transformer predicted NaN/Inf")
                else:
                     print("[FAIL] Cannot test Transformer (Dataset empty)")
        except Exception as e:
            print(f"[FAIL] Transformer check error: {e}")
    else:
        print(f"[FAIL] Transformer model not found at {trans_path}")

    # ---------------------------------------------------------
    # STEP 5 — MC Dropout Uncertainty Check
    # ---------------------------------------------------------
    print("\nSTEP 5 — MC Dropout Uncertainty Check")
    if results["Transformer"] == "PASS" and model is not None:
        try:
            sample_seq = torch.tensor(X_seq[0:1], dtype=torch.float32).to(DEVICE)
            # predict_uncertainty(model, X_seq, n_samples=50)
            mean_preds, std_preds, all_preds = predict_uncertainty(model, sample_seq, n_samples=30)
            
            mean_val = mean_preds[0]
            std_val = std_preds[0]
            
            print(f"  Transformer MC prediction: mean = {mean_val:.2f}, std = {std_val:.4f}")
            
            if std_val > 0:
                print("[PASS] MC Dropout uncertainty check")
                results["Uncertainty"] = "PASS"
            else:
                print("[FAIL] MC Dropout not working (std=0). Is dropout enabled?")
        except Exception as e:
            print(f"[FAIL] MC Dropout check error: {e}")
    else:
        print("[SKIP] Skipping Uncertainty check (Transformer failed or not loaded)")

    # ---------------------------------------------------------
    # STEP 6 — Attention Map Check
    # ---------------------------------------------------------
    print("\nSTEP 6 — Attention Map Check")
    if results["Transformer"] == "PASS" and model is not None:
        try:
            output_dir = "outputs/attention"
            os.makedirs(output_dir, exist_ok=True)
            debug_plot_path = os.path.join(output_dir, "debug.png")
            
            sample_seq = torch.tensor(X_seq[0:1], dtype=torch.float32).to(DEVICE)
            
            with torch.no_grad():
                 pred, attn_weights = model(sample_seq, return_attention=True)
            
            # attn_weights: (Batch, Heads, Seq, Seq)
            attn_avg = attn_weights[0].mean(dim=0).cpu().numpy()
            
            plt.figure()
            plt.imshow(attn_avg, aspect='auto')
            plt.title("Debug Attention Map")
            plt.savefig(debug_plot_path)
            plt.close()
            
            if os.path.exists(debug_plot_path) and os.path.getsize(debug_plot_path) > 0:
                print("[PASS] Attention map generation check")
                results["Attention"] = "PASS"
            else:
                print("[FAIL] Attention map file not created or empty")
                
        except Exception as e:
            print(f"[FAIL] Attention check error: {e}")
    else:
        print("[SKIP] Skipping Attention check (Transformer failed)")

    # ---------------------------------------------------------
    # STEP 7 — Final Summary
    # ---------------------------------------------------------
    print("\n===============================")
    print("SYSTEM VERIFICATION SUMMARY")
    all_passed = True
    for key, val in results.items():
        print(f"{key}: {val}")
        if val != "PASS":
            all_passed = False
    print("===============================")
    
    if all_passed:
        print("[OK] SYSTEM IS DEMO-READY")
    else:
        print("[WARNING] SYSTEM HAS FAILURES -- SEE LOGS")

if __name__ == "__main__":
    verify_system()
