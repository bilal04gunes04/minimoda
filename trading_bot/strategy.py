"""EMA kesisimi + RSI filtresi stratejisi.

AL sinyali : hizli EMA, yavas EMA'yi yukari keser ve RSI asiri alim bolgesinde degildir.
SAT sinyali: hizli EMA, yavas EMA'yi asagi keser veya RSI asiri alim bolgesine girer.
"""

import logging
from dataclasses import dataclass

from .config import StrategyConfig
from .indicators import ema, rsi

log = logging.getLogger(__name__)

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"


@dataclass
class Signal:
    action: str          # BUY / SELL / HOLD
    price: float
    reason: str


class EmaRsiStrategy:
    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    def min_candles(self) -> int:
        return max(self.cfg.ema_slow, self.cfg.rsi_period) + 2

    def evaluate(self, closes: list[float]) -> Signal:
        price = closes[-1]
        if len(closes) < self.min_candles():
            return Signal(HOLD, price, "yeterli mum verisi yok")

        fast = ema(closes, self.cfg.ema_fast)
        slow = ema(closes, self.cfg.ema_slow)
        rsi_vals = rsi(closes, self.cfg.rsi_period)

        # EMA listelerini ayni uzunlukta hizala (sondan)
        n = min(len(fast), len(slow))
        fast, slow = fast[-n:], slow[-n:]

        cross_up = fast[-2] <= slow[-2] and fast[-1] > slow[-1]
        cross_down = fast[-2] >= slow[-2] and fast[-1] < slow[-1]
        current_rsi = rsi_vals[-1]

        log.debug(
            "fiyat=%.2f ema%d=%.2f ema%d=%.2f rsi=%.1f",
            price, self.cfg.ema_fast, fast[-1], self.cfg.ema_slow, slow[-1], current_rsi,
        )

        if cross_up and current_rsi < self.cfg.rsi_overbought:
            return Signal(BUY, price, f"EMA yukari kesisim, RSI={current_rsi:.1f}")
        if cross_down:
            return Signal(SELL, price, f"EMA asagi kesisim, RSI={current_rsi:.1f}")
        if current_rsi >= self.cfg.rsi_overbought:
            return Signal(SELL, price, f"RSI asiri alim ({current_rsi:.1f})")
        return Signal(HOLD, price, f"sinyal yok, RSI={current_rsi:.1f}")
