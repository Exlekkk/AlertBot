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

    def build_report_message(self) -> str:
        klines_4h = self._fetch_enriched("4h")
        klines_1h = self._fetch_enriched("1h")
        klines_15m = self._fetch_enriched("15m")

        raw_result = detect_signals(self.symbol, klines_4h, klines_1h, klines_15m)
        self._normalize_signal_result(raw_result)

        return (
            "🧪 2h系统检测报告\n"
            "系统状态: running\n"
            "如果你能看到此条，说明系统正常"
        )

    def build_failure_message(self, error: str) -> str:
        brief = (error or "unknown")[:180]
        return (
            "🧪 2h系统检测报告\n"
            "系统状态: 异常\n"
            "如果你能看到此条，说明系统异常\n"
            f"错误信息: {brief}"
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