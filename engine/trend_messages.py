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
}


def _is_pin_context(d: dict) -> bool:
    return (
        str(d.get("sweep_type", "none")) != "none"
        or str(d.get("reclaim_or_reject", "none")) != "none"
        or bool(d.get("bars_since_sweep") is not None)
    )


def _neutral_observation_title(d: dict, family: str = "key") -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type in {"RANGE_LOWER_PROBE", "RANGE_UPPER_PROBE"}:
        return "📍 BTC 1H 震荡观察"
    if _is_pin_context(d):
        return "📍 BTC 1H 插针观察"
    return "📍 BTC 1H 关键区观察"


def _long_probe_title() -> str:
    return "📈 BTC 1H 试多观察 📈"


def _short_probe_title() -> str:
    return "📉 BTC 1H 试空观察 📉"


def _long_confirm_title() -> str:
    return "📈 BTC 1H 多头确认 📈"


def _short_confirm_title() -> str:
    return "📉 BTC 1H 空头确认 📉"


def _secondary_lower_title() -> str:
    return "✅ BTC 1H 二次确认：承接成立 ✅"


def _secondary_upper_title() -> str:
    return "✅ BTC 1H 二次确认：承压成立 ✅"


def _lower_observation_title() -> str:
    return "📍 BTC 1H 下方关键区观察"


def _upper_observation_title() -> str:
    return "📍 BTC 1H 上方关键区观察"


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


def _prealert_zone_note(d: dict) -> str:
    direction = str(d.get("direction", "neutral"))
    if direction == "short":
        return "反抽压制区，站不上则预警有效。"
    if direction == "long":
        return "回踩承接区，守住则预警有效。"
    return "短线反应区，仅作预警参考。"


def format_prealert_message(d: dict) -> str:
    """Format 15m prealerts as a single-emoji, non-formal family.

    15m remains shadow-only unless explicitly enabled elsewhere.  This copy is
    intentionally short: status, zone, and risk/handling only.  It must never
    look like a 1H formal trade alert.
    """

    direction = str(d.get("direction", "neutral"))
    title = str(d.get("title") or ("📍 BTC 15m 做空预警" if direction == "short" else "📍 BTC 15m 做多预警"))
    invalid = float(d.get("invalid_level", 0.0) or 0.0)

    if direction == "short":
        status = "15m 出现可能的做空位置。\n这不是 1H 正式单，只用于提醒看盘确认。"
        zone_note = "关注反抽是否继续受压。"
        risk = (
            f"若价格重新站回 {invalid:.2f}，本次 15m 做空预警失效。\n"
            "仅作为入场位置提醒，最终仍以 1H / 4H 结构判断为主。"
        )
    elif direction == "long":
        status = "15m 出现可能的做多位置。\n这不是 1H 正式单，只用于提醒看盘确认。"
        zone_note = "关注回踩是否继续承接。"
        risk = (
            f"若价格重新跌破 {invalid:.2f}，本次 15m 做多预警失效。\n"
            "仅作为入场位置提醒，最终仍以 1H / 4H 结构判断为主。"
        )
    else:
        status = "15m 出现可能的入场位置。\n这不是 1H 正式单，只用于提醒看盘确认。"
        zone_note = "关注该区间是否出现明确反应。"
        risk = (
            f"若价格突破风险位 {invalid:.2f}，本次 15m 预警失效。\n"
            "仅作为入场位置提醒，最终仍以 1H / 4H 结构判断为主。"
        )

    text = (
        f"{title}\n\n"
        "📌 状态：\n"
        f"{status}\n\n"
        "🎯 关注区间：\n"
        f"{_zone_text(d)}\n"
        f"{zone_note}\n\n"
        "⚠️ 风险点：\n"
        f"{risk}"
    )
    return _sanitize(text)


def _single_observation_sections(d: dict, title: str, detail: str, zone_note: str, risk_line: str) -> str:
    return (
        f"{title}\n\n"
        "📌 状态：\n"
        f"{detail}\n\n"
        "🎯 关注区间：\n"
        f"{_zone_text(d)}\n"
        f"{zone_note}\n\n"
        "⚠️ 风险点：\n"
        f"{risk_line}"
    )

def _format_lower_observation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "LOWER_KEY_ZONE_RECLAIM":
        title = _long_probe_title()
        detail = "价格测试下方关键区后快速收回。\n当前出现试多观察条件。"
        conclusion = "具备试多观察条件。\n严格以风险位控制。"
        risk_line = f"若重新跌破 {float(d['invalid_level']):.2f}，下方结构可能再次转弱。"
        return (
            f"{title}\n\n"
            "📌 状态：\n"
            f"{detail}\n\n"
            + _common_sections(d, risk_line, conclusion)
        )

    if alert_type == "FAST_PULLBACK_OBSERVE":
        detail = "价格快速回踩下方关键区。\n当前仅属于观察提醒，尚未形成试多条件。"
        zone_note = "观察下方是否出现收回、承接或继续失守。"
        risk_line = (
            f"若有效跌破 {float(d['invalid_level']):.2f}，下方结构可能继续转弱。\n"
            "若快速收回，则可能转入试多观察。"
        )
    elif alert_type == "RANGE_LOWER_PROBE":
        detail = "价格正在测试区间下沿。\n当前仅属于观察提醒，尚未形成试多条件。"
        zone_note = "观察区间下沿是否守住，或是否出现快速收回。"
        risk_line = (
            f"若有效跌破 {float(d['invalid_level']):.2f}，下方结构可能继续转弱。\n"
            "若快速收回，则可能转入试多观察。"
        )
    else:
        detail = "价格接近下方关键区。\n当前仅属于观察提醒，尚未形成试多条件。"
        zone_note = "观察下方是否出现收回、承接或继续失守。"
        risk_line = (
            f"若有效跌破 {float(d['invalid_level']):.2f}，下方结构可能继续转弱。\n"
            "若快速收回，则可能转入试多观察。"
        )

    return _single_observation_sections(d, _lower_observation_title(), detail, zone_note, risk_line)

def _format_upper_observation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "UPPER_KEY_ZONE_REJECTION":
        title = _short_probe_title()
        detail = "价格触及上方关键区后快速回落。\n当前出现试空观察条件。"
        conclusion = "具备试空观察条件。\n严格以风险位控制。"
        risk_line = f"若有效站回 {float(d['invalid_level']):.2f}，上方结构可能重新修复。"
        return (
            f"{title}\n\n"
            "📌 状态：\n"
            f"{detail}\n\n"
            + _common_sections(d, risk_line, conclusion)
        )

    if alert_type == "FAST_REBOUND_OBSERVE":
        detail = "价格快速反抽上方关键区。\n当前仅属于观察提醒，尚未形成试空条件。"
        zone_note = "观察反抽是否受压，或是否有效站回区间上方。"
        risk_line = (
            f"若有效站回 {float(d['invalid_level']):.2f}，上方结构可能继续修复。\n"
            "若反抽失败，则可能转入试空观察。"
        )
    elif alert_type == "RANGE_UPPER_PROBE":
        detail = "价格正在测试区间上沿。\n当前仅属于观察提醒，尚未形成试空条件。"
        zone_note = "观察区间上沿是否承压，或是否有效站回。"
        risk_line = (
            f"若有效站回 {float(d['invalid_level']):.2f}，上方结构可能继续修复。\n"
            "若反抽失败，则可能转入试空观察。"
        )
    else:
        detail = "价格接近上方关键区。\n当前仅属于观察提醒，尚未形成试空条件。"
        zone_note = "观察反抽是否受压，或是否有效站回区间上方。"
        risk_line = (
            f"若有效站回 {float(d['invalid_level']):.2f}，上方结构可能继续修复。\n"
            "若反抽失败，则可能转入试空观察。"
        )

    return _single_observation_sections(d, _upper_observation_title(), detail, zone_note, risk_line)

def _format_confirmation(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    if alert_type == "SECONDARY_CONFIRM_LOWER":
        return (
            f"{_secondary_lower_title()}\n\n"
            "⚠️ 风险位：\n"
            f"若重新跌破 {float(d['invalid_level']):.2f}，承接确认失效。"
        )
    if alert_type == "SECONDARY_CONFIRM_UPPER":
        return (
            f"{_secondary_upper_title()}\n\n"
            "⚠️ 风险位：\n"
            f"若重新站回 {float(d['invalid_level']):.2f}，承压确认失效。"
        )

    # Invalidation alerts are intentionally not part of the public copy family.
    # They should be suppressed before formatting and only update internal state.
    return _single_observation_sections(
        d,
        _neutral_observation_title(d),
        "价格离开前一关注区间。\n当前仅属于观察提醒，等待新的关键区形成。",
        "观察该区间是否重新出现收回、失守或承压。",
        f"若突破 {float(d['invalid_level']):.2f}，需要重新评估结构。",
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
            _long_probe_title() + "\n\n"
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
            _short_probe_title() + "\n\n"
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
            _long_confirm_title() + "\n\n"
            "📌 状态：\n"
            "下方关键区触发后，价格重新收回。\n"
            "1H 结构正在转多。\n\n"
            + _common_sections(
                d,
                f"若跌破 {float(d['invalid_level']):.2f}，本轮转多结构失败。",
                "多头条件成立。\n回踩不破可继续按多头处理。",
            )
        )
    elif direction == "short":
        text = (
            _short_confirm_title() + "\n\n"
            "📌 状态：\n"
            "上方关键区触发后，价格开始回落。\n"
            "1H 结构正在转空。\n\n"
            + _common_sections(
                d,
                f"若重新站回 {float(d['invalid_level']):.2f}，本轮转空结构失败。",
                "空头条件成立。\n反抽不破可继续按空头处理。",
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
