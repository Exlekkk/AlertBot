import requests


class BinanceMarketDataClient:
    BASE_URL = "https://api.binance.com/api/v3/klines"

    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> list[dict]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(self.BASE_URL, params=params, timeout=20)
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
