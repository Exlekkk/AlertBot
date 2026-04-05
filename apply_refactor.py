from pathlib import Path

FILES = {
    "config.py": '''import os
from dotenv import load_dotenv

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
''',

    "app.py": '''from __future__ import annotations

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
''',

    "engine/market_data.py": '''from __future__ import annotations

import requests

from config import (
    BINANCE_FUTURES_KLINES_URL,
    BINANCE_SPOT_KLINES_URL,
    KLINE_LIMIT,
    MARKET_SOURCE,
    REQUEST_TIMEOUT_SECONDS,
)


class BinanceMarketDataClient:
    def __init__(self, market_source: str | None = None):
        source = (market_source or MARKET_SOURCE or "binance_futures").lower()
        self.market_source = source
        self.base_url = BINANCE_FUTURES_KLINES_URL if source == "binance_futures" else BINANCE_SPOT_KLINES_URL

    def get_klines(self, symbol: str, interval: str, limit: int = KLINE_LIMIT) -> list[dict]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(self.base_url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        rows = response.json()
        klines = []
        for r in rows:
            klines.append(
                {
                    "open_time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                    "close_time": int(r[6]),
                }
            )
        return klines
''',

    "engine/cooldown.py": '''from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import SMCT_SIGNAL_STATE_FILE


class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.001,
        state_file: str | None = None,
    ):
        self.price_change_threshold = price_change_threshold
        self.state_file = Path(state_file or SMCT_SIGNAL_STATE_FILE)
        self.last_sent: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.state_file.exists():
                self.last_sent = json.loads(self.state_file.read_text())
        except Exception:
            self.last_sent = {}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.last_sent, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def _rank(self, signal_name: str) -> int:
        if signal_name.startswith("A_"):
            return 3
        if signal_name.startswith("B_"):
            return 2
        if signal_name.startswith("C_"):
            return 1
        if signal_name.startswith("X_"):
            return 4
        return 0

    def _family_key(self, signal: dict[str, Any]) -> str:
        if signal["signal"].startswith("X_"):
            return f"X|{signal['symbol']}|{signal.get('timeframe','15m')}|{signal['signal']}|{signal.get('direction','na')}"
        if signal.get("phase_anchor"):
            return f"ABC|{signal['symbol']}|{signal.get('timeframe','15m')}|{signal.get('direction','na')}|{signal['phase_anchor']}"
        return f"ABC|{signal['symbol']}|{signal.get('timeframe','15m')}|{signal.get('direction','na')}"

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._family_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0))
        tiny_move = self._price_change_ratio(
            float(previous.get("price", 0.0)),
            float(signal.get("price", 0.0)),
        ) <= self.price_change_threshold

        if now - prev_sent_at >= cooldown_seconds:
            return True

        if signal.get("signature") and signal.get("signature") == previous.get("signature"):
            return False

        prev_rank = int(previous.get("phase_rank", self._rank(previous.get("signal", ""))))
        curr_rank = int(signal.get("phase_rank", self._rank(signal.get("signal", ""))))

        if curr_rank > prev_rank:
            return True

        if curr_rank <= prev_rank and tiny_move:
            return False

        return not tiny_move

    def mark_sent(self, signal: dict[str, Any]):
        key = self._family_key(signal)
        self.last_sent[key] = {
            "signal": signal["signal"],
            "status": signal.get("status", "active"),
            "price": signal.get("price", 0.0),
            "signature": signal.get("signature", ""),
            "cooldown_seconds": int(signal.get("cooldown_seconds", 1800) or 1800),
            "phase_rank": int(signal.get("phase_rank", self._rank(signal.get("signal", "")))),
            "phase_name": signal.get("phase_name", ""),
            "phase_context": signal.get("phase_context", ""),
            "phase_anchor": signal.get("phase_anchor", ""),
            "h1_tai_bias": signal.get("h1_tai_bias", "flat"),
            "h1_tai_slot": signal.get("h1_tai_slot", ""),
            "sent_at": time.time(),
        }
        self._save()
''',

    "engine/runtime_state.py": '''from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import HEARTBEAT_STALE_AFTER_SECONDS, SMCT_RUNTIME_STATE_FILE


class RuntimeStateStore:
    def __init__(self, state_file: str | None = None):
        self.state_file = Path(state_file or SMCT_RUNTIME_STATE_FILE)
        self.state: dict[str, Any] = {
            "last_scan_at": 0.0,
            "last_scan_ok": False,
            "last_scan_error": "",
            "last_symbol": "",
            "last_summary": {},
            "last_sent_signal": {},
            "last_webhook": {},
        }
        self._load()

    def _load(self) -> None:
        try:
            if self.state_file.exists():
                self.state.update(json.loads(self.state_file.read_text()))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def mark_scan(self, ok: bool, symbol: str, summary: dict[str, Any] | None = None, error: str = "") -> None:
        self.state["last_scan_at"] = time.time()
        self.state["last_scan_ok"] = bool(ok)
        self.state["last_scan_error"] = error
        self.state["last_symbol"] = symbol
        self.state["last_summary"] = summary or {}
        self._save()

    def mark_sent_signal(self, signal: dict[str, Any]) -> None:
        self.state["last_sent_signal"] = {
            "signal": signal.get("signal"),
            "symbol": signal.get("symbol"),
            "direction": signal.get("direction"),
            "price": signal.get("price"),
            "state_1h": signal.get("state_1h"),
            "trigger_15m_state": signal.get("trigger_15m_state"),
            "tai_budget_mode": signal.get("tai_budget_mode"),
            "sent_at": time.time(),
        }
        self._save()

    def mark_webhook_send(self, symbol: str, signal: str) -> None:
        self.state["last_webhook"] = {
            "symbol": symbol,
            "signal": signal,
            "status": "sent",
            "at": time.time(),
        }
        self._save()

    def mark_webhook_skip(self, symbol: str, signal: str, reason: str) -> None:
        self.state["last_webhook"] = {
            "symbol": symbol,
            "signal": signal,
            "status": "skipped",
            "reason": reason,
            "at": time.time(),
        }
        self._save()

    def get_snapshot(self) -> dict[str, Any]:
        return dict(self.state)

    def build_health_payload(self) -> dict[str, Any]:
        last_scan_at = float(self.state.get("last_scan_at", 0.0) or 0.0)
        age = max(0, int(time.time() - last_scan_at)) if last_scan_at else None
        stale = age is None or age > HEARTBEAT_STALE_AFTER_SECONDS
        return {
            "ok": bool(self.state.get("last_scan_ok")) and not stale,
            "stale": stale,
            "seconds_since_last_scan": age,
            "last_scan_error": self.state.get("last_scan_error", ""),
            "last_symbol": self.state.get("last_symbol", ""),
            "last_summary": self.state.get("last_summary", {}),
            "last_sent_signal": self.state.get("last_sent_signal", {}),
            "last_webhook": self.state.get("last_webhook", {}),
        }
''',

    "services/telegram.py": '''from __future__ import annotations

import requests


TYPE_LABELS = {1: "A类", 2: "B类", 3: "C类", 4: "X类"}

ACTION_LABELS = {
    "A_LONG": "顺势做多候选",
    "A_SHORT": "顺势做空候选",
    "B_PULLBACK_LONG": "回踩承接候选",
    "B_PULLBACK_SHORT": "反弹承压候选",
    "C_LEFT_LONG": "左侧试多观察",
    "C_LEFT_SHORT": "左侧试空观察",
    "X_BREAKOUT_LONG": "异动上破观察",
    "X_BREAKOUT_SHORT": "异动下破观察",
}

STATE_LABELS = {
    "trend_drive_long": "趋势推动偏多",
    "trend_drive_short": "趋势推动偏空",
    "repair_long": "修复后延续偏多",
    "repair_short": "修复后延续偏空",
    "probe_long": "早期试多",
    "probe_short": "早期试空",
    "range_neutral": "震荡/中性",
}

TRIGGER_LABELS = {
    "confirm_long": "15m触发已确认",
    "confirm_short": "15m触发已确认",
    "repairing_long": "15m处于修复转强",
    "repairing_short": "15m处于修复转弱",
    "probing_long": "15m早期试多",
    "probing_short": "15m早期试空",
    "idle": "15m暂无有效触发",
}

BUDGET_LABELS = {
    "expanded": "热度放行",
    "normal": "热度正常",
    "restricted": "热度受限",
    "frozen": "热度冻结",
}

DEFAULT_START_WINDOWS = {1: (5, 30), 2: (15, 120), 3: (60, 360), 4: (5, 120)}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def _format_minutes_compact(minutes: int | None) -> str:
    if minutes is None:
        return ""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}m"
    hours, remain = divmod(minutes, 60)
    return f"{hours}h" if remain == 0 else f"{hours}h{remain}m"


def _observe_window(priority: int, eta_min_minutes: int | None = None, eta_max_minutes: int | None = None) -> str:
    start_min, end_min = DEFAULT_START_WINDOWS.get(priority, (15, 45))
    if eta_min_minutes is not None:
        start_min = int(eta_min_minutes)
    if eta_max_minutes is not None:
        end_min = int(eta_max_minutes)
    end_min = max(start_min, end_min)
    return f"{_format_minutes_compact(start_min)} - {_format_minutes_compact(end_min)}"


def _normalized_zone(low: float | None, high: float | None, price: float) -> tuple[float, float]:
    if low is None or high is None:
        pad = max(abs(float(price)) * 0.0012, 12.0)
        low = float(price) - pad * 0.5
        high = float(price) + pad * 0.5
    low, high = min(float(low), float(high)), max(float(low), float(high))
    return low, high


def _confidence_text(signal: dict) -> str:
    value = int(signal.get("confidence", 0) or 0)
    if value >= 85:
        band = "高"
    elif value >= 70:
        band = "中高"
    elif value >= 58:
        band = "中"
    else:
        band = "观察"
    return f"{band}({value})"


def _basis_text(structure_basis: list[str] | None) -> str:
    if not structure_basis:
        return "结构依据不足，更多偏观察"
    mapping = {
        "smc_bos_up": "SMC上破结构",
        "smc_bos_down": "SMC下破结构",
        "ict_mss_up": "ICT偏多MSS",
        "ict_mss_down": "ICT偏空MSS",
        "support_zone": "位于支撑/承接区",
        "resistance_zone": "位于阻力/承压区",
        "trigger_repair": "15m修复触发出现",
        "ema_support": "EMA背景未明显对冲",
        "ema_resistance": "EMA背景未明显对冲",
        "early_warning": "出现早期预警信号",
        "probing_trigger": "15m已有试探动作",
    }
    return "、".join(mapping.get(x, x) for x in structure_basis[:4])


def _status_line(signal: dict) -> str:
    state_1h = STATE_LABELS.get(signal.get("state_1h", ""), signal.get("state_1h", "未知状态"))
    trigger = TRIGGER_LABELS.get(signal.get("trigger_15m_state", ""), signal.get("trigger_15m_state", "未知触发"))
    budget = BUDGET_LABELS.get(signal.get("tai_budget_mode", "normal"), signal.get("tai_budget_mode", "normal"))
    return f"1h状态：{state_1h}｜15m触发：{trigger}｜TAI：{budget}"


def format_engine_message(signal: dict) -> str:
    name = signal.get("signal", "")
    priority = int(signal.get("priority", 1) or 1)
    symbol = signal.get("symbol", "BTCUSDT")
    direction = signal.get("direction", "")
    price = float(signal.get("price", 0.0) or 0.0)
    low, high = _normalized_zone(signal.get("entry_zone_low"), signal.get("entry_zone_high"), price)
    key_level = float(signal.get("trigger_level") or signal.get("breakout_level") or (low if direction == "long" else high))
    title = "🧨 异动观察" if name.startswith("X_") else "🚨 读盘提示"
    action = ACTION_LABELS.get(name, name)
    confidence = _confidence_text(signal)
    basis = _basis_text(signal.get("structure_basis"))
    observe = _observe_window(priority, signal.get("eta_min_minutes"), signal.get("eta_max_minutes"))

    lines = [
        f"{title}｜{type_label(priority)}｜{symbol}",
        f"方向：{action}｜{confidence}",
        _status_line(signal),
        f"当前价：{price:.2f}",
        f"观察区：{low:.2f} - {high:.2f}",
        f"关键位：{key_level:.2f}",
        f"依据：{basis}",
        f"观察窗：{observe}",
    ]

    abnormal_type = signal.get("abnormal_type")
    if abnormal_type:
        lines.append(f"异动类型：{abnormal_type}")

    if signal.get("freeze_mode"):
        lines.append("备注：当前热度冻结，除明显异动外不建议高频追单")
    elif signal.get("heat_restricted"):
        lines.append("备注：当前热度受限，优先等待更干净的结构确认")

    return "\\n".join(lines)


def format_webhook_message(signal: str, symbol: str, timeframe: str, direction: str = "unknown") -> str:
    direction_text = direction if direction and direction != "unknown" else "外部方向未注明"
    return (
        f"📩 外部Webhook信号｜{symbol}\\n"
        f"信号：{signal}\\n"
        f"周期：{timeframe}\\n"
        f"方向：{direction_text}\\n"
        f"说明：该消息来自外部触发源，未经过SMCT内部多周期分层解释。"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    return response.text
''',
}


def main():
    root = Path.cwd()
    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"wrote {rel_path}")
    print("done")


if __name__ == "__main__":
    main()
