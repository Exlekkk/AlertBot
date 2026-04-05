from __future__ import annotations

import requests


TYPE_LABELS = {1: "A类", 2: "B类", 3: "C类", 4: "X类"}

ACTION_LABELS = {
    "A_LONG": "顺势做多候选",
    "A_SHORT": "顺势做空候选",
    "B_PULLBACK_LONG": "回踩承接候选",
    "B_PULLBACK_SHORT": "反弹承压候选",
    "C_LEFT_LONG": "左侧试多观察",
    "C_LEFT_SHORT": "左侧试空观察",
    "X_BREAKOUT_LONG": "异动上破观察",
    "X_BREAKOUT_SHORT": "异动下破观察",
}

STATE_LABELS = {
    "trend_drive_long": "趋势推动偏多",
    "trend_drive_short": "趋势推动偏空",
    "repair_long": "修复后延续偏多",
    "repair_short": "修复后延续偏空",
    "probe_long": "早期试多",
    "probe_short": "早期试空",
    "range_neutral": "震荡/中性",
}

TRIGGER_LABELS = {
    "confirm_long": "15m触发已确认",
    "confirm_short": "15m触发已确认",
    "repairing_long": "15m处于修复转强",
    "repairing_short": "15m处于修复转弱",
    "probing_long": "15m早期试多",
    "probing_short": "15m早期试空",
    "idle": "15m暂无有效触发",
}

BUDGET_LABELS = {
    "expanded": "热度放行",
    "normal": "热度正常",
    "restricted": "热度受限",
    "frozen": "热度冻结",
}

DEFAULT_START_WINDOWS = {1: (5, 30), 2: (15, 120), 3: (60, 360), 4: (5, 120)}


def type_label(priority: int) -> str:
    return TYPE_LABELS.get(priority, f"{priority}类")


def _format_minutes_compact(minutes: int | None) -> str:
    if minutes is None:
        return ""
    minutes = max(0, int(minutes))
    if minutes < 60:
        return f"{minutes}m"
    hours, remain = divmod(minutes, 60)
    return f"{hours}h" if remain == 0 else f"{hours}h{remain}m"


def _observe_window(priority: int, eta_min_minutes: int | None = None, eta_max_minutes: int | None = None) -> str:
    start_min, end_min = DEFAULT_START_WINDOWS.get(priority, (15, 45))
    if eta_min_minutes is not None:
        start_min = int(eta_min_minutes)
    if eta_max_minutes is not None:
        end_min = int(eta_max_minutes)
    end_min = max(start_min, end_min)
    return f"{_format_minutes_compact(start_min)} - {_format_minutes_compact(end_min)}"


def _normalized_zone(low: float | None, high: float | None, price: float) -> tuple[float, float]:
    if low is None or high is None:
        pad = max(abs(float(price)) * 0.0012, 12.0)
        low = float(price) - pad * 0.5
        high = float(price) + pad * 0.5
    low, high = min(float(low), float(high)), max(float(low), float(high))
    return low, high


def _confidence_text(signal: dict) -> str:
    value = int(signal.get("confidence", 0) or 0)
    if value >= 85:
        band = "高"
    elif value >= 70:
        band = "中高"
    elif value >= 58:
        band = "中"
    else:
        band = "观察"
    return f"{band}({value})"


def _basis_text(structure_basis: list[str] | None) -> str:
    if not structure_basis:
        return "结构依据不足，更多偏观察"
    mapping = {
        "smc_bos_up": "SMC上破结构",
        "smc_bos_down": "SMC下破结构",
        "ict_mss_up": "ICT偏多MSS",
        "ict_mss_down": "ICT偏空MSS",
        "support_zone": "位于支撑/承接区",
        "resistance_zone": "位于阻力/承压区",
        "trigger_repair": "15m修复触发出现",
        "ema_support": "EMA背景未明显对冲",
        "ema_resistance": "EMA背景未明显对冲",
        "early_warning": "出现早期预警信号",
        "probing_trigger": "15m已有试探动作",
    }
    return "、".join(mapping.get(x, x) for x in structure_basis[:4])


def _status_line(signal: dict) -> str:
    state_1h = STATE_LABELS.get(signal.get("state_1h", ""), signal.get("state_1h", "未知状态"))
    trigger = TRIGGER_LABELS.get(signal.get("trigger_15m_state", ""), signal.get("trigger_15m_state", "未知触发"))
    budget = BUDGET_LABELS.get(signal.get("tai_budget_mode", "normal"), signal.get("tai_budget_mode", "normal"))
    return f"1h状态：{state_1h}｜15m触发：{trigger}｜TAI：{budget}"


def format_engine_message(signal: dict) -> str:
    name = signal.get("signal", "")
    priority = int(signal.get("priority", 1) or 1)
    symbol = signal.get("symbol", "BTCUSDT")
    direction = signal.get("direction", "")
    price = float(signal.get("price", 0.0) or 0.0)
    low, high = _normalized_zone(signal.get("entry_zone_low"), signal.get("entry_zone_high"), price)
    key_level = float(signal.get("trigger_level") or signal.get("breakout_level") or (low if direction == "long" else high))
    title = "🧨 异动观察" if name.startswith("X_") else "🚨 读盘提示"
    action = ACTION_LABELS.get(name, name)
    confidence = _confidence_text(signal)
    basis = _basis_text(signal.get("structure_basis"))
    observe = _observe_window(priority, signal.get("eta_min_minutes"), signal.get("eta_max_minutes"))

    lines = [
        f"{title}｜{type_label(priority)}｜{symbol}",
        f"方向：{action}｜{confidence}",
        _status_line(signal),
        f"当前价：{price:.2f}",
        f"观察区：{low:.2f} - {high:.2f}",
        f"关键位：{key_level:.2f}",
        f"依据：{basis}",
        f"观察窗：{observe}",
    ]

    abnormal_type = signal.get("abnormal_type")
    if abnormal_type:
        lines.append(f"异动类型：{abnormal_type}")

    if signal.get("freeze_mode"):
        lines.append("备注：当前热度冻结，除明显异动外不建议高频追单")
    elif signal.get("heat_restricted"):
        lines.append("备注：当前热度受限，优先等待更干净的结构确认")

    return "\n".join(lines)


def format_webhook_message(signal: str, symbol: str, timeframe: str, direction: str = "unknown") -> str:
    direction_text = direction if direction and direction != "unknown" else "外部方向未注明"
    return (
        f"📩 外部Webhook信号｜{symbol}\n"
        f"信号：{signal}\n"
        f"周期：{timeframe}\n"
        f"方向：{direction_text}\n"
        f"说明：该消息来自外部触发源，未经过SMCT内部多周期分层解释。"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    return response.text
