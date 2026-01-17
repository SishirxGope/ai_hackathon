import torch
import torch.nn as nn
import math

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        # Create PE matrix of shape [max_len, d_model]
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        # Reshape to [1, max_len, d_model] for broadcasting over batch
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x):
        # x shape: [Batch, SeqLen, Features]
        # pe shape: [1, MaxLen, Features] -> Slice to [1, SeqLen, Features]
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class CustomTransformerEncoderLayer(nn.TransformerEncoderLayer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_attn_weights = None

    def forward(self, src, src_mask=None, src_key_padding_mask=None, is_causal=False):
        # Fully override forward to ensure we capture weights
        x = src
        # Self Attention Block
        # We need to manually call self_attn to get weights
        attn_output, weights = self.self_attn(x, x, x, 
                                            attn_mask=src_mask, 
                                            key_padding_mask=src_key_padding_mask,
                                            need_weights=True,
                                            average_attn_weights=False,
                                            is_causal=is_causal)
        self.last_attn_weights = weights
        
        x = x + self.dropout1(attn_output)
        x = self.norm1(x)
        
        # Feed Forward Block
        x2 = self.linear2(self.dropout(self.activation(self.linear1(x))))
        x = x + self.dropout2(x2)
        x = self.norm2(x)
        
        return x

class RULTransformer(nn.Module):
    def __init__(self, input_dim, d_model=64, nhead=4, num_layers=2, dropout=0.1, output_dim=1):
        super(RULTransformer, self).__init__()
        
        # 1. Input Projection
        self.embedding = nn.Linear(input_dim, d_model)
        
        # 2. Positional Encoding
        self.pos_encoder = PositionalEncoding(d_model, dropout)
        
        # 3. Transformer Encoder
        # Use our custom layer
        encoder_layer = CustomTransformerEncoderLayer(d_model=d_model, nhead=nhead, dropout=dropout, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # 4. Output Head
        self.decoder = nn.Linear(d_model, output_dim)
        
        self.d_model = d_model

    def forward(self, src, return_attention=False):
        # src shape: [Batch, SeqLen, Features]
        
        # Embed and Add Position
        x = self.embedding(src) * math.sqrt(self.d_model)
        x = self.pos_encoder(x)
        
        # Transformer Pass
        output = self.transformer_encoder(x)
        
        # Global Average Pooling or Take Last Token?
        x_last = output[:, -1, :] 
        
        # Prediction
        rul_pred = self.decoder(x_last)
        pred = rul_pred.squeeze(-1)

        if return_attention:
            # Extract weights from the *last* layer of the encoder
            # The encoder is a stack of layers.
            last_layer = self.transformer_encoder.layers[-1]
            attention_weights = last_layer.last_attn_weights
            
            # attention_weights shape: (Batch, NumHeads, SeqLen, SeqLen)
            # The user requested: (num_heads, seq_len, seq_len)
            # This implies they might expect a single sample's weights or we return the full batch.
            # We return the full batch tensor to be general.
            return pred, attention_weights
        
        return pred

    def get_attention_weights(self, src):
        # Deprecated helper, use forward(return_attention=True)
        return self.forward(src, return_attention=True)[1]
