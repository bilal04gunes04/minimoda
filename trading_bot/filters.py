"""AL sinyali onay filtreleri.

Bu filtreler sinyal URETMEZ; stratejinin verdigi AL sinyalini dogrular.
Herhangi biri "hayir" derse islem acilmaz. API hatasinda filtre gecer
(fail-open): ag sorunu yuzunden bot kilitlenmez, sadece uyari loglanir.

1. Hacim onayi     : kesisim ortalamanin ustunde hacimle gelmeli
2. Emir defteri    : alis tarafi (bid) yeterince agir olmali
3. Fear & Greed    : piyasa asiri korku/acgozlulukteyse alim yapma
4. Balina dedektoru: buyuk emirlerde satis baskisi varsa alim yapma
"""

import logging
import time

import requests

from .binance_client import BinanceError
from .config import FiltersConfig

log = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/?limit=1"
FNG_CACHE_SECONDS = 3600


class SignalFilters:
    def __init__(self, cfg: FiltersConfig, client_getter):
        self.cfg = cfg
        self._get_client = client_getter  # canli istemciye her cagrida erisim
        self._fng_value: int | None = None
        self._fng_time = 0.0

    @property
    def client(self):
        return self._get_client()

    def check_buy(self, symbol: str, volumes: list[float]) -> tuple[bool, str]:
        """AL sinyalini dogrular. Donus: (gecti_mi, engelleme_sebebi)"""
        for check in (
            lambda: self._check_volume(volumes),
            lambda: self._check_orderbook(symbol),
            lambda: self._check_fear_greed(),
            lambda: self._check_whales(symbol),
        ):
            ok, reason = check()
            if not ok:
                return False, reason
        return True, ""

    # ---------- 1) hacim onayi ----------

    def _check_volume(self, volumes: list[float]) -> tuple[bool, str]:
        f = self.cfg.volume
        if not f.enabled or len(volumes) < f.lookback + 1:
            return True, ""
        last = volumes[-1]
        avg = sum(volumes[-f.lookback - 1:-1]) / f.lookback
        if avg <= 0:
            return True, ""
        ratio = last / avg
        if ratio < f.min_ratio:
            return False, f"hacim onayi yok ({ratio:.2f}x < {f.min_ratio}x ortalama)"
        return True, ""

    # ---------- 2) emir defteri dengesi ----------

    def _check_orderbook(self, symbol: str) -> tuple[bool, str]:
        f = self.cfg.orderbook
        if not f.enabled:
            return True, ""
        try:
            depth = self.client.get_depth(symbol, f.depth)
        except BinanceError as e:
            log.warning("%s: emir defteri alinamadi, filtre atlandi: %s", symbol, e)
            return True, ""
        bid_vol = sum(float(p) * float(q) for p, q in depth.get("bids", []))
        ask_vol = sum(float(p) * float(q) for p, q in depth.get("asks", []))
        total = bid_vol + ask_vol
        if total <= 0:
            return True, ""
        bid_ratio = bid_vol / total
        if bid_ratio < f.min_bid_ratio:
            return False, (
                f"emir defteri zayif (alis orani {bid_ratio:.2f} < {f.min_bid_ratio})"
            )
        return True, ""

    # ---------- 3) Fear & Greed endeksi ----------

    def _fetch_fng(self) -> int | None:
        if self._fng_value is not None and time.time() - self._fng_time < FNG_CACHE_SECONDS:
            return self._fng_value
        try:
            resp = requests.get(FNG_URL, timeout=10)
            value = int(resp.json()["data"][0]["value"])
            self._fng_value, self._fng_time = value, time.time()
            log.info("Fear & Greed endeksi: %d", value)
            return value
        except (requests.RequestException, KeyError, ValueError, IndexError) as e:
            log.warning("Fear & Greed alinamadi, filtre atlandi: %s", e)
            return None

    def _check_fear_greed(self) -> tuple[bool, str]:
        f = self.cfg.fear_greed
        if not f.enabled:
            return True, ""
        value = self._fetch_fng()
        if value is None:
            return True, ""
        if value < f.min_value:
            return False, f"piyasa asiri korkuda (F&G {value} < {f.min_value})"
        if value > f.max_value:
            return False, f"piyasa asiri acgozlulukta (F&G {value} > {f.max_value})"
        return True, ""

    # ---------- 4) balina emir dedektoru ----------

    def _check_whales(self, symbol: str) -> tuple[bool, str]:
        f = self.cfg.whale
        if not f.enabled:
            return True, ""
        try:
            trades = self.client.get_agg_trades(symbol, 1000)
        except BinanceError as e:
            log.warning("%s: islem akisi alinamadi, filtre atlandi: %s", symbol, e)
            return True, ""
        big = [t for t in trades if t["price"] * t["qty"] >= f.min_trade_usdt]
        if not big:
            return True, ""  # buyuk emir yoksa engel de yok
        sell_vol = sum(t["price"] * t["qty"] for t in big if t["is_sell"])
        total_vol = sum(t["price"] * t["qty"] for t in big)
        sell_ratio = sell_vol / total_vol
        if sell_ratio > f.max_sell_ratio:
            return False, (
                f"balina satis baskisi ({len(big)} buyuk emirde satis orani "
                f"{sell_ratio:.2f} > {f.max_sell_ratio})"
            )
        return True, ""
