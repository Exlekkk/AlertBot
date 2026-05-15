from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from engine.aux_filters import build_aux_filters_proxy
from engine.indicators import enrich_klines
from engine.liquidity import build_liquidity_context
from engine.msb_ob import build_msb_ob_context
from engine.trend_matrix import build_trend_matrix_proxy


@dataclass(frozen=True)
class PrealertConfig:
    touch_atr_mult: float = 0.30
    touch_pct: float = 0.0012
    min_reaction_body_ratio: float = 0.42
    min_wick_body_ratio: float = 0.55
    min_risk_reward_room: float = 0.0025
    max_risk_pct: float = 0.0065
    cooldown_bars: int = 4
    min_klines_15m: int = 80
    min_klines_1h: int = 80


DEFAULT_PREALERT_CONFIG = PrealertConfig()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ordered_zone(zone: tuple[float, float] | list[float]) -> tuple[float, float]:
    a, b = float(zone[0]), float(zone[1])
    return (round(min(a, b), 2), round(max(a, b), 2))


def _zone_hash(zone: tuple[float, float], side: str) -> str:
    zl, zh = zone
    return hashlib.md5(f"{side}|{zl:.2f}|{zh:.2f}".encode()).hexdigest()[:10]


def _temperature_bucket(k: dict[str, Any]) -> str:
    value = _f(k.get("tai_value"))
    p20 = _f(k.get("tai_p20"))
    p40 = _f(k.get("tai_p40"))
    p60 = _f(k.get("tai_p60"))
    p80 = _f(k.get("tai_p80"))
    if value < p20:
        return "过冷"
    if value < p40:
        return "偏冷"
    if value < p60:
        return "中性"
    if value < p80:
        return "偏热"
    return "过热"


def _momentum_bucket(k15: list[dict[str, Any]], side: str) -> str:
    latest = k15[-1]
    prev = k15[-2]
    rar_now = _f(latest.get("rar_value"), 50.0)
    rar_prev = _f(prev.get("rar_value"), 50.0)
    trigger = _f(latest.get("rar_trigger"), 50.0)
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    if side == "short":
        if close < open_ and (rar_now < trigger or rar_now < rar_prev):
            return "短线动能转弱"
        return "短线买盘衰减"
    if close > open_ and (rar_now > trigger or rar_now > rar_prev):
        return "短线动能修复"
    return "短线卖压衰减"


def _htf_context_text(klines_4h: list[dict[str, Any]]) -> str:
    latest = klines_4h[-1]
    ema10 = _f(latest.get("ema10"))
    ema20 = _f(latest.get("ema20"))
    close = _f(latest.get("close"))
    atr = max(_f(latest.get("atr")), abs(close) * 0.002, 1.0)
    strength = abs(ema10 - ema20) / atr
    if strength <= 0.45:
        return "4H 震荡"
    return "4H 偏多" if ema10 > ema20 else "4H 偏空"


def _candidate_zones(klines_1h: list[dict[str, Any]]) -> list[dict[str, Any]]:
    liq = build_liquidity_context(klines_1h)
    msb = build_msb_ob_context(klines_1h, liq)
    zones: list[dict[str, Any]] = []

    fvg_zone = msb.get("active_fvg_zone")
    if fvg_zone:
        zones.append(
            {
                "zone": _ordered_zone(fvg_zone),
                "source": "fvg_zone",
                "direction": str(msb.get("active_fvg_direction", "none")),
                "priority": 3,
            }
        )

    for key, source, priority in (
        ("mid_observe_zone", "mid_observe_zone", 2),
        ("structure_zone", "structure_zone", 2),
        ("order_block_zone", "order_block_zone", 1),
    ):
        zone = msb.get(key)
        if zone:
            zones.append(
                {
                    "zone": _ordered_zone(zone),
                    "source": source,
                    "direction": str(msb.get("direction", "neutral")),
                    "priority": priority,
                }
            )

    # Deduplicate near-identical zones while preserving priority.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for z in sorted(zones, key=lambda x: x["priority"], reverse=True):
        zl, zh = z["zone"]
        key = f"{round(zl / 50)}-{round(zh / 50)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(z)
    return out


def _touches_zone(k: dict[str, Any], zone: tuple[float, float], pad: float) -> bool:
    zl, zh = zone
    return _f(k.get("high")) >= zl - pad and _f(k.get("low")) <= zh + pad


def _reaction_quality(k: dict[str, Any]) -> tuple[float, float, float]:
    open_ = _f(k.get("open"))
    close = _f(k.get("close"))
    high = _f(k.get("high"))
    low = _f(k.get("low"))
    rng = max(high - low, 1e-9)
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return body / rng, upper_wick / max(body, 1e-9), lower_wick / max(body, 1e-9)


def _is_short_reaction(k15: list[dict[str, Any]], zone: tuple[float, float], cfg: PrealertConfig) -> bool:
    latest = k15[-1]
    prev = k15[-2]
    atr = max(_f(latest.get("atr")), abs(_f(latest.get("close"))) * 0.001, 1.0)
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    zone_low, zone_high = zone
    zone_mid = (zone_low + zone_high) / 2
    body_ratio, upper_wick_ratio, _ = _reaction_quality(latest)
    touched = _touches_zone(latest, zone, max(atr * cfg.touch_atr_mult, close * cfg.touch_pct)) or _touches_zone(
        prev, zone, max(atr * cfg.touch_atr_mult, close * cfg.touch_pct)
    )
    rar_now = _f(latest.get("rar_value"), 50.0)
    rar_prev = _f(prev.get("rar_value"), 50.0)
    rar_trigger = _f(latest.get("rar_trigger"), 50.0)
    price_reject = close <= zone_mid or close < open_
    momentum_turn = rar_now < rar_trigger or rar_now < rar_prev
    wick_reject = upper_wick_ratio >= cfg.min_wick_body_ratio
    strong_body = body_ratio >= cfg.min_reaction_body_ratio and close < open_
    return touched and price_reject and (momentum_turn or wick_reject or strong_body)


def _is_long_reaction(k15: list[dict[str, Any]], zone: tuple[float, float], cfg: PrealertConfig) -> bool:
    latest = k15[-1]
    prev = k15[-2]
    atr = max(_f(latest.get("atr")), abs(_f(latest.get("close"))) * 0.001, 1.0)
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    zone_low, zone_high = zone
    zone_mid = (zone_low + zone_high) / 2
    body_ratio, _, lower_wick_ratio = _reaction_quality(latest)
    touched = _touches_zone(latest, zone, max(atr * cfg.touch_atr_mult, close * cfg.touch_pct)) or _touches_zone(
        prev, zone, max(atr * cfg.touch_atr_mult, close * cfg.touch_pct)
    )
    rar_now = _f(latest.get("rar_value"), 50.0)
    rar_prev = _f(prev.get("rar_value"), 50.0)
    rar_trigger = _f(latest.get("rar_trigger"), 50.0)
    price_reclaim = close >= zone_mid or close > open_
    momentum_turn = rar_now > rar_trigger or rar_now > rar_prev
    wick_reclaim = lower_wick_ratio >= cfg.min_wick_body_ratio
    strong_body = body_ratio >= cfg.min_reaction_body_ratio and close > open_
    return touched and price_reclaim and (momentum_turn or wick_reclaim or strong_body)


def _risk_ok(side: str, entry: float, zone: tuple[float, float], latest: dict[str, Any], cfg: PrealertConfig) -> tuple[bool, float, float]:
    atr = max(_f(latest.get("atr")), abs(entry) * 0.001, 1.0)
    pad = max(atr * 0.25, abs(entry) * 0.001)
    zl, zh = zone
    if side == "short":
        invalid = round(max(zh, _f(latest.get("high"))) + pad, 2)
        risk_pct = max(0.0, (invalid - entry) / max(entry, 1e-9))
        room_pct = max(0.0, (entry - zl) / max(entry, 1e-9))
    else:
        invalid = round(min(zl, _f(latest.get("low"))) - pad, 2)
        risk_pct = max(0.0, (entry - invalid) / max(entry, 1e-9))
        room_pct = max(0.0, (zh - entry) / max(entry, 1e-9))
    return risk_pct <= cfg.max_risk_pct and room_pct >= cfg.min_risk_reward_room, invalid, risk_pct


def evaluate_15m_prealert(
    symbol: str,
    klines_15m: list[dict[str, Any]],
    klines_1h: list[dict[str, Any]],
    klines_4h: list[dict[str, Any]],
    cfg: PrealertConfig = DEFAULT_PREALERT_CONFIG,
) -> dict[str, Any]:
    """Return a 15m prealert decision.

    This layer is deliberately a *prealert* only: 1H/4H context defines the
    area, and 15m only checks whether price reaction inside that area is useful
    enough to log.  It does not replace 1H structure confirmation.
    """

    if len(klines_15m) < cfg.min_klines_15m or len(klines_1h) < cfg.min_klines_1h or len(klines_4h) < 20:
        return {
            "symbol": symbol,
            "timeframe": "15m",
            "alert_type": "NO_15M_PREALERT",
            "direction": "neutral",
            "should_alert": False,
            "suppress_reason": "insufficient_history",
        }

    latest = klines_15m[-1]
    entry = _f(latest.get("close"))
    atr = max(_f(latest.get("atr")), abs(entry) * 0.001, 1.0)
    pad = max(atr * cfg.touch_atr_mult, abs(entry) * cfg.touch_pct)

    candidates = _candidate_zones(klines_1h)
    best: dict[str, Any] | None = None

    for cand in candidates:
        zone = cand["zone"]
        zl, zh = zone
        # Focus only on nearby 1H areas.  This is the main anti-noise gate.
        near = _touches_zone(latest, zone, pad) or (zl - pad <= entry <= zh + pad)
        if not near:
            continue

        short_ok = _is_short_reaction(klines_15m, zone, cfg)
        long_ok = _is_long_reaction(klines_15m, zone, cfg)

        # Prefer contextual direction when FVG / OB proxy has one, but do not
        # hard-lock it because reclaimed zones can flip role after displacement.
        side: str | None = None
        if short_ok and not long_ok:
            side = "short"
        elif long_ok and not short_ok:
            side = "long"
        elif short_ok and long_ok:
            side = "short" if entry <= (zl + zh) / 2 else "long"

        if not side:
            continue

        risk_ok, invalid, risk_pct = _risk_ok(side, entry, zone, latest, cfg)
        if not risk_ok:
            continue

        priority = int(cand.get("priority", 1))
        score = 50 + priority * 5
        candidate = {
            "symbol": symbol,
            "timeframe": "15m",
            "alert_type": "PREALERT_SHORT" if side == "short" else "PREALERT_LONG",
            "direction": side,
            "title": "📍 BTC 15m 做空预警" if side == "short" else "📍 BTC 15m 做多预警",
            "price": round(entry, 2),
            "zone": zone,
            "zone_low": zone[0],
            "zone_high": zone[1],
            "zone_source": cand.get("source", "context_zone"),
            "zone_hash": _zone_hash(zone, side),
            "invalid_level": invalid,
            "risk_pct": round(risk_pct, 5),
            "score": score,
            "should_alert": True,
            "suppress_reason": "",
            "htf_context": _htf_context_text(klines_4h),
            "momentum_desc": _momentum_bucket(klines_15m, side),
            "temperature_desc": f"热度 {_temperature_bucket(latest)}",
            "open_time": int(latest.get("open_time", 0) or 0),
            "close_time": int(latest.get("close_time", 0) or 0),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if best:
        return best

    return {
        "symbol": symbol,
        "timeframe": "15m",
        "alert_type": "NO_15M_PREALERT",
        "direction": "neutral",
        "price": round(entry, 2),
        "should_alert": False,
        "suppress_reason": "no_qualified_15m_reaction_near_1h_zone",
    }


def format_prealert_log(decision: dict[str, Any]) -> str:
    if not decision.get("should_alert"):
        return (
            f"no_15m_prealert symbol={decision.get('symbol')} "
            f"reason={decision.get('suppress_reason')} price={decision.get('price')}"
        )

    zone = decision.get("zone") or (decision.get("zone_low"), decision.get("zone_high"))
    return (
        "would_send_15m_prealert "
        f'title="{decision.get("title")}" '
        f"side={decision.get('direction')} "
        f"price={float(decision.get('price')):.2f} "
        f"zone={float(zone[0]):.2f}-{float(zone[1]):.2f} "
        f"invalid={float(decision.get('invalid_level')):.2f} "
        f"source={decision.get('zone_source')} "
        f"htf={decision.get('htf_context')} "
        f"momentum={decision.get('momentum_desc')} "
        f"temperature={decision.get('temperature_desc')}"
    )


def ensure_enriched(klines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not klines:
        return []
    if "atr" in klines[-1] and "rar_value" in klines[-1] and "tai_value" in klines[-1]:
        return klines
    return enrich_klines(klines)
