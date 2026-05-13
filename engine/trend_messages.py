from __future__ import annotations

BANNED = [
    "liquidity",
    "MSB",
    "OB",
    "MB",
    "BB",
    "CHoCH",
    "RAR",
    "TAI",
    "SMC",
    "ICT",
    "ABCX",
    "流动性",
    "订单块",
    "CHOCH",
]


def _sanitize(text: str) -> str:
    lowered = text.lower()
    for term in BANNED:
        if term.lower() in lowered:
            raise ValueError(f"banned term leaked: {term}")
    return text


def format_trend_message(d: dict) -> str:
    zl, zh = d["zone"]
    if d["direction"] == "long":
        text = (
            "📈 BTC 1H 结构转多提醒\n\n"
            "状态：\n"
            "下方关键区触发后，价格重新收回。\n"
            "1H 结构正在转多。\n\n"
            "关注区间：\n"
            f"{zl:.2f} - {zh:.2f}\n\n"
            "大周期：\n"
            f"{d['htf_context']}\n"
            "但本次提醒以 1H 结构变化为主。\n\n"
            "动能与热度：\n"
            f"{d['momentum_desc']}\n"
            f"{d['temperature_desc']}\n\n"
            "风险位：\n"
            f"若跌破 {d['invalid_level']:.2f}，本轮转多结构失败。\n\n"
            "结论：\n"
            "不追价。\n"
            "等待价格回到关注区间后的反应。"
        )
    else:
        text = (
            "📉 BTC 1H 结构转空提醒\n\n"
            "状态：\n"
            "上方关键区触发后，价格开始回落。\n"
            "1H 结构正在转空。\n\n"
            "关注区间：\n"
            f"{zl:.2f} - {zh:.2f}\n\n"
            "大周期：\n"
            f"{d['htf_context']}\n"
            "但本次提醒以 1H 结构变化为主。\n\n"
            "动能与热度：\n"
            f"{d['momentum_desc']}\n"
            f"{d['temperature_desc']}\n\n"
            "风险位：\n"
            f"若重新站回 {d['invalid_level']:.2f}，本轮转空结构失败。\n\n"
            "结论：\n"
            "不追空。\n"
            "等待价格反抽关注区间后的承压反应。"
        )
    return _sanitize(text)
