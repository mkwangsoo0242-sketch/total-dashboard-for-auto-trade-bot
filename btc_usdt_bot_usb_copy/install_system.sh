#!/bin/bash

# Stop on compilation errors
set -e

# Root Check
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: Please run as root (use sudo)"
  echo "   Usage: sudo ./install_system.sh"
  exit 1
fi

echo "🐧 Ubuntu All-in-One Auto-Installer for Trading Bot"
echo "==================================================="

# 0. Prevent Sleep/Suspend (Server Mode)
echo "💤 Disabling Sleep/Suspend modes..."
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# 1. Update System & Install Application + SSH
echo "📦 Updating apt repositories..."
apt-get update

echo "📦 Installing Python, SSH, Utils..."
apt-get install -y python3 python3-pip python3-venv git htop openssh-server curl net-tools ca-certificates gnupg lsb-release

# 1.1 Install Docker Engine
echo "🐳 Installing Docker & Docker Compose..."
# Remove old versions if any
apt-get remove -y docker docker-engine docker.io containerd runc || true

# Add Docker's official GPG key
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Set up the repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker
systemctl enable docker
systemctl start docker
echo "   -> Docker installed and running."

# 2. Setup SSH
echo "🔐 Enabling SSH Server..."
systemctl enable ssh
systemctl start ssh
echo "   -> SSH is active. IP Address:"
hostname -I

# 3. Setup Virtual Environment
echo "🐍 Setting up Python Virtual Environment (venv)..."
# Get the absolute path of the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   -> Virtual environment created."
else
    echo "   -> 'venv' already exists. Skipping creation."
fi

# 4. Upgrading Pip & Installing Libs
echo "⬆️ Installing Dependencies..."
./venv/bin/pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    ./venv/bin/pip install -r requirements.txt
fi

# Install sub-requirements
find . -name "requirements.txt" -not -path "./venv/*" -not -path "./requirements.txt" | while read req_file; do
    echo "   -> Installing from $req_file..."
    ./venv/bin/pip install -r "$req_file"
done

# 5. Fix Start Scripts (Patching to use venv)
echo "🔧 Patching start scripts..."
chmod +x *.sh
sed -i 's|nohup python3 |nohup ./venv/bin/python3 |g' start_dashboard.sh
sed -i 's|nohup python -u |nohup ./venv/bin/python3 -u |g' start_dashboard.sh

# 5.5 Setup Log Rotation
echo "🔄 Configuring Log Rotation..."
LOG_CONFIG="/etc/logrotate.d/trading_bot"
cat > $LOG_CONFIG <<EOF
$SCRIPT_DIR/*.log $SCRIPT_DIR/*/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 640 root root
    copytruncate
}
EOF
echo "   -> Log rotation configured at $LOG_CONFIG"

# 6. Auto-Start Setup (Integrated)
echo "🚀 Configuring Auto-Start Service..."
# Update service file path
cp bot_manager.service bot_manager.service.bak
sed -i "s|THIS_PATH|$SCRIPT_DIR|g" bot_manager.service

# Move and Enable
cp bot_manager.service /etc/systemd/system/bot_manager.service
systemctl daemon-reload
systemctl enable bot_manager.service
systemctl restart bot_manager.service

echo ""
echo "🎉 ALL DONE! Installation Complete."
echo "----------------------------------------------"
echo "1. SSH is enabled. Connect via: ssh username@$(hostname -I | awk '{print $1}')"
echo "2. Bot Service is RUNNING and will auto-start on boot."
echo "3. Dashboard is available at: http://$(hostname -I | awk '{print $1}'):8000"
echo "----------------------------------------------"
