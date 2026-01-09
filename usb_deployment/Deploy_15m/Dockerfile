FROM python:3.10-slim

WORKDIR /app
# Copy the shared bots module
COPY bots /app/bots

# Copy the project files
COPY "deploy_package--15분봉" /app/project

WORKDIR /app/project

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the bot
CMD ["python", "-u", "main.py"]
