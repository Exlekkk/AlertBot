import logging
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from config import BINANCE_SYMBOL, SCAN_INTERVAL_SECONDS
from engine.scanner import SMCTScanner


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("smct_scanner")


def main():
    scanner = SMCTScanner(symbol=BINANCE_SYMBOL)
    logger.info(
        "scanner_loop_started symbol=%s interval_seconds=%s",
        BINANCE_SYMBOL,
        SCAN_INTERVAL_SECONDS,
    )

    while True:
        try:
            result = scanner.run_once()
            logger.info("scanner_loop_tick result=%s", result)
        except Exception as exc:
            logger.exception("scanner_loop_error")
            try:
                from services.ops_status import notify_backend_error

                notify_backend_error("scanner.loop", str(exc), state=scanner.runtime_state)
            except Exception:
                logger.exception("scanner_loop_error_notify_failed")

        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
