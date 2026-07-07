#!/usr/bin/env bash
# ============================================================
# Binance Trade Botu - Otomatik VPS Kurulumu (Ubuntu/Debian)
#
# Kullanim (VPS'te, repo klasorunun icinde):
#   chmod +x setup_vps.sh
#   ./setup_vps.sh
#
# Yaptiklari:
#   1. Python ve gerekli paketleri kurar
#   2. Sanal ortam (venv) olusturur, bagimliliklari yukler
#   3. .env dosyasi yoksa sablondan olusturur
#   4. systemd servisi kurar: bot acilista otomatik baslar,
#      cokerse kendini yeniden baslatir
# ============================================================
set -euo pipefail

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="tradebot"
RUN_USER="${SUDO_USER:-$(whoami)}"

echo "==> Bot dizini: $BOT_DIR"
echo "==> Servis kullanicisi: $RUN_USER"

# 1) Sistem paketleri
echo "==> Python kuruluyor..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip

# 2) Sanal ortam + bagimliliklar
echo "==> Sanal ortam hazirlaniyor..."
cd "$BOT_DIR"
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

# 3) .env dosyasi
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "!!! .env dosyasi olusturuldu ama API anahtarlariniz eksik."
    echo "!!! Kurulumdan sonra su komutla duzenleyin: nano $BOT_DIR/.env"
    echo ""
fi

# 4) systemd servisi
echo "==> systemd servisi kuruluyor: $SERVICE_NAME"
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Binance Trade Botu
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "============================================================"
echo "Kurulum tamamlandi! Bot arka planda calisiyor."
echo ""
echo "Faydali komutlar:"
echo "  sudo systemctl status $SERVICE_NAME    # durumu gor"
echo "  sudo journalctl -u $SERVICE_NAME -f    # canli log izle"
echo "  sudo systemctl stop $SERVICE_NAME      # durdur"
echo "  sudo systemctl restart $SERVICE_NAME   # yeniden baslat"
echo ""
echo "API anahtari girdiyseniz/degistirdiyseniz yeniden baslatin:"
echo "  nano $BOT_DIR/.env && sudo systemctl restart $SERVICE_NAME"
echo "============================================================"
