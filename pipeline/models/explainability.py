import shap
import matplotlib.pyplot as plt
import os
import pandas as pd
import numpy as np
from pipeline.models.xgb_baseline import XGBoostBaseline

OUTPUT_DIR = "output/explainability"

def explain_track_a(model_path, X):
    """
    Generates SHAP explanations for the XGBoost model.
    """
    print(f"\n--- Generating SHAP Explanations ---")
    
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    # Load model
    xgb_wrapper = XGBoostBaseline.load(model_path)
    model = xgb_wrapper.model
    
    # SHAP Explainer
    # Use a subsample of X for speed if X is very large, but for CMAPSS it's okay-ish.
    # If X > 5000 rows, maybe sample 1000 for background.
    # TreeExplainer is fast.
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. Global Summary Plot
    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X, show=False)
    plt.tight_layout()
    summary_path = os.path.join(OUTPUT_DIR, "shap_summary.png")
    plt.savefig(summary_path)
    print(f"Saved SHAP summary plot to {summary_path}")
    plt.close()
    
    # 2. Top 10 Features
    # Mean absolute SHAP value per feature
    vals = np.abs(shap_values).mean(0)
    feature_importance = pd.DataFrame(list(zip(X.columns, vals)), columns=['col_name','feature_importance_vals'])
    feature_importance.sort_values(by=['feature_importance_vals'], ascending=False, inplace=True)
    print("\nTop 10 Important Features:")
    print(feature_importance.head(10))
    
    # 3. Single Engine Explanation (First sample in X)
    # Just force plot for the first instance
    plt.figure(figsize=(20, 3))
    shap.force_plot(explainer.expected_value, shap_values[0,:], X.iloc[0,:], matplotlib=True, show=False)
    force_path = os.path.join(OUTPUT_DIR, "shap_force_single.png")
    plt.savefig(force_path)
    print(f"Saved SHAP force plot to {force_path}")
    plt.close()

if __name__ == "__main__":
    from pipeline.models.xgb_baseline import load_full_data
    df, features = load_full_data()
    X = df[features]
    model_path = "pipeline/models/checkpoints/xgb_model.pkl"
    explain_track_a(model_path, X)
