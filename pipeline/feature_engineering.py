import pandas as pd
import numpy as np
from scipy import stats
import sys

def _slope_func(y):
    """Helper to compute slope for a rolling window."""
    x = np.arange(len(y))
    # Simple linear regression: slope = cov(x, y) / var(x)
    # Using np.polyfit is also an option but has overhead.
    # explicit formula is faster for small fixed windows than linregress
    mx = x.mean()
    my = y.mean()
    # slope = sum((x - mx) * (y - my)) / sum((x - mx)**2)
    # x is constant for a given window size, so sum((x - mx)**2) is constant.
    # But for simplicity/readability as requested, we can use a numpy polyfit or similar.
    # Given the prompt asks for "clean, readable", np.polyfit(x, y, 1)[0] is very readable.
    if len(y) < 2:
        return 0.0
    return np.polyfit(x, y, 1)[0]

def add_degradation_features(df: pd.DataFrame, sensor_cols: list, window_short: int = 5, window_long: int = 10) -> pd.DataFrame:
    """
    Adds rolling statistics, trends, and drift features to the DataFrame.

    Args:
        df: Input DataFrame.
        sensor_cols: List of sensor columns to calculate features for.
        window_short: Window size for short-term rolling stats.
        window_long: Window size for long-term rolling stats and trend.

    Returns:
        pd.DataFrame: DataFrame enriched with new features.
    """
    df_feat = df.copy()
    
    # Pre-calculate x for slope if we wanted to optimize, but we'll specific implementation inside loop
    
    print(f"Generating features for {len(sensor_cols)} sensors using vectorized operations...")
    sys.stdout.flush()
    
    # Pre-compute weights for slope calculation
    # Slope = sum((x - mx) * (y - my)) / sum((x - mx)^2)
    # Since sum(x-mx) = 0, numerator = sum((x-mx)*y)
    # We can compute this as a convolution of y with (x-mx).
    # We need to do this for both window_long (trend).
    
    # Weights for window_long
    x_long = np.arange(window_long)
    mx_long = x_long.mean()
    w_long = x_long - mx_long
    denom_long = (w_long**2).sum()
    
    # We reverse weights for np.convolve (or use correlate), but pandas rolling supports 'win_type' for some things, but not arbitrary weights easily without apply.
    # Actually, using rolling().mean() etc is fine. The bottleneck was rolling().apply().
    # We will use explicit numpy strides or simple convolution per group if possible.
    # But grouping + convolution might be tricky with pandas indices.
    # Faster approach for Hackathon:
    # Iterate sensors (15) is fine.
    # Inside: grouping by engine is slow if many engines? No, 200 engines is fine.
    # The slow part was 200 engines * N cycles * rolling apply.
    # Let's vectorize across the whole dataframe (ignoring engine boundaries for the convolution, then masking boundaries).
    # OR: Just loop over sensors, and for each sensor, use a fast rolling window on the whole column, 
    # but we MUST respect engine boundaries.
    # Best way: Use grouping but optimize the function.
    
    # Let's use a custom function that operates on the whole array but resets at engine boundaries?
    # Simpler: groupby().transform() with a vectorized func?
    # No, rolling() on a GroupBy object is optimized for mean/std. It is NOT optimized for apply.
    
    # OPTIMIZATION:
    # We can use the fact that data is likely sorted by engine_id, cycle.
    # We can apply convolution on the entire column, then set the first (window-1) values of each engine to NaN.
    # This avoids python loops per window.
    
    # Ensure sorted
    df_feat = df_feat.sort_values(by=['engine_id', 'cycle'])
    
    # Identify engine boundaries (indices where engine_id changes)
    # Actually, if we just run rolling on the whole column, we bleed data from Engine 1 to Engine 2.
    # But if we mask out the first W-1 elements of each engine, we are safe.
    
    # Get starts of engines
    # shift(1) != current
    engine_change = df_feat['engine_id'] != df_feat['engine_id'].shift(1)
    # We need to invalidate 'window' steps after engine change.
    # We'll handle this cleanup at the end.
    
    for i, sensor in enumerate(sensor_cols):
        # Quick progress
        # print(f"Processing {sensor}...") 
        
        # 1. Rolling Mean & Std (Pandas is fast enough here usually, but we can do global too)
        # To be safe and correct with boundaries without complex masking logic for EVERY feature,
        # let's try the global approach with masking.
        
        # Extract series
        vals = df_feat[sensor].values
        
        # 1. Rolling Mean/Std
        # global rolling
        s_series = df_feat[sensor]
        
        # Using pure pandas rolling on the whole column is fast
        df_feat[f'{sensor}_rm{window_short}'] = s_series.rolling(window=window_short).mean().fillna(0)
        df_feat[f'{sensor}_rm{window_long}'] = s_series.rolling(window=window_long).mean().fillna(0)
        df_feat[f'{sensor}_rs{window_short}'] = s_series.rolling(window=window_short).std().fillna(0)
        df_feat[f'{sensor}_rs{window_long}'] = s_series.rolling(window=window_long).std().fillna(0)
        
        # 2. Delta
        df_feat[f'{sensor}_delta'] = s_series.diff().fillna(0)

        # 3. Rolling Trend (Slope) - Vectorized Convolution
        # convolve(vals, w_long, mode='same')?
        # valid: output size N - K + 1. 
        # same: output size N. 
        # We need casual convolution (only past). 
        # np.convolve is "full" overlap centered usually?
        # We want: y[t] = dot(x[t-W+1:t+1], w)
        # This is cross-correlation or convolution with reversed weights.
        
        # Let's use np.convolve with 'full', then slice.
        # w_long needs to be applied such that w_long[-1] multiplies x[t], w_long[-2] multiplies x[t-1]...
        # So if we define w_long as [x_0, x_1...], we align latest with latest.
        # Actually standard definition of slope is weighted sum.
        # If we use np.convolve(input, weights_reversed, mode='valid') we get valid outputs.
        # We can pad input with NaNs or 0s at start.
        
        # Weights (x_long - mx) correspond to positions [0, 1, ..., W-1] in the window.
        # 0 is the oldest point, W-1 is the newest.
        # So we want dot product of window[0..W-1] with w_long[0..W-1].
        # Convolution flip kernel. So we use w_long[::-1].
        
        check_conv = np.convolve(vals, w_long[::-1], mode='full')
        # The result at index t (corresponding to input index t) should use input[t-W+1 : t+1].
        # np.convolve 'full' output size is N+W-1.
        # We want the value at index `t` to represent the window ending at `t`.
        # The convolution result at index `i` corresponds to overlap.
        # Correct shift:
        # We want the result to align with the end of the window.
        # For 'full', the first complete overlap (using W points) is at index W-1.
        # So we take slice [W-1 : N + W-1] -> NO.
        # Input length N. Output length N+W-1.
        # We want output length N.
        # Slice should be: [:N] with some shift?
        # Let's trace:
        # Index W-1 of convolve is dot(vals[0:W], w_reversed). Perfet.
        # So we take `check_conv[window_long-1 : -window_long+1]` if we padded?
        # Actually easiest is: check_conv[:len(vals)] shifted?
        # Let's just use slicing: `check_conv[window_long-1 : len(vals) + window_long - 1]`
        
        conv_res = check_conv[window_long-1 : len(vals) + window_long - 1]
        
        # Denominator is constant
        slope = conv_res / denom_long
        df_feat[f'{sensor}_trend'] = slope

        # 4. Drift (Baseline)
        # This needs per-engine baseline. 
        # Groupby is unavoidable for calculating the baseline, but we can map it back fast.
        # This part was not the slow bottleneck (it's one agg per engine).
        # We can allow this to remain or optimize.
        # Optimization:
        # Calculate all baselines at once for all sensors?
        # We are inside sensor loop.
        # It's fast enough.
        
        # Correction: We must NOT use data from previous engine.
        # We will mask "bad" indices.
        
    # Correcting data bleeding across engines
    # For each engine, the first `window` rows have potentially used data from previous engine (for rolling)
    # or are incomplete.
    # Group by engine and just re-apply mask?
    # Or cleaner:
    # Iterate through engine start indices and set previous `window` rows to NaN or 0?
    
    # We can detect engine switches and build a mask.
    # mask = True valid, False invalid.
    # Initially all True.
    # For every engine change at index `idx`:
    # indices [idx, idx+1, ..., idx+window-1] are invalid for window-based features.
    
    # Since window sizes are small (5, 10, 30), we can just loop engine starts (200 of them) and mask.
    # This is negligible cost.
    
    # Find indices where engine changes
    # engine_id is integer?
    ids = df_feat['engine_id'].values
    change_indices = np.where(ids[:-1] != ids[1:])[0] + 1
    # Include index 0
    start_indices = np.insert(change_indices, 0, 0)
    
    # Windows used
    windows = [window_short, window_long]
    # Delta uses 1.
    
    for idx in start_indices:
        # 1. Delta: index `idx` delta is invalid (diff with prev engine). Set to 0.
        for sensor in sensor_cols:
             df_feat.at[idx, f'{sensor}_delta'] = 0
             
        # 2. Rolling
        # For rows `idx` to `idx + window - 1`, the rolling value includes prev engine data.
        # We should set them to 0 or first valid value?
        # The prompt said "forward-fill then zero-fill".
        # If we set to NaN, we can fill later. 
        # But wait, original code did: rolling()... then fillna(0) within group.
        # Which implicitly means start of group is NaN then filled with 0.
        # So we should set these bleeding values to 0 (or NaN then 0).
        
        for w in windows:
            # Range to invalid
            if idx + w - 1 < len(df_feat): # Check bounds
                # We want to clear [idx : idx + w - 1]
                # Actually, pandas rolling min_periods=None implies we need full window.
                # If we have less than window, it gives NaN.
                # But here we ran global rolling, so it took prev values.
                # So yes, we MUST clear them.
                
                # Doing this cell-by-cell in python loop for every sensor is slow if done loosely.
                # Better: Create a global boolean mask for each window size.
                pass 
                
    # Vectorized masking
    # Create a mask for each window size
    # invalid_mask_W = zeros(N)
    # for idx in start_indices: invalid_mask[idx : idx+W-1] = 1
    # This is fast.
    
    for w in windows:
        mask = np.ones(len(df_feat), dtype=bool)
        for idx in start_indices:
            end = min(idx + w - 1, len(df_feat))
            mask[idx : end] = False
            
        # Apply mask to all columns using this window
        # Which columns?
        cols_w = [c for c in df_feat.columns if c.endswith(f'_rm{w}') or c.endswith(f'_rs{w}') or c.endswith(f'_trend') and w == window_long]
        # Note: trend uses window_long
        
        df_feat.loc[~mask, cols_w] = 0.0

    # Drift Calculation (Needs Baseline)
    # We can do this vectorized for all sensors at once?
    # Or keep the per-sensor loop for drift as it is not the bottleneck (agg is fast).
    # Re-implement drift inside the sensor loop or after?
    # Let's do it after to keep the main loop clean or inside.
    # Inside is cleaner for column management.
    
    # Let's re-add drift calculation in a separate block or iterate again?
    # Iterating 15 times for lightweight AGG is fine.
    
    print("Calculating drift features...")
    sys.stdout.flush()
    # Baseline: First 20 cycles.
    base_mask = df_feat['cycle'] <= 20
    
    for sensor in sensor_cols:
        # Global drift calc
        # We need mean/std per engine.
        # transform() is efficient.
        
        # Filter baseline data
        # grouping entire df is slightly expensive? No, 20k rows is nothing.
        # But we only want baseline rows.
        
        # Fast aligned mapping:
        # 1. Compute baselines
        stats = df_feat[base_mask].groupby('engine_id')[sensor].agg(['mean', 'std'])
        # stats index is engine_id
        
        # 2. Map to full df
        # map() is fast
        df_feat[f'{sensor}_mean'] = df_feat['engine_id'].map(stats['mean'])
        df_feat[f'{sensor}_std'] = df_feat['engine_id'].map(stats['std'])
        
        # 3. Compute
        epsilon = 1e-9
        df_feat[f'{sensor}_drift'] = (df_feat[sensor] - df_feat[f'{sensor}_mean']) / (df_feat[f'{sensor}_std'] + epsilon)
        
        # Drop temp
        df_feat.drop(columns=[f'{sensor}_mean', f'{sensor}_std'], inplace=True)
    
    # Final fillna for safety
    df_feat = df_feat.fillna(0)
    
    return df_feat

if __name__ == "__main__":
    from pipeline.data_loader import load_and_label
    from pipeline.sensor_cleaner import remove_constant_sensors
    from pipeline.normalizer import normalize_dataframe
    from pipeline.config import DATA_PATH, TRAIN_FILE
    import os

    # Construct path
    train_path = os.path.join(DATA_PATH, TRAIN_FILE)
    
    if os.path.exists(train_path):
        print("1. Loading...")
        df = load_and_label(train_path)
        
        print(f"2. Cleaning (Original cols: {df.shape[1]})...")
        df_clean, kept_sensors = remove_constant_sensors(df)
        
        print("3. Normalizing...")
        setting_cols = ['op1', 'op2', 'op3']
        features_to_normalize = setting_cols + kept_sensors
        df_norm, _ = normalize_dataframe(df_clean, features_to_normalize)
        
        print("4. Feature Engineering...")
        # Use kept_sensors from cleaning step
        df_final = add_degradation_features(df_norm, kept_sensors)
        
        print(f"\nOriginal column count: {df_norm.shape[1]}")
        print(f"New column count: {df_final.shape[1]}")
        
        new_cols = [c for c in df_final.columns if c not in df_norm.columns]
        print(f"Added {len(new_cols)} features.")
        
        print("\nHead of dataframe:")
        # Selecting a few interesting columns to show
        # ID, cycle, RUL, plus features for one sensor (e.g., s2)
        cols_to_show = ['engine_id', 'cycle', 'RUL'] + [c for c in new_cols if 's2_' in c]
        # Only show if s2 exists
        if any('s2_' in c for c in new_cols):
             print(df_final[cols_to_show].head(15))
        else:
             print(df_final.head())
             
    else:
        print(f"Error: File not found at {train_path}")
