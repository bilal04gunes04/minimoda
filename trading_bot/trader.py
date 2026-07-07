"""Ana islem dongusu: sinyal uret, risk kurallarini uygula, emir ver."""

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass

from .binance_client import BinanceClient, BinanceError
from .config import Config
from .strategy import BUY, SELL, EmaRsiStrategy

log = logging.getLogger(__name__)

STATE_FILE = "state.json"


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    opened_at: float


class Trader:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = BinanceClient(cfg.api_key, cfg.api_secret, cfg.testnet)
        self.strategy = EmaRsiStrategy(cfg.strategy)
        self.position: Position | None = None
        self.filters: dict | None = None
        self._load_state()

    # ---------- durum kaydi (bot yeniden baslasa da pozisyonu hatirlar) ----------

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("position"):
                    self.position = Position(**data["position"])
                    log.info("Kayitli pozisyon yuklendi: %s", self.position)
            except (json.JSONDecodeError, TypeError):
                log.warning("state.json okunamadi, sifirdan baslaniyor")

    def _save_state(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"position": asdict(self.position) if self.position else None}, f, indent=2
            )

    # ---------- miktar hesaplama ----------

    def _round_qty(self, qty: float) -> float:
        step = self.filters["step_size"]
        if step <= 0:
            return qty
        return math.floor(qty / step) * step

    def _calc_buy_qty(self, price: float) -> float:
        qty = self._round_qty(self.cfg.risk.quote_per_trade / price)
        if qty < self.filters["min_qty"]:
            log.warning("Hesaplanan miktar cok kucuk: %s", qty)
            return 0.0
        if qty * price < self.filters["min_notional"]:
            log.warning(
                "Emir tutari minimum islem tutarinin altinda (%.2f < %.2f)",
                qty * price, self.filters["min_notional"],
            )
            return 0.0
        return qty

    # ---------- emir islemleri ----------

    def _buy(self, price: float, reason: str):
        qty = self._calc_buy_qty(price)
        if qty <= 0:
            return
        if self.cfg.dry_run:
            log.info("[KAGIT ISLEM] AL %s %.8f @ %.2f (%s)", self.cfg.symbol, qty, price, reason)
        else:
            result = self.client.market_order(self.cfg.symbol, "BUY", qty)
            price = float(result["fills"][0]["price"]) if result.get("fills") else price
            log.info("ALINDI %s %.8f @ %.2f (%s)", self.cfg.symbol, qty, price, reason)
        self.position = Position(self.cfg.symbol, qty, price, time.time())
        self._save_state()

    def _sell(self, price: float, reason: str):
        pos = self.position
        if not pos:
            return
        pnl_pct = (price - pos.entry_price) / pos.entry_price * 100
        if self.cfg.dry_run:
            log.info(
                "[KAGIT ISLEM] SAT %s %.8f @ %.2f | K/Z: %+.2f%% (%s)",
                pos.symbol, pos.quantity, price, pnl_pct, reason,
            )
        else:
            self.client.market_order(pos.symbol, "SELL", self._round_qty(pos.quantity))
            log.info(
                "SATILDI %s %.8f @ %.2f | K/Z: %+.2f%% (%s)",
                pos.symbol, pos.quantity, price, pnl_pct, reason,
            )
        self.position = None
        self._save_state()

    # ---------- risk kontrolu ----------

    def _check_stop_take(self, price: float) -> str | None:
        """Acik pozisyon icin zarar-durdur / kar-al kontrolu."""
        pos = self.position
        if not pos:
            return None
        change_pct = (price - pos.entry_price) / pos.entry_price * 100
        if change_pct <= -self.cfg.risk.stop_loss_pct:
            return f"zarar durdur tetiklendi ({change_pct:+.2f}%)"
        if change_pct >= self.cfg.risk.take_profit_pct:
            return f"kar al tetiklendi ({change_pct:+.2f}%)"
        return None

    # ---------- ana dongu ----------

    def run_once(self):
        klines = self.client.get_klines(
            self.cfg.symbol, self.cfg.interval, limit=self.strategy.min_candles() + 50
        )
        # Son mum henuz kapanmadigi icin kapali mumlarla calis
        closes = [k["close"] for k in klines[:-1]]
        live_price = klines[-1]["close"]

        # 1) Acik pozisyonda zarar-durdur / kar-al her zaman once kontrol edilir
        exit_reason = self._check_stop_take(live_price)
        if exit_reason:
            self._sell(live_price, exit_reason)
            return

        # 2) Strateji sinyali
        signal = self.strategy.evaluate(closes)
        log.info(
            "%s fiyat=%.2f sinyal=%s (%s) pozisyon=%s",
            self.cfg.symbol, live_price, signal.action, signal.reason,
            "ACIK" if self.position else "YOK",
        )

        if signal.action == BUY and not self.position:
            self._buy(live_price, signal.reason)
        elif signal.action == SELL and self.position:
            self._sell(live_price, signal.reason)

    def run_forever(self):
        mode = "KAGIT ISLEM (dry-run)" if self.cfg.dry_run else "GERCEK EMIR"
        net = "TESTNET" if self.cfg.testnet else "GERCEK HESAP (MAINNET)"
        log.info("Bot basliyor | %s | %s | %s %s", net, mode, self.cfg.symbol, self.cfg.interval)

        self.filters = self.client.get_symbol_filters(self.cfg.symbol)
        log.info("Sembol filtreleri: %s", self.filters)

        while True:
            try:
                self.run_once()
            except BinanceError as e:
                log.error("Binance hatasi: %s", e)
            except Exception:
                log.exception("Beklenmeyen hata")
            time.sleep(self.cfg.poll_seconds)
