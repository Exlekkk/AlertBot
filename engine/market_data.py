from __future__ import annotations

import requests

from config import (
    BINANCE_FUTURES_KLINES_URL,
    BINANCE_SPOT_KLINES_URL,
    KLINE_LIMIT,
    MARKET_SOURCE,
    REQUEST_TIMEOUT_SECONDS,
)


class BinanceMarketDataClient:
    def __init__(self, market_source: str | None = None):
        source = (market_source or MARKET_SOURCE or "binance_futures").lower()
        self.market_source = source
        self.base_url = BINANCE_FUTURES_KLINES_URL if source == "binance_futures" else BINANCE_SPOT_KLINES_URL

    def get_klines(self, symbol: str, interval: str, limit: int = KLINE_LIMIT) -> list[dict]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(self.base_url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        rows = response.json()
        klines = []
        for r in rows:
            klines.append(
                {
                    "open_time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                    "close_time": int(r[6]),
                }
            )
        return klines
