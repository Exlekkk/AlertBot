from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import IO

from fastapi import FastAPI, HTTPException, Request

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_OPS_POLL_ENABLED,
    TELEGRAM_OPS_POLL_LOCK_FILE,
    TELEGRAM_OPS_POLL_TIMEOUT_SECONDS,
    WEBHOOK_LOG_FILE,
    WEBHOOK_PERSIST_SECONDS,
    WEBHOOK_SECRET,
    WEBHOOK_STATE_FILE,
)
from engine.cooldown import SignalStateStore
from engine.runtime_state import RuntimeStateStore
from services.logger import get_logger
from services.ops_poll_lock import release_ops_poll_lock, try_acquire_ops_poll_lock
from services.ops_status import process_telegram_update
from services.telegram import format_webhook_message, send_telegram_message

logger = get_logger("webhook", WEBHOOK_LOG_FILE)
webhook_state = SignalStateStore(state_file=WEBHOOK_STATE_FILE, price_change_threshold=0.0)
runtime_state = RuntimeStateStore()
_ops_poll_stop = threading.Event()
_ops_poll_thread: threading.Thread | None = None
_ops_poll_lock_fh: IO[str] | None = None


def _telegram_get_updates(token: str, offset: int | None, timeout: int) -> list[dict]:
    try:
        import requests
    except ModuleNotFoundError:
        return []
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params: dict = {"timeout": max(1, int(timeout))}
    if offset is not None:
        params["offset"] = int(offset)
    try:
        response = requests.get(url, params=params, timeout=max(5, int(timeout) + 5))
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("telegram_get_updates_failed error=%s", exc)
        return []
    if not data.get("ok"):
        logger.warning("telegram_get_updates_not_ok body=%s", str(data)[:300])
        return []
    result = data.get("result") or []
    return result if isinstance(result, list) else []


def _ops_poll_loop() -> None:
    """Long-poll Bot API getUpdates for /check and /test (no Telegram webhook required)."""
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("ops_poll_disabled reason=missing_bot_token")
        return
    offset: int | None = None
    timeout = TELEGRAM_OPS_POLL_TIMEOUT_SECONDS
    logger.info("ops_poll_started timeout_seconds=%s", timeout)
    while not _ops_poll_stop.is_set():
        updates = _telegram_get_updates(token, offset, timeout)
        for update in updates:
            try:
                update_id = int(update.get("update_id", 0))
                offset = update_id + 1
                process_telegram_update(update, state=runtime_state)
            except Exception:
                logger.exception("ops_poll_update_failed")
        if not updates:
            # Brief pause on empty/error so a hard-failing API does not spin.
            _ops_poll_stop.wait(1.0)
    logger.info("ops_poll_stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ops_poll_thread, _ops_poll_lock_fh
    _ops_poll_stop.clear()
    _ops_poll_lock_fh = None
    _ops_poll_thread = None
    if TELEGRAM_OPS_POLL_ENABLED and TELEGRAM_BOT_TOKEN:
        lock_fh = try_acquire_ops_poll_lock(TELEGRAM_OPS_POLL_LOCK_FILE)
        if lock_fh is None:
            logger.info("ops_poll_skipped reason=lock_held path=%s", TELEGRAM_OPS_POLL_LOCK_FILE)
        else:
            _ops_poll_lock_fh = lock_fh
            _ops_poll_thread = threading.Thread(target=_ops_poll_loop, name="tg-ops-poll", daemon=True)
            _ops_poll_thread.start()
    else:
        logger.info(
            "ops_poll_not_started enabled=%s has_token=%s",
            TELEGRAM_OPS_POLL_ENABLED,
            bool(TELEGRAM_BOT_TOKEN),
        )
    try:
        yield
    finally:
        _ops_poll_stop.set()
        thread = _ops_poll_thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        release_ops_poll_lock(_ops_poll_lock_fh)
        _ops_poll_lock_fh = None


app = FastAPI(lifespan=lifespan)


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


@app.post("/telegram/updates")
async def telegram_updates(request: Request):
    """Optional Bot API webhook path for /check and /test (alternative to getUpdates poll)."""
    update = await request.json()
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="invalid update")
    result = process_telegram_update(update, state=runtime_state)
    return {"ok": True, "result": result}


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
