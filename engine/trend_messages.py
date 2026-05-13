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


def _zone_text(d: dict) -> str:
    zl, zh = d["zone"]
    return f"{float(zl):.2f} - {float(zh):.2f}"


def _common_sections(d: dict, risk_line: str, conclusion: str) -> str:
    return (
        "关注区间：\n"
        f"{_zone_text(d)}\n\n"
        "大周期：\n"
        f"{d['htf_context']}\n"
        "但本次提醒以 1H 结构变化为主。\n\n"
        "动能与热度：\n"
        f"{d['momentum_desc']}\n"
        f"{d['temperature_desc']}\n\n"
        "风险位：\n"
        f"{risk_line}\n\n"
        "结论：\n"
        f"{conclusion}"
    )


def format_trend_message(d: dict) -> str:
    direction = d.get("direction", "neutral")
    alert_type = str(d.get("alert_type", ""))

    if direction == "long" and alert_type == "BULLISH_CONTINUATION":
        text = (
            "📈 BTC 1H 多头延续观察\n\n"
            "状态：\n"
            "1H 多头结构仍在延续。\n"
            "价格正在测试趋势中段关键区。\n\n"
            + _common_sections(
                d,
                f"若跌破 {float(d['invalid_level']):.2f}，短线多头结构失败。",
                "不追高。\n观察中段关键区能否继续承接。",
            )
        )
    elif direction == "short" and alert_type == "BEARISH_CONTINUATION":
        text = (
            "📉 BTC 1H 空头延续观察\n\n"
            "状态：\n"
            "1H 空头结构仍在延续。\n"
            "价格正在测试趋势中段关键区。\n\n"
            + _common_sections(
                d,
                f"若重新站回 {float(d['invalid_level']):.2f}，短线空头结构失败。",
                "不追空。\n观察反抽关注区间后的承压反应。",
            )
        )
    elif direction == "long":
        text = (
            "📈 BTC 1H 结构转多提醒\n\n"
            "状态：\n"
            "下方关键区触发后，价格重新收回。\n"
            "1H 结构正在转多。\n\n"
            + _common_sections(
                d,
                f"若跌破 {float(d['invalid_level']):.2f}，本轮转多结构失败。",
                "不追价。\n等待价格回到关注区间后的反应。",
            )
        )
    elif direction == "short":
        text = (
            "📉 BTC 1H 结构转空提醒\n\n"
            "状态：\n"
            "上方关键区触发后，价格开始回落。\n"
            "1H 结构正在转空。\n\n"
            + _common_sections(
                d,
                f"若重新站回 {float(d['invalid_level']):.2f}，本轮转空结构失败。",
                "不追空。\n等待价格反抽关注区间后的承压反应。",
            )
        )
    else:
        text = (
            "🧊 BTC 1H 结构观察\n\n"
            "状态：\n"
            "当前 1H 结构方向不清晰。\n\n"
            + _common_sections(
                d,
                f"等待价格脱离 {float(d['invalid_level']):.2f} 附近的无效震荡。",
                "暂不追单。\n等待新的关键区反应。",
            )
        )

    return _sanitize(text)
