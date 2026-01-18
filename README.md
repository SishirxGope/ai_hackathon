# AI Digital Twin: Advanced Prognostics and Predictive Maintenance

## Overview
This project implements an end-to-end Predictive Maintenance system using an **AI Digital Twin** approach. It leverages advanced machine learning techniques to predict the Remaining Useful Life (RUL) of aircraft engines based on sensor data (CMAPSS dataset). The system features a comprehensive data processing pipeline, a hybrid modeling approach (XGBoost + Transformer), and an interactive dashboard for real-time monitoring and explainability.

## Key Features
- **Robust Data Pipeline**: Automated data loading, cleaning (constant sensor removal), normalization, and feature engineering.
- **Health Index Calculation**: Derives a composite Health Index (HI) using PCA to represent the degradation status of the engine.
- **Hybrid Modeling**:
  - **Track A (Baseline)**: XGBoost regressor for robust, interpretable predictions.
  - **Track B (Advanced)**: Transformer-based deep learning model for capturing long-term temporal dependencies in sensor sequences.
- **Uncertainty Quantification**: Provides confidence intervals for RUL predictions.
- **Explainable AI (XAI)**: SHAP (SHapley Additive exPlanations) values to interpret model decisions and feature importance.
- **Interactive Dashboard**: A modern web interface for visualizing engine status, real-time RUL forecasts, and sensor trends.

<video src="AI Hackathon Vid.mp4" controls title="Project Demo Video">
  Your browser does not support the video tag.
</video>


## Project Structure
```
rul_hackathon/
├── backend/                # FastAPI backend server
│   ├── server.py           # API entry point & static file serving
│   └── inference.py        # Inference logic for RUL and Health Index
├── pipeline/               # Core data processing & modeling
│   ├── models/             # Model definitions (XGBoost, Transformer)
│   ├── data_loader.py      # Data ingestion
│   ├── feature_engineering.py # Signal processing & feature generation
│   ├── health_index.py     # PCA-based Health Index calculation
│   └── ...                 # Normalization, cleaning, utils
├── ui/                     # Frontend dashboard
│   └── public/             # HTML, CSS, JS assets
├── data/                   # Raw CMAPSS datasets
├── output/                 # Processed datasets and reports
├── run_pipeline.py         # Main script to run the full processing & training pipeline
└── requirements.txt        # Python dependencies
```

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd rul_hackathon
    ```

2.  **Set up a virtual environment (optional but recommended):**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: Ensure you have PyTorch installed appropriate for your system, e.g., with CUDA support if available)*

## Usage

### 1. Run the Data Pipeline & Baseline Training
Execute the main pipeline script to process data, generate the Health Index, and train the XGBoost baseline model.
```bash
python run_pipeline.py
```
This will:
- Load and clean the CMAPSS data.
- Normalize and generate features.
- Calculate the Health Index.
- Train the XGBoost model and save checkpoints to `pipeline/models/checkpoints/`.
- Evaluate model performance and save metrics.

### 2. Train the Transformer Model (Optional/Advanced)
To train the deep learning Transformer model:
```bash
python pipeline/models/train_transformer.py
```

### 3. Start the Inference Server & Dashboard
Launch the FastAPI server to serve the predictions and the visualization dashboard.
```bash
python backend/server.py
```
The server will start at `http://0.0.0.0:5000`.

### 4. Access the Dashboard
Open your web browser and navigate to:
```
http://localhost:5000/
```
Here, you can:
- Select different Engines IDs to visualize.
- View real-time RUL predictions and confidence intervals.
- Monitor the Health Index degradation curve.
- Analyze sensor data trends.

## Methodology

### Data Preprocessing
- **Cleaning**: Sensors with constant values (std dev = 0) are removed to reduce noise.
- **Normalization**: MinMax scaling is applied to standardize sensor readings.
- **Feature Engineering**: Rolling statistics (mean, std) and trend features are generated to capture signal dynamics.

### Health Index (HI)
A Health Index is constructed to quantify the degradation level. We use Principal Component Analysis (PCA) to fuse multiple sensor signals into a single monotonic prognostic parameter that correlates with the RUL.

### Models
- **XGBoost**: Uses a window of recent sensor data and engineered features to predict RUL. Optimized for speed and interpretability.
- **Transformer**: Uses a self-attention mechanism to process long sequences of sensor history, effectively capturing the long-term degradation patterns critical for accurate prognostics in late-stage failure.

## Technologies
- **Language**: Python 3.8+
- **ML/DL**: PyTorch, XGBoost, Scikit-learn
- **Data**: Pandas, NumPy
- **Backend**: FastAPI, Uvicorn
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla), Chart.js
- **Visualization**: Matplotlib, Seaborn

## License
[MIT License](LICENSE)
