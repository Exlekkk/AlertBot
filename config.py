import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False

ENV_FILE = os.getenv("SMCT_ENV_FILE", "/opt/smct-alert/config/.env")
load_dotenv(ENV_FILE)
load_dotenv(override=False)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_LOG_FILE = os.getenv("WEBHOOK_LOG_FILE", "/opt/smct-alert/logs/smct-alert.log")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "BTCUSDT")

MARKET_SOURCE = os.getenv("MARKET_SOURCE", "binance_futures").lower()
BINANCE_SPOT_KLINES_URL = os.getenv("BINANCE_SPOT_KLINES_URL", "https://api.binance.com/api/v3/klines")
BINANCE_FUTURES_KLINES_URL = os.getenv("BINANCE_FUTURES_KLINES_URL", "https://fapi.binance.com/fapi/v1/klines")
KLINE_LIMIT = int(os.getenv("KLINE_LIMIT", "300"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))

SMCT_SIGNAL_STATE_FILE = os.getenv("SMCT_SIGNAL_STATE_FILE", "/opt/smct-alert/state/signal_state.json")
SMCT_RUNTIME_STATE_FILE = os.getenv("SMCT_RUNTIME_STATE_FILE", "/opt/smct-alert/state/runtime_state.json")
WEBHOOK_STATE_FILE = os.getenv("WEBHOOK_STATE_FILE", "/opt/smct-alert/state/webhook_state.json")

FREEZE_MODE_SEND_X_ONLY = os.getenv("FREEZE_MODE_SEND_X_ONLY", "1") == "1"
SEND_NEAR_MISS_SUMMARY = os.getenv("SEND_NEAR_MISS_SUMMARY", "0") == "1"
HEARTBEAT_STALE_AFTER_SECONDS = int(os.getenv("HEARTBEAT_STALE_AFTER_SECONDS", "240"))
WEBHOOK_PERSIST_SECONDS = int(os.getenv("WEBHOOK_PERSIST_SECONDS", "300"))
