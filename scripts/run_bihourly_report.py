from collections import Counter

from config import BINANCE_SYMBOL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.signals import classify_trend, detect_signals
from services.logger import get_logger
from services.telegram import send_telegram_message


TYPE_LABELS = {
    1: "A类",
    2: "B类",
    3: "C类",
}

ACTION_LABELS = {
    "A_LONG": "顺势做多机会",
    "A_SHORT": "顺势做空机会",
    "B_PULLBACK_LONG": "回踩后做多机会",
    "B_PULLBACK_SHORT": "反弹后做空机会",
    "C_LEFT_LONG": "左侧预警做多机会",
    "C_LEFT_SHORT": "左侧预警做空机会",
}

STATUS_LABELS = {
    "A_LONG": "顺势环境已成立，等待15m突破触发",
    "A_SHORT": "顺势环境已成立，等待15m跌破触发",
    "B_PULLBACK_LONG": "高周期偏多，等待回踩后二次承接",
    "B_PULLBACK_SHORT": "高周期偏空，等待反弹后二次转弱",
    "C_LEFT_LONG": "高周期允许观察，等待左侧预警进一步成型",
    "C_LEFT_SHORT": "高周期允许观察，等待左侧预警进一步成型",
}

TREND_LABELS = {
    "bull": "偏多",
    "lean_bull": "偏多（弱）",
    "bear": "偏空",
    "lean_bear": "偏空（弱）",
    "neutral": "中性",
}

REASON_LABELS = {
    # 新版 / 旧版兼容
    "htf_a_long_allowed": "1h与4h未形成A类做多顺势环境",
    "htf_a_short_allowed": "1h与4h未形成A类做空顺势环境",
    "htf_b_long_allowed": "1h与4h未形成B类做多前提",
    "htf_b_short_allowed": "1h与4h未形成B类做空前提",
    "htf_c_long_allowed": "1h与4h未形成C类做多观察前提",
    "htf_c_short_allowed": "1h与4h未形成C类做空观察前提",
    "regime_allows_long": "高周期未允许做多",
    "regime_allows_short": "高周期未允许做空",

    "not_hard_icepoint": "市场活跃度处于极低冰点",
    "tai_not_icepoint": "市场活跃度仍偏低",
    "tai_supportive": "市场活跃度仍偏弱",

    "15m_breakout_trigger": "15m未出现顺势突破触发",
    "15m_breakdown_trigger": "15m未出现顺势跌破触发",
    "smc_breakout": "15m未出现有效突破触发",
    "smc_breakdown": "15m未出现有效跌破触发",

    "15m_bullish_structure": "15m多头结构未确认",
    "15m_bearish_structure": "15m空头结构未确认",
    "bullish_structure": "15m多头结构未确认",
    "bearish_structure": "15m空头结构未确认",

    "ema_supportive": "EMA骨架未配合",
    "fl_supportive": "FL未给出顺势支持",
    "cm_supportive": "CM动能未配合",
    "rar_trend_not_weak": "RAR趋势效率不足",

    "no_sss_bear_div": "EQ存在反向空头干扰",
    "no_sss_bull_div": "EQ存在反向多头干扰",
    "no_sss_overbought_warning": "EQ仍处于过热预警区",
    "no_sss_oversold_warning": "EQ仍处于过冷预警区",
    "no_hard_counterflow": "出现明显反向共振干扰",

    "not_too_far_from_ema20": "价格离EMA20偏远",
    "not_too_far_from_ema10": "价格离EMA10偏远",
    "close_above_ema20": "价格仍未站稳EMA20",
    "close_below_ema20": "价格仍未跌破EMA20",

    "15m_smc_premise_long": "15m未回到有效做多结构位",
    "15m_smc_premise_short": "15m未回到有效做空结构位",
    "smc_premise_long": "15m未回到有效做多结构位",
    "smc_premise_short": "15m未回到有效做空结构位",

    "pullback_then_reclaim": "回踩后未完成重新承接",
    "pullback_then_reject": "反弹后未完成重新转弱",
    "reclaim_after_pullback": "回踩后未完成重新承接",
    "reject_after_pullback": "反弹后未完成重新转弱",

    "fl_not_bearish": "FL仍偏空或未转稳",
    "fl_not_bullish": "FL仍偏多或未转弱",

    "no_strong_sss_contradiction": "EQ存在明显反向干扰",
    "near_support": "位置还未回到有效支撑带",
    "near_resistance": "位置还未回到有效压力带",

    "15m_strategy_premise_long": "15m左侧做多前提不足",
    "15m_strategy_premise_short": "15m左侧做空前提不足",
    "strategy_premise_long": "15m左侧做多前提不足",
    "strategy_premise_short": "15m左侧做空前提不足",

    "eq_core_long": "EQ左侧做多触发未成立",
    "eq_core_short": "EQ左侧做空触发未成立",

    "price_confirm": "价格确认不足",
    "cm_not_weakening": "CM仍未改善",
}


class BihourlyReporter:
    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.market_data = BinanceMarketDataClient()
        self.logger = get_logger("bihourly_report", WEBHOOK_LOG_FILE)

    def _fetch_enriched(self, interval: str) -> list[dict]:
        klines = self.market_data.get_klines(self.symbol, interval=interval, limit=300)
        return enrich_klines(klines[:-1])

    @staticmethod
    def _normalize_signal_result(result) -> tuple[list[dict], list[dict], dict]:
        if isinstance(result, dict):
            signals = result.get("signals", [])
            near_miss_signals = result.get("near_miss_signals", [])
            blocked_reasons = result.get("blocked_reasons", {})
            return signals, near_miss_signals, blocked_reasons
        if isinstance(result, list):
            return result, [], {}
        return [], [], {}

    @staticmethod
    def _trend_text(trend: str) -> str:
        return TREND_LABELS.get(trend, trend)

    @staticmethod
    def _trend_side(trend: str) -> int:
        if trend in ("bull", "lean_bull"):
            return 1
        if trend in ("bear", "lean_bear"):
            return -1
        return 0

    def _summarize_trend_environment(self, trend_1d: str, trend_4h: str, trend_1h: str) -> tuple[str, str]:
        h1_side = self._trend_side(trend_1h)
        h4_side = self._trend_side(trend_4h)
        d1_side = self._trend_side(trend_1d)

        detail = f"1h{self._trend_text(trend_1h)}｜4h{self._trend_text(trend_4h)}｜1d{self._trend_text(trend_1d)}"

        if h1_side > 0 and h4_side > 0:
            return detail, "1h与4h同向偏多，以多头机会为主"
        if h1_side < 0 and h4_side < 0:
            return detail, "1h与4h同向偏空，以空头机会为主"
        if h1_side > 0 and h4_side == 0:
            return detail, "1h偏多、4h中性，暂按多头观察"
        if h1_side < 0 and h4_side == 0:
            return detail, "1h偏空、4h中性，暂按空头观察"
        if h4_side > 0 and h1_side == 0:
            return detail, "4h偏多、1h中性，暂按多头观察"
        if h4_side < 0 and h1_side == 0:
            return detail, "4h偏空、1h中性，暂按空头观察"

        if h1_side * h4_side == -1:
            if d1_side > 0:
                return detail, "1h与4h冲突，但1d偏多，暂按多头观察"
            if d1_side < 0:
                return detail, "1h与4h冲突，但1d偏空，暂按空头观察"
            return detail, "1h与4h冲突，1d未明确裁决，当前以等待为主"

        return detail, "高周期方向暂不清晰，当前以等待为主"

    @staticmethod
    def _reason_text(reason: str) -> str:
        return REASON_LABELS.get(reason, reason.replace("_", " "))

    @staticmethod
    def _candidate_text(candidate: str) -> str:
        priority = {
            "A_LONG": 1,
            "A_SHORT": 1,
            "B_PULLBACK_LONG": 2,
            "B_PULLBACK_SHORT": 2,
            "C_LEFT_LONG": 3,
            "C_LEFT_SHORT": 3,
        }.get(candidate, 0)

        type_text = TYPE_LABELS.get(priority, "未知类型")
        action_text = ACTION_LABELS.get(candidate, candidate)
        return f"{type_text}｜{action_text}"

    def _format_signal_list(self, signals: list[dict]) -> str:
        if not signals:
            return "当前无正式信号"

        items = []
        for idx, signal in enumerate(signals, start=1):
            signal_name = signal.get("signal", "UNKNOWN")
            priority = signal.get("priority", 0)
            timeframe = signal.get("timeframe", "-")
            trend_text = self._trend_text(signal.get("trend_1h", "neutral"))
            type_text = TYPE_LABELS.get(priority, f"{priority}类")
            action_text = ACTION_LABELS.get(signal_name, signal_name)
            status_text = STATUS_LABELS.get(signal_name, signal.get("status", "-"))

            items.append(
                f"{idx}. {type_text}｜{action_text}\n"
                f"   触发周期：{timeframe}\n"
                f"   趋势方向：{trend_text}\n"
                f"   状态说明：{status_text}"
            )

        return "\n".join(items)

    def _format_near_miss(self, near_miss_signals: list[dict], top_n: int = 2) -> str:
        if not near_miss_signals:
            return "当前无接近触发的候选"

        lines = []
        for item in near_miss_signals[:top_n]:
            candidate = item.get("candidate", "UNKNOWN")
            failed_checks = item.get("failed_checks", [])
            reason_text = "；".join(self._reason_text(r) for r in failed_checks) if failed_checks else "条件不足"
            lines.append(f"- {self._candidate_text(candidate)}：{reason_text}")

        return "\n".join(lines)

    def _format_blocked_summary(self, blocked_reasons: dict, top_n: int = 3) -> str:
        if not isinstance(blocked_reasons, dict) or not blocked_reasons:
            return "无明显额外阻碍"

        reason_counter: Counter = Counter()
        for key, count in blocked_reasons.items():
            if ":" in key:
                _, reason = key.split(":", 1)
            else:
                reason = key
            reason_counter[reason] += int(count)

        top_items = reason_counter.most_common(top_n)
        if not top_items:
            return "无明显额外阻碍"

        return "；".join(self._reason_text(reason) for reason, _ in top_items)

    def build_report_message(self) -> str:
        klines_1d = self._fetch_enriched("1d")
        klines_4h = self._fetch_enriched("4h")
        klines_1h = self._fetch_enriched("1h")
        klines_15m = self._fetch_enriched("15m")

        trend_1d = classify_trend(klines_1d, structure_len=8)
        trend_4h = classify_trend(klines_4h, structure_len=10)
        trend_1h = classify_trend(klines_1h, structure_len=10)
        trend_detail, trend_environment = self._summarize_trend_environment(trend_1d, trend_4h, trend_1h)

        raw_result = detect_signals(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
        signals, near_miss_signals, blocked_reasons = self._normalize_signal_result(raw_result)

        if signals:
            return (
                "🧾 2h系统检测报告\n"
                "系统状态：running\n"
                f"标的：{self.symbol}\n"
                f"高周期：{trend_detail}\n"
                f"趋势环境：{trend_environment}\n"
                "当前结论：存在正式信号\n"
                "正式信号列表：\n"
                f"{self._format_signal_list(signals)}"
            )

        return (
            "🧾 2h系统检测报告\n"
            "系统状态：running\n"
            f"标的：{self.symbol}\n"
            f"高周期：{trend_detail}\n"
            f"趋势环境：{trend_environment}\n"
            "当前结论：暂无正式信号\n"
            "最接近触发：\n"
            f"{self._format_near_miss(near_miss_signals)}\n"
            f"主要阻碍：{self._format_blocked_summary(blocked_reasons)}"
        )

    def build_failure_message(self, error: str) -> str:
        brief = (error or "unknown")[:180]
        return (
            "🧾 2h系统检测报告\n"
            "系统状态：异常\n"
            f"标的：{self.symbol}\n"
            "当前结论：系统脚本异常\n"
            f"错误信息：{brief}"
        )

    def run_once(self):
        try:
            message = self.build_report_message()
            result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
            self.logger.info("bihourly_report_sent symbol=%s result=%s", self.symbol, result)
            return {"ok": True, "message": message, "telegram_result": result}
        except Exception as exc:
            self.logger.exception("bihourly_report_failed error=%s", exc)
            failure_message = self.build_failure_message(str(exc))
            try:
                result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, failure_message)
                self.logger.info("bihourly_report_failure_notice_sent symbol=%s result=%s", self.symbol, result)
                return {"ok": False, "error": str(exc), "telegram_result": result}
            except Exception as send_exc:
                self.logger.exception("bihourly_report_failure_notice_send_failed error=%s", send_exc)
                raise


if __name__ == "__main__":
    reporter = BihourlyReporter(symbol=BINANCE_SYMBOL)
    reporter.run_once()
