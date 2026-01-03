module.exports = {
  apps: [
    {
      name: "bot-15m",
      script: "main.py",
      interpreter: "python3",
      args: "-u",
      watch: false,
      autorestart: true,
      max_memory_restart: "500M",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "../logs/bot_15m_error.log",
      out_file: "../logs/bot_15m_out.log",
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ".."
      }
    }
  ]
};
