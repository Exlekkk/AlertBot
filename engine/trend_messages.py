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


LOWER_OBSERVATION_ALERTS = {
    "LOWER_KEY_ZONE_TEST",
    "FAST_PULLBACK_OBSERVE",
    "RANGE_LOWER_PROBE",
}

UPPER_OBSERVATION_ALERTS = {
    "UPPER_KEY_ZONE_TEST",
    "FAST_REBOUND_OBSERVE",
    "RANGE_UPPER_PROBE",
}


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


def _format_lower_observation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "FAST_PULLBACK_OBSERVE":
        title = "📍 BTC 1H 快速回踩观察"
        detail = "价格快速回踩下方关键区。\n当前还不是结构转空，而是关键区测试。"
        conclusion = "不追空。\n观察关注区间是否出现承接。"
    elif alert_type == "RANGE_LOWER_PROBE":
        title = "📍 BTC 1H 区间下沿测试"
        detail = "价格正在测试区间下沿。\n当前以关键区反应为主。"
        conclusion = "不追空。\n观察下沿是否守住或快速收回。"
    else:
        title = "📍 BTC 1H 下方关键区测试"
        detail = "价格触及下方关键区。\n当前还不是结构转空，而是关键区测试。"
        conclusion = "不追空。\n观察关键区是否出现承接。"

    return (
        f"{title}\n\n"
        "状态：\n"
        f"{detail}\n\n"
        + _common_sections(
            d,
            f"若继续跌破 {float(d['invalid_level']):.2f}，下方结构可能进一步转弱。",
            conclusion,
        )
    )


def _format_upper_observation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "FAST_REBOUND_OBSERVE":
        title = "📍 BTC 1H 快速反抽观察"
        detail = "价格快速反抽上方关键区。\n当前还不是结构转多，而是关键区测试。"
        conclusion = "不追多。\n观察关注区间是否出现承压。"
    elif alert_type == "RANGE_UPPER_PROBE":
        title = "📍 BTC 1H 区间上沿测试"
        detail = "价格正在测试区间上沿。\n当前以关键区反应为主。"
        conclusion = "不追多。\n观察上沿是否承压或快速回落。"
    else:
        title = "📍 BTC 1H 上方关键区测试"
        detail = "价格触及上方关键区。\n当前还不是结构转多，而是关键区测试。"
        conclusion = "不追多。\n观察关键区是否出现承压。"

    return (
        f"{title}\n\n"
        "状态：\n"
        f"{detail}\n\n"
        + _common_sections(
            d,
            f"若重新站上 {float(d['invalid_level']):.2f}，上方结构可能继续修复。",
            conclusion,
        )
    )


def format_trend_message(d: dict) -> str:
    direction = d.get("direction", "neutral")
    alert_type = str(d.get("alert_type", ""))

    if alert_type in LOWER_OBSERVATION_ALERTS:
        text = _format_lower_observation(d)
    elif alert_type in UPPER_OBSERVATION_ALERTS:
        text = _format_upper_observation(d)
    elif direction == "long" and alert_type == "BULLISH_CONTINUATION":
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
