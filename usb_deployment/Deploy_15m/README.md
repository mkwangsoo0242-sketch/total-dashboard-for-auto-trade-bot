# High ROI Trading Bot Deployment Package

This package contains everything needed to run the High ROI Trading Bot from a USB drive or any other location.

## Package Contents
- `main.py`: Core trading logic.
- `strategy.py`: RSI2 + Trend + LightGBM strategy.
- `lgbm_model.pkl`: Trained model for trade signal validation.
- `frontend/`: Web dashboard for monitoring and control.
- `run.sh`: One-click execution script.

## How to Run
1. Copy this `deploy_package` folder to your target machine.
2. Open a terminal in the folder.
3. Make the script executable: `chmod +x run.sh`
4. Run the script: `./run.sh`
5. Open your browser and go to `http://localhost:5000`

## Requirements
- Python 3.8 or higher.
- Internet connection for API access.
