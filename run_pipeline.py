from pipeline.data_loader import load_and_label
from pipeline.sensor_cleaner import remove_constant_sensors
from pipeline.normalizer import normalize_dataframe
from pipeline.feature_engineering import add_degradation_features
from pipeline.health_index import add_health_index
from pipeline.dataset_builder import build_tabular_dataset, build_sequence_dataset
from pipeline.config import DATA_PATH, TRAIN_FILE
from pipeline.models.xgb_baseline import train_xgb_baseline_model
from pipeline.models.evaluation import evaluate_track_a
from pipeline.models.explainability import explain_track_a
import os
import traceback

def main():
    print("Running predictive maintenance pipeline...")
    
    file_path = os.path.join(DATA_PATH, TRAIN_FILE)
    
    print(f"Loading data from {file_path}...")
    try:
        # 1. Load Data
        df = load_and_label(file_path)
        print(f"Data loaded successfully. Shape: {df.shape}")
        
        # 2. Clean Sensors
        print("\nCleaning sensors...")
        df_clean, kept_sensors = remove_constant_sensors(df)
        print(f"Shape after cleaning: {df_clean.shape}")
        print(f"Kept sensors: {kept_sensors}")
        
        # 3. Normalize Data
        print("\nNormalizing data...")
        # Define features to normalize: settings (op1, op2, op3) + kept sensors
        setting_cols = ['op1', 'op2', 'op3']
        features_to_normalize = setting_cols + kept_sensors
        
        df_norm, scaler = normalize_dataframe(df_clean, features_to_normalize)
        print(f"Shape after normalization: {df_norm.shape}")
        
        # 4. Feature Engineering
        print("\nGenerating features...")
        df_feat = add_degradation_features(df_norm, kept_sensors)
        print(f"Shape after feature engineering: {df_feat.shape}")
        print(f"Total number of columns: {df_feat.shape[1]}")
        
        # 5. Health Index
        print("\nCalculating Health Index...")
        exclude_cols = ['engine_id', 'cycle', 'RUL']
        feature_cols = [c for c in df_feat.columns if c not in exclude_cols]
        print(f"Using {len(feature_cols)} features for HI calculation.")
        
        df_final, pca = add_health_index(df_feat, feature_cols)
        
        print(f"Health Index Min: {df_final['health_index'].min()}")
        print(f"Health Index Max: {df_final['health_index'].max()}")
        
        print("\nFinal DataFrame Head:")
        print(df_final.head())
        
        # Stats for Engine 1
        print("\n--- Engine 1 Health Index Stats ---")
        engine1 = df_final[df_final['engine_id'] == 1]
        
        print("Head (First 5):")
        print(engine1[['cycle', 'health_index']].head())
        
        print("\nTail (Last 5):")
        print(engine1[['cycle', 'health_index']].tail())
        
        mean_first_10 = engine1['health_index'].iloc[:10].mean()
        mean_last_10 = engine1['health_index'].iloc[-10:].mean()
        
        print(f"\nMean HI (First 10 cycles): {mean_first_10:.4f}")
        print(f"Mean HI (Last 10 cycles): {mean_last_10:.4f}")

        # Save to Excel
        print("\nSaving full dataset to Excel...")
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "full_dataset.xlsx")
        df_final.to_excel(output_path, index=False)
        print(f"Full dataset saved to {output_path}")

        # 6. Map Datasets
        print("\nBuilding datasets...")
        feature_cols_dataset = [c for c in df_final.columns if c not in exclude_cols]
        
        X_tab, y_tab = build_tabular_dataset(df_final, feature_cols_dataset)
        X_seq, y_seq = build_sequence_dataset(df_final, feature_cols_dataset, window=30)
        
        print(f"X_tabular shape: {X_tab.shape}")
        print(f"y_tabular shape: {y_tab.shape}")
        print(f"X_seq shape: {X_seq.shape}")
        print(f"X_seq shape: {X_seq.shape}")
        print(f"y_seq shape: {y_seq.shape}")

        # --- PHASE 2: TRACK A (XGBOOST) ---
        print("\n=== Running Phase 2: Track A (XGBoost Baseline) ===")
        model_path = "pipeline/models/checkpoints/xgb_model.pkl"
        
        # Train (if needed or forced, here we force or check)
        # For this hackathon step, we always train to ensure freshness
        final_model, X_full, y_full = train_xgb_baseline_model(df_final)
        
        # Evaluate
        # We evaluate on the full training set here just to show functionality. 
        # In a real scenario, we'd use a held-out test set.
        # But we already printed CV metrics in training.
        evaluate_track_a(model_path, X_full, y_full)
        
        # Explain
        explain_track_a(model_path, X_full)

    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
    except Exception:
        print("An error occurred:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
