from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _atr(k: dict) -> float:
    close = abs(_float(k.get("close")))
    return max(_float(k.get("atr")), close * 0.0012, 1e-9)


def _count_true(*conds: bool) -> int:
    return sum(bool(c) for c in conds)


def _price_above_stack(k: dict) -> bool:
    close = _float(k.get("close"))
    ema10 = _float(k.get("ema10"))
    ema20 = _float(k.get("ema20"))
    return close >= ema10 >= ema20


def _price_below_stack(k: dict) -> bool:
    close = _float(k.get("close"))
    ema10 = _float(k.get("ema10"))
    ema20 = _float(k.get("ema20"))
    return close <= ema10 <= ema20


def _momentum_up(k: dict) -> bool:
    return bool(k.get("cm_macd_above_signal")) and (
        bool(k.get("cm_hist_up")) or _float(k.get("sss_hist")) >= 0
    )


def _momentum_down(k: dict) -> bool:
    return (not bool(k.get("cm_macd_above_signal"))) and (
        bool(k.get("cm_hist_down")) or _float(k.get("sss_hist")) <= 0
    )


def _volume_ratio(k: dict) -> float:
    volume = _float(k.get("volume"))
    baseline = max(_float(k.get("vol_sma20")), 1e-9)
    return volume / baseline


def _trend_score(direction: str, k_1h: dict, k_4h: dict, k_1d: dict | None = None) -> int:
    if direction == "long":
        score = 0
        score += 2 if _price_above_stack(k_1h) else 0
        score += 1 if _float(k_1h.get("close")) >= _float(k_1h.get("ema20")) else 0
        score += 1 if _price_above_stack(k_4h) else 0
        score += 1 if _momentum_up(k_1h) else 0
        score += 1 if _momentum_up(k_4h) else 0
        if k_1d:
            score += 1 if _float(k_1d.get("close")) >= _float(k_1d.get("ema20")) else 0
        return score

    score = 0
    score += 2 if _price_below_stack(k_1h) else 0
    score += 1 if _float(k_1h.get("close")) <= _float(k_1h.get("ema20")) else 0
    score += 1 if _price_below_stack(k_4h) else 0
    score += 1 if _momentum_down(k_1h) else 0
    score += 1 if _momentum_down(k_4h) else 0
    if k_1d:
        score += 1 if _float(k_1d.get("close")) <= _float(k_1d.get("ema20")) else 0
    return score


def _trend_display(direction: str, score: int) -> str:
    if direction == "long":
        if score >= 6:
            return "bull"
        if score >= 3:
            return "lean_bull"
        return "neutral"
    if score >= 6:
        return "bear"
    if score >= 3:
        return "lean_bear"
    return "neutral"


def _normalize_zone(low: float, high: float) -> tuple[float, float]:
    low = float(low)
    high = float(high)
    return (round(min(low, high), 2), round(max(low, high), 2))


def _round5(value: float) -> int:
    return int(round(value / 5.0) * 5)


def _window_from_extension(extension_atr: float, vol_ratio: float, news_score: int) -> tuple[int, int]:
    speed_boost = max(0.0, news_score - 40) / 40.0
    start = 5 + max(0.0, 1.2 - min(vol_ratio, 3.5)) * 12 + max(0.0, extension_atr - 1.4) * 6 - speed_boost * 8
    end = 30 + max(0.0, extension_atr - 0.8) * 20 + max(0.0, 2.0 - min(vol_ratio, 3.5)) * 18 - speed_boost * 10
    start_i = max(5, min(60, _round5(start)))
    end_i = max(start_i + 15, min(180, _round5(end)))
    return start_i, end_i


def _signal_dict(
    signal: str,
    symbol: str,
    direction: str,
    price: float,
    trend_1h: str,
    structure_basis: list[str],
    zone_low: float,
    zone_high: float,
    breakout_level: float,
    abnormal_type: str,
    eta_min_minutes: int,
    eta_max_minutes: int,
    *,
    x_driver: str,
    x_confidence: int,
    x_news_score: int,
    x_event_score: int,
) -> dict[str, Any]:
    return {
        "signal": signal,
        "symbol": symbol,
        "timeframe": "15m",
        "direction": direction,
        "priority": 4,
        "price": round(float(price), 2),
        "trend_1h": trend_1h,
        "status": "abnormal",
        "zone_low": round(float(zone_low), 2),
        "zone_high": round(float(zone_high), 2),
        "breakout_level": round(float(breakout_level), 2),
        "structure_basis": structure_basis,
        "abnormal_type": abnormal_type,
        "eta_min_minutes": int(eta_min_minutes),
        "eta_max_minutes": int(eta_max_minutes),
        "x_driver": x_driver,
        "x_confidence": int(x_confidence),
        "x_news_score": int(x_news_score),
        "x_event_score": int(x_event_score),
    }


def _recent_breakout_level_long(klines_15m: list[dict]) -> float:
    recent = klines_15m[-9:-1]
    return max(_float(k.get("high")) for k in recent)


def _recent_breakout_level_short(klines_15m: list[dict]) -> float:
    recent = klines_15m[-9:-1]
    return min(_float(k.get("low")) for k in recent)


def _parse_ts(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        return ts / 1000.0 if ts > 10_000_000_000 else ts
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            ts = float(text)
            return ts / 1000.0 if ts > 10_000_000_000 else ts
        except ValueError:
            pass
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None
    return None


def _now_ts(latest_15m: dict) -> float:
    open_time = _parse_ts(latest_15m.get("open_time"))
    if open_time is None:
        return datetime.now(tz=timezone.utc).timestamp()
    return open_time + 15 * 60


def _news_feed_path() -> Path:
    return Path(os.getenv("X_NEWS_FEED_FILE", "/opt/smct-alert/config/x_news_feed.json"))


def _load_news_events() -> list[dict[str, Any]]:
    path = _news_feed_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict):
        payload = payload.get("events", [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _symbol_aliases(symbol: str) -> set[str]:
    raw = symbol.upper()
    aliases = {raw}
    for suffix in ("USDT", "USD", "PERP"):
        if raw.endswith(suffix):
            aliases.add(raw[: -len(suffix)])
    return {item for item in aliases if item}


def _match_news_event(symbol: str, event: dict[str, Any]) -> bool:
    aliases = _symbol_aliases(symbol)
    symbols = event.get("symbols") or event.get("symbol") or event.get("assets") or []
    if isinstance(symbols, str):
        symbols = [symbols]
    symbols = {str(item).upper() for item in symbols if str(item).strip()}
    if not symbols:
        headline = str(event.get("headline") or event.get("title") or "").upper()
        return any(alias in headline for alias in aliases)
    return bool(aliases & symbols)


def _news_scores(symbol: str, latest_15m: dict) -> dict[str, Any]:
    events = _load_news_events()
    if not events:
        return {
            "long": 0,
            "short": 0,
            "driver": "none",
            "headline": "",
            "direction": "mixed",
        }
    now_ts = _now_ts(latest_15m)
    default_ttl = int(os.getenv("X_NEWS_TTL_MINUTES", "180") or 180)
    long_score = 0.0
    short_score = 0.0
    best_weight = -1.0
    best_driver = "none"
    best_headline = ""
    best_direction = "mixed"
    for event in events:
        if not _match_news_event(symbol, event):
            continue
        event_ts = _parse_ts(event.get("timestamp") or event.get("ts") or event.get("time"))
        if event_ts is None:
            continue
        ttl_minutes = int(event.get("ttl_minutes") or default_ttl)
        age_minutes = max(0.0, (now_ts - event_ts) / 60.0)
        if age_minutes > ttl_minutes:
            continue
        recency = max(0.15, 1.0 - age_minutes / max(ttl_minutes, 1))
        base_score = max(10.0, min(100.0, _float(event.get("score") or event.get("importance") or 50.0)))
        weight = base_score * recency
        direction = str(event.get("direction") or event.get("bias") or "mixed").lower()
        if direction == "long":
            long_score += weight
        elif direction == "short":
            short_score += weight
        else:
            long_score += weight * 0.5
            short_score += weight * 0.5
        if weight > best_weight:
            best_weight = weight
            best_driver = str(event.get("driver") or event.get("type") or "news")
            best_headline = str(event.get("headline") or event.get("title") or "")[:72]
            best_direction = direction
    return {
        "long": min(100, int(round(long_score))),
        "short": min(100, int(round(short_score))),
        "driver": best_driver,
        "headline": best_headline,
        "direction": best_direction,
    }


def _event_shape(latest: dict, prev: dict, klines_15m: list[dict]) -> dict[str, Any]:
    recent_4 = klines_15m[-4:]
    atr = _atr(latest)
    recent_high = _recent_breakout_level_long(klines_15m)
    recent_low = _recent_breakout_level_short(klines_15m)
    close = _float(latest.get("close"))
    high = _float(latest.get("high"))
    low = _float(latest.get("low"))
    open_ = _float(latest.get("open"))
    prev_close = _float(prev.get("close"))
    prev_high = _float(prev.get("high"))
    prev_low = _float(prev.get("low"))

    candle_range = max(high - low, 1e-9)
    body = abs(close - open_)
    body_ratio = body / candle_range
    upper_wick = max(0.0, high - max(open_, close))
    lower_wick = max(0.0, min(open_, close) - low)
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    range_ratio = candle_range / max(atr, 1e-9)

    breakout_cross_up = prev_close < recent_high and close > recent_high
    breakout_cross_down = prev_close > recent_low and close < recent_low
    fresh_break_up = max(prev_high, open_) <= recent_high + atr * 0.10
    fresh_break_down = min(prev_low, open_) >= recent_low - atr * 0.10
    impulse_up = breakout_cross_up and fresh_break_up and body_ratio >= 0.50 and range_ratio >= 1.05
    impulse_down = breakout_cross_down and fresh_break_down and body_ratio >= 0.50 and range_ratio >= 1.05

    hour_open = _float(recent_4[0].get("open"))
    hour_close = _float(recent_4[-1].get("close"))
    hour_high = max(_float(k.get("high")) for k in recent_4)
    hour_low = min(_float(k.get("low")) for k in recent_4)
    hour_range = max(hour_high - hour_low, 1e-9)
    hour_upper_wick = max(0.0, hour_high - max(hour_open, hour_close))
    hour_lower_wick = max(0.0, min(hour_open, hour_close) - hour_low)
    hour_upper_wick_ratio = hour_upper_wick / hour_range
    hour_lower_wick_ratio = hour_lower_wick / hour_range
    hour_break_up = hour_high >= recent_high + atr * 0.05 and hour_close >= recent_high - atr * 0.10
    hour_break_down = hour_low <= recent_low - atr * 0.05 and hour_close <= recent_low + atr * 0.10
    hour_pin_short = hour_high >= recent_high + atr * 0.05 and hour_close <= recent_high + atr * 0.12 and hour_upper_wick_ratio >= 0.35
    hour_pin_long = hour_low <= recent_low - atr * 0.05 and hour_close >= recent_low - atr * 0.12 and hour_lower_wick_ratio >= 0.35
    dual_sided_sweep = hour_high >= recent_high + atr * 0.05 and hour_low <= recent_low - atr * 0.05 and hour_range >= atr * 1.25
    dual_bias_short = dual_sided_sweep and hour_upper_wick_ratio >= hour_lower_wick_ratio * 1.03
    dual_bias_long = dual_sided_sweep and hour_lower_wick_ratio >= hour_upper_wick_ratio * 1.03

    return {
        "atr": atr,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "close": close,
        "high": high,
        "low": low,
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "range_ratio": range_ratio,
        "impulse_up": impulse_up,
        "impulse_down": impulse_down,
        "hour_break_up": hour_break_up,
        "hour_break_down": hour_break_down,
        "hour_pin_short": hour_pin_short,
        "hour_pin_long": hour_pin_long,
        "dual_bias_short": dual_bias_short,
        "dual_bias_long": dual_bias_long,
        "hour_close": hour_close,
        "hour_open": hour_open,
    }


def _driver_and_type(direction: str, shape: dict[str, Any], news: dict[str, Any]) -> tuple[str, str, list[str]]:
    basis: list[str] = []
    if direction == "long":
        if shape["impulse_up"] or shape["hour_break_up"]:
            basis.append("impulse_breakout_up")
            x_type = "起爆上破"
            driver = "price+volume"
        elif shape["hour_pin_long"]:
            basis.append("wick_rejection_down")
            x_type = "下插针扫流动性"
            driver = "liquidity_sweep"
        else:
            basis.append("dual_sided_sweep_long")
            x_type = "双边扫后偏多"
            driver = "liquidity_sweep"
    else:
        if shape["impulse_down"] or shape["hour_break_down"]:
            basis.append("impulse_breakdown_down")
            x_type = "起跌下破"
            driver = "price+volume"
        elif shape["hour_pin_short"]:
            basis.append("wick_rejection_up")
            x_type = "上插针扫流动性"
            driver = "liquidity_sweep"
        else:
            basis.append("dual_sided_sweep_short")
            x_type = "双边扫后偏空"
            driver = "liquidity_sweep"

    if news.get(direction, 0) >= 35:
        headline = news.get("headline") or "消息催化"
        driver = f"news+{driver}"
        x_type = f"消息驱动{ x_type }"
        basis.append("news_catalyst")
        basis.append(headline[:32])
    return driver, x_type, basis


def _event_scores(direction: str, latest: dict, latest_1h: dict, latest_4h: dict, latest_1d: dict, shape: dict[str, Any], news: dict[str, Any]) -> dict[str, Any]:
    vol_ratio_15m = _volume_ratio(latest)
    vol_ratio_1h = _volume_ratio(latest_1h)
    volume_score = 0
    volume_score += 3 if vol_ratio_15m >= 1.8 else 2 if vol_ratio_15m >= 1.35 else 1 if vol_ratio_15m >= 1.15 else 0
    volume_score += 3 if vol_ratio_1h >= 1.8 else 2 if vol_ratio_1h >= 1.35 else 1 if vol_ratio_1h >= 1.15 else 0

    price_score = 0
    price_score += 3 if shape["range_ratio"] >= 1.8 else 2 if shape["range_ratio"] >= 1.25 else 1 if shape["range_ratio"] >= 1.05 else 0
    price_score += 2 if abs(shape["close"] - _float(latest_1h.get("open"))) / max(shape["atr"], 1e-9) >= 1.0 else 0

    if direction == "long":
        structure_score = _count_true(shape["impulse_up"], shape["hour_break_up"], shape["hour_pin_long"], shape["dual_bias_long"])
        support_ok = _count_true(_price_above_stack(latest), _float(latest.get("close")) >= _float(latest.get("ema20")), _momentum_up(latest), _momentum_up(latest_1h))
        trend_score = _trend_score("long", latest_1h, latest_4h, latest_1d)
    else:
        structure_score = _count_true(shape["impulse_down"], shape["hour_break_down"], shape["hour_pin_short"], shape["dual_bias_short"])
        support_ok = _count_true(_price_below_stack(latest), _float(latest.get("close")) <= _float(latest.get("ema20")), _momentum_down(latest), _momentum_down(latest_1h))
        trend_score = _trend_score("short", latest_1h, latest_4h, latest_1d)

    news_score = news.get(direction, 0)
    total = price_score + volume_score + structure_score * 2 + min(4, support_ok) + min(4, trend_score // 2) + min(5, news_score // 20)
    return {
        "price_score": price_score,
        "volume_score": volume_score,
        "structure_score": structure_score,
        "support_score": support_ok,
        "trend_score": trend_score,
        "news_score": news_score,
        "total": total,
        "vol_ratio_15m": vol_ratio_15m,
        "vol_ratio_1h": vol_ratio_1h,
    }


def _should_emit_x(direction: str, scores: dict[str, Any], shape: dict[str, Any]) -> bool:
    event_present = scores["structure_score"] >= 1
    strong_combo = scores["price_score"] >= 2 and scores["volume_score"] >= 2 and scores["structure_score"] >= 1
    news_combo = scores["news_score"] >= 45 and scores["structure_score"] >= 1 and scores["price_score"] >= 1
    sweep_combo = scores["structure_score"] >= 2 and scores["price_score"] >= 1 and scores["volume_score"] >= 1
    return event_present and (scores["total"] >= 11 or strong_combo or news_combo or sweep_combo)


def _confidence(scores: dict[str, Any]) -> int:
    return max(35, min(95, int(round(scores["total"] * 7.5 + scores["news_score"] * 0.18))))


def _abnormal_type_text(x_type: str, driver: str, confidence: int, headline: str) -> str:
    driver_text = {
        "price+volume": "盘口放量驱动",
        "liquidity_sweep": "流动性扫单驱动",
        "news+price+volume": "消息+盘口驱动",
        "news+liquidity_sweep": "消息+扫流动性驱动",
    }.get(driver, driver)
    if headline:
        return f"{x_type}｜{driver_text}｜置信度{confidence}｜{headline}"
    return f"{x_type}｜{driver_text}｜置信度{confidence}"


def detect_abnormal_signals(
    symbol: str,
    klines_1d: list[dict],
    klines_4h: list[dict],
    klines_1h: list[dict],
    klines_15m: list[dict],
) -> list[dict[str, Any]]:
    """
    X 模块重构：
    - X 独立于 ABC，只负责非正常异动
    - 采用 价格 + 量能 + 结构 + 消息 四维评分，不再使用绝对放量二极管
    - 支持本地 news feed 文件增强消息面侦测
    - 同轮双向只保留更强的一边
    """
    if min(len(klines_15m), len(klines_1h), len(klines_4h), len(klines_1d)) < 12:
        return []

    latest = klines_15m[-1]
    prev = klines_15m[-2]
    latest_1h = klines_1h[-1]
    latest_4h = klines_4h[-1]
    latest_1d = klines_1d[-1]

    price = _float(latest.get("close"))
    shape = _event_shape(latest, prev, klines_15m)
    news = _news_scores(symbol, latest)

    candidates: list[dict[str, Any]] = []

    for direction in ("long", "short"):
        if direction == "long" and not _count_true(shape["impulse_up"], shape["hour_break_up"], shape["hour_pin_long"], shape["dual_bias_long"]):
            continue
        if direction == "short" and not _count_true(shape["impulse_down"], shape["hour_break_down"], shape["hour_pin_short"], shape["dual_bias_short"]):
            continue

        scores = _event_scores(direction, latest, latest_1h, latest_4h, latest_1d, shape, news)
        if not _should_emit_x(direction, scores, shape):
            continue

        trend_display = _trend_display(direction, scores["trend_score"])
        driver, x_type, basis = _driver_and_type(direction, shape, news)
        confidence = _confidence(scores)
        abnormal_type = _abnormal_type_text(x_type, driver, confidence, news.get("headline", ""))

        atr = shape["atr"]
        if direction == "long":
            breakout_level = shape["recent_high"] if (shape["impulse_up"] or shape["hour_break_up"]) else shape["recent_low"]
            zone_low = max(min(_float(latest.get("ema10")), _float(latest.get("ema20")), price), breakout_level - atr * 0.40)
            zone_high = max(price, shape["recent_high"] + atr * 0.22)
            extension = max(0.0, (price - _float(latest.get("ema20"))) / max(atr, 1e-9))
            signal_name = "X_BREAKOUT_LONG"
        else:
            breakout_level = shape["recent_low"] if (shape["impulse_down"] or shape["hour_break_down"]) else shape["recent_high"]
            zone_low = min(price, shape["recent_low"] - atr * 0.22)
            zone_high = min(max(_float(latest.get("ema10")), _float(latest.get("ema20")), price), breakout_level + atr * 0.40)
            extension = max(0.0, (_float(latest.get("ema20")) - price) / max(atr, 1e-9))
            signal_name = "X_BREAKOUT_SHORT"

        zone_low, zone_high = _normalize_zone(zone_low, zone_high)
        eta_min, eta_max = _window_from_extension(extension, max(scores["vol_ratio_15m"], scores["vol_ratio_1h"]), scores["news_score"])
        candidates.append(
            _signal_dict(
                signal_name,
                symbol,
                direction,
                price,
                trend_display,
                basis,
                zone_low,
                zone_high,
                breakout_level,
                abnormal_type,
                eta_min,
                eta_max,
                x_driver=driver,
                x_confidence=confidence,
                x_news_score=scores["news_score"],
                x_event_score=scores["total"],
            )
        )

    if len(candidates) <= 1:
        return candidates

    def _pick_score(sig: dict[str, Any]) -> tuple[int, int, int]:
        return (
            int(sig.get("x_confidence", 0)),
            int(sig.get("x_news_score", 0)),
            int(sig.get("x_event_score", 0)),
        )

    return [max(candidates, key=_pick_score)]
