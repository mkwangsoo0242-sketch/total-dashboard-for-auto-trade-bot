FROM python:3.10-slim

# Install procps for pgrep (used by app.py)
RUN apt-get update && apt-get install -y procps && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Copy the shared bots module
COPY bots /app/bots

# Copy the project files
COPY "RealTradingBot_Deployment(5분봉)" /app/project

WORKDIR /app/project

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the application
CMD ["python", "-u", "app.py"]
