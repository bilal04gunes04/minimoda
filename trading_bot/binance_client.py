"""Hafif Binance Spot REST API istemcisi (harici SDK gerektirmez)."""

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

MAINNET_URL = "https://api.binance.com"
TESTNET_URL = "https://testnet.binance.vision"


class BinanceError(Exception):
    pass


class BinanceClient:
    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = TESTNET_URL if testnet else MAINNET_URL
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-MBX-APIKEY"] = api_key

    # ---------- alt yapi ----------

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urlencode(params)
        params["signature"] = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        if signed:
            params = self._sign(params)
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, params=params, timeout=15)
        if resp.status_code != 200:
            raise BinanceError(f"HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    # ---------- herkese acik uclar ----------

    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> list[dict]:
        """Mum verilerini dondurur (en yenisi sonda)."""
        data = self._request(
            "GET", "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [
            {
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            }
            for k in data
        ]

    def get_price(self, symbol: str) -> float:
        data = self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"])

    def get_symbol_filters(self, symbol: str) -> dict:
        """LOT_SIZE / NOTIONAL filtrelerini dondurur (miktar yuvarlama icin)."""
        data = self._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
        info = data["symbols"][0]
        filters = {f["filterType"]: f for f in info["filters"]}
        return {
            "step_size": float(filters.get("LOT_SIZE", {}).get("stepSize", 0.000001)),
            "min_qty": float(filters.get("LOT_SIZE", {}).get("minQty", 0)),
            "min_notional": float(
                filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional", 0)
            ),
        }

    # ---------- imzali uclar ----------

    def get_balances(self) -> dict[str, float]:
        data = self._request("GET", "/api/v3/account", signed=True)
        return {
            b["asset"]: float(b["free"])
            for b in data["balances"]
            if float(b["free"]) > 0
        }

    def market_order(self, symbol: str, side: str, quantity: float) -> dict:
        """MARKET emir gonderir. side: BUY veya SELL"""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
        }
        log.info("Emir gonderiliyor: %s", params)
        return self._request("POST", "/api/v3/order", params, signed=True)
