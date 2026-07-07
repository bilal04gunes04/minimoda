"""Yapilandirma yukleme: config.yaml + .env"""

import os
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv


@dataclass
class StrategyConfig:
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0


@dataclass
class RiskConfig:
    quote_per_trade: float = 100.0
    max_open_positions: int = 1
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0


@dataclass
class Config:
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True
    dry_run: bool = True
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    poll_seconds: int = 60
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)


def load_config(path: str = "config.yaml") -> Config:
    load_dotenv()

    raw = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    cfg = Config(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=bool(raw.get("testnet", True)),
        dry_run=bool(raw.get("dry_run", True)),
        symbol=str(raw.get("symbol", "BTCUSDT")).upper(),
        interval=str(raw.get("interval", "15m")),
        poll_seconds=int(raw.get("poll_seconds", 60)),
        strategy=StrategyConfig(**(raw.get("strategy") or {})),
        risk=RiskConfig(**(raw.get("risk") or {})),
    )

    if cfg.strategy.ema_fast >= cfg.strategy.ema_slow:
        raise ValueError("ema_fast, ema_slow'dan kucuk olmalidir")
    if not cfg.dry_run and (not cfg.api_key or not cfg.api_secret):
        raise ValueError(
            "dry_run kapaliyken BINANCE_API_KEY ve BINANCE_API_SECRET zorunludur (.env dosyasi)"
        )
    return cfg
