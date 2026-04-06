import requests


TYPE_LABELS = {
    1: "A类",
    2: "B类",
    3: "C类",
    4: "X类",
}

ACTION_LABELS = {
    "A_LONG": "顺势做多机会",
    "A_SHORT": "顺势做空机会",
    "B_PULLBACK_LONG": "回踩后做多机会",
    "B_PULLBACK_SHORT": "反弹后做空机会",
    "C_LEFT_LONG": "左侧预警做多机会",
    "C_LEFT_SHORT": "左侧预警做空机会",
    "X_BREAKOUT_LONG": "异动上破观察",
    "X_BREAKOUT_SHORT": "异动下破观察",
}

MARKET_LABELS = {
    "A_LONG": "盘口多头推进",
    "A_SHORT": "盘口空头推进",
    "B_PULLBACK_LONG": "盘口修复承接",
    "B_PULLBACK_SHORT": "盘口修复承压",
    "C_LEFT_LONG": "盘口早期试多",
    "C_LEFT_SHORT": "盘口早期试空",
    "X_BREAKOUT_LONG": "盘口异动上破",
    "X_BREAKOUT_SHORT": "盘口异动下破",
}

DEFAULT_CONFIDENCE = {
    "A_LONG": 82,
    "A_SHORT": 82,
    "B_PULLBACK_LONG": 70,
    "B_PULLBACK_SHORT": 70,
    "C_LEFT_LONG": 60,
    "C_LEFT_SHORT": 60,
    "X_BREAKOUT_LONG": 56,
    "X_BREAKOUT_SHORT": 56,
}

DEFAULT_START_WINDOWS = {
    1: (5, 30),
    2: (15, 120),
    3: (60, 360),
    4: (15, 95),
}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def action_label(signal: str) -> str:
    return ACTION_LABELS.get(signal, signal)


def market_label(signal: str, abnormal_type: str | None = None) -> str:
    if signal.startswith("X_") and abnormal_type:
        return abnormal_type
    return MARKET_LABELS.get(signal, signal)


def _format_minutes_compact(minutes: int | None) -> str:
    if minutes is None:
        return ""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}m"
    hours, remain = divmod(minutes, 60)
    if remain == 0:
        return f"{hours}h"
    return f"{hours}h{remain}m"


def _get_window_minutes(
    priority: int,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> tuple[int, int]:
    default_min, default_max = DEFAULT_START_WINDOWS.get(priority, (15, 45))
    start_min = int(eta_min_minutes) if eta_min_minutes is not None else default_min
    end_min = int(eta_max_minutes) if eta_max_minutes is not None else default_max
    start_min = max(0, start_min)
    end_min = max(start_min, end_min)
    return start_min, end_min


def build_observe_window_text(
    priority: int,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> str:
    start_min, end_min = _get_window_minutes(priority, eta_min_minutes, eta_max_minutes)
    return f"{_format_minutes_compact(start_min)}-{_format_minutes_compact(end_min)}"


def build_status_text(signal: str, status: str) -> str:
    if signal == "A_LONG":
        return "趋势条件满足，等待延续确认"
    if signal == "A_SHORT":
        return "趋势条件满足，等待延续确认"
    if signal == "B_PULLBACK_LONG":
        return "回踩条件满足，等待延续确认"
    if signal == "B_PULLBACK_SHORT":
        return "反弹条件满足，等待延续确认"
    if signal in ("C_LEFT_LONG", "C_LEFT_SHORT"):
        return "早期条件出现，先观察"
    if signal in ("X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"):
        return "异动出现，先观察"
    if status == "active":
        return "条件满足，等待执行"
    if status == "early":
        return "条件满足，等待延续确认"
    return "保持观察"


def _normalized_zone(
    entry_zone_low: float | None,
    entry_zone_high: float | None,
    price: float,
) -> tuple[float, float]:
    if entry_zone_low is None or entry_zone_high is None:
        pad = max(abs(float(price)) * 0.0012, 12.0)
        low = float(price) - pad * 0.5
        high = float(price) + pad * 0.5
    else:
        low = min(float(entry_zone_low), float(entry_zone_high))
        high = max(float(entry_zone_low), float(entry_zone_high))
        if abs(high - low) < max(abs(float(price)) * 0.0008, 8.0):
            pad = max(abs(float(price)) * 0.0012, 12.0)
            low -= pad * 0.5
            high += pad * 0.5
    return low, high


def zone_text(entry_zone_low: float | None, entry_zone_high: float | None, price: float) -> str:
    low, high = _normalized_zone(entry_zone_low, entry_zone_high, price)
    return f"{low:.2f}-{high:.2f}"


def _pick_key_level(
    signal: str,
    low: float,
    high: float,
    trigger_level: float | None,
    price: float,
) -> float:
    if trigger_level is not None:
        return float(trigger_level)
    if signal.endswith("_LONG"):
        return max(price, high)
    return min(price, low)


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _display_confidence(signal: dict) -> int:
    signal_name = str(signal.get("signal", ""))
    base = _safe_int(signal.get("confidence"), DEFAULT_CONFIDENCE.get(signal_name, 66))
    if base <= 0:
        base = DEFAULT_CONFIDENCE.get(signal_name, 66)

    budget = str(signal.get("tai_budget_mode", "normal"))
    trigger = str(signal.get("trigger_15m_state", ""))
    status = str(signal.get("status", "active"))

    # 先按预算降档
    if budget == "restricted":
        base -= 8
    elif budget == "frozen":
        base -= 14

    # 再按触发质量降档
    if trigger.startswith("repairing"):
        base -= 3
    elif trigger.startswith("probing") or trigger == "idle":
        base -= 7

    # early 状态不能太高
    if status == "early":
        base -= 4

    # 各类信号分别限制上限下限，避免 A 乱上 89，也避免 X 变 0
    if signal_name.startswith("A_"):
        base = max(66, min(86, base))
    elif signal_name.startswith("B_"):
        base = max(60, min(76, base))
    elif signal_name.startswith("C_"):
        base = max(52, min(66, base))
    elif signal_name.startswith("X_"):
        base = max(48, min(62, base))
    else:
        base = max(50, min(80, base))

    return base


def format_engine_message(signal: dict) -> str:
    signal_name = signal.get("signal", "")
    symbol = signal.get("symbol", "BTCUSDT")
    priority = int(signal.get("priority", 1) or 1)
    price = float(signal.get("price", 0.0) or 0.0)
    confidence = _display_confidence(signal)

    low, high = _normalized_zone(
        signal.get("entry_zone_low", signal.get("zone_low")),
        signal.get("entry_zone_high", signal.get("zone_high")),
        price,
    )
    key_level = _pick_key_level(signal_name, low, high, signal.get("trigger_level"), price)

    title = "异动观察" if signal_name.startswith("X_") else "交易提示"
    background = action_label(signal_name)
    market = market_label(signal_name, signal.get("abnormal_type"))
    observe = build_observe_window_text(
        priority,
        signal.get("eta_min_minutes"),
        signal.get("eta_max_minutes"),
    )
    status_text = build_status_text(signal_name, signal.get("status", "active"))

    lines = [
        f"🚨 {title} | {type_label(priority)} | {symbol}",
        f"背景：{background} | {market} | 置信度{confidence}",
        f"承接区：{zone_text(low, high, price)}",
        f"关键位：{key_level:.2f}",
        f"观察：{observe}",
        f"状态：{status_text}",
    ]

    return "\n".join(lines)


def format_webhook_message(signal: str, symbol: str, timeframe: str, direction: str = "unknown") -> str:
    direction_text = direction if direction and direction != "unknown" else "未注明"
    return (
        f"📩 外部信号 | {symbol}\n"
        f"信号：{signal}\n"
        f"周期：{timeframe}\n"
        f"方向：{direction_text}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    return response.text
