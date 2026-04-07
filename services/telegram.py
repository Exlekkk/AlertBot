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
    "X_BREAKOUT_LONG": "异动放量上破预警",
    "X_BREAKOUT_SHORT": "异动放量下破预警",
}

MARKET_LABELS = {
    "A_LONG": "盘口主升推进",
    "A_SHORT": "盘口主跌推进",
    "B_PULLBACK_LONG": "盘口修复承接",
    "B_PULLBACK_SHORT": "盘口修复承压",
    "C_LEFT_LONG": "盘口早期试多",
    "C_LEFT_SHORT": "盘口早期试压",
    "X_BREAKOUT_LONG": "盘口起涨上破",
    "X_BREAKOUT_SHORT": "盘口起跌下破",
}

DEFAULT_START_WINDOWS = {
    1: (5, 30),
    2: (15, 120),
    3: (60, 360),
    4: (5, 120),
}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def action_label(signal: str) -> str:
    return ACTION_LABELS.get(signal, signal)


def market_label(signal: str, abnormal_type: str | None = None) -> str:
    if signal.startswith("X_") and abnormal_type:
        return abnormal_type
    return MARKET_LABELS.get(signal, signal)


def title_prefix(priority: int) -> str:
    return "🧨" if priority == 4 else "🚨"


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
    legacy_text: str | None = None,
) -> str:
    if legacy_text:
        return legacy_text
    start_min, end_min = _get_window_minutes(priority, eta_min_minutes, eta_max_minutes)
    start_text = _format_minutes_compact(start_min)
    end_text = _format_minutes_compact(end_min)
    return f"{start_text} - {end_text}"


def _stage_text(signal: str, status: str, trigger_state: str | None = None) -> str:
    trigger_state = trigger_state or ""

    if signal.startswith("A_"):
        if trigger_state.startswith("confirm_"):
            return "确认"
        return "关注"

    if signal.startswith("B_"):
        if trigger_state.startswith("confirm_"):
            return "确认"
        if trigger_state.startswith("repairing_"):
            return "修复"
        return "关注"

    if signal.startswith("C_"):
        if trigger_state.startswith("probing_"):
            return "早期"
        return "观察"

    if signal.startswith("X_"):
        return "异动"

    if status == "active":
        return "确认"
    if status == "early":
        return "早期"
    return "观察"


def build_status_text(signal: str, status: str) -> str:
    if signal == "A_LONG":
        return "已满足突破确认，等待顺势执行"
    if signal == "A_SHORT":
        return "已满足跌破确认，等待顺势执行"
    if signal == "B_PULLBACK_LONG":
        return "回踩条件满足，等待延续确认"
    if signal == "B_PULLBACK_SHORT":
        return "反弹条件满足，等待延续确认"
    if signal in ("C_LEFT_LONG", "C_LEFT_SHORT"):
        return "前提初步满足，处于早期观察阶段"
    if signal in ("X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"):
        return "异动已触发，进入特别关注阶段"
    if status == "active":
        return "条件已满足，等待执行"
    if status == "early":
        return "前提初步满足，处于观察阶段"
    return status


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
    return f"{low:.2f} - {high:.2f}"


def _pick_key_level(signal: str, low: float, high: float, trigger_level: float | None) -> float:
    if trigger_level is not None:
        return float(trigger_level)
    if signal in {"A_SHORT", "B_PULLBACK_LONG", "C_LEFT_LONG", "X_BREAKOUT_LONG"}:
        return low
    return high


def _zone_field_name(signal: str) -> str:
    if signal.startswith("A_"):
        return "区间"
    if signal == "B_PULLBACK_LONG":
        return "承接区"
    if signal == "B_PULLBACK_SHORT":
        return "反抽区"
    if signal.startswith("C_"):
        return "关注区"
    return "观察区"


def _watch_field_name(signal: str) -> str:
    if signal == "X_BREAKOUT_LONG":
        return "回踩观察区"
    if signal == "X_BREAKOUT_SHORT":
        return "反抽观察区"
    return _zone_field_name(signal)


def format_engine_message(
    signal: str,
    symbol: str,
    timeframe: str,
    priority: int,
    price: float,
    trend_1h: str,
    status: str,
    entry_zone_low: float | None = None,
    entry_zone_high: float | None = None,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
    trigger_level: float | None = None,
    burst_level: float | None = None,
    abnormal_type: str | None = None,
    start_window_text_value: str | None = None,
    start_window_text: str | None = None,
    confidence: int | float | None = None,
    trigger_state: str | None = None,
    **_: object,
) -> str:
    signal_type = type_label(priority)
    prefix = title_prefix(priority)
    action_text = action_label(signal)
    market_text = market_label(signal, abnormal_type=abnormal_type)
    stage_text = _stage_text(signal, status, trigger_state)
    status_text = build_status_text(signal, status)
    observe_text = build_observe_window_text(
        priority,
        eta_min_minutes,
        eta_max_minutes,
        legacy_text=start_window_text_value or start_window_text,
    )

    low, high = _normalized_zone(entry_zone_low, entry_zone_high, price)
    zone_value = f"{low:.2f} - {high:.2f}"
    key_level = _pick_key_level(signal, low, high, trigger_level)

    header = f"{prefix} {'异动预警' if priority == 4 else '交易提示'}｜{signal_type}｜{symbol}"
    background = f"背景：{action_text}｜{market_text}｜阶段{stage_text}"

    if priority == 4 and signal in {"X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"}:
        watch_field = _watch_field_name(signal)
        return (
            f"{header}\n"
            f"{background}\n"
            f"关键位：{key_level:.2f}\n"
            f"{watch_field}：{zone_value}\n"
            f"观察：{observe_text}\n"
            f"状态：{status_text}"
        )

    zone_field = _zone_field_name(signal)
    return (
        f"{header}\n"
        f"{background}\n"
        f"{zone_field}：{zone_value}\n"
        f"关键位：{key_level:.2f}\n"
        f"观察：{observe_text}\n"
        f"状态：{status_text}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    response = requests.post(url, json=payload, timeout=20)
    return response.text
