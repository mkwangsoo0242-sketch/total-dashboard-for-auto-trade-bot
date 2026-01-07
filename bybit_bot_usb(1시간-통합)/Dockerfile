FROM python:3.12-slim

WORKDIR /app
# Copy the shared bots module
COPY bots /app/bots

# Copy the project files
COPY "bybit_bot_usb(1시간-통합)" /app/project

WORKDIR /app/project

# Install dependencies
# System deps for potential build needs
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Default command (can be overridden in compose)
CMD ["python", "-u", "live_trader_bybit.py"]
