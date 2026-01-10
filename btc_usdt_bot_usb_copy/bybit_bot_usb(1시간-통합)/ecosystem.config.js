module.exports = {
  apps: [
    {
      name: "bot-1h",
      script: "live_trader_bybit.py",
      interpreter: "python3",
      args: "-u",
      watch: false,
      autorestart: true,
      max_memory_restart: "500M",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "../logs/bot_1h_error.log",
      out_file: "../logs/bot_1h_out.log",
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ".."
      }
    }
  ]
};
