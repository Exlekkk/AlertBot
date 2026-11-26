"""Multi-scale liquidity sweep evidence (closed-candle approximation).

Builds a per-timeframe map of upper / lower liquidity levels from fast / mid /
slow rolling extremes, retires levels on wick trade-through or max age, and
emits a sweep evidence event only after price clears at least two visibly
distinct bands, the average band strength clears the engine threshold, and
price closes back beyond the reclaim level within two bars.

Timeframes are independent: a higher-timeframe map (alive vs ended) is never
revived by a lower-timeframe path signal. Trade-drawing targets and stops are
not produced and must not enter alerts; location still comes from OTE / IFVG /
POC elsewhere.

Engineering evidence only — not a solo formal entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


# Engine defaults (detection only). Trade-drawing risk / expiry knobs are
# intentionally unused: this module never emits TP / SL geometry.
_SHIFT_COMPARE_BARS = 3
_LEVEL_MERGE_TICKS = 2
_CLEANUP_BARS = 10
_VOLUME_AVERAGE_BARS = 100
_MAX_VOLUME_SCORE_PER_BAR = 3.0
_STRENGTH_CAP = 50.0
_CLOSEST_LEVEL_WEIGHT = 1.0
_SECOND_LEVEL_WEIGHT = 0.25
_THIRD_LEVEL_WEIGHT = 0.05
_MIN_VISIBLE_BANDS = 2
_RECLAIM_BARS = 2
_RECENT_SIGNAL_BARS = 6
_ENDED_MEMORY = 48


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _cfg() -> dict[str, Any]:
    raw = TREND_ENGINE_CONFIG.get("sweep_hunter", {})
    return raw if isinstance(raw, dict) else {}


def _engine_params() -> dict[str, Any]:
    cfg = _cfg()
    return {
        "fast_bars": int(cfg.get("fast_bars", 14)),
        "mid_bars": int(cfg.get("mid_bars", 42)),
        "slow_bars": int(cfg.get("slow_bars", 120)),
        "max_age": int(cfg.get("max_age", 1000)),
        "remove_on": str(cfg.get("remove_on", "wick")).lower(),
        "range_lookback": int(cfg.get("range_lookback", 777)),
        "price_resolution": int(cfg.get("price_resolution", 200)),
        "cell_width": int(cfg.get("cell_width", 5)),
        "filter_by_strength": bool(cfg.get("filter_by_strength", True)),
        "strength_threshold": float(cfg.get("strength_threshold", 33.0)),
    }


def _count_decimals(value: float) -> int:
    text = f"{value:.10f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".")[1])


def _infer_tick(klines: list[dict[str, Any]]) -> float:
    """Exchange-style tick from printed decimals — not candle range size."""
    dmax = 0
    for k in klines[-80:]:
        for key in ("open", "high", "low", "close"):
            dmax = max(dmax, _count_decimals(_f(k.get(key))))
    return 10 ** (-dmax) if dmax > 0 else 0.01


def _round_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    return round(round(price / tick) * tick, 10)


def _rolling_extreme(values: list[float], end: int, length: int, want_high: bool) -> float | None:
    start = end - length + 1
    if start < 0 or end >= len(values) or length <= 0:
        return None
    window = values[start : end + 1]
    if not window:
        return None
    return max(window) if want_high else min(window)


def _shift_locked(current: float | None, lagged: float | None, previous: float | None, *, upward: bool) -> bool:
    if current is None or lagged is None or previous is None:
        return False
    if current == lagged:
        return False
    moved = current > lagged if upward else current < lagged
    return moved and current == previous


@dataclass
class _Level:
    price: float
    birth: int
    strength: float = 0.0
    last_norm: float | None = None
    last_cell_height: float | None = None
    last_draw_bar: int | None = None


@dataclass
class _PendingSweep:
    bar: int
    reclaim_level: float
    layers: int = 0
    strength: float = 0.0


@dataclass
class _EndedLevel:
    price: float
    side: str
    reason: str
    ended_bar: int


@dataclass
class _SideMap:
    descending: bool
    levels: list[_Level] = field(default_factory=list)
    pending: list[_PendingSweep] = field(default_factory=list)
    ended: list[_EndedLevel] = field(default_factory=list)
    stored_extremes: list[float | None] = field(default_factory=lambda: [None, None, None])

    def _side_name(self) -> str:
        return "buy_side" if self.descending else "sell_side"

    def _insert_index(self, price: float) -> int:
        lo, hi = 0, len(self.levels)
        while lo < hi:
            mid = (lo + hi) // 2
            mid_price = self.levels[mid].price
            if self.descending:
                if mid_price > price:
                    lo = mid + 1
                else:
                    hi = mid
            else:
                if mid_price < price:
                    lo = mid + 1
                else:
                    hi = mid
        return lo

    def add(self, raw_price: float, bar_index: int, tick: float, tolerance: float) -> None:
        price = _round_to_tick(raw_price, tick)
        idx = self._insert_index(price)
        match: int | None = None
        best: float | None = None
        if idx < len(self.levels):
            dist = abs(self.levels[idx].price - price)
            if dist <= tolerance:
                match = idx
                best = dist
        if idx > 0:
            dist = abs(self.levels[idx - 1].price - price)
            if dist <= tolerance and (best is None or dist < best):
                match = idx - 1
        if match is None:
            self.levels.insert(idx, _Level(price=price, birth=bar_index))
        else:
            self.levels[match].birth = bar_index

    def prune_expired(self, bar_index: int, max_age: int) -> None:
        kept: list[_Level] = []
        for lv in self.levels:
            if bar_index - lv.birth > max_age:
                self._remember_ended(lv, bar_index, "expired")
            else:
                kept.append(lv)
        self.levels = kept

    def mitigate(self, mitigation_price: float, bar_index: int) -> int:
        removed = 0
        while self.levels:
            last = self.levels[-1]
            hit = last.price <= mitigation_price if self.descending else last.price >= mitigation_price
            if not hit:
                break
            self._remember_ended(last, bar_index, "wick")
            self.levels.pop()
            removed += 1
        return removed

    def _remember_ended(self, lv: _Level, bar_index: int, reason: str) -> None:
        self.ended.append(
            _EndedLevel(price=lv.price, side=self._side_name(), reason=reason, ended_bar=bar_index)
        )
        if len(self.ended) > _ENDED_MEMORY:
            self.ended = self.ended[-_ENDED_MEMORY:]

    def visible_sweep_stats(
        self, wick: float, bar_index: int, max_visible_age: int
    ) -> tuple[int, float | None, float]:
        band_count = 0
        reclaim: float | None = None
        strength_sum = 0.0
        band_open = False
        band_edge: float | None = None
        band_strength = 0.0

        for lv in reversed(self.levels):
            swept = lv.price <= wick if self.descending else lv.price >= wick
            if not swept:
                break
            recently = lv.last_draw_bar is not None and bar_index - lv.last_draw_bar <= max_visible_age
            visible = (
                recently
                and lv.last_norm is not None
                and lv.last_cell_height is not None
                and lv.last_cell_height > 0.0
            )
            if not visible:
                continue
            half = lv.last_cell_height * 0.5
            level_bottom = lv.price - half
            level_top = lv.price + half
            if reclaim is None:
                reclaim = lv.price
            else:
                reclaim = min(reclaim, lv.price) if self.descending else max(reclaim, lv.price)

            if not band_open:
                band_open = True
                band_edge = level_top if self.descending else level_bottom
                band_strength = lv.last_norm
            else:
                overlaps = (
                    level_bottom <= band_edge if self.descending else level_top >= (band_edge or 0.0)
                )
                if overlaps:
                    if self.descending:
                        band_edge = max(band_edge or level_top, level_top)
                    else:
                        band_edge = min(band_edge or level_bottom, level_bottom)
                    band_strength = max(band_strength, lv.last_norm)
                else:
                    band_count += 1
                    strength_sum += band_strength
                    band_edge = level_top if self.descending else level_bottom
                    band_strength = lv.last_norm

        if band_open:
            band_count += 1
            strength_sum += band_strength

        avg = strength_sum / band_count if band_count else 0.0
        return band_count, reclaim, avg

    def resolve(self, close: float, bar_index: int, max_bars: int) -> _PendingSweep | None:
        fired: _PendingSweep | None = None
        kept: list[_PendingSweep] = []
        for item in self.pending:
            age = bar_index - item.bar
            if age > max_bars:
                continue
            recrossed = close < item.reclaim_level if self.descending else close > item.reclaim_level
            if recrossed:
                fired = item
                continue
            kept.append(item)
        self.pending = kept
        return fired

    def nearest_active(self, close: float, bar_index: int, max_age: int) -> list[tuple[int, _Level]]:
        found: list[tuple[int, _Level]] = []
        for i in range(len(self.levels) - 1, -1, -1):
            lv = self.levels[i]
            on_side = lv.price > close if self.descending else lv.price < close
            if on_side and bar_index - lv.birth <= max_age:
                found.append((i, lv))
                if len(found) >= 3:
                    break
        return found

    def active_payload(self) -> list[dict[str, Any]]:
        side = self._side_name()
        return [
            {"price": round(lv.price, 2), "side": side, "strength": round(lv.strength, 3)}
            for lv in self.levels
        ][-12:]

    def ended_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "price": round(item.price, 2),
                "side": item.side,
                "reason": item.reason,
                "ended_bar": item.ended_bar,
            }
            for item in self.ended[-12:]
        ]


def _add_strength(lv: _Level | None, amount: float) -> None:
    if lv is None or amount <= 0:
        return
    lv.strength = min(lv.strength + amount, _STRENGTH_CAP)


def _heatmap_norm(strength: float, max_strength: float) -> float:
    if max_strength <= 0:
        return 0.0
    return max(0.0, min(1.0, strength / max_strength))


def _empty_context(params: dict[str, Any], timeframe: str, reason: str) -> dict[str, Any]:
    return {
        "side": None,
        "level": None,
        "swept": False,
        "reclaim_or_reject": None,
        "strength": 0.0,
        "approx": True,
        "candle_proxy": True,
        "bars_since": None,
        "active_levels": [],
        "ended_levels": [],
        "legacy_sweep_type": "none",
        "recent_sweep_valid": False,
        "reason": reason,
        "timeframe": timeframe,
        "layers_swept": 0,
        "path": None,
        "params": dict(params),
    }


def build_sweep_context(
    klines: list[dict[str, Any]],
    timeframe: str = "1h",
) -> dict[str, Any]:
    """Sweep context plus legacy liquidity field mapping. Not a solo entry."""
    params = _engine_params()
    fast = params["fast_bars"]
    mid = params["mid_bars"]
    slow = params["slow_bars"]
    max_age = params["max_age"]
    remove_on_wick = params["remove_on"] != "close"
    range_lookback = max(1, params["range_lookback"])
    price_resolution = max(1, params["price_resolution"])
    cell_width = max(1, params["cell_width"])
    filter_by_strength = params["filter_by_strength"]
    strength_floor = max(0.0, params["strength_threshold"]) / 100.0

    empty = _empty_context(params, timeframe, "insufficient_history")
    min_bars = slow + _SHIFT_COMPARE_BARS + 5
    if len(klines) < min_bars:
        return empty

    highs = [_f(k.get("high")) for k in klines]
    lows = [_f(k.get("low")) for k in klines]
    closes = [_f(k.get("close")) for k in klines]
    opens = [_f(k.get("open"), closes[i] if i < len(closes) else 0.0) for i, k in enumerate(klines)]
    volumes = [_f(k.get("volume")) for k in klines]
    n = len(klines)
    tick = _infer_tick(klines)
    tolerance = tick * _LEVEL_MERGE_TICKS

    uppers = _SideMap(descending=True)
    lowers = _SideMap(descending=False)

    last_signal: dict[str, Any] | None = None

    for i in range(n):
        h1 = _rolling_extreme(highs, i, fast, True)
        h2 = _rolling_extreme(highs, i, mid, True)
        h3 = _rolling_extreme(highs, i, slow, True)
        l1 = _rolling_extreme(lows, i, fast, False)
        l2 = _rolling_extreme(lows, i, mid, False)
        l3 = _rolling_extreme(lows, i, slow, False)

        h1_lag = _rolling_extreme(highs, i - _SHIFT_COMPARE_BARS, fast, True) if i >= _SHIFT_COMPARE_BARS else None
        h2_lag = _rolling_extreme(highs, i - _SHIFT_COMPARE_BARS, mid, True) if i >= _SHIFT_COMPARE_BARS else None
        h3_lag = _rolling_extreme(highs, i - _SHIFT_COMPARE_BARS, slow, True) if i >= _SHIFT_COMPARE_BARS else None
        l1_lag = _rolling_extreme(lows, i - _SHIFT_COMPARE_BARS, fast, False) if i >= _SHIFT_COMPARE_BARS else None
        l2_lag = _rolling_extreme(lows, i - _SHIFT_COMPARE_BARS, mid, False) if i >= _SHIFT_COMPARE_BARS else None
        l3_lag = _rolling_extreme(lows, i - _SHIFT_COMPARE_BARS, slow, False) if i >= _SHIFT_COMPARE_BARS else None

        h1_prev = _rolling_extreme(highs, i - 1, fast, True) if i >= 1 else None
        h2_prev = _rolling_extreme(highs, i - 1, mid, True) if i >= 1 else None
        h3_prev = _rolling_extreme(highs, i - 1, slow, True) if i >= 1 else None
        l1_prev = _rolling_extreme(lows, i - 1, fast, False) if i >= 1 else None
        l2_prev = _rolling_extreme(lows, i - 1, mid, False) if i >= 1 else None
        l3_prev = _rolling_extreme(lows, i - 1, slow, False) if i >= 1 else None

        h_shifts = [
            h1 is not None and (uppers.stored_extremes[0] is None or _shift_locked(h1, h1_lag, h1_prev, upward=True)),
            h2 is not None and (uppers.stored_extremes[1] is None or _shift_locked(h2, h2_lag, h2_prev, upward=True)),
            h3 is not None and (uppers.stored_extremes[2] is None or _shift_locked(h3, h3_lag, h3_prev, upward=True)),
        ]
        l_shifts = [
            l1 is not None and (lowers.stored_extremes[0] is None or _shift_locked(l1, l1_lag, l1_prev, upward=False)),
            l2 is not None and (lowers.stored_extremes[1] is None or _shift_locked(l2, l2_lag, l2_prev, upward=False)),
            l3 is not None and (lowers.stored_extremes[2] is None or _shift_locked(l3, l3_lag, l3_prev, upward=False)),
        ]
        h_vals = [h1, h2, h3]
        l_vals = [l1, l2, l3]
        for j, flag in enumerate(h_shifts):
            if flag and h_vals[j] is not None:
                uppers.stored_extremes[j] = h_vals[j]
        for j, flag in enumerate(l_shifts):
            if flag and l_vals[j] is not None:
                lowers.stored_extremes[j] = l_vals[j]

        high = highs[i]
        low = lows[i]
        close = closes[i]
        open_px = opens[i]
        upper_mitigation = high if remove_on_wick else close
        lower_mitigation = low if remove_on_wick else close

        upper_bands, upper_reclaim, upper_avg = uppers.visible_sweep_stats(high, i, cell_width)
        lower_bands, lower_reclaim, lower_avg = lowers.visible_sweep_stats(low, i, cell_width)

        uppers.mitigate(upper_mitigation, i)
        lowers.mitigate(lower_mitigation, i)

        upper_ok = (not filter_by_strength) or upper_avg >= strength_floor
        lower_ok = (not filter_by_strength) or lower_avg >= strength_floor
        if remove_on_wick and upper_bands >= _MIN_VISIBLE_BANDS and upper_ok and upper_reclaim is not None:
            uppers.pending.append(
                _PendingSweep(bar=i, reclaim_level=upper_reclaim, layers=upper_bands, strength=upper_avg)
            )
        if remove_on_wick and lower_bands >= _MIN_VISIBLE_BANDS and lower_ok and lower_reclaim is not None:
            lowers.pending.append(
                _PendingSweep(bar=i, reclaim_level=lower_reclaim, layers=lower_bands, strength=lower_avg)
            )

        bearish = uppers.resolve(close, i, _RECLAIM_BARS)
        bullish = lowers.resolve(close, i, _RECLAIM_BARS)
        if bearish is not None:
            last_signal = {
                "side": "buy_side",
                "reclaim_or_reject": "reject",
                "level": bearish.reclaim_level,
                "strength": bearish.strength,
                "bars_since": 0,
                "bar": i,
                "layers_swept": bearish.layers,
            }
        if bullish is not None:
            last_signal = {
                "side": "sell_side",
                "reclaim_or_reject": "reclaim",
                "level": bullish.reclaim_level,
                "strength": bullish.strength,
                "bars_since": 0,
                "bar": i,
                "layers_swept": bullish.layers,
            }

        if i % _CLEANUP_BARS == 0:
            uppers.prune_expired(i, max_age)
            lowers.prune_expired(i, max_age)

        if h_shifts[0] and h1 is not None:
            uppers.add(h1, i, tick, tolerance)
        if h_shifts[1] and h2 is not None:
            uppers.add(h2, i, tick, tolerance)
        if h_shifts[2] and h3 is not None:
            uppers.add(h3, i, tick, tolerance)
        if l_shifts[0] and l1 is not None:
            lowers.add(l1, i, tick, tolerance)
        if l_shifts[1] and l2 is not None:
            lowers.add(l2, i, tick, tolerance)
        if l_shifts[2] and l3 is not None:
            lowers.add(l3, i, tick, tolerance)

        near_up = uppers.nearest_active(close, i, max_age)
        near_down = lowers.nearest_active(close, i, max_age)

        start_vol = max(0, i - _VOLUME_AVERAGE_BARS + 1)
        window_vol = volumes[start_vol : i + 1]
        bar_volume = volumes[i]
        vol_avg = (sum(window_vol) / len(window_vol)) if window_vol else bar_volume
        safe_avg = bar_volume if vol_avg <= 0 else vol_avg
        raw_norm = (bar_volume / safe_avg) if safe_avg > 0 else 0.0
        norm_vol = min(raw_norm, _MAX_VOLUME_SCORE_PER_BAR)
        direction = 1.0 if close > open_px else -1.0 if close < open_px else 0.0
        signed = norm_vol * direction
        if signed < 0.0:
            contrib = abs(signed)
            weights = (_CLOSEST_LEVEL_WEIGHT, _SECOND_LEVEL_WEIGHT, _THIRD_LEVEL_WEIGHT)
            for w, pair in zip(weights, near_up):
                _add_strength(pair[1], contrib * w)
        elif signed > 0.0:
            weights = (_CLOSEST_LEVEL_WEIGHT, _SECOND_LEVEL_WEIGHT, _THIRD_LEVEL_WEIGHT)
            for w, pair in zip(weights, near_down):
                _add_strength(pair[1], signed * w)

        strengths = [lv.strength for _, lv in near_up + near_down]
        max_strength = max(strengths) if strengths else 0.0

        lookback_end = i
        lookback_start = max(0, lookback_end - range_lookback + 1)
        hm_high = max(highs[lookback_start : lookback_end + 1]) if lookback_end >= 0 else high
        hm_low = min(lows[lookback_start : lookback_end + 1]) if lookback_end >= 0 else low
        price_range = max(hm_high - hm_low, tick * price_resolution)
        cell_height = price_range / price_resolution

        if (i + 1) % cell_width == 0:
            for _, lv in near_up + near_down:
                lv.last_norm = _heatmap_norm(lv.strength, max_strength)
                lv.last_cell_height = cell_height
                lv.last_draw_bar = i

        if last_signal is not None and last_signal.get("bar") is not None:
            last_signal["bars_since"] = i - int(last_signal["bar"])

    # Recover reclaim level stored at signal time; strength/layers already set.
    if last_signal is not None:
        bars_since = int(last_signal.get("bars_since") or 0)
        level = last_signal.get("level")
        legacy = "buyside" if last_signal["side"] == "buy_side" else "sellside"
        return {
            "side": last_signal["side"],
            "level": None if level is None else round(float(level), 2),
            "swept": True,
            "reclaim_or_reject": last_signal["reclaim_or_reject"],
            "strength": round(float(last_signal.get("strength") or 0.0), 3),
            "approx": True,
            "candle_proxy": True,
            "bars_since": bars_since,
            "active_levels": uppers.active_payload() + lowers.active_payload(),
            "ended_levels": uppers.ended_payload() + lowers.ended_payload(),
            "legacy_sweep_type": legacy,
            "recent_sweep_valid": bars_since <= _RECENT_SIGNAL_BARS,
            "reason": "multi_level_sweep_reclaim",
            "timeframe": timeframe,
            "layers_swept": int(last_signal.get("layers_swept") or 0),
            "path": None,
            "params": dict(params),
        }

    out = _empty_context(params, timeframe, "no_recent_sweep")
    out["active_levels"] = uppers.active_payload() + lowers.active_payload()
    out["ended_levels"] = uppers.ended_payload() + lowers.ended_payload()
    return out


def attach_path_context(map_ctx: dict[str, Any], path_ctx: dict[str, Any] | None) -> dict[str, Any]:
    """Attach a lower-TF path view onto a higher-TF map without reviving ended lines.

    The map context (typically 1H) stays the source of truth for whether a
    level is alive. A path signal (typically 15m) is recorded as `path` only;
    it cannot re-insert an ended map level into `active_levels` or flip the
    map's `swept` / `recent_sweep_valid` flags.
    """
    out = dict(map_ctx or {})
    out["active_levels"] = list(out.get("active_levels") or [])
    out["ended_levels"] = list(out.get("ended_levels") or [])
    if not path_ctx:
        out["path"] = None
        return out

    path = {
        "timeframe": path_ctx.get("timeframe"),
        "side": path_ctx.get("side"),
        "level": path_ctx.get("level"),
        "swept": bool(path_ctx.get("swept")),
        "reclaim_or_reject": path_ctx.get("reclaim_or_reject"),
        "recent_sweep_valid": bool(path_ctx.get("recent_sweep_valid")),
        "bars_since": path_ctx.get("bars_since"),
        "layers_swept": path_ctx.get("layers_swept") or 0,
        "strength": path_ctx.get("strength") or 0.0,
        "reason": path_ctx.get("reason"),
    }
    out["path"] = path

    ended = out["ended_levels"]
    if not ended:
        return out

    # Path may not refresh a dead map line at the same price.
    def _ended_hit(price: Any) -> bool:
        if price is None:
            return False
        try:
            px = float(price)
        except (TypeError, ValueError):
            return False
        for item in ended:
            try:
                if abs(float(item.get("price")) - px) <= 0.01 * _LEVEL_MERGE_TICKS:
                    return True
            except (TypeError, ValueError, AttributeError):
                continue
        return False

    # Defensive: an ended map price must not remain in active_levels, even if
    # the path view just printed a signal there.
    out["active_levels"] = [
        lv
        for lv in out["active_levels"]
        if not (isinstance(lv, dict) and _ended_hit(lv.get("price")))
    ]
    return out


def merge_sweep_into_liquidity(liq: dict[str, Any], sweep: dict[str, Any]) -> dict[str, Any]:
    """When hunter has a recent valid sweep, overlay onto legacy liq fields."""
    out = dict(liq or {})
    out["sweep_hunter"] = sweep
    if not sweep or not sweep.get("swept") or not sweep.get("recent_sweep_valid"):
        return out
    bars = sweep.get("bars_since")
    legacy_bars = out.get("bars_since_sweep")
    hunter_fresher = bars is not None and (legacy_bars is None or int(bars) <= int(legacy_bars))
    if hunter_fresher:
        out["sweep_type"] = sweep.get("legacy_sweep_type", "none")
        out["reclaim_or_reject"] = sweep.get("reclaim_or_reject") or "none"
        out["sweep_level"] = sweep.get("level")
        out["bars_since_sweep"] = bars
        out["recent_sweep_valid"] = True
        out["sweep_source"] = "sweep_hunter"
    return out


__all__ = ["attach_path_context", "build_sweep_context", "merge_sweep_into_liquidity"]
