from config import BINANCE_SYMBOL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.signals import detect_signals
from services.logger import get_logger
from services.telegram import send_telegram_message


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
    def _format_signal_list(signals: list[dict]) -> str:
        if not signals:
            return "当前无正式信号"

        items = []
        for signal in signals:
            signal_name = signal.get("signal", "UNKNOWN")
            timeframe = signal.get("timeframe", "-")
            items.append(f"- {signal_name} ({timeframe})")
        return "\n".join(items)

    @staticmethod
    def _top_blocked_reasons(blocked_reasons: dict, top_n: int = 3) -> list[tuple[str, int]]:
        if not isinstance(blocked_reasons, dict):
            return []
        pairs = sorted(blocked_reasons.items(), key=lambda kv: kv[1], reverse=True)
        return pairs[:top_n]

    def build_report_message(self) -> str:
        klines_1d = self._fetch_enriched("1d")
        klines_4h = self._fetch_enriched("4h")
        klines_1h = self._fetch_enriched("1h")
        klines_15m = self._fetch_enriched("15m")

        raw_result = detect_signals(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
        signals, near_miss_signals, blocked_reasons = self._normalize_signal_result(raw_result)

        blocked_top = self._top_blocked_reasons(blocked_reasons, top_n=3)
        blocked_text = "无"
        if blocked_top:
            blocked_text = "；".join([f"{k} x{v}" for k, v in blocked_top])

        return (
            "😎 2h系统检测报告\n"
            "系统状态: running\n"
            f"标的: {self.symbol}\n"
            f"当前正式信号数量: {len(signals)}\n"
            "当前正式信号列表:\n"
            f"{self._format_signal_list(signals)}\n"
            f"near_miss_signals 数量: {len(near_miss_signals)}\n"
            f"blocked_reasons 前3项: {blocked_text}"
        )

    def build_failure_message(self, error: str) -> str:
        brief = (error or "unknown")[:180]
        return (
            "😎 2h系统检测报告\n"
            "系统状态: 异常\n"
            f"标的: {self.symbol}\n"
            "当前正式信号数量: -\n"
            "当前正式信号列表:\n"
            "当前无正式信号\n"
            "near_miss_signals 数量: -\n"
            f"blocked_reasons 前3项: 脚本异常({brief})"
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
