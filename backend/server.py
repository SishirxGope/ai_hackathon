import sys
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List

# Add project root to path
sys.path.append(os.getcwd())

import backend.inference as inference

app = FastAPI(title="RUL Prediction Backend")

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory="ui/public"), name="ui")

@app.get("/")
def serve_index():
    return FileResponse("ui/public/index.html")

# @app.get("/health")
# def health_check():
#     return {"status": "online", "system": "RUL Prediction Backend"}

@app.get("/engines", response_model=List[str])
def get_engines():
    """Returns list of engine IDs"""
    return inference.get_engine_ids()

@app.get("/debug")
def debug_status():
    """Returns internal system status"""
    return inference.get_system_status()

@app.get("/metrics")
def metrics():
    return inference.get_model_metrics()

@app.get("/predict/{engine_id}", response_model=Dict[str, Any])
def predict(engine_id: str, cycle: int = None):
    """
    Returns RUL, Uncertainty, Confidence, and Trend.
    """
    # 1. RUL Logic
    rul_data = inference.predict_rul(engine_id, cycle=cycle)
    if not rul_data:
        raise HTTPException(status_code=404, detail="Engine not found")
        
    # 2. Return Response
    return rul_data

@app.get("/health/{engine_id}", response_model=Dict[str, float])
def get_health(engine_id: str):
    """
    Returns Health Index.
    """
    health_val = inference.predict_health(engine_id)
    # Return as raw value or percentage? 
    # User request output example: { health }
    # Let's keep consistency with previous Flask attempt: return raw or percent?
    # inference.predict_health returns 0-1 (presumably).
    # If UI expects %, we multiply by 100.
    # User didn't strictly specify unit here, but frontend usually expects 0-100 or 0-1.
    # Looking at index.html gauge logic (Step 19), it uses percentage classes.
    # Previous Flask server was multiplying by 100. Let's do that for safety if it's 0-1.
    # Actually let's assume predict_health returns whatever the health index is. 
    # If it is 0-1, multiplying by 100 is safer for display.
    # Let's double check predict_health docs in inference.py: "Returns health index 0-1 (or scaled)."
    
    return {
        "health": health_val * 100
    }

@app.get("/history/{engine_id}")
def api_history(engine_id: str):
    return inference.get_engine_history(engine_id)

if __name__ == '__main__':
    print("Starting RUL Backend (FastAPI) on port 5000...")
    uvicorn.run(app, host="0.0.0.0", port=5000)
