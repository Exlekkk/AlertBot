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
    "A_LONG": "盘口主升推进",
    "A_SHORT": "盘口主跌推进",
    "B_PULLBACK_LONG": "盘口修复承接",
    "B_PULLBACK_SHORT": "盘口修复承压",
    "C_LEFT_LONG": "盘口早期试多",
    "C_LEFT_SHORT": "盘口早期试压",
    "X_BREAKOUT_LONG": "盘口异动上破",
    "X_BREAKOUT_SHORT": "盘口异动下破",
}

DEFAULT_CONFIDENCE = {
    "A_LONG": 88,
    "A_SHORT": 88,
    "B_PULLBACK_LONG": 72,
    "B_PULLBACK_SHORT": 72,
    "C_LEFT_LONG": 64,
    "C_LEFT_SHORT": 64,
    "X_BREAKOUT_LONG": 60,
    "X_BREAKOUT_SHORT": 60,
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
    start_text = _format_minutes_compact(start_min)
    end_text = _format_minutes_compact(end_min)
    return f"{start_text} - {end_text}"


def build_status_text(signal: str, status: str) -> str:
    if signal == "A_LONG":
        return "突破条件满足，等待顺势确认"
    if signal == "A_SHORT":
        return "跌破条件满足，等待顺势确认"
    if signal == "B_PULLBACK_LONG":
        return "回踩条件满足，等待延续确认"
    if signal == "B_PULLBACK_SHORT":
        return "反弹条件满足，等待延续确认"
    if signal in ("C_LEFT_LONG", "C_LEFT_SHORT"):
        return "早期条件出现，先观察"
    if signal in ("X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"):
        return "异动出现，观察是否延续"
    if status == "active":
        return "条件满足，等待执行"
    if status == "early":
        return "早期信号，先观察"
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


def _confidence(signal: dict) -> int:
    value = signal.get("confidence")
    if value is None:
        return DEFAULT_CONFIDENCE.get(signal.get("signal", ""), 68)
    try:
        return int(value)
    except Exception:
        return DEFAULT_CONFIDENCE.get(signal.get("signal", ""), 68)


def _state_text(signal: dict) -> str:
    state_1h = signal.get("state_1h", "")
    trigger = signal.get("trigger_15m_state", "")
    budget = signal.get("tai_budget_mode", "")

    state_map = {
        "trend_drive_long": "趋势推动偏多",
        "trend_drive_short": "趋势推动偏空",
        "repair_long": "修复后延续偏多",
        "repair_short": "修复后延续偏空",
        "probe_long": "早期试多",
        "probe_short": "早期试空",
        "range_neutral": "震荡中性",
    }
    trigger_map = {
        "confirm_long": "15m触发已确认",
        "confirm_short": "15m触发已确认",
        "repairing_long": "15m修复触发出现",
        "repairing_short": "15m修复触发出现",
        "probing_long": "15m早期试多",
        "probing_short": "15m早期试空",
        "idle": "15m触发未出现",
    }
    budget_map = {
        "expanded": "热度放行",
        "normal": "热度正常",
        "restricted": "热度受限",
        "frozen": "热度冻结",
    }

    state_text = state_map.get(state_1h, "未知状态")
    trigger_text = trigger_map.get(trigger, "未知触发")
    budget_text = budget_map.get(budget, "热度未知")
    return f"1h状态：{state_text} | 15m触发：{trigger_text} | TAI：{budget_text}"


def _basis_text(signal: dict) -> str:
    basis = signal.get("structure_basis") or []
    if not basis:
        return "结构依据不足"

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
        "early_warning": "出现早期预警",
        "probing_trigger": "15m已有试探动作",
    }
    return "，".join(mapping.get(x, x) for x in basis[:3])


def format_engine_message(signal: dict) -> str:
    signal_name = signal.get("signal", "")
    symbol = signal.get("symbol", "BTCUSDT")
    priority = int(signal.get("priority", 1) or 1)
    price = float(signal.get("price", 0.0) or 0.0)
    confidence = _confidence(signal)

    low, high = _normalized_zone(
        signal.get("entry_zone_low", signal.get("zone_low")),
        signal.get("entry_zone_high", signal.get("zone_high")),
        price,
    )
    key_level = _pick_key_level(
        signal_name,
        low,
        high,
        signal.get("trigger_level"),
        price,
    )

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
