import torch
import torch.nn as nn
from pipeline.models.transformer_model import RULTransformer

def verify_attention():
    print("Verifying Attention Mechanism...")
    
    # Init Model
    # input_dim=10, seq_len=30, batch=2
    input_dim = 10
    seq_len = 30
    batch_size = 2
    nhead = 4
    
    model = RULTransformer(input_dim=input_dim, d_model=32, nhead=nhead, num_layers=2)
    model.eval()
    
    # Fake Input
    x = torch.randn(batch_size, seq_len, input_dim)
    
    # Forward with flag
    pred, attn_weights = model(x, return_attention=True)
    
    print(f"Prediction Shape: {pred.shape}")
    print(f"Attention Weights Shape: {attn_weights.shape}")
    
    # Expected: (Batch, NumHeads, SeqLen, SeqLen)
    expected_shape = (batch_size, nhead, seq_len, seq_len)
    
    if attn_weights.shape == expected_shape:
        print("SUCCESS: Attention weights shape matches expectation.")
    else:
        print(f"FAILURE: Expected {expected_shape}, got {attn_weights.shape}")
        
    # Check if weights sum to 1 roughly (softmax)
    # Check last dim sum
    sums = attn_weights.sum(dim=-1)
    # Should be all close to 1
    if torch.allclose(sums, torch.ones_like(sums), atol=1e-5):
         print("SUCCESS: Attention weights sum to 1.")
    else:
         print("WARNING: Attention weights do not sum to 1 (might be masking issue or logic)")
         print(sums[0,0,:5])

if __name__ == "__main__":
    verify_attention()
