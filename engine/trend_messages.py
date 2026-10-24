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
    "FVG",
    "IFVG",
    "Heatmap",
    "热力图",
    "流动性",
    "订单块",
    "CHOCH",
]


LOWER_OBSERVATION_ALERTS = {
    "LOWER_KEY_ZONE_TEST",
    "LOWER_KEY_ZONE_RECLAIM",
    "FAST_PULLBACK_OBSERVE",
    "RANGE_LOWER_PROBE",
    "EARLY_LONG_TRIAL",
}

UPPER_OBSERVATION_ALERTS = {
    "UPPER_KEY_ZONE_TEST",
    "UPPER_KEY_ZONE_REJECTION",
    "FAST_REBOUND_OBSERVE",
    "RANGE_UPPER_PROBE",
    "EARLY_SHORT_TRIAL",
}

CONFIRMATION_ALERTS = {
    "SECONDARY_CONFIRM_LOWER",
    "SECONDARY_CONFIRM_UPPER",
}

# Telegram send allowlist (L 2026-10-24): only 试多观察 / 试空观察 full template.
# Scoring / decide_* algorithms unchanged; scanner gates on this before send.
TRIAL_PROBE_SEND_ALERT_TYPES = {
    "EARLY_LONG_TRIAL",
    "LOWER_KEY_ZONE_RECLAIM",
    "EARLY_SHORT_TRIAL",
    "UPPER_KEY_ZONE_REJECTION",
    # Continuations already use 试多观察 / 试空观察 titles via _long/_short_probe_title.
    "BULLISH_CONTINUATION",
    "BEARISH_CONTINUATION",
}

KEY_ZONE_OBSERVATION_SUPPRESS_ALERT_TYPES = {
    "LOWER_KEY_ZONE_TEST",
    "FAST_PULLBACK_OBSERVE",
    "RANGE_LOWER_PROBE",
    "UPPER_KEY_ZONE_TEST",
    "FAST_REBOUND_OBSERVE",
    "RANGE_UPPER_PROBE",
}

CONFIRM_SUPPRESS_ALERT_TYPES = {
    "BULLISH_STRUCTURE_SHIFT",
    "BEARISH_STRUCTURE_SHIFT",
    "SECONDARY_CONFIRM_LOWER",
    "SECONDARY_CONFIRM_UPPER",
    "LOWER_CONFIRM_INVALIDATED",
    "UPPER_CONFIRM_INVALIDATED",
}


def should_send_alert_copy(decision: dict) -> bool:
    """True only for allowlisted 试多/试空 probe templates."""
    alert_type = str(decision.get("alert_type", "") or "")
    return alert_type in TRIAL_PROBE_SEND_ALERT_TYPES


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


MAJOR_SECTION_HEADERS = {
    "📌 状态：",
    "🎯 关注区间：",
    "🧭 大周期：",
    "⚡ 动能与热度：",
    "⚠️ 风险位：",
    "⚠️ 风险点：",
    "✅ 结论：",
    "✅ 结论",
    "📍 开单建议",
    "👁 关注点",
}


def _dedupe_major_sections(text: str) -> str:
    """Keep one copy of each Telegram section if upstream text is duplicated."""

    output: list[str] = []
    seen: set[str] = set()
    skipping_duplicate = False
    for line in text.splitlines():
        if line in MAJOR_SECTION_HEADERS:
            if line in seen:
                skipping_duplicate = True
                continue
            seen.add(line)
            skipping_duplicate = False
            output.append(line)
            continue
        if not skipping_duplicate:
            output.append(line)
    return "\n".join(output).strip()


def _zone_text(d: dict) -> str:
    zl, zh = d["zone"]
    return f"{float(zl):.2f} - {float(zh):.2f}"




def _zone_note(d: dict) -> str:
    alert_type = str(d.get("alert_type", ""))
    direction = str(d.get("direction", "neutral"))

    notes = {
        "LOWER_KEY_ZONE_RECLAIM": "下方承接观察区，回踩不破才有确认价值。",
        "EARLY_LONG_TRIAL": "下方早期承接观察区，守住风险位才有延续价值。",
        "UPPER_KEY_ZONE_REJECTION": "上方承压观察区，反抽不破才有确认价值。",
        "EARLY_SHORT_TRIAL": "上方早期承压观察区，站不上风险位才有延续价值。",
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


def _framework_line(htf: str, *, side: str) -> str:
    """Framework row is the section title itself (L lock: 🧭 4H 偏多/偏空/中性)."""
    text = str(htf or "")
    if "偏多" in text:
        return "🧭 4H 偏多"
    if "偏空" in text:
        return "🧭 4H 偏空"
    if any(token in text for token in ("中性", "震荡", "不足", "背景")):
        return "🧭 4H 中性"
    return "🧭 4H 偏多" if side == "long" else "🧭 4H 偏空"


def _take_profit_zone(d: dict, *, side: str) -> tuple[float, float]:
    """Structure-extension TP range for TG copy (numbers only; no brand words).

    Preference order:
    1) decision.take_profit_zone / tp_zone (wired by key_zones)
    2) opposite IFVG zones from evidence.ifvg
    3) range_lock opposite box edge band
    4) fibonacci extension_targets band
    5) entry-zone width projected in profit direction
    """
    for key in ("take_profit_zone", "tp_zone"):
        raw = d.get(key)
        if raw and len(raw) >= 2:
            a, b = float(raw[0]), float(raw[1])
            return (round(min(a, b), 2), round(max(a, b), 2))

    zone = d.get("zone") or (d.get("zone_low"), d.get("zone_high"))
    zl, zh = float(zone[0]), float(zone[1])
    zl, zh = min(zl, zh), max(zl, zh)
    width = max(zh - zl, 1e-9)

    evidence = d.get("evidence") if isinstance(d.get("evidence"), dict) else {}
    ifvg = evidence.get("ifvg") if isinstance(evidence.get("ifvg"), dict) else {}
    candidates: list[tuple[float, float, float]] = []
    zones = list(ifvg.get("zones") or [])
    nearest = ifvg.get("nearest_active")
    if isinstance(nearest, dict):
        zones = [nearest] + zones
    for item in zones:
        if not isinstance(item, dict):
            continue
        if item.get("invalidated") or item.get("mitigated"):
            continue
        top = item.get("top")
        bottom = item.get("bottom")
        if top is None or bottom is None:
            continue
        lo, hi = min(float(bottom), float(top)), max(float(bottom), float(top))
        if side == "long" and lo >= zh - 1e-9:
            candidates.append((lo - zh, lo, hi))
        elif side == "short" and hi <= zl + 1e-9:
            candidates.append((zl - hi, lo, hi))
    if candidates:
        candidates.sort(key=lambda row: row[0])
        _, lo, hi = candidates[0]
        return (round(lo, 2), round(hi, 2))

    box_lo = d.get("range_lock_box_low")
    box_hi = d.get("range_lock_box_high")
    if box_lo is not None and box_hi is not None:
        blo, bhi = float(box_lo), float(box_hi)
        blo, bhi = min(blo, bhi), max(blo, bhi)
        pad = max((bhi - blo) * 0.15, width * 0.5)
        if side == "long" and bhi > zh:
            return (round(max(zh, bhi - pad), 2), round(bhi, 2))
        if side == "short" and blo < zl:
            return (round(blo, 2), round(min(zl, blo + pad), 2))

    fib = None
    for src in (
        evidence.get("fibonacci"),
        d.get("fibonacci"),
        (d.get("msb") or {}).get("fibonacci") if isinstance(d.get("msb"), dict) else None,
    ):
        if isinstance(src, dict) and src.get("extension_targets"):
            fib = src
            break
    if fib:
        vals = sorted(float(v) for v in fib["extension_targets"].values())
        if side == "long":
            vals = [v for v in vals if v > zh]
        else:
            vals = [v for v in vals if v < zl]
        if len(vals) >= 2:
            return (round(vals[0], 2), round(vals[1], 2))
        if len(vals) == 1:
            v = vals[0]
            half = width * 0.35
            return (round(v - half, 2), round(v + half, 2))

    if side == "long":
        return (round(zh + width, 2), round(zh + 2.0 * width, 2))
    return (round(zl - 2.0 * width, 2), round(zl - width, 2))


def _take_profit_text(d: dict, *, side: str) -> str:
    lo, hi = _take_profit_zone(d, side=side)
    return f"{lo:.2f} - {hi:.2f}"


def _trial_probe_sections(d: dict, *, side: str) -> str:
    """AMST-aligned 试多/试空 TG copy (L 2026-10-24 lock). Indicators unchanged."""
    invalid = float(d["invalid_level"])
    htf = str(d.get("htf_context") or ("4H 偏多" if side == "long" else "4H 偏空"))
    zone = _zone_text(d)
    tp = _take_profit_text(d, side=side)
    framework = _framework_line(htf, side=side)
    if side == "long":
        attention = f"跌破 {invalid:.2f} → 本观察作废，等新结构。"
        conclusion = "具备试多观察条件。严格按关注点管理。"
    else:
        attention = f"站回 {invalid:.2f} → 本观察作废，等新结构。"
        conclusion = "具备试空观察条件。严格按关注点管理。"
    return (
        f"{framework}\n\n"
        "📍 开单建议\n"
        f"区间 {zone}。\n"
        f"止盈目标 {tp}。\n\n"
        "👁 关注点\n"
        f"{attention}\n\n"
        "✅ 结论\n"
        f"{conclusion}"
    )


def _common_sections(d: dict, risk_line: str, conclusion: str) -> str:
    # Legacy full layout (structure-shift / non-trial). Trial probes use
    # _trial_probe_sections instead.
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
    return _sanitize(_dedupe_major_sections(text))


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
    if alert_type in {"LOWER_KEY_ZONE_RECLAIM", "EARLY_LONG_TRIAL"}:
        return f"{_long_probe_title()}\n\n" + _trial_probe_sections(d, side="long")

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
    if alert_type in {"UPPER_KEY_ZONE_REJECTION", "EARLY_SHORT_TRIAL"}:
        return f"{_short_probe_title()}\n\n" + _trial_probe_sections(d, side="short")

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
        text = _long_probe_title() + "\n\n" + _trial_probe_sections(d, side="long")
    elif direction == "short" and alert_type == "BEARISH_CONTINUATION":
        text = _short_probe_title() + "\n\n" + _trial_probe_sections(d, side="short")
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

    return _sanitize(_dedupe_major_sections(text))


# Fixed illustrative levels for TG /test (not live prices; deterministic CI).
_SAMPLE_TRIAL_LONG = {
    "zone": (95000.0, 95200.0),
    "invalid_level": 94850.0,
    "htf_context": "4H 偏多",
    "take_profit_zone": (96000.0, 96500.0),
}
_SAMPLE_TRIAL_SHORT = {
    "zone": (97000.0, 97200.0),
    "invalid_level": 97350.0,
    "htf_context": "4H 偏空",
    "take_profit_zone": (95800.0, 96200.0),
}

TEST_FORMAT_PREFIX = "🧪 播报格式测试（非实盘信号）"


def _sample_trial_title(*, side: str) -> str:
    if side == "long":
        return "📈 BTC 1H 试多观察【测试】📈"
    return "📉 BTC 1H 试空观察【测试】📉"


def format_sample_trial_alert(*, side: str) -> str:
    """One ops /test sample alert; reuses production section builder + 【测试】 title."""
    if side not in {"long", "short"}:
        raise ValueError(f"unsupported sample side: {side}")
    payload = dict(_SAMPLE_TRIAL_LONG if side == "long" else _SAMPLE_TRIAL_SHORT)
    text = f"{_sample_trial_title(side=side)}\n\n" + _trial_probe_sections(payload, side=side)
    return _sanitize(_dedupe_major_sections(text))


def build_format_test_message() -> str:
    """Full /test reply: required prefix + 试多样例 + 试空样例. No state / no send path."""
    return (
        f"{TEST_FORMAT_PREFIX}\n\n"
        f"{format_sample_trial_alert(side='long')}\n\n"
        f"{format_sample_trial_alert(side='short')}"
    )
