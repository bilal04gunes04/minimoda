"""Ana islem dongusu: coklu coin, sinyal uretimi, risk kurallari, emir yonetimi."""

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import date

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
    peak_price: float = 0.0  # trailing stop icin girisden beri gorulen en yuksek fiyat


@dataclass
class DailyStats:
    day: str = ""              # YYYY-MM-DD
    realized_pnl: float = 0.0  # gun ici gerceklesen kar/zarar (USDT)
    trades: int = 0
    wins: int = 0


class Trader:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = BinanceClient(cfg.api_key, cfg.api_secret, cfg.testnet)
        self.strategy = EmaRsiStrategy(cfg.strategy)
        self.positions: dict[str, Position] = {}
        self.filters: dict[str, dict] = {}
        self.daily = DailyStats(day=str(date.today()))
        self.paused = False           # Telegram /duraklat ile yeni alimlar durdurulur
        self.lock = threading.RLock() # Telegram komutlari ile ana dongu cakismasin
        self.notify = lambda msg: None  # Telegram baglaninca gercek gonderici atanir
        self._load_state()

    # ---------- durum kaydi (bot yeniden baslasa da pozisyonlari hatirlar) ----------

    def _load_state(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sym, p in (data.get("positions") or {}).items():
                self.positions[sym] = Position(**p)
            if self.positions:
                log.info("Kayitli pozisyonlar yuklendi: %s", list(self.positions))
            if data.get("daily"):
                saved = DailyStats(**data["daily"])
                if saved.day == str(date.today()):
                    self.daily = saved
                    log.info(
                        "Gunluk durum yuklendi: K/Z=%.2f USDT, %d islem",
                        saved.realized_pnl, saved.trades,
                    )
        except (json.JSONDecodeError, TypeError):
            log.warning("state.json okunamadi, sifirdan baslaniyor")

    def _save_state(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "positions": {s: asdict(p) for s, p in self.positions.items()},
                    "daily": asdict(self.daily),
                },
                f, indent=2,
            )

    # ---------- gunluk hedef / limit ----------

    def _roll_day(self):
        """Gun degistiyse gunluk sayaclari sifirla."""
        today = str(date.today())
        if self.daily.day != today:
            msg = (
                f"Yeni gun basladi. Dunku sonuc: K/Z={self.daily.realized_pnl:+.2f} USDT, "
                f"{self.daily.trades} islem"
            )
            log.info(msg)
            self.notify(msg)
            self.daily = DailyStats(day=today)
            self._save_state()

    def _daily_halt_reason(self) -> str | None:
        """Gunluk kar hedefine veya zarar limitine ulasildiysa sebep dondurur."""
        target = self.cfg.daily.capital * self.cfg.daily.profit_target_pct / 100
        loss_limit = self.cfg.daily.capital * self.cfg.daily.max_loss_pct / 100
        if self.daily.realized_pnl >= target:
            return (
                f"gunluk kar hedefine ulasildi: {self.daily.realized_pnl:+.2f} USDT "
                f"(hedef {target:.2f})"
            )
        if self.daily.realized_pnl <= -loss_limit:
            return (
                f"gunluk zarar limiti asildi: {self.daily.realized_pnl:+.2f} USDT "
                f"(limit -{loss_limit:.2f})"
            )
        return None

    # ---------- miktar hesaplama ----------

    def _round_qty(self, symbol: str, qty: float) -> float:
        step = self.filters.get(symbol, {}).get("step_size", 0)
        if step <= 0:
            return qty
        return math.floor(qty / step) * step

    def _calc_buy_qty(self, symbol: str, price: float) -> float:
        f = self.filters.get(symbol, {"min_qty": 0, "min_notional": 0})
        qty = self._round_qty(symbol, self.cfg.risk.quote_per_trade / price)
        if qty < f["min_qty"]:
            log.warning("%s: hesaplanan miktar cok kucuk: %s", symbol, qty)
            return 0.0
        if qty * price < f["min_notional"]:
            log.warning(
                "%s: emir tutari minimum islem tutarinin altinda (%.2f < %.2f)",
                symbol, qty * price, f["min_notional"],
            )
            return 0.0
        return qty

    # ---------- emir islemleri ----------

    def _buy(self, symbol: str, price: float, reason: str):
        qty = self._calc_buy_qty(symbol, price)
        if qty <= 0:
            return
        if self.cfg.dry_run:
            log.info("[KAGIT ISLEM] AL %s %.8f @ %.2f (%s)", symbol, qty, price, reason)
        else:
            result = self.client.market_order(symbol, "BUY", qty)
            price = float(result["fills"][0]["price"]) if result.get("fills") else price
            log.info("ALINDI %s %.8f @ %.2f (%s)", symbol, qty, price, reason)
        self.positions[symbol] = Position(symbol, qty, price, time.time(), peak_price=price)
        self._save_state()
        self.notify(f"🟢 AL {symbol} @ {price:.2f}\nSebep: {reason}")

    def _sell(self, symbol: str, price: float, reason: str):
        pos = self.positions.get(symbol)
        if not pos:
            return
        pnl_pct = (price - pos.entry_price) / pos.entry_price * 100
        pnl_quote = (price - pos.entry_price) * pos.quantity
        if self.cfg.dry_run:
            log.info(
                "[KAGIT ISLEM] SAT %s %.8f @ %.2f | K/Z: %+.2f%% (%s)",
                symbol, pos.quantity, price, pnl_pct, reason,
            )
        else:
            self.client.market_order(symbol, "SELL", self._round_qty(symbol, pos.quantity))
            log.info(
                "SATILDI %s %.8f @ %.2f | K/Z: %+.2f%% (%s)",
                symbol, pos.quantity, price, pnl_pct, reason,
            )
        del self.positions[symbol]
        self.daily.realized_pnl += pnl_quote
        self.daily.trades += 1
        if pnl_quote > 0:
            self.daily.wins += 1
        target = self.cfg.daily.capital * self.cfg.daily.profit_target_pct / 100
        log.info(
            "Gunluk durum: K/Z=%+.2f USDT / hedef %.2f USDT | %d islem",
            self.daily.realized_pnl, target, self.daily.trades,
        )
        self._save_state()
        emoji = "✅" if pnl_quote >= 0 else "🔻"
        self.notify(
            f"{emoji} SAT {symbol} @ {price:.2f} | K/Z: {pnl_pct:+.2f}% ({pnl_quote:+.2f} USDT)\n"
            f"Sebep: {reason}\n"
            f"Gunluk K/Z: {self.daily.realized_pnl:+.2f} / {target:.2f} USDT"
        )

    def close_position(self, symbol: str) -> str:
        """Telegram /kapat komutu icin: pozisyonu piyasa fiyatindan kapatir."""
        with self.lock:
            if symbol not in self.positions:
                return f"{symbol} icin acik pozisyon yok."
            price = self.client.get_price(symbol)
            self._sell(symbol, price, "kullanici istegi (/kapat)")
            return f"{symbol} pozisyonu kapatildi."

    # ---------- cikis kontrolu (stop-loss / take-profit / trailing) ----------

    def _check_exits(self, symbol: str, price: float) -> str | None:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        r = self.cfg.risk
        pos.peak_price = max(pos.peak_price, price)
        change_pct = (price - pos.entry_price) / pos.entry_price * 100

        if change_pct <= -r.stop_loss_pct:
            return f"zarar durdur tetiklendi ({change_pct:+.2f}%)"
        if r.take_profit_pct > 0 and change_pct >= r.take_profit_pct:
            return f"kar al tetiklendi ({change_pct:+.2f}%)"
        if r.trailing_stop_pct > 0:
            peak_gain_pct = (pos.peak_price - pos.entry_price) / pos.entry_price * 100
            if peak_gain_pct >= r.trailing_activation_pct:
                drop_pct = (pos.peak_price - price) / pos.peak_price * 100
                if drop_pct >= r.trailing_stop_pct:
                    return (
                        f"iz suren stop: tepe {pos.peak_price:.2f}'den "
                        f"%{drop_pct:.2f} dusus (K/Z {change_pct:+.2f}%)"
                    )
        return None

    # ---------- ana dongu ----------

    def _process_symbol(self, symbol: str):
        klines = self.client.get_klines(
            symbol, self.cfg.interval, limit=self.strategy.min_candles() + 50
        )
        # Son mum henuz kapanmadigi icin kapali mumlarla calis
        closes = [k["close"] for k in klines[:-1]]
        live_price = klines[-1]["close"]

        # 1) Acik pozisyonda cikis kosullari her zaman once kontrol edilir
        exit_reason = self._check_exits(symbol, live_price)
        if exit_reason:
            self._sell(symbol, live_price, exit_reason)
            return

        # 2) Strateji sinyali
        signal = self.strategy.evaluate(closes)
        log.info(
            "%s fiyat=%.2f sinyal=%s (%s) pozisyon=%s",
            symbol, live_price, signal.action, signal.reason,
            "ACIK" if symbol in self.positions else "YOK",
        )

        if signal.action == SELL and symbol in self.positions:
            self._sell(symbol, live_price, signal.reason)
            return

        # 3) Yeni alim onu kesen kosullar
        if signal.action != BUY or symbol in self.positions:
            return
        if self.paused:
            log.info("%s: bot duraklatildi (/duraklat), alim yapilmadi", symbol)
            return
        halt = self._daily_halt_reason()
        if halt:
            log.info("%s: bugun icin islem durduruldu: %s", symbol, halt)
            return
        if len(self.positions) >= self.cfg.risk.max_open_positions:
            log.info("%s: maksimum acik pozisyon sayisina ulasildi", symbol)
            return
        self._buy(symbol, live_price, signal.reason)

    def run_once(self):
        with self.lock:
            self._roll_day()
            for symbol in self.cfg.symbols:
                try:
                    self._process_symbol(symbol)
                except BinanceError as e:
                    log.error("%s: Binance hatasi: %s", symbol, e)

    def status_text(self) -> str:
        """Telegram /durum komutu icin ozet."""
        with self.lock:
            target = self.cfg.daily.capital * self.cfg.daily.profit_target_pct / 100
            lines = [
                f"🤖 Bot: {'⏸ DURAKLATILDI' if self.paused else '▶️ CALISIYOR'}",
                f"Mod: {'TESTNET' if self.cfg.testnet else 'GERCEK'}"
                f" | {'kagit islem' if self.cfg.dry_run else 'gercek emir'}",
                f"Coinler: {', '.join(self.cfg.symbols)} ({self.cfg.interval})",
                f"Gunluk K/Z: {self.daily.realized_pnl:+.2f} / hedef {target:.2f} USDT",
                f"Bugun: {self.daily.trades} islem, {self.daily.wins} kazanan",
            ]
            if self.positions:
                lines.append("\nAcik pozisyonlar:")
                for sym, pos in self.positions.items():
                    try:
                        price = self.client.get_price(sym)
                        pnl = (price - pos.entry_price) / pos.entry_price * 100
                        lines.append(
                            f"• {sym}: giris {pos.entry_price:.2f}, "
                            f"simdiki {price:.2f} ({pnl:+.2f}%)"
                        )
                    except BinanceError:
                        lines.append(f"• {sym}: giris {pos.entry_price:.2f}")
            else:
                lines.append("Acik pozisyon yok.")
            halt = self._daily_halt_reason()
            if halt:
                lines.append(f"\n⛔ {halt}")
            return "\n".join(lines)

    def run_forever(self):
        mode = "KAGIT ISLEM (dry-run)" if self.cfg.dry_run else "GERCEK EMIR"
        net = "TESTNET" if self.cfg.testnet else "GERCEK HESAP (MAINNET)"
        log.info(
            "Bot basliyor | %s | %s | %s %s",
            net, mode, ",".join(self.cfg.symbols), self.cfg.interval,
        )

        for symbol in self.cfg.symbols:
            self.filters[symbol] = self.client.get_symbol_filters(symbol)
            log.info("%s filtreleri: %s", symbol, self.filters[symbol])

        self.notify(f"🚀 Bot basladi: {', '.join(self.cfg.symbols)} ({net}, {mode})")

        while True:
            try:
                self.run_once()
            except BinanceError as e:
                log.error("Binance hatasi: %s", e)
            except Exception:
                log.exception("Beklenmeyen hata")
            time.sleep(self.cfg.poll_seconds)
