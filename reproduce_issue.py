
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from pipeline.models.train_transformer import load_seq_data
import time

print("Starting reproduction script...")
start = time.time()
try:
    X, y, dim = load_seq_data()
    print(f"Loaded {len(X)} sequences in {time.time() - start:.2f}s")
except Exception as e:
    print(f"Error: {e}")
