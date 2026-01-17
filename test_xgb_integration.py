#!/usr/bin/env python
"""Test XGBoost integration"""

import sys
import os
sys.path.insert(0, os.getcwd())

print("=" * 60)
print("Testing XGBoost Integration")
print("=" * 60)

try:
    print("\n1. Testing load_xgb_model() import and function...")
    from pipeline.models.xgb_baseline import load_xgb_model, XGB_MODEL_PATH
    
    print(f"   XGB_MODEL_PATH: {XGB_MODEL_PATH}")
    print(f"   File exists: {os.path.exists(XGB_MODEL_PATH)}")
    
    print("\n2. Loading XGBoost model...")
    model = load_xgb_model()
    print(f"   Model loaded successfully: {type(model)}")
    
    print("\n3. Testing model prediction...")
    # Create dummy data for testing
    import numpy as np
    import pandas as pd
    
    # Get feature dimensions from actual data
    from pipeline.models.xgb_baseline import load_full_data
    df, features = load_full_data()
    
    X = df[features]
    
    # Take first 5 samples
    samples = X.iloc[:5]
    print(f"   Sample data shape: {samples.shape}")
    
    preds = model.predict(samples)
    print(f"   Sample XGBoost predictions: {preds}")
    
    print("\n4. Verification checks...")
    # Check: Values are finite
    all_finite = np.all(np.isfinite(preds))
    print(f"   All values are finite: {all_finite}")
    
    # Check: Not all values are identical
    unique_vals = len(np.unique(preds))
    not_all_identical = unique_vals > 1
    print(f"   Not all values identical (unique values: {unique_vals}): {not_all_identical}")
    
    if all_finite and not_all_identical:
        print("\n[PASS] XGBoost inference check")
    else:
        print("\n[FAIL] XGBoost inference check")
        
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
