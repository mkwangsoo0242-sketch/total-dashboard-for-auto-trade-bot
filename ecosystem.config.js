module.exports = {
  apps: [
    {
      name: "bot-integrated-manager",
      script: "bot_manager.py",
      interpreter: "python3",
      args: "-u",
      watch: false,
      autorestart: true,
      max_memory_restart: "1G",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "./logs/pm2_manager_error.log",
      out_file: "./logs/pm2_manager_out.log",
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: "."
      }
    }
    // Standalone bots are commented out because bot_manager.py runs them internally.
    // If you want to run them separately, disable bot_manager.py run logic and uncomment these.
    /*
    {
      name: "bot-30m-standalone",
      cwd: "./BTC_30분봉_Live",
      script: "live_bot.py",
      interpreter: "python3",
      args: "-u",
      env: { PYTHONPATH: ".." }
    },
    {
      name: "bot-5m-standalone",
      cwd: "./RealTradingBot_Deployment(5분봉)",
      script: "live_trading_bot.py",
      interpreter: "python3",
      args: "-u",
      env: { PYTHONPATH: ".." }
    },
    {
      name: "bot-15m-standalone",
      cwd: "./deploy_package--15분봉",
      script: "main.py",
      interpreter: "python3",
      args: "-u",
      env: { PYTHONPATH: ".." }
    },
    {
      name: "bot-1h-standalone",
      cwd: "./bybit_bot_usb(1시간-통합)",
      script: "live_trader_bybit.py",
      interpreter: "python3",
      args: "-u",
      env: { PYTHONPATH: ".." }
    }
    */
  ]
};
