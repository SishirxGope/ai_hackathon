import sys
import os
import torch
import numpy as np
import pandas as pd
import logging
import math

# Ensure pipeline can be imported
sys.path.append(os.getcwd())

from pipeline.models.xgb_baseline import load_xgb_model, load_full_data
from pipeline.dataset_builder import build_sequence_dataset
from pipeline.models.transformer_model import RULTransformer
from pipeline.models.uncertainty import predict_uncertainty as compute_mc_uncertainty
from pipeline.models.train_transformer import DEVICE

# Configuration
TRANSFORMER_RMSE = 11.6
COMBINED_RMSE = 9.5
MODEL_RMSE = 11.6
MODEL_MAE = 6.3
TRANSFORMER_PATH = "pipeline/models/checkpoints/transformer.pt"
WINDOW_SIZE = 50
XGB_RMSE = 7.7

# Global State (Singleton pattern via module-level variables)
_XGB_MODEL = None
_TRANS_MODEL = None
_FULL_DF = None
_FEATURES = None
_ENGINE_IDS = []

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _initialize_system():
    global _XGB_MODEL, _TRANS_MODEL, _FULL_DF, _FEATURES, _ENGINE_IDS
    
    if _FULL_DF is not None:
        return # Already initialized

    logger.info("Initializing Inference Logic...")

    # 1. Load Data (Once)
    logger.info("Loading full dataset via pipeline...")
    _FULL_DF, _FEATURES = load_full_data()
    
    # Store unique Engine IDs (sorted)
    # _FULL_DF has 'engine_id' (int), 'cycle' (int), 'RUL', 'health_index', etc.
    _ENGINE_IDS = sorted(_FULL_DF['engine_id'].unique().tolist())
    logger.info(f"Loaded data for {len(_ENGINE_IDS)} engines.")

    # 2. Load XGBoost (Once)
    logger.info("Loading XGBoost Model...")
    try:
        _XGB_MODEL = load_xgb_model()
    except Exception as e:
        logger.error(f"Failed to load XGBoost: {e}")

    # 3. Load Transformer (Once)
    logger.info("Loading Transformer Model...")
    if os.path.exists(TRANSFORMER_PATH):
        try:
            # Determine input_dim from dataset features
            # The pipeline uses features from load_full_data. 
            # In verify_system we see input_dim is derived from X_seq shape.
            # Here we assume X_seq features == _FEATURES
            input_dim = len(_FEATURES) 
            
            _TRANS_MODEL = RULTransformer(
                input_dim=input_dim, 
                d_model=64, 
                nhead=4, 
                num_layers=2, 
                dropout=0.1
            ).to(DEVICE)
            
            _TRANS_MODEL.load_state_dict(torch.load(TRANSFORMER_PATH, map_location=DEVICE))
            _TRANS_MODEL.eval()
            logger.info("Transformer Loaded Successfully.")
        except Exception as e:
            logger.error(f"Failed to load Transformer: {e}")
    else:
        logger.warning(f"Transformer checkpoint not found at {TRANSFORMER_PATH}")

# Initialize immediately on import
_initialize_system()

# --- Public API ---

def get_engine_ids():
    """Returns a list of available engine IDs (as strings "engine-X")."""
    return [f"engine-{eid}" for eid in _ENGINE_IDS]

def _parse_engine_id(engine_id_str):
    """Parses 'engine-1' to 1."""
    try:
        if isinstance(engine_id_str, int):
            return engine_id_str
        return int(engine_id_str.split('-')[-1])
    except:
        return None

def _get_engine_data(eid):
    """Returns the dataframe slice for valid engine logic."""
    if _FULL_DF is None:
        raise RuntimeError("System not initialized")
    return _FULL_DF[_FULL_DF['engine_id'] == eid]

def predict_rul(engine_id):
    """
    Returns RUL predictions for the specific engine.
    Output: { "rul_xgb": float, "rul_transformer": float, "rul_combined": float }
    """
    eid = _parse_engine_id(engine_id)
    if eid not in _ENGINE_IDS:
        return None

    eng_df = _get_engine_data(eid)
    if eng_df.empty:
        return None
        
    # XGBoost Inference (Last State)
    rul_xgb = 0.0
    if _XGB_MODEL:
        try:
            # Get expected features
            booster = _XGB_MODEL.get_booster()
            expected_feats = booster.feature_names
            
            # Prepare single row input (Mid-life sampling)
            idx = len(eng_df) // 2
            logger.info(f"Using cycle index {idx} / {len(eng_df)} for inference (mid-life sampling)")
            last_row = eng_df.iloc[[idx]].copy()
            
            # Ensure features exist
            # Note: verify_system logic handles 'health_index' mismatch if needed.
            # We assume load_full_data provides necessary columns (including health_index).
            
            # Filter to expected features
            valid_feats = [f for f in expected_feats if f in last_row.columns]
            
            # Add missing if any (e.g. from global features if loaded differently)
            # Just predict on valid intersection for now to be safe
            if valid_feats:
                xgb_input = last_row[valid_feats]
                preds = _XGB_MODEL.predict(xgb_input)
                rul_xgb = float(preds[0])
        except Exception as e:
            logger.error(f"XGB inference error: {e}")

    # Transformer Inference (Sequence)
    rul_trans = 0.0
    if _TRANS_MODEL:
        try:
            # Build sequence for THIS engine only
            # We need at least 'window' rows.
            # dataset_builder.build_sequence_dataset iterates. 
            # We can pass this single-engine DF.
            # Using _FEATURES as the feature set.
            
            # Check length
            if len(eng_df) >= WINDOW_SIZE:
                X_seq, _ = build_sequence_dataset(eng_df, _FEATURES, window=WINDOW_SIZE)
                
                if len(X_seq) > 0:
                    # Take mid-life sequence
                    idx = len(X_seq) // 2
                    logger.info(f"Using sequence index {idx} / {len(X_seq)} for inference (mid-life sampling)")
                    last_seq = X_seq[idx]
                    
                    # Tensorize
                    seq_tensor = torch.tensor(last_seq, dtype=torch.float32).unsqueeze(0).to(DEVICE)
                    
                    with torch.no_grad():
                        pred = _TRANS_MODEL(seq_tensor)
                        rul_trans = pred.item()
        except Exception as e:
            logger.error(f"Transformer inference error: {e}")

    # Fallback / Combination logic
    final_rul = rul_xgb
    if rul_trans != 0:
         if rul_xgb != 0:
             final_rul = (rul_xgb + rul_trans) / 2
         else:
             final_rul = rul_trans
             
    return {
        "rul_xgb": round(rul_xgb, 2),
        "rul_transformer": round(rul_trans, 2),
        "rul_combined": round(final_rul, 2),
        "rmse": MODEL_RMSE
    }

def predict_uncertainty(engine_id):
    """
    Returns uncertainty metrics using MC Dropout.
    Output: { "uncertainty": float (std_dev), "confidence": float (0-100) }
    """
    eid = _parse_engine_id(engine_id)
    if eid not in _ENGINE_IDS or _TRANS_MODEL is None:
        return {"uncertainty": 0.0, "confidence": 0.0}

    eng_df = _get_engine_data(eid)
    if len(eng_df) < WINDOW_SIZE:
        return {"uncertainty": 0.0, "confidence": 0.0}

    try:
        # Get last sequence
        X_seq, _ = build_sequence_dataset(eng_df, _FEATURES, window=WINDOW_SIZE)
        if len(X_seq) == 0:
             return {"uncertainty": 0.0, "confidence": 0.0}
             
        idx = len(X_seq) // 2
        last_seq = X_seq[idx]
        seq_tensor = torch.tensor(last_seq, dtype=torch.float32).unsqueeze(0).to(DEVICE)
        
        # Run MC Dropout
        mean_preds, std_preds, _ = compute_mc_uncertainty(_TRANS_MODEL, seq_tensor, n_samples=30)
        
        std_val = float(std_preds[0])
        
        
        # Expected max uncertainty observed in this system (tuneable)
        MAX_STD = 12.0

        # Normalize to 0..1
        norm = min(std_val / MAX_STD, 1.0)

        # Invert: low std => high confidence
        confidence = (1.0 - norm) * 100.0

        confidence = max(0.0, min(100.0, confidence))

        logger.info(f"MC STD={std_val:.3f}, NORM={norm:.3f}, CONF={confidence:.2f}%")
        
        return {
            "uncertainty": round(std_val, 2),
            "confidence": round(confidence, 1)
        }
            
    except Exception as e:
        logger.error(f"Uncertainty error: {e}")
        return {"uncertainty": 0.0, "confidence": 0.0}

def predict_health(engine_id):
    """
    Returns health index 0-1 (or scaled).
    Output: float
    """
    eid = _parse_engine_id(engine_id)
    if eid not in _ENGINE_IDS:
        return 0.0
        
    eng_df = _get_engine_data(eid)
    if eng_df.empty:
        return 0.0
        
    # Assuming 'health_index' is in the DF (verified in load_full_data)
    if 'health_index' in eng_df.columns:
        return float(eng_df.iloc[-1]['health_index'])
    return 0.0

def get_system_status():
    """Returns internal system state for debugging."""
    return {
        "num_engines": len(_ENGINE_IDS),
        "input_dim": len(_FEATURES) if _FEATURES else 0,
        "transformer_loaded": _TRANS_MODEL is not None,
        "xgboost_loaded": _XGB_MODEL is not None
    }

def get_model_metrics():
    return {
        "rmse": MODEL_RMSE,
        "mae": MODEL_MAE
    }
