#!/usr/bin/env python3
"""Backtest modulu: stratejiyi gecmis verilerle test eder.

Kullanim:
    python backtest.py                                  # config.yaml'daki ilk coin, 1000 mum
    python backtest.py --symbol ETHUSDT --candles 3000  # baska coin, daha uzun gecmis
    python backtest.py --interval 5m --candles 2000     # farkli mum araligi
"""

import argparse
from dataclasses import dataclass

from trading_bot.binance_client import BinanceClient
from trading_bot.config import Config, load_config
from trading_bot.strategy import BUY, SELL, EmaRsiStrategy

FEE_PCT = 0.1  # Binance spot komisyonu (% / islem yonu)


@dataclass
class Trade:
    entry: float
    exit: float
    reason: str

    @property
    def pnl_pct(self) -> float:
        """Komisyon dahil net getiri yuzdesi."""
        gross = (self.exit - self.entry) / self.entry * 100
        return gross - 2 * FEE_PCT


def fetch_history(client: BinanceClient, symbol: str, interval: str, total: int) -> list[dict]:
    """Binance'ten geriye dogru sayfalayarak 'total' adet mum ceker."""
    klines: list[dict] = []
    end_time = None
    while len(klines) < total:
        batch = min(1000, total - len(klines))
        params = {"symbol": symbol, "interval": interval, "limit": batch}
        if end_time:
            params["endTime"] = end_time
        chunk = client._request("GET", "/api/v3/klines", params)
        if not chunk:
            break
        parsed = [
            {"open_time": k[0], "high": float(k[2]), "low": float(k[3]), "close": float(k[4])}
            for k in chunk
        ]
        klines = parsed + klines
        end_time = parsed[0]["open_time"] - 1
        if len(chunk) < batch:
            break
    return klines


def run_backtest(klines: list[dict], cfg: Config) -> tuple[list[Trade], list[float]]:
    """Stratejiyi mum mum ilerleterek simule eder.

    Cikislar mum ici high/low ile kontrol edilir (kotumser siralama: once stop).
    Donus: (islemler, islem sonrasi kumulatif getiri egrisi %)
    """
    strategy = EmaRsiStrategy(cfg.strategy)
    r = cfg.risk
    trades: list[Trade] = []
    equity_curve: list[float] = [0.0]
    entry = peak = 0.0
    in_position = False

    def close(price: float, reason: str):
        nonlocal in_position
        trades.append(Trade(entry, price, reason))
        equity_curve.append(equity_curve[-1] + trades[-1].pnl_pct)
        in_position = False

    for i in range(strategy.min_candles() + 1, len(klines)):
        candle = klines[i]
        closes = [k["close"] for k in klines[:i]]  # su ana kadar kapanan mumlar

        if in_position:
            # 1) sabit stop (mum dibiyle, kotumser)
            stop_price = entry * (1 - r.stop_loss_pct / 100)
            if candle["low"] <= stop_price:
                close(stop_price, "zarar durdur")
                continue
            # 2) sabit kar al (mum tepesiyle)
            if r.take_profit_pct > 0:
                tp_price = entry * (1 + r.take_profit_pct / 100)
                if candle["high"] >= tp_price:
                    close(tp_price, "kar al")
                    continue
            # 3) trailing stop: tepe guncelle, dusus kontrolu
            if r.trailing_stop_pct > 0:
                peak = max(peak, candle["high"])
                peak_gain_pct = (peak - entry) / entry * 100
                if peak_gain_pct >= r.trailing_activation_pct:
                    trail_price = peak * (1 - r.trailing_stop_pct / 100)
                    if candle["low"] <= trail_price:
                        close(trail_price, "iz suren stop")
                        continue

        signal = strategy.evaluate(closes)
        if not in_position and signal.action == BUY:
            entry = peak = candle["close"]
            in_position = True
        elif in_position and signal.action == SELL:
            close(candle["close"], signal.reason)

    return trades, equity_curve


def print_report(symbol: str, interval: str, klines: list[dict], trades: list[Trade],
                 equity: list[float], cfg: Config):
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    total_pct = equity[-1]
    quote = cfg.risk.quote_per_trade
    total_usdt = sum(t.pnl_pct / 100 * quote for t in trades)

    # maksimum dusus (drawdown)
    peak_eq, max_dd = 0.0, 0.0
    for e in equity:
        peak_eq = max(peak_eq, e)
        max_dd = max(max_dd, peak_eq - e)

    hold_pct = (klines[-1]["close"] - klines[0]["close"]) / klines[0]["close"] * 100
    days = (klines[-1]["open_time"] - klines[0]["open_time"]) / 86_400_000

    print("=" * 56)
    print(f"BACKTEST RAPORU  {symbol} {interval}  ({len(klines)} mum, ~{days:.1f} gun)")
    print("=" * 56)
    print(f"Toplam islem        : {len(trades)}")
    if trades:
        print(f"Kazanan / kaybeden  : {len(wins)} / {len(losses)}"
              f"  (kazanma orani %{len(wins) / len(trades) * 100:.0f})")
        print(f"Ortalama islem      : {total_pct / len(trades):+.3f}%")
        best = max(trades, key=lambda t: t.pnl_pct)
        worst = min(trades, key=lambda t: t.pnl_pct)
        print(f"En iyi / en kotu    : {best.pnl_pct:+.2f}% / {worst.pnl_pct:+.2f}%")
    print(f"Net getiri (komisyon dahil): {total_pct:+.2f}%"
          f"  (~{total_usdt:+.2f} USDT @ {quote:.0f} USDT/islem)")
    print(f"Maksimum dusus      : -{max_dd:.2f}%")
    print(f"Al-ve-tut karsilastirmasi: {hold_pct:+.2f}%")
    if days > 0 and trades:
        print(f"Gunluk ortalama     : {total_usdt / days:+.2f} USDT")
    print("=" * 56)
    print("Not: Gecmis performans gelecegi garanti etmez. Komisyon %0.1/yon"
          " dahildir; kayma (slippage) dahil degildir.")


def main():
    parser = argparse.ArgumentParser(description="Strateji backtest araci")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--symbol", default=None, help="islem cifti (vars: config'deki ilk coin)")
    parser.add_argument("--interval", default=None, help="mum araligi (vars: config'deki)")
    parser.add_argument("--candles", type=int, default=1000, help="test edilecek mum sayisi")
    args = parser.parse_args()

    cfg = load_config(args.config)
    symbol = (args.symbol or cfg.symbols[0]).upper()
    interval = args.interval or cfg.interval

    client = BinanceClient(testnet=False)  # gecmis veri icin ana ag (sadece okuma, anahtar gerekmez)
    print(f"{symbol} {interval} icin {args.candles} mum indiriliyor...")
    klines = fetch_history(client, symbol, interval, args.candles)
    if len(klines) < 100:
        print(f"Yeterli veri alinamadi ({len(klines)} mum). Sembolu/araligi kontrol edin.")
        return

    trades, equity = run_backtest(klines, cfg)
    print_report(symbol, interval, klines, trades, equity, cfg)


if __name__ == "__main__":
    main()
