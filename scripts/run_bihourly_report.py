from importlib import import_module

from config import BINANCE_SYMBOL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from services.logger import get_logger
from services.ops_status import build_error_message, notify_backend_error
from services.telegram import send_telegram_message


class BihourlyReporter:
    """Host-timer health probe.

    Success is silent (no Telegram). Failures push an ops error alert.
    Manual status is via Telegram ``/check``, not this timer.
    """

    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.logger = get_logger("bihourly_report", WEBHOOK_LOG_FILE)

    def build_running_message(self) -> str:
        # Kept for tests/compat; run_once no longer sends this to Telegram.
        return (
            "🧪 2h系统检测报告\n"
            "系统状态: running\n"
            "如果你能看到此条，说明系统正常"
        )

    def build_failure_message(self, error: str) -> str:
        return build_error_message("bihourly_healthcheck", error)

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
        if health.get("ok"):
            self.logger.info(
                "bihourly_healthcheck_ok_silent symbol=%s health=%s",
                self.symbol,
                health,
            )
            return {
                "ok": True,
                "health": health,
                "message": None,
                "telegram_result": None,
                "sent": False,
            }

        error = health.get("error", "unknown")
        message = self.build_failure_message(error)
        try:
            notice = notify_backend_error("bihourly_healthcheck", str(error))
            if notice.get("skipped") and notice.get("reason") == "missing_telegram_creds":
                result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
                notice = {"ok": True, "skipped": False, "telegram_result": result, "message": message}
            self.logger.info(
                "bihourly_report_failure_notice symbol=%s health=%s notice=%s",
                self.symbol,
                health,
                notice,
            )
            return {
                "ok": False,
                "health": health,
                "message": notice.get("message") or message,
                "telegram_result": notice.get("telegram_result"),
                "sent": bool(notice.get("ok")) and not notice.get("skipped"),
            }
        except Exception as exc:
            self.logger.exception("bihourly_report_send_failed error=%s", exc)
            raise


if __name__ == "__main__":
    reporter = BihourlyReporter(symbol=BINANCE_SYMBOL)
    reporter.run_once()
