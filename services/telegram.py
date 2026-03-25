import requests


TYPE_LABELS = {
    1: "A类",
    2: "B类",
    3: "C类",
    4: "X类",
}

ACTION_LABELS = {
    "A_LONG": "顺势做多机会",
    "A_SHORT": "顺势做空机会",
    "B_PULLBACK_LONG": "回踩后做多机会",
    "B_PULLBACK_SHORT": "反弹后做空机会",
    "C_LEFT_LONG": "左侧提前预警做多机会",
    "C_LEFT_SHORT": "左侧提前预警做空机会",
    "X_BREAKOUT_LONG": "异动放量上破预警",
    "X_BREAKOUT_SHORT": "异动放量下破预警",
}

TREND_LABELS = {
    "bull": "偏多（强）",
    "lean_bull": "偏多（弱）",
    "neutral": "中性",
    "lean_bear": "偏空（弱）",
    "bear": "偏空（强）",
}

DEFAULT_START_WINDOWS = {
    1: (5, 30),
    2: (15, 120),
    3: (60, 360),
    4: (5, 120),
}

TIMEOUT_OUTCOME_TEXT = {
    1: "则本轮信号大概率转弱",
    2: "则反弹/回踩预期下调",
    3: "则继续以观察为主，实战优先级下降",
    4: "则异动延续性下降，优先回归普通结构观察",
}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def action_label(signal: str) -> str:
    return ACTION_LABELS.get(signal, signal)


def trend_label(trend_1h: str) -> str:
    return TREND_LABELS.get(trend_1h, trend_1h)


def title_prefix(priority: int) -> str:
    return "🚨"


def _format_minutes_compact(minutes: int | None) -> str:
    if minutes is None:
        return ""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}分钟"
    hours, remain = divmod(minutes, 60)
    if remain == 0:
        return f"{hours}小时"
    return f"{hours}小时{remain}分钟"


def _get_window_minutes(
    priority: int,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> tuple[int, int]:
    default_min, default_max = DEFAULT_START_WINDOWS.get(priority, (15, 45))
    start_min = int(eta_min_minutes) if eta_min_minutes is not None else default_min
    end_min = int(eta_max_minutes) if eta_max_minutes is not None else default_max
    start_min = max(0, start_min)
    end_min = max(start_min, end_min)
    return start_min, end_min


def build_start_window_text(
    priority: int,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
    legacy_text: str | None = None,
) -> str:
    if legacy_text:
        return legacy_text
    start_min, end_min = _get_window_minutes(priority, eta_min_minutes, eta_max_minutes)
    start_text = _format_minutes_compact(start_min)
    end_text = _format_minutes_compact(end_min)
    return f"此条播报发出后 {start_text}—{end_text}内"


def timeout_text(
    priority: int,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> str:
    outcome_text = TIMEOUT_OUTCOME_TEXT.get(priority, "则本轮信号参考价值下降")
    return f"若超过预计启动时段仍未完成确认动作，{outcome_text}"


def build_status_text(signal: str, status: str) -> str:
    if signal == "A_LONG":
        return "已满足突破确认，等待顺势执行"
    if signal == "A_SHORT":
        return "已满足跌破确认，等待顺势执行"
    if signal == "B_PULLBACK_LONG":
        return "回踩条件满足，等待延续确认"
    if signal == "B_PULLBACK_SHORT":
        return "反弹条件满足，等待延续确认"
    if signal in ("C_LEFT_LONG", "C_LEFT_SHORT"):
        return "前提初步满足，处于早期观察阶段"
    if signal in ("X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"):
        return "异动已触发，进入特别关注阶段"
    if status == "active":
        return "条件已满足，等待执行"
    if status == "early":
        return "前提初步满足，处于观察阶段"
    return status


def _normalized_zone(
    entry_zone_low: float | None,
    entry_zone_high: float | None,
    price: float,
) -> tuple[float, float]:
    if entry_zone_low is None or entry_zone_high is None:
        pad = max(abs(float(price)) * 0.0012, 12.0)
        low = float(price) - pad * 0.5
        high = float(price) + pad * 0.5
    else:
        low = min(float(entry_zone_low), float(entry_zone_high))
        high = max(float(entry_zone_low), float(entry_zone_high))
        if abs(high - low) < max(abs(float(price)) * 0.0008, 8.0):
            pad = max(abs(float(price)) * 0.0012, 12.0)
            low -= pad * 0.5
            high += pad * 0.5
    return low, high


def zone_text(entry_zone_low: float | None, entry_zone_high: float | None, price: float) -> str:
    low, high = _normalized_zone(entry_zone_low, entry_zone_high, price)
    return f"{low:.2f} - {high:.2f}"


def _c_level_lines(signal: str, trigger_level: float | None, burst_level: float | None) -> str:
    lines: list[str] = []
    if signal == "C_LEFT_LONG":
        if trigger_level is not None:
            lines.append(f"初始突破位：{float(trigger_level):.2f}")
        if burst_level is not None:
            lines.append(f"拉升加速位：{float(burst_level):.2f}")
    elif signal == "C_LEFT_SHORT":
        if trigger_level is not None:
            lines.append(f"初始失守位：{float(trigger_level):.2f}")
        if burst_level is not None:
            lines.append(f"瀑布加速位：{float(burst_level):.2f}")
    return "\n".join(lines) + ("\n" if lines else "")


def _build_b_start_text(eta_min_minutes: int | None, eta_max_minutes: int | None) -> str:
    start_min, end_min = _get_window_minutes(2, eta_min_minutes, eta_max_minutes)
    start_text = _format_minutes_compact(start_min)
    end_text = _format_minutes_compact(end_min)
    return f"最早约在此条播报发出后 {start_text} 开始，最晚关注至 {end_text} 内"


def _format_b_message(
    signal: str,
    symbol: str,
    trend_text: str,
    status_text: str,
    entry_zone_low: float | None,
    entry_zone_high: float | None,
    price: float,
    eta_min_minutes: int | None,
    eta_max_minutes: int | None,
) -> str:
    prefix = title_prefix(2)
    action_text = action_label(signal)
    low, high = _normalized_zone(entry_zone_low, entry_zone_high, price)
    range_text = f"{low:.2f} - {high:.2f}"
    timing_text = _build_b_start_text(eta_min_minutes, eta_max_minutes)
    if signal == "B_PULLBACK_SHORT":
        zone_label = "预期反弹目标区"
        key_level_label = "关键上沿参考"
        key_level_value = f"{high:.2f}"
        timeout_hint = "若超出预计反弹时段仍未进入目标区，则本轮反弹预期下调"
        timing_label = "预期反弹启动"
    else:
        zone_label = "预期回踩承接区"
        key_level_label = "关键下沿参考"
        key_level_value = f"{low:.2f}"
        timeout_hint = "若超出预计回踩时段仍未进入承接区，则本轮回踩预期下调"
        timing_label = "预期回踩启动"

    return (
        f"{prefix} 交易提示｜B类\n"
        f"操作建议：{action_text}\n"
        f"标的：{symbol}\n"
        f"{timing_label}：{timing_text}\n"
        f"{zone_label}：{range_text}\n"
        f"{key_level_label}：{key_level_value}\n"
        f"总体趋势方向：{trend_text}\n"
        f"时效说明：{timeout_hint}\n"
        f"状态：{status_text}"
    )


def _format_x_message(
    signal: str,
    symbol: str,
    trend_text: str,
    status_text: str,
    entry_zone_low: float | None,
    entry_zone_high: float | None,
    price: float,
    eta_min_minutes: int | None,
    eta_max_minutes: int | None,
    trigger_level: float | None,
    abnormal_type: str | None = None,
) -> str:
    prefix = title_prefix(4)
    action_text = action_label(signal)
    start_window = build_start_window_text(4, eta_min_minutes, eta_max_minutes)
    timeout_hint = timeout_text(4, eta_min_minutes, eta_max_minutes)
    range_text = zone_text(entry_zone_low, entry_zone_high, price)

    if signal == "X_BREAKOUT_LONG":
        anomaly_type = abnormal_type or "放量上破 / 可能空头回补"
        trigger_label = "关键上破位"
        watch_label = "回踩观察区"
    else:
        anomaly_type = abnormal_type or "放量下破 / 可能多头踩踏"
        trigger_label = "关键下破位"
        watch_label = "反抽观察区"

    trigger_text = f"{float(trigger_level):.2f}" if trigger_level is not None else "-"

    return (
        f"{prefix} 异动预警｜X类\n"
        f"操作建议：{action_text}\n"
        f"标的：{symbol}\n"
        f"异动类型：{anomaly_type}\n"
        f"{trigger_label}：{trigger_text}\n"
        f"{watch_label}：{range_text}\n"
        f"总体趋势方向：{trend_text}\n"
        f"预计启动时段：{start_window}\n"
        f"时效说明：{timeout_hint}\n"
        f"状态：{status_text}"
    )


def format_engine_message(
    signal: str,
    symbol: str,
    timeframe: str,
    priority: int,
    price: float,
    trend_1h: str,
    status: str,
    entry_zone_low: float | None = None,
    entry_zone_high: float | None = None,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
    trigger_level: float | None = None,
    burst_level: float | None = None,
    abnormal_type: str | None = None,
    start_window_text_value: str | None = None,
    start_window_text: str | None = None,
    **_: object,
) -> str:
    signal_type = type_label(priority)
    status_text = build_status_text(signal, status)
    trend_text = trend_label(trend_1h)

    if priority == 2 and signal in {"B_PULLBACK_LONG", "B_PULLBACK_SHORT"}:
        return _format_b_message(
            signal=signal,
            symbol=symbol,
            trend_text=trend_text,
            status_text=status_text,
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            price=price,
            eta_min_minutes=eta_min_minutes,
            eta_max_minutes=eta_max_minutes,
        )

    if priority == 4 and signal in {"X_BREAKOUT_LONG", "X_BREAKOUT_SHORT"}:
        return _format_x_message(
            signal=signal,
            symbol=symbol,
            trend_text=trend_text,
            status_text=status_text,
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            price=price,
            eta_min_minutes=eta_min_minutes,
            eta_max_minutes=eta_max_minutes,
            trigger_level=trigger_level,
            abnormal_type=abnormal_type,
        )

    prefix = title_prefix(priority)
    action_text = action_label(signal)
    entry_zone_text = zone_text(entry_zone_low, entry_zone_high, price)
    start_window = build_start_window_text(
        priority,
        eta_min_minutes,
        eta_max_minutes,
        legacy_text=start_window_text_value or start_window_text,
    )
    timeout_hint = timeout_text(priority, eta_min_minutes, eta_max_minutes)
    c_level_lines = _c_level_lines(signal, trigger_level, burst_level)

    return (
        f"{prefix} 交易提示｜{signal_type}\n"
        f"操作建议：{action_text}\n"
        f"标的：{symbol}\n"
        f"参考价位区间：{entry_zone_text}\n"
        f"{c_level_lines}"
        f"总体趋势方向：{trend_text}\n"
        f"预计启动时段：{start_window}\n"
        f"时效说明：{timeout_hint}\n"
        f"状态：{status_text}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    response = requests.post(url, json=payload, timeout=20)
    return response.text
