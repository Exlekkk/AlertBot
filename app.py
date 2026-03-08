from fastapi import FastAPI, HTTPException, Request

from config import (
    ALERT_COOLDOWN_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_LOG_FILE,
    WEBHOOK_SECRET,
)
from engine.cooldown import CooldownStore
from services.logger import get_logger
from services.telegram import format_alert_message, send_telegram_message

app = FastAPI()
logger = get_logger("webhook", WEBHOOK_LOG_FILE)
cooldown = CooldownStore(ALERT_COOLDOWN_SECONDS)


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
    if cooldown.is_in_cooldown(cooldown_key):
        return {"ok": True, "skipped": True, "reason": "cooldown"}

    message = format_alert_message(
        signal=signal,
        symbol=symbol,
        timeframe=timeframe,
        context="Webhook事件",
        trigger="外部信号触发",
        source="TradingView",
    )
    result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
    cooldown.mark_sent(cooldown_key)

    return {"ok": True, "telegram_result": result}
