import requests


TYPE_LABELS = {
    1: "A类",
    2: "B类",
    3: "C类",
}

ACTION_LABELS = {
    "A_LONG": "顺势做多机会",
    "A_SHORT": "顺势做空机会",
    "B_PULLBACK_LONG": "回踩后做多机会",
    "B_PULLBACK_SHORT": "反弹后做空机会",
    "C_LEFT_LONG": "左侧提前预警做多机会",
    "C_LEFT_SHORT": "左侧提前预警做空机会",
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
}

TIMEOUT_TEXT = {
    1: "若 1 小时内仍未走出确认动作，本轮信号大概率转弱",
    2: "若 2 小时内仍未出现延续确认，本轮反弹/回踩预期需下调",
    3: "若 6 小时内仍未完成关键确认，该预警继续以观察为主，实战优先级下降",
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
        return f"{minutes} 分钟"
    hours, remain = divmod(minutes, 60)
    if remain == 0:
        return f"{hours} 小时"
    return f"{hours} 小时 {remain} 分钟"



def start_window_text(
    priority: int,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> str:
    default_min, default_max = DEFAULT_START_WINDOWS.get(priority, (15, 45))
    start_min = eta_min_minutes if eta_min_minutes is not None else default_min
    end_min = eta_max_minutes if eta_max_minutes is not None else default_max

    start_text = _format_minutes(start_min)
    end_text = _format_minutes(end_min)
    return f"此条播报发出后 {start_text} - {end_text} 内"



def timeout_text(priority: int) -> str:
    return TIMEOUT_TEXT.get(priority, "若超出预期时段仍未确认，则本轮信号参考价值下降")



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
    start_window_text_override: str | None = None,
    start_window_text: str | None = None,
    **_: object,
) -> str:
    signal_type = type_label(priority)
    action_text = action_label(signal)
    status_text = build_status_text(signal, status)
    trend_text = trend_label(trend_1h)
    prefix = title_prefix(priority)
    entry_zone_text = zone_text(entry_zone_low, entry_zone_high, price)

    start_window = (
        start_window_text_override
        or start_window_text
        or start_window_text_func(priority=priority, eta_min_minutes=eta_min_minutes, eta_max_minutes=eta_max_minutes)
    )
    timeout_hint = timeout_text(priority)

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


# 避免形参与兼容变量同名冲突
start_window_text_func = start_window_text



def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    response = requests.post(url, json=payload, timeout=20)
    return response.text
