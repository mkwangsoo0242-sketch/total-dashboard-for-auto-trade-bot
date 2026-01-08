FROM python:3.9-slim
WORKDIR /app
ENV TZ=Asia/Seoul
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "final_trading_bot.py"]
