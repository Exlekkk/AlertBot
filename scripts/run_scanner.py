from config import BINANCE_SYMBOL, SCAN_INTERVAL_SECONDS
from engine.scanner import SMCTScanner


if __name__ == "__main__":
    scanner = SMCTScanner(symbol=BINANCE_SYMBOL)
    scanner.run_forever(interval_seconds=SCAN_INTERVAL_SECONDS)
