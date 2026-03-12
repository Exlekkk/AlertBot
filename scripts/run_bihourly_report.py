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

    def run_once(self):
        try:
            message = self.build_running_message()
            result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
            self.logger.info("bihourly_report_sent symbol=%s result=%s", self.symbol, result)
            return {"ok": True, "message": message, "telegram_result": result}
        except Exception as exc:
            self.logger.exception("bihourly_report_failed error=%s", exc)
            failure_message = self.build_failure_message(str(exc))
            try:
                result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, failure_message)
                self.logger.info(
                    "bihourly_report_failure_notice_sent symbol=%s result=%s",
                    self.symbol,
                    result,
                )
                return {"ok": False, "error": str(exc), "telegram_result": result}
            except Exception as send_exc:
                self.logger.exception("bihourly_report_failure_notice_send_failed error=%s", send_exc)
                raise


if __name__ == "__main__":
    reporter = BihourlyReporter(symbol=BINANCE_SYMBOL)
    reporter.run_once()
