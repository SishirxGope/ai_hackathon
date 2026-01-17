import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error, mean_absolute_error
import os

def compute_metrics(y_true, y_pred):
    """
    Computes RMSE and MAE.
    
    Args:
        y_true: scalar or array-like
        y_pred: scalar or array-like
        
    Returns:
        rmse, mae
    """
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    return rmse, mae

def plot_actual_vs_pred(y_true, y_pred, title="Actual vs Predicted", save_path=None):
    """
    Plots Actual RUL vs Predicted RUL.
    """
    plt.figure(figsize=(10, 6))
    plt.scatter(y_true, y_pred, alpha=0.5, label='Predictions')
    
    # Perfect fit line
    min_val = min(y_true.min(), y_pred.min())
    max_val = max(y_true.max(), y_pred.max())
    plt.plot([min_val, max_val], [min_val, max_val], 'r--', label='Perfect Fit')
    
    plt.xlabel("Actual RUL")
    plt.ylabel("Predicted RUL")
    plt.title(title)
    plt.legend()
    plt.grid(True)
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
        print(f"Plot saved to {save_path}")
    plt.close()

def plot_residuals(y_true, y_pred, save_path=None):
    """
    Plots histogram of residuals (Predicted - Actual).
    """
    residuals = y_pred - y_true
    plt.figure(figsize=(10, 6))
    plt.hist(residuals, bins=30, edgecolor='k', alpha=0.7)
    plt.axvline(0, color='r', linestyle='--')
    plt.xlabel("Residual (Predicted - Actual)")
    plt.ylabel("Frequency")
    plt.title("Residual Distribution")
    plt.grid(True)
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
        print(f"Residual plot saved to {save_path}")
    plt.close()
def infer_max_rul_from_training(df):
    """
    Infers the maximum RUL value from the training dataframe.
    
    Args:
        df: pandas DataFrame with a 'RUL' column
        
    Returns:
        float: Maximum RUL value
    """
    return df["RUL"].max()

def compute_health_percentage(rul, max_rul):
    """
    Computes health percentage from RUL.
    
    Health percentage = 100 * rul / max_rul, clamped to [0, 100].
    
    Args:
        rul: float or numpy array of RUL values
        max_rul: float, the maximum RUL value
        
    Returns:
        float or numpy array (same shape as input): Health percentage in range [0, 100]
    """
    health_percent = 100.0 * rul / max_rul
    # Clamp to [0, 100]
    return np.clip(health_percent, 0, 100)

def plot_health_curve(df_engine, save_path=None):
    """
    Plots health percentage curve over cycles for a single engine.
    
    Args:
        df_engine: DataFrame for a single engine with columns:
                   - 'cycle': cycle number
                   - 'health_percent': health percentage (0-100)
                   - (optional) 'predicted_rul': predicted RUL if available
        save_path: Path to save the PNG file (optional)
        
    Returns:
        None (displays/saves plot)
    """
    plt.figure(figsize=(12, 6))
    
    # Sort by cycle to ensure proper line plotting
    df_sorted = df_engine.sort_values('cycle')
    
    # Plot health percentage curve
    plt.plot(df_sorted['cycle'], df_sorted['health_percent'], 
             linewidth=2, label='Health Percentage', color='#2E86AB', marker='o', markersize=4)
    
    # If predicted RUL is available, plot it on secondary axis
    if 'predicted_rul' in df_sorted.columns:
        ax1 = plt.gca()
        ax2 = ax1.twinx()
        
        ax2.plot(df_sorted['cycle'], df_sorted['predicted_rul'], 
                linewidth=2, label='Predicted RUL', color='#A23B72', marker='s', markersize=4, linestyle='--')
        
        ax2.set_ylabel('Predicted RUL', fontsize=12, color='#A23B72')
        ax2.tick_params(axis='y', labelcolor='#A23B72')
        ax2.legend(loc='upper right')
    
    plt.xlabel('Cycle', fontsize=12)
    plt.ylabel('Health Percentage (%)', fontsize=12, color='#2E86AB')
    plt.title(f'Engine Health Curve', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.tick_params(axis='y', labelcolor='#2E86AB')
    plt.legend(loc='upper left')
    
    if save_path:
        os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
        plt.savefig(save_path, dpi=100, bbox_inches='tight')
        print(f"Health curve plot saved to {save_path}")
    
    plt.close()

def plot_rul_curve(df_engine, save_path=None, actual_col='RUL', pred_col='predicted_rul'):
    """
    Plots RUL curve (actual and/or predicted) over cycles for a single engine.
    
    Args:
        df_engine: DataFrame for a single engine with columns:
                   - 'cycle': cycle number
                   - actual_col: column name for actual RUL (default 'RUL')
                   - pred_col: column name for predicted RUL (optional, default 'predicted_rul')
        save_path: Path to save the PNG file (optional)
        actual_col: Name of actual RUL column (default 'RUL')
        pred_col: Name of predicted RUL column (default 'predicted_rul')
        
    Returns:
        None (displays/saves plot)
    """
    plt.figure(figsize=(12, 6))
    
    # Sort by cycle to ensure proper line plotting
    df_sorted = df_engine.sort_values('cycle')
    
    # Plot actual RUL if available
    if actual_col in df_sorted.columns:
        plt.plot(df_sorted['cycle'], df_sorted[actual_col], 
                linewidth=2.5, label='Actual RUL', color='#06A77D', marker='o', markersize=5)
    
    # Plot predicted RUL if available
    if pred_col in df_sorted.columns:
        plt.plot(df_sorted['cycle'], df_sorted[pred_col], 
                linewidth=2, label='Predicted RUL', color='#D62246', marker='s', markersize=4, linestyle='--')
    
    plt.xlabel('Cycle', fontsize=12)
    plt.ylabel('Remaining Useful Life (Cycles)', fontsize=12)
    plt.title(f'Engine RUL Curve', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend(loc='best', fontsize=11)
    
    if save_path:
        os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
        plt.savefig(save_path, dpi=100, bbox_inches='tight')
        print(f"RUL curve plot saved to {save_path}")
    
    plt.close()