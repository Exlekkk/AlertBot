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
    "C_LEFT_LONG": "左侧提前预警做多机会",
    "C_LEFT_SHORT": "左侧提前预警做空机会",
    "X_BREAKOUT_LONG": "异动放量上破预警",
    "X_BREAKOUT_SHORT": "异动放量下破预警",
}

TREND_LABELS = {
    "bull": "偏多（强）",
    "lean_bull": "偏多（弱）",
    "neutral": "中性",
    "lean_bear": "偏空（弱）",
    "bear": "偏空（强）",
}

DEFAULT_START_WINDOWS = {
    1: (5, 30),
    2: (15, 120),
    3: (60, 360),
    4: (5, 90),
}

TIMEOUT_TEXT = {
    1: "若超时未确认，则信号转弱",
    2: "若超时未进入观察区，则预期下调",
    3: "若超时未确认，则继续观察",
    4: "若超时未确认，则异动降温",
}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def action_label(signal: str) -> str:
    return ACTION_LABELS.get(signal, signal)


def trend_label(trend_1h: str) -> str:
    return TREND_LABELS.get(trend_1h, trend_1h)


def title_prefix(priority: int) -> str:
    return "🚨"


def _format_minutes(minutes: int | None) -> str:
    if minutes is None:
        return ""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}分钟"
    hours, remain = divmod(minutes, 60)
    if remain == 0:
        return f"{hours}小时"
    return f"{hours}小时{remain}分钟"


def start_window_text(priority: int, eta_min_minutes: int | None = None, eta_max_minutes: int | None = None) -> str:
    default_min, default_max = DEFAULT_START_WINDOWS.get(priority, (15, 45))
    start_min = eta_min_minutes if eta_min_minutes is not None else default_min
    end_min = eta_max_minutes if eta_max_minutes is not None else default_max
    return f"此条播报发出后 {_format_minutes(start_min)}—{_format_minutes(end_min)}内"


def timeout_text(priority: int) -> str:
    return TIMEOUT_TEXT.get(priority, "若超时未确认，则参考价值下降")


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


def zone_text(entry_zone_low: float | None, entry_zone_high: float | None, price: float) -> str:
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
    return f"{low:.2f} - {high:.2f}"


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
    abnormal_type: str | None = None,
    event_summary: str | None = None,
    tech_score: int | None = None,
    news_score: int | None = None,
    x_score: int | None = None,
) -> str:
    signal_type = type_label(priority)
    action_text = action_label(signal)
    status_text = build_status_text(signal, status)
    trend_text = trend_label(trend_1h)
    prefix = title_prefix(priority)
    entry_zone_text = zone_text(entry_zone_low, entry_zone_high, price)
    start_window = start_window_text(priority, eta_min_minutes, eta_max_minutes)
    timeout_hint = timeout_text(priority)

    if signal in ("X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"):
        trigger_label = "关键上破位" if signal == "X_BREAKOUT_LONG" else "关键下破位"
        watch_label = "回踩观察区" if signal == "X_BREAKOUT_LONG" else "反抽观察区"
        type_text = abnormal_type or ("放量上破 / 技术异动" if signal == "X_BREAKOUT_LONG" else "放量下破 / 技术异动")
        event_text = event_summary or "none｜中性｜强度0｜标签: none"
        score_text = f"技术{int(tech_score or 0)} / 消息{int(news_score or 0)} / 综合{int(x_score or 0)}"
        trigger_text = f"{float(trigger_level):.2f}" if trigger_level is not None else f"{float(price):.2f}"
        return (
            f"{prefix} 异动预警｜{signal_type}\n"
            f"操作建议：{action_text}\n"
            f"标的：{symbol}\n"
            f"异动类型：{type_text}\n"
            f"事件偏置：{event_text}\n"
            f"异动评分：{score_text}\n"
            f"{trigger_label}：{trigger_text}\n"
            f"{watch_label}：{entry_zone_text}\n"
            f"总体趋势方向：{trend_text}\n"
            f"预计启动时段：{start_window}\n"
            f"时效说明：{timeout_hint}\n"
            f"状态：{status_text}"
        )

    return (
        f"{prefix} 交易提示｜{signal_type}\n"
        f"操作建议：{action_text}\n"
        f"标的：{symbol}\n"
        f"参考价位区间：{entry_zone_text}\n"
        f"总体趋势方向：{trend_text}\n"
        f"预计启动时段：{start_window}\n"
        f"时效说明：{timeout_hint}\n"
        f"状态：{status_text}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=20)
    return response.text
