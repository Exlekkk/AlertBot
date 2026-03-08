import requests

SIGNAL_LABELS = {
    "A_LONG": "A类做多机会",
    "A_SHORT": "A类做空机会",
    "B_PULLBACK_LONG": "B类回踩做多",
    "B_PULLBACK_SHORT": "B类回踩做空",
    "C_LEFT_LONG": "C类左侧预警做多",
    "C_LEFT_SHORT": "C类左侧预警做空",
}


def signal_label(signal: str) -> str:
    return SIGNAL_LABELS.get(signal, signal)


def format_alert_message(signal: str, symbol: str, timeframe: str, context: str, trigger: str, source: str) -> str:
    return (
        "📡 SMCT预警\n"
        f"类型：{signal_label(signal)}\n"
        f"标的：{symbol}\n"
        f"周期：{timeframe}\n"
        f"背景：{context}\n"
        f"触发：{trigger}\n"
        f"来源：{source}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    r = requests.post(url, json=payload, timeout=20)
    return r.text
