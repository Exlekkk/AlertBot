import os
from dotenv import load_dotenv

load_dotenv('/opt/smct-alert/config/.env')


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_LOG_FILE = os.getenv("WEBHOOK_LOG_FILE", "webhook.log")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "BTCUSDT")
