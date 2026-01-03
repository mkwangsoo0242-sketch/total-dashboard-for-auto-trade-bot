import subprocess
import os
from datetime import datetime

def run_script(script_name):
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    print(f"Running {script_path}...")
    process = subprocess.run(['python3', script_path], capture_output=True, text=True)
    if process.returncode != 0:
        print(f"Error running {script_name}:")
        print(process.stderr)
        return False
    else:
        print(f"{script_name} completed successfully.")
        print(process.stdout)
        return True

if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting data update and model retraining process...")

    # 1. Update historical data
    print("Step 1: Updating historical data...")
    if not run_script("data_collector.py"):
        print("Data collection failed. Aborting retraining process.")
    else:
        # 2. Train the trend model with updated data
        print("Step 2: Retraining the trend model...")
        if not run_script("train_trend_model.py"):
            print("Model retraining failed.")
        else:
            print(f"[{datetime.now()}] Data update and model retraining completed successfully.")
