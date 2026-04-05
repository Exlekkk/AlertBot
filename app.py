from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_LOG_FILE,
    WEBHOOK_PERSIST_SECONDS,
    WEBHOOK_SECRET,
    WEBHOOK_STATE_FILE,
)
from engine.cooldown import SignalStateStore
from engine.runtime_state import RuntimeStateStore
from services.logger import get_logger
from services.telegram import format_webhook_message, send_telegram_message

app = FastAPI()
logger = get_logger("webhook", WEBHOOK_LOG_FILE)
webhook_state = SignalStateStore(state_file=WEBHOOK_STATE_FILE, price_change_threshold=0.0)
runtime_state = RuntimeStateStore()


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
    snapshot = runtime_state.get_snapshot()
    return {
        "status": "ok",
        "message": "SMCT Alert Bot is running",
        "runtime": snapshot,
    }


@app.get("/health")
def health():
    return runtime_state.build_health_payload()


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    request_secret = data.get("secret")
    if WEBHOOK_SECRET and request_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    symbol = normalize_field(data, "symbol", "ticker")
    timeframe = normalize_field(data, "timeframe", "interval")
    signal = normalize_field(data, "signal", "alert")
    direction = normalize_field(data, "direction", default="unknown")

    forwarded_for = request.headers.get("x-forwarded-for")
    source_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (request.client.host if request.client else "unknown")

    logger.info(
        "webhook_received ip=%s symbol=%s signal=%s timeframe=%s direction=%s",
        source_ip,
        symbol,
        signal,
        timeframe,
        direction,
    )

    webhook_signal = {
        "signal": signal,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "price": float(data.get("price", 0.0) or 0.0),
        "signature": f"webhook|{symbol}|{timeframe}|{signal}|{direction}",
        "cooldown_seconds": WEBHOOK_PERSIST_SECONDS,
        "phase_name": "external",
        "phase_context": "webhook",
        "phase_anchor": f"{symbol}|{timeframe}|{signal}",
    }

    if not webhook_state.should_send(webhook_signal):
        runtime_state.mark_webhook_skip(symbol=symbol, signal=signal, reason="cooldown")
        return {"ok": True, "skipped": True, "reason": "cooldown"}

    message = format_webhook_message(signal=signal, symbol=symbol, timeframe=timeframe, direction=direction)
    result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
    webhook_state.mark_sent(webhook_signal)
    runtime_state.mark_webhook_send(symbol=symbol, signal=signal)

    return {"ok": True, "telegram_result": result}
