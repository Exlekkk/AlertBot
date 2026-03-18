from __future__ import annotations

import requests


TYPE_LABELS = {
    1: "A类",
    2: "B类",
    3: "C类",
}

ACTION_LABELS = {
    "A_LONG": "顺势做多",
    "A_SHORT": "顺势做空",
    "B_PULLBACK_LONG": "回踩后做多",
    "B_PULLBACK_SHORT": "反弹后做空",
    "C_LEFT_LONG": "左侧提前预警做多",
    "C_LEFT_SHORT": "左侧提前预警做空",
}

TREND_LABELS = {
    "bull": "偏多（强）",
    "lean_bull": "偏多（弱）",
    "neutral": "中性",
    "lean_bear": "偏空（弱）",
    "bear": "偏空（强）",
}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def action_label(signal: str) -> str:
    return ACTION_LABELS.get(signal, signal)


def trend_label(trend_1h: str) -> str:
    return TREND_LABELS.get(trend_1h, trend_1h)


def build_status_text(signal: str, status: str) -> str:
    if signal == "A_LONG":
        return "突破结构成立，等待顺势跟随"
    if signal == "A_SHORT":
        return "跌破结构成立，等待顺势跟随"
    if signal == "B_PULLBACK_LONG":
        return "回踩条件满足，等待延续确认"
    if signal == "B_PULLBACK_SHORT":
        return "反弹条件满足，等待延续确认"
    if signal == "C_LEFT_LONG":
        return "左侧前提满足，处于提前观察阶段"
    if signal == "C_LEFT_SHORT":
        return "左侧前提满足，处于提前观察阶段"
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


def estimate_start_window(signal: str, trend_1h: str, status: str) -> str:
    strong = trend_1h in ("bull", "bear") and status == "active"
    semi = trend_1h in ("lean_bull", "lean_bear") and status == "active"

    if signal.startswith("A_"):
        minutes_low, minutes_high = (10, 60) if strong else (20, 120) if semi else (30, 150)
    elif signal.startswith("B_"):
        minutes_low, minutes_high = (20, 120) if strong else (30, 180) if semi else (45, 240)
    else:
        minutes_low, minutes_high = (30, 180) if strong else (45, 240) if semi else (60, 300)

    hours_high = round(minutes_high / 60.0, 1)
    if abs(hours_high - int(hours_high)) < 1e-9:
        hours_text = f"{int(hours_high)}小时内"
    else:
        hours_text = f"{hours_high:.1f}小时内"
    return f"约{minutes_low}分钟后 - {hours_text}"


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
) -> str:
    signal_type = type_label(priority)
    action_text = action_label(signal)
    status_text = build_status_text(signal, status)
    trend_text = trend_label(trend_1h)
    entry_zone_text = zone_text(entry_zone_low, entry_zone_high, price)
    startup_text = estimate_start_window(signal, trend_1h, status)

    return (
        f"🚨 盘面预警｜{signal_type}\n"
        f"操作建议：{action_text}\n"
        f"标的：{symbol}\n"
        f"参考价位区间：{entry_zone_text}\n"
        f"总体趋势方向：{trend_text}\n"
        f"预计启动时段：{startup_text}\n"
        f"状态：{status_text}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=20)
    return response.text
