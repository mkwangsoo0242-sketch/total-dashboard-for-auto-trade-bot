#!/bin/bash

# 1. Check Root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run as root (use sudo)"
  echo "Usage: sudo ./setup_autostart.sh"
  exit 1
fi

echo "🚀 Setting up Autostart for Ubuntu..."

# 2. Get Current Absolute Path
CURRENT_DIR=$(pwd)
echo "📂 Current Directory: $CURRENT_DIR"

# 3. Update Service File with Real Path
echo "🔧 Configuring service file..."
cp bot_manager.service bot_manager.service.bak
sed -i "s|THIS_PATH|$CURRENT_DIR|g" bot_manager.service

# 4. Copy to Systemd
echo "📦 Installing service..."
cp bot_manager.service /etc/systemd/system/bot_manager.service

# 5. Reload and Enable
echo "🔄 Enabling service..."
systemctl daemon-reload
systemctl enable bot_manager.service
systemctl restart bot_manager.service

echo "✅ Success! The bot will now start automatically on boot."
echo "   - Check Status: sudo systemctl status bot_manager.service"
echo "   - View Logs: sudo journalctl -u bot_manager.service -f"
