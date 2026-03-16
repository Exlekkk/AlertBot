from importlib import import_module

from config import BINANCE_SYMBOL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from services.logger import get_logger
from services.telegram import send_telegram_message


class BihourlyReporter:
    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.logger = get_logger("bihourly_report", WEBHOOK_LOG_FILE)

    def build_running_message(self) -> str:
        return (
            "🧪 2h系统检测报告\n"
            "系统状态: running\n"
            "如果你能看到此条，说明系统正常"
        )

    def build_failure_message(self, error: str) -> str:
        brief = (error or "unknown")[:200]
        return (
            "🧪 2h系统检测报告\n"
            "系统状态: 异常\n"
            "如果你能看到此条，说明系统异常\n"
            f"错误信息: {brief}"
        )

    def run_healthcheck(self) -> dict:
        try:
            scanner_module = import_module("engine.scanner")
            scanner_cls = getattr(scanner_module, "SMCTScanner")
            scanner = scanner_cls(symbol=self.symbol)

            if hasattr(scanner, "health_check"):
                return scanner.health_check()

            if hasattr(scanner, "healthcheck"):
                return scanner.healthcheck()

            raise AttributeError("SMCTScanner has neither 'health_check' nor 'healthcheck'")

        except Exception as exc:
            self.logger.exception("bihourly_healthcheck_failed error=%s", exc)
            return {"ok": False, "error": str(exc)}

    def run_once(self):
        health = self.run_healthcheck()
        message = (
            self.build_running_message()
            if health.get("ok")
            else self.build_failure_message(health.get("error", "unknown"))
        )

        try:
            result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
            if health.get("ok"):
                self.logger.info(
                    "bihourly_report_sent symbol=%s health=%s result=%s",
                    self.symbol,
                    health,
                    result,
                )
            else:
                self.logger.info(
                    "bihourly_report_failure_notice_sent symbol=%s health=%s result=%s",
                    self.symbol,
                    health,
                    result,
                )
            return {
                "ok": bool(health.get("ok")),
                "health": health,
                "message": message,
                "telegram_result": result,
            }
        except Exception as exc:
            self.logger.exception("bihourly_report_send_failed error=%s", exc)
            raise


if __name__ == "__main__":
    reporter = BihourlyReporter(symbol=BINANCE_SYMBOL)
    reporter.run_once()
