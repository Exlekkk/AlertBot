from datetime import datetime, timedelta
import logging
import os

from fastapi import FastAPI, HTTPException, Request
import requests
from dotenv import load_dotenv

load_dotenv('/opt/smct-alert/config/.env')

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

LOG_FILE = os.getenv("WEBHOOK_LOG_FILE", "webhook.log")
COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))

logger = logging.getLogger("webhook")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(file_handler)

last_sent = {}


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    r = requests.post(url, json=payload, timeout=20)
    return r.text


def normalize_field(data: dict, *keys: str, default: str = "unknown") -> str:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue
        return str(value).strip()
    return default


@app.get("/")
def root():
    return {"status": "ok", "message": "SMCT Alert Bot is running"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    request_secret = data.get("secret")
    if WEBHOOK_SECRET and request_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    symbol = normalize_field(data, "symbol", "ticker")
    timeframe = normalize_field(data, "timeframe", "interval")
    signal = normalize_field(data, "signal", "alert")

    forwarded_for = request.headers.get("x-forwarded-for")
    source_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")

    logger.info(
        "webhook_received ip=%s symbol=%s signal=%s timeframe=%s",
        source_ip,
        symbol,
        signal,
        timeframe,
    )

    cooldown_key = (symbol, timeframe, signal)
    now = datetime.now()
    previous_time = last_sent.get(cooldown_key)
    if previous_time and now - previous_time < timedelta(seconds=COOLDOWN_SECONDS):
        return {"ok": True, "skipped": True, "reason": "cooldown"}

    message = (
        "📡 SMCT预警\n"
        f"标的：{symbol}\n"
        f"周期：{timeframe}\n"
        f"信号：{signal}\n"
        "来源：TradingView"
    )
    result = send_telegram_message(message)
    last_sent[cooldown_key] = now

    return {"ok": True, "telegram_result": result}
