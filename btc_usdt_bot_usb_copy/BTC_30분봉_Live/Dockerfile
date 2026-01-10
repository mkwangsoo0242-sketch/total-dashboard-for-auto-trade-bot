FROM python:3.10-slim

WORKDIR /app
# Copy the shared bots module
COPY bots /app/bots

# Copy the project files
COPY "BTC_30분봉_Live" /app/project

WORKDIR /app/project

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the bot
CMD ["python", "-u", "live_bot.py"]
