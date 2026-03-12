import math


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def sma(values: list[float], period: int) -> list[float]:
    out = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        out.append(s / min(i + 1, period))
    return out


def rolling_std(values: list[float], period: int) -> list[float]:
    out = []
    for i in range(len(values)):
        start = max(0, i - period + 1)
        window = values[start : i + 1]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        out.append(math.sqrt(var))
    return out


def percentile_linear(values: list[float], period: int, percentile: float) -> list[float]:
    out = []
    p = percentile / 100.0
    for i in range(len(values)):
        start = max(0, i - period + 1)
        window = sorted(values[start : i + 1])
        if len(window) == 1:
            out.append(window[0])
            continue
        idx = (len(window) - 1) * p
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            out.append(window[lo])
        else:
            frac = idx - lo
            out.append(window[lo] * (1 - frac) + window[hi] * frac)
    return out


def rolling_low(values: list[float], period: int) -> list[float]:
    out = []
    for i in range(len(values)):
        start = max(0, i - period + 1)
        out.append(min(values[start : i + 1]))
    return out


def atr(klines: list[dict], period: int = 14) -> list[float]:
    if not klines:
        return []
    tr = [klines[0]["high"] - klines[0]["low"]]
    for i in range(1, len(klines)):
        high = klines[i]["high"]
        low = klines[i]["low"]
        prev_close = klines[i - 1]["close"]
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return ema(tr, period)


def macd_components(values: list[float], fast_len: int = 12, slow_len: int = 26, signal_len: int = 9):
    fast = ema(values, fast_len)
    slow = ema(values, slow_len)
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal_line = ema(macd_line, signal_len)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def sss_macd_for_eq_components(values: list[float], fast_len: int = 12, slow_len: int = 26, signal_len: int = 9):
    macd_line, signal_line, hist = macd_components(values, fast_len, slow_len, signal_len)

    warn_lookback = 100
    warn_smoothing = 5
    warn_sensitivity = 1.4

    sig_smoothed = ema(signal_line, warn_smoothing)
    sig_mean = sma(sig_smoothed, warn_lookback)
    sig_std = rolling_std(sig_smoothed, warn_lookback)

    z_scores = []
    overbought_warning = []
    oversold_warning = []

    for i in range(len(values)):
        std = sig_std[i]
        z = (sig_smoothed[i] - sig_mean[i]) / std if std != 0 else 0.0
        z_scores.append(z)
        overbought_warning.append(z > warn_sensitivity)
        oversold_warning.append(z < -warn_sensitivity)

    bull_div = [False] * len(values)
    bear_div = [False] * len(values)

    for i in range(2, len(values)):
        bull_div[i] = (
            values[i] <= values[i - 1] * 1.002
            and hist[i] > hist[i - 1]
            and hist[i - 1] <= 0
        )
        bear_div[i] = (
            values[i] >= values[i - 1] * 0.998
            and hist[i] < hist[i - 1]
            and hist[i - 1] >= 0
        )

    return {
        "sss_macd_line": macd_line,
        "sss_signal_line": signal_line,
        "sss_hist": hist,
        "sss_zscore": z_scores,
        "sss_overbought_warning": overbought_warning,
        "sss_oversold_warning": oversold_warning,
        "sss_bull_div": bull_div,
        "sss_bear_div": bear_div,
    }


def follow_line_components(klines: list[dict], atr_period: int = 5, bb_period: int = 21, bb_deviation: float = 1.0):
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]

    basis = sma(closes, bb_period)
    dev = rolling_std(closes, bb_period)
    bb_upper = [b + d * bb_deviation for b, d in zip(basis, dev)]
    bb_lower = [b - d * bb_deviation for b, d in zip(basis, dev)]
    atr_values = atr(klines, atr_period)

    fl_values = []
    fl_trend = []
    fl_buy = []
    fl_sell = []

    follow_line = None
    trend = 0

    for i in range(len(klines)):
        bb_signal = 0
        if closes[i] > bb_upper[i]:
            bb_signal = 1
        elif closes[i] < bb_lower[i]:
            bb_signal = -1

        if bb_signal == 1:
            candidate = lows[i] - atr_values[i]
            if follow_line is not None and candidate < follow_line:
                candidate = follow_line
            follow_line = candidate
        elif bb_signal == -1:
            candidate = highs[i] + atr_values[i]
            if follow_line is not None and candidate > follow_line:
                candidate = follow_line
            follow_line = candidate
        elif follow_line is None:
            follow_line = closes[i]

        prev_fl = fl_values[-1] if fl_values else follow_line
        if follow_line > prev_fl:
            new_trend = 1
        elif follow_line < prev_fl:
            new_trend = -1
        else:
            new_trend = trend

        fl_buy.append(trend == -1 and new_trend == 1)
        fl_sell.append(trend == 1 and new_trend == -1)

        trend = new_trend
        fl_values.append(follow_line)
        fl_trend.append(trend)

    return {
        "fl_value": fl_values,
        "fl_trend": fl_trend,
        "fl_buy_signal": fl_buy,
        "fl_sell_signal": fl_sell,
    }


def rsi_series(values: list[float], period: int = 14) -> list[float]:
    if not values:
        return []
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = ema(gains, period)
    avg_loss = ema(losses, period)

    out = []
    for g, l in zip(avg_gain, avg_loss):
        if l == 0:
            out.append(100.0)
        else:
            rs = g / l
            out.append(100 - 100 / (1 + rs))
    return out


def rar_components(values: list[float], length: int = 15, power: float = 1.0):
    ama = []
    current_ama = values[0]

    for i, value in enumerate(values):
        prev_ama = current_ama if i > 0 else value
        alpha_source = value - prev_ama
        alpha = min(1.0, abs(alpha_source) / max(abs(value), 1e-9))
        current_ama = prev_ama + (alpha**power) * (value - prev_ama)
        ama.append(current_ama)

    rar_value = rsi_series(ama, length)
    ema_src_half = ema(values, max(1, length // 2))
    rar_trigger = rsi_series(ema(ema_src_half, length), max(1, length // 2))
    rar_spread = [abs(a - b) for a, b in zip(rar_value, rar_trigger)]
    rar_spread_ma = sma(rar_spread, length)
    rar_trend_strong = [rar_spread[i] <= rar_spread_ma[i] for i in range(len(rar_spread))]

    return {
        "rar_value": rar_value,
        "rar_trigger": rar_trigger,
        "rar_spread": rar_spread,
        "rar_trend_strong": rar_trend_strong,
    }


def tai_components(klines: list[dict], len_form: int = 20, len_hist: int = 252):
    dollar_vol = [k["close"] * k["volume"] for k in klines]
    dollar_vol_avg = sma(dollar_vol, len_form)
    vscale = [math.log(max(v, 1e-10)) for v in dollar_vol_avg]

    p20 = percentile_linear(vscale, len_hist, 20)
    p40 = percentile_linear(vscale, len_hist, 40)
    p60 = percentile_linear(vscale, len_hist, 60)
    p80 = percentile_linear(vscale, len_hist, 80)

    tai_floor = rolling_low(vscale, len_hist)

    tai_icepoint_threshold = []
    tai_is_icepoint = []
    for v, floor_v, p20_v in zip(vscale, tai_floor, p20):
        threshold = floor_v + max(p20_v - floor_v, 0.0) * 0.30
        tai_icepoint_threshold.append(threshold)
        tai_is_icepoint.append(v <= threshold)

    tai_rising = [False] + [vscale[i] > vscale[i - 1] for i in range(1, len(vscale))]

    return {
        "tai_value": vscale,
        "tai_p20": p20,
        "tai_p40": p40,
        "tai_p60": p60,
        "tai_p80": p80,
        "tai_floor": tai_floor,
        "tai_icepoint_threshold": tai_icepoint_threshold,
        "tai_is_icepoint": tai_is_icepoint,
        "tai_rising": tai_rising,
    }


def cm_macd_mtf_components(values: list[float]):
    macd_line, _, _ = macd_components(values, 12, 26, 9)
    signal_line = sma(macd_line, 9)
    hist = [m - s for m, s in zip(macd_line, signal_line)]

    cm_macd_above_signal = [m >= s for m, s in zip(macd_line, signal_line)]
    cm_hist_up = [False] + [hist[i] > hist[i - 1] for i in range(1, len(hist))]
    cm_hist_down = [False] + [hist[i] < hist[i - 1] for i in range(1, len(hist))]

    return {
        "cm_macd": macd_line,
        "cm_signal": signal_line,
        "cm_hist": hist,
        "cm_macd_above_signal": cm_macd_above_signal,
        "cm_hist_up": cm_hist_up,
        "cm_hist_down": cm_hist_down,
    }


def enrich_klines(klines: list[dict]) -> list[dict]:
    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]

    ema10 = ema(closes, 10)
    ema20 = ema(closes, 20)
    ema120 = ema(closes, 120)
    ema169 = ema(closes, 169)
    atr14 = atr(klines, 14)
    vol20 = sma(volumes, 20)

    sss = sss_macd_for_eq_components(closes)
    fl = follow_line_components(klines)
    rar = rar_components(closes)
    tai = tai_components(klines)
    cm = cm_macd_mtf_components(closes)

    enriched = []
    for i, k in enumerate(klines):
        item = dict(k)
        item.update(
            {
                "ema10": ema10[i],
                "ema20": ema20[i],
                "ema120": ema120[i],
                "ema169": ema169[i],
                "atr": atr14[i],
                "vol_sma20": vol20[i],
                "sss_macd_line": sss["sss_macd_line"][i],
                "sss_signal_line": sss["sss_signal_line"][i],
                "sss_hist": sss["sss_hist"][i],
                "sss_zscore": sss["sss_zscore"][i],
                "sss_overbought_warning": sss["sss_overbought_warning"][i],
                "sss_oversold_warning": sss["sss_oversold_warning"][i],
                "sss_bull_div": sss["sss_bull_div"][i],
                "sss_bear_div": sss["sss_bear_div"][i],
                "fl_value": fl["fl_value"][i],
                "fl_trend": fl["fl_trend"][i],
                "fl_buy_signal": fl["fl_buy_signal"][i],
                "fl_sell_signal": fl["fl_sell_signal"][i],
                "rar_value": rar["rar_value"][i],
                "rar_trigger": rar["rar_trigger"][i],
                "rar_spread": rar["rar_spread"][i],
                "rar_trend_strong": rar["rar_trend_strong"][i],
                "tai_value": tai["tai_value"][i],
                "tai_p20": tai["tai_p20"][i],
                "tai_p40": tai["tai_p40"][i],
                "tai_p60": tai["tai_p60"][i],
                "tai_p80": tai["tai_p80"][i],
                "tai_floor": tai["tai_floor"][i],
                "tai_icepoint_threshold": tai["tai_icepoint_threshold"][i],
                "tai_is_icepoint": tai["tai_is_icepoint"][i],
                "tai_rising": tai["tai_rising"][i],
                "cm_macd": cm["cm_macd"][i],
                "cm_signal": cm["cm_signal"][i],
                "cm_hist": cm["cm_hist"][i],
                "cm_macd_above_signal": cm["cm_macd_above_signal"][i],
                "cm_hist_up": cm["cm_hist_up"][i],
                "cm_hist_down": cm["cm_hist_down"][i],
            }
        )
        enriched.append(item)
    return enriched
