import requests


class TelegramSendError(RuntimeError):
    """Raised when Telegram does not confirm message delivery."""


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


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def action_label(signal: str) -> str:
    return ACTION_LABELS.get(signal, signal)


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


def _dynamic_window_minutes(
    signal_name: str,
    priority: int,
    trigger_state: str | None = None,
    status: str | None = None,
    abnormal_type: str | None = None,
) -> tuple[int, int]:
    trigger_state = trigger_state or ""
    status = status or "active"
    abnormal_type = abnormal_type or ""

    if signal_name.startswith("A_"):
        if trigger_state.startswith("confirm_"):
            return 15, 135
        if status == "early":
            return 20, 120
        return 20, 135

    if signal_name.startswith("B_"):
        if trigger_state.startswith("confirm_"):
            return 25, 165
        if trigger_state.startswith("repairing_"):
            return 25, 165
        return 30, 180

    if signal_name.startswith("C_"):
        if trigger_state.startswith("probing_"):
            return 25, 165
        return 30, 180

    if signal_name.startswith("X_"):
        if "扫流动性" in abnormal_type:
            return 10, 60
        if "上破" in abnormal_type or "下破" in abnormal_type:
            return 5, 45
        return 10, 75

    if priority == 1:
        return 15, 135
    if priority == 2:
        return 25, 165
    if priority == 3:
        return 25, 165
    return 5, 120


def build_observe_window_text(signal: dict) -> str:
    legacy_text = signal.get("start_window_text_value") or signal.get("start_window_text")
    if legacy_text:
        return str(legacy_text)

    eta_min = signal.get("eta_min_minutes")
    eta_max = signal.get("eta_max_minutes")
    if eta_min is not None and eta_max is not None:
        start_min = max(0, int(eta_min))
        end_min = max(start_min, int(eta_max))
    else:
        start_min, end_min = _dynamic_window_minutes(
            signal_name=str(signal.get("signal", "")),
            priority=int(signal.get("priority", 1) or 1),
            trigger_state=str(signal.get("trigger_state") or signal.get("trigger_15m_state") or ""),
            status=str(signal.get("status", "active")),
            abnormal_type=str(signal.get("abnormal_type", "")),
        )

    return f"{_format_minutes_compact(start_min)} - {_format_minutes_compact(end_min)}"


def build_status_text(signal_name: str, status: str) -> str:
    if signal_name == "A_LONG":
        return "已满足突破确认，等待顺势执行"
    if signal_name == "A_SHORT":
        return "已满足跌破确认，等待顺势执行"
    if signal_name == "B_PULLBACK_LONG":
        return "回踩条件满足，等待延续确认"
    if signal_name == "B_PULLBACK_SHORT":
        return "反弹条件满足，等待延续确认"
    if signal_name in ("C_LEFT_LONG", "C_LEFT_SHORT"):
        return "前提初步满足，处于早期观察阶段"
    if signal_name in ("X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"):
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


def _zone_field_name(signal_name: str) -> str:
    if signal_name.startswith("A_"):
        return "区间"
    if signal_name == "B_PULLBACK_LONG":
        return "承接区"
    if signal_name == "B_PULLBACK_SHORT":
        return "反抽区"
    if signal_name.startswith("C_"):
        return "关注区"
    return "观察区"


def _watch_field_name(signal_name: str) -> str:
    if signal_name == "X_BREAKOUT_LONG":
        return "回踩观察区"
    if signal_name == "X_BREAKOUT_SHORT":
        return "反抽观察区"
    return _zone_field_name(signal_name)


def _pick_key_level(signal_name: str, low: float, high: float, trigger_level: float | None) -> float:
    if trigger_level is not None:
        return float(trigger_level)

    if signal_name == "A_LONG":
        return high
    if signal_name == "A_SHORT":
        return low
    if signal_name == "B_PULLBACK_LONG":
        return low
    if signal_name == "B_PULLBACK_SHORT":
        return high
    if signal_name == "C_LEFT_LONG":
        return low
    if signal_name == "C_LEFT_SHORT":
        return high
    if signal_name == "X_BREAKOUT_LONG":
        return high
    if signal_name == "X_BREAKOUT_SHORT":
        return low

    return high


def _start_line(signal_name: str, low: float, high: float, key_level: float) -> str:
    if signal_name == "A_LONG":
        return f"自 {low:.2f} 一带启动上拉，上看 {high:.2f} 延续确认"
    if signal_name == "A_SHORT":
        return f"自 {high:.2f} 一带准备下杀，下看 {low:.2f} 延续确认"

    if signal_name == "B_PULLBACK_LONG":
        return f"自 {high:.2f} 开始回踩，下探 {low:.2f} 一带承接"
    if signal_name == "B_PULLBACK_SHORT":
        return f"自 {low:.2f} 开始反抽，上看 {high:.2f} 一带承压"

    if signal_name == "C_LEFT_LONG":
        return f"自 {high:.2f} 区域开始关注，下方 {key_level:.2f} 为首个承接参考"
    if signal_name == "C_LEFT_SHORT":
        return f"自 {low:.2f} 区域开始关注，上方 {key_level:.2f} 为首个压力参考"

    if signal_name == "X_BREAKOUT_LONG":
        return f"自 {low:.2f} 一带出现异动，上方 {key_level:.2f} 为首个突破参考"
    if signal_name == "X_BREAKOUT_SHORT":
        return f"自 {high:.2f} 一带出现异动，下方 {key_level:.2f} 为首个跌破参考"

    return f"自 {low:.2f} - {high:.2f} 区域开始关注"


def format_engine_message(signal: dict) -> str:
    signal_name = str(signal.get("signal", ""))
    symbol = str(signal.get("symbol", "BTCUSDT"))
    priority = int(signal.get("priority", 1) or 1)
    price = float(signal.get("price", 0.0) or 0.0)
    status = str(signal.get("status", "active"))

    signal_type = type_label(priority)
    prefix = title_prefix(priority)
    action_text = action_label(signal_name)
    status_text = build_status_text(signal_name, status)
    observe_text = build_observe_window_text(signal)

    entry_zone_low = signal.get("entry_zone_low", signal.get("zone_low"))
    entry_zone_high = signal.get("entry_zone_high", signal.get("zone_high"))
    low, high = _normalized_zone(entry_zone_low, entry_zone_high, price)

    trigger_level = signal.get("trigger_level")
    key_level = _pick_key_level(signal_name, low, high, trigger_level)

    zone_field = _watch_field_name(signal_name) if priority == 4 else _zone_field_name(signal_name)
    zone_value = f"{low:.2f} - {high:.2f}"
    start_text = _start_line(signal_name, low, high, key_level)

    header = f"{prefix} {'异动预警' if priority == 4 else '交易提示'}｜{signal_type}｜{symbol}"
    background = f"背景：{action_text}"

    return (
        f"{header}\n"
        f"{background}\n"
        f"起点：{start_text}\n"
        f"{zone_field}：{zone_value}\n"
        f"关键位：{key_level:.2f}\n"
        f"观察：{observe_text}\n"
        f"状态：{status_text}"
    )


def format_webhook_message(signal: str, symbol: str, timeframe: str, direction: str = "unknown") -> str:
    direction_text = direction if direction and direction != "unknown" else "未注明"
    return (
        f"📩 外部信号 | {symbol}\n"
        f"信号：{signal}\n"
        f"周期：{timeframe}\n"
        f"方向：{direction_text}"
    )


def send_telegram_message(token: str, chat_id: str, text: str) -> dict:
    """Send a Telegram message and require Telegram's ok=true confirmation.

    The scanner should only enter cooldown after this function returns
    successfully. HTTP errors, non-JSON responses, and Telegram {"ok": false}
    responses raise TelegramSendError.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=20)
    except requests.RequestException as exc:
        raise TelegramSendError(f"telegram_request_failed: {exc}") from exc

    if response.status_code >= 400:
        raise TelegramSendError(f"telegram_http_error status={response.status_code} body={response.text[:500]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise TelegramSendError(f"telegram_invalid_json body={response.text[:500]}") from exc

    if not data.get("ok"):
        description = data.get("description") or data
        raise TelegramSendError(f"telegram_api_error: {description}")

    return data
