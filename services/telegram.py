import requests

SIGNAL_LABELS = {
    "A_LONG": "A类做多机会",
    "A_SHORT": "A类做空机会",
    "B_LONG": "B类回踩后做多机会",
    "B_SHORT": "B类反弹后做空机会",
    "B_PULLBACK_LONG": "B类回踩后做多机会",
    "B_PULLBACK_SHORT": "B类反弹后做空机会",
    "C_LONG": "C类做多机会",
    "C_SHORT": "C类做空机会",
    "C_LEFT_LONG": "C类做多机会",
    "C_LEFT_SHORT": "C类做空机会",
}

PRIORITY_LABELS = {
    1: "A",
    2: "B",
    3: "C",
}

TREND_1H_LABELS = {
    "bull": "偏多",
    "lean_bull": "偏多(弱)",
    "neutral": "中性",
    "lean_bear": "偏空(弱)",
    "bear": "偏空",
}

STATUS_LABELS = {
    "active": "进行中",
    "early": "早期预警",
}


def signal_label(signal: str) -> str:
    return SIGNAL_LABELS.get(signal, signal)


def priority_label(priority: int) -> str:
    return PRIORITY_LABELS.get(priority, str(priority))


def trend_1h_label(trend_1h: str) -> str:
    return TREND_1H_LABELS.get(trend_1h, trend_1h)


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def format_webhook_message(signal: str, symbol: str, timeframe: str) -> str:
    return (
        "📡 交易预警\n"
        "优先级: -\n"
        f"类型建议: {signal_label(signal)}\n"
        f"标的: {symbol}\n"
        "价格: -\n"
        f"周期: {timeframe}\n"
        "1h方向: -\n"
        "状态: -"
    )


def format_engine_message(
    signal: str,
    symbol: str,
    timeframe: str,
    priority: int,
    price: float,
    trend_1h: str,
    status: str,
) -> str:
    return (
        "📡 交易预警\n"
        f"优先级: {priority_label(priority)}\n"
        f"类型建议: {signal_label(signal)}\n"
        f"标的: {symbol}\n"
        f"价格: {price:.2f}\n"
        f"周期: {timeframe}\n"
        f"1h方向: {trend_1h_label(trend_1h)}\n"
        f"状态: {status_label(status)}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    r = requests.post(url, json=payload, timeout=20)
    return r.text
