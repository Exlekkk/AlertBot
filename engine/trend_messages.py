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
    "LOWER_KEY_ZONE_RECLAIM",
    "FAST_PULLBACK_OBSERVE",
    "RANGE_LOWER_PROBE",
}

UPPER_OBSERVATION_ALERTS = {
    "UPPER_KEY_ZONE_TEST",
    "UPPER_KEY_ZONE_REJECTION",
    "FAST_REBOUND_OBSERVE",
    "RANGE_UPPER_PROBE",
}

CONFIRMATION_ALERTS = {
    "SECONDARY_CONFIRM_LOWER",
    "SECONDARY_CONFIRM_UPPER",
    "LOWER_CONFIRM_INVALIDATED",
    "UPPER_CONFIRM_INVALIDATED",
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




def _zone_note(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    direction = str(d.get("direction", "neutral"))

    notes = {
        "LOWER_KEY_ZONE_RECLAIM": "下方承接观察区，回踩不破才有确认价值。",
        "UPPER_KEY_ZONE_REJECTION": "上方承压观察区，反抽不破才有确认价值。",
        "FAST_PULLBACK_OBSERVE": "急跌后的下方反应区，先看是否收回区间上沿。",
        "FAST_REBOUND_OBSERVE": "急拉后的上方反应区，先看是否跌回区间下沿。",
        "LOWER_KEY_ZONE_TEST": "下方反应观察区，先看是否出现收回。",
        "UPPER_KEY_ZONE_TEST": "上方反应观察区，先看是否出现回落。",
        "RANGE_LOWER_PROBE": "区间下沿观察区，守住或收回才有价值。",
        "RANGE_UPPER_PROBE": "区间上沿观察区，承压或回落才有价值。",
        "SECONDARY_CONFIRM_LOWER": "二次确认参考区，继续守住则承接有效。",
        "SECONDARY_CONFIRM_UPPER": "二次确认参考区，继续压制则承压有效。",
        "LOWER_CONFIRM_INVALIDATED": "原承接观察区已失效，等待新的关键区形成。",
        "UPPER_CONFIRM_INVALIDATED": "原承压观察区已失效，等待新的关键区形成。",
        "BULLISH_CONTINUATION": "多头中段观察区，守住则延续更稳。",
        "BEARISH_CONTINUATION": "空头中段观察区，承压则延续更稳。",
        "BULLISH_STRUCTURE_SHIFT": "结构转多后的回踩观察区，守住则更有延续价值。",
        "BEARISH_STRUCTURE_SHIFT": "结构转空后的反抽观察区，承压则更有延续价值。",
    }

    if alert_type in notes:
        return notes[alert_type]

    if direction == "long":
        return "下方承接观察区，等待价格给出延续反应。"
    if direction == "short":
        return "上方承压观察区，等待价格给出延续反应。"
    return "当前结构参考区，等待明确反应。"


def _clean_momentum(desc: str) -> str:
    desc = str(desc).strip()
    if not desc:
        return "短线动能一般。"
    desc = desc.replace("动能 ", "").replace("动能", "").strip()
    mapping = {
        "偏强": "短线动能偏强。",
        "偏弱": "短线动能偏弱。",
        "一般": "短线动能一般。",
    }
    return mapping.get(desc, desc if desc.endswith("。") else f"{desc}。")


def _clean_temperature(desc: str) -> str:
    desc = str(desc).strip()
    if not desc:
        return "市场热度中性。"
    desc = desc.replace("热度 ", "").replace("热度", "").strip()
    mapping = {
        "过热": "市场热度偏热。",
        "偏热": "市场热度偏热。",
        "中性": "市场热度中性。",
        "偏冷": "市场热度偏冷。",
        "过冷": "市场热度偏冷。",
    }
    return mapping.get(desc, desc if desc.endswith("。") else f"{desc}。")


def _common_sections(d: dict, risk_line: str, conclusion: str) -> str:
    return (
        "🎯 关注区间：\n"
        f"{_zone_text(d)}\n"
        f"{_zone_note(d)}\n\n"
        "🧭 大周期：\n"
        f"{d['htf_context']}\n"
        "但本次提醒以 1H 结构变化为主。\n\n"
        "⚡ 动能与热度：\n"
        f"{_clean_momentum(d.get('momentum_desc', ''))}\n"
        f"{_clean_temperature(d.get('temperature_desc', ''))}\n\n"
        "⚠️ 风险位：\n"
        f"{risk_line}\n\n"
        "✅ 结论：\n"
        f"{conclusion}"
    )


def _format_lower_observation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "LOWER_KEY_ZONE_RECLAIM":
        title = "📈 BTC 1H 下方关键区收回 📈"
        detail = "价格测试下方关键区后快速收回。\n当前不是追多信号，而是下方承接观察。"
        conclusion = "已有初步承接。\n若后续回踩不破，将进入试仓观察。"
        risk_line = f"若重新跌破 {float(d['invalid_level']):.2f}，下方结构可能再次转弱。"
    elif alert_type == "FAST_PULLBACK_OBSERVE":
        title = "📍 BTC 1H 快速回踩观察"
        detail = "价格快速回踩下方关键区。\n当前还不是结构转空，而是关键区测试。"
        conclusion = "不追空。\n观察关注区间是否出现承接。"
        risk_line = f"若继续跌破 {float(d['invalid_level']):.2f}，下方结构可能进一步转弱。"
    elif alert_type == "RANGE_LOWER_PROBE":
        title = "📍 BTC 1H 区间下沿测试"
        detail = "价格正在测试区间下沿。\n当前以关键区反应为主。"
        conclusion = "不追空。\n观察下沿是否守住或快速收回。"
        risk_line = f"若继续跌破 {float(d['invalid_level']):.2f}，下方结构可能进一步转弱。"
    else:
        title = "📍 BTC 1H 下方关键区测试"
        detail = "价格触及下方关键区。\n当前还不是结构转空，而是关键区测试。"
        conclusion = "不追空。\n观察关键区是否出现承接。"
        risk_line = f"若继续跌破 {float(d['invalid_level']):.2f}，下方结构可能进一步转弱。"

    return (
        f"{title}\n\n"
        "📌 状态：\n"
        f"{detail}\n\n"
        + _common_sections(d, risk_line, conclusion)
    )


def _format_upper_observation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "UPPER_KEY_ZONE_REJECTION":
        title = "📉 BTC 1H 上方关键区承压 📉"
        detail = "价格触及上方关键区后快速回落。\n当前不是追空信号，而是卖压释放观察。"
        conclusion = "已有初步承压。\n若后续反抽不破，将进入试空观察。"
        risk_line = f"若有效站回 {float(d['invalid_level']):.2f}，上方结构可能重新修复。"
    elif alert_type == "FAST_REBOUND_OBSERVE":
        title = "📍 BTC 1H 快速反抽观察"
        detail = "价格快速反抽上方关键区。\n当前还不是结构转多，而是关键区测试。"
        conclusion = "不追多。\n观察关注区间是否出现承压。"
        risk_line = f"若有效站上 {float(d['invalid_level']):.2f}，上方结构可能继续修复。"
    elif alert_type == "RANGE_UPPER_PROBE":
        title = "📍 BTC 1H 区间上沿测试"
        detail = "价格正在测试区间上沿。\n当前以关键区反应为主。"
        conclusion = "不追多。\n观察上沿是否承压或快速回落。"
        risk_line = f"若有效站上 {float(d['invalid_level']):.2f}，上方结构可能继续修复。"
    else:
        title = "📍 BTC 1H 上方关键区测试"
        detail = "价格触及上方关键区。\n当前还不是结构转多，而是关键区测试。"
        conclusion = "不追多。\n观察关键区是否出现承压。"
        risk_line = f"若有效站上 {float(d['invalid_level']):.2f}，上方结构可能继续修复。"

    return (
        f"{title}\n\n"
        "📌 状态：\n"
        f"{detail}\n\n"
        + _common_sections(d, risk_line, conclusion)
    )


def _format_confirmation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "SECONDARY_CONFIRM_LOWER":
        title = "✅ BTC 1H 二次确认：下方承接成立"
        detail = "价格回踩关注区间不破，短线承接延续。"
        conclusion = "具备小仓试探条件。\n重点观察关注区间是否继续承接。"
        risk_line = f"若重新跌破 {float(d['invalid_level']):.2f}，本轮承接失效。"
    elif alert_type == "SECONDARY_CONFIRM_UPPER":
        title = "✅ BTC 1H 二次确认：上方承压成立"
        detail = "价格反抽关注区间不破，短线承压延续。"
        conclusion = "具备小仓试空条件。\n重点观察关注区间是否继续承压。"
        risk_line = f"若重新站上 {float(d['invalid_level']):.2f}，本轮承压失效。"
    elif alert_type == "LOWER_CONFIRM_INVALIDATED":
        title = "⚠️ BTC 1H 下方承接失效"
        detail = "价格跌破前一关注区间的风险位。"
        conclusion = "本轮观察失效。\n等待新的关键区重新形成。"
        risk_line = f"已跌破 {float(d['invalid_level']):.2f}，下方结构需要重新评估。"
    else:
        title = "⚠️ BTC 1H 上方承压失效"
        detail = "价格站上前一关注区间的风险位。"
        conclusion = "本轮观察失效。\n等待新的关键区重新形成。"
        risk_line = f"已站上 {float(d['invalid_level']):.2f}，上方结构需要重新评估。"

    return (
        f"{title}\n\n"
        "📌 状态：\n"
        f"{detail}\n\n"
        + _common_sections(d, risk_line, conclusion)
    )


def format_trend_message(d: dict) -> str:
    direction = d.get("direction", "neutral")
    alert_type = str(d.get("alert_type", ""))

    if alert_type in CONFIRMATION_ALERTS:
        text = _format_confirmation(d)
    elif alert_type in LOWER_OBSERVATION_ALERTS:
        text = _format_lower_observation(d)
    elif alert_type in UPPER_OBSERVATION_ALERTS:
        text = _format_upper_observation(d)
    elif direction == "long" and alert_type == "BULLISH_CONTINUATION":
        text = (
            "📈 BTC 1H 多头延续观察\n\n"
            "📌 状态：\n"
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
            "📌 状态：\n"
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
            "📌 状态：\n"
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
            "📌 状态：\n"
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
            "🔎 BTC 1H 结构观察\n\n"
            "📌 状态：\n"
            "当前未形成高质量方向提醒。\n\n"
            + _common_sections(
                d,
                f"若突破 {float(d['invalid_level']):.2f}，需要重新评估结构。",
                "继续观察，等待关键区反应。",
            )
        )

    return _sanitize(text)
