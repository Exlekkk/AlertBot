def format_engine_message(
    signal: str,
    symbol: str,
    timeframe: str,
    priority: int,
    price: float,
    trend_1h: str,
    status: str,
) -> str:
    type_map = {
        1: "A类",
        2: "B类",
        3: "C类",
    }

    action_map = {
        "A_LONG": "顺势做多机会",
        "A_SHORT": "顺势做空机会",
        "B_PULLBACK_LONG": "回踩后做多机会",
        "B_PULLBACK_SHORT": "反弹后做空机会",
        "C_LEFT_LONG": "左侧提前预警做多机会",
        "C_LEFT_SHORT": "左侧提前预警做空机会",
    }

    status_map = {
        "A_LONG": "已满足突破确认，等待顺势执行",
        "A_SHORT": "已满足跌破确认，等待顺势执行",
        "B_PULLBACK_LONG": "回踩条件满足，等待延续确认",
        "B_PULLBACK_SHORT": "反弹条件满足，等待延续确认",
        "C_LEFT_LONG": "前提初步满足，处于早期观察阶段",
        "C_LEFT_SHORT": "前提初步满足，处于早期观察阶段",
    }

    trend_map = {
        "bull": "偏多",
        "bear": "偏空",
        "lean_bull": "偏多（弱）",
        "lean_bear": "偏空（弱）",
        "neutral": "中性",
    }

    signal_type = type_map.get(priority, f"{priority}类")
    action_text = action_map.get(signal, signal)
    status_text = status_map.get(signal, status)
    trend_text = trend_map.get(trend_1h, trend_1h)

    return (
        "📡 交易预警\n"
        f"类型: {signal_type}\n"
        f"操作建议: {action_text}\n"
        f"标的: {symbol}\n"
        f"价格: {price:.2f}\n"
        f"触发周期: {timeframe}\n"
        f"趋势方向: {trend_text}\n"
        f"状态说明: {status_text}"
    )
