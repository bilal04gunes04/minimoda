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
    max_open_positions: int = 2       # tum coinlerde toplam acik pozisyon
    stop_loss_pct: float = 0.5        # % sabit zarar durdur
    take_profit_pct: float = 0.0      # % sabit kar al (0 = kapali, trailing kullanilir)
    trailing_activation_pct: float = 0.4  # kar bu yuzdeye ulasinca trailing devreye girer
    trailing_stop_pct: float = 0.3        # tepe fiyattan bu kadar dusunce satilir (0 = kapali)


@dataclass
class DailyConfig:
    capital: float = 1000.0          # ana para (USDT) - gunluk hedef/limit bunun yuzdesi
    profit_target_pct: float = 10.0  # gunluk kar HEDEFI: ulasilinca bot o gun durur
    max_loss_pct: float = 3.0        # gunluk zarar LIMITI: asilirsa bot o gun durur


@dataclass
class TelegramConfig:
    enabled: bool = False
    token: str = ""     # .env: TELEGRAM_BOT_TOKEN
    chat_id: str = ""   # .env: TELEGRAM_CHAT_ID


@dataclass
class Config:
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True
    dry_run: bool = True
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT"])
    interval: str = "1m"
    poll_seconds: int = 15
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    daily: DailyConfig = field(default_factory=DailyConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


def load_config(path: str = "config.yaml") -> Config:
    load_dotenv()

    raw = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    # coklu coin: 'symbols' listesi; eski 'symbol' alani da kabul edilir
    symbols = raw.get("symbols") or [raw.get("symbol", "BTCUSDT")]
    if isinstance(symbols, str):
        symbols = [symbols]
    symbols = [str(s).upper() for s in symbols]

    tg_raw = raw.get("telegram") or {}
    telegram = TelegramConfig(
        enabled=bool(tg_raw.get("enabled", False)),
        token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )

    cfg = Config(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=bool(raw.get("testnet", True)),
        dry_run=bool(raw.get("dry_run", True)),
        symbols=symbols,
        interval=str(raw.get("interval", "1m")),
        poll_seconds=int(raw.get("poll_seconds", 15)),
        strategy=StrategyConfig(**(raw.get("strategy") or {})),
        risk=RiskConfig(**(raw.get("risk") or {})),
        daily=DailyConfig(**(raw.get("daily") or {})),
        telegram=telegram,
    )

    if cfg.strategy.ema_fast >= cfg.strategy.ema_slow:
        raise ValueError("ema_fast, ema_slow'dan kucuk olmalidir")
    if not cfg.symbols:
        raise ValueError("en az bir islem cifti (symbols) gereklidir")
    if cfg.daily.capital <= 0:
        raise ValueError("daily.capital pozitif olmalidir")
    if cfg.risk.quote_per_trade > cfg.daily.capital:
        raise ValueError("risk.quote_per_trade, daily.capital'den buyuk olamaz")
    if not cfg.dry_run and (not cfg.api_key or not cfg.api_secret):
        raise ValueError(
            "dry_run kapaliyken BINANCE_API_KEY ve BINANCE_API_SECRET zorunludur (.env dosyasi)"
        )
    if cfg.telegram.enabled and (not cfg.telegram.token or not cfg.telegram.chat_id):
        raise ValueError(
            "telegram.enabled acikken TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID zorunludur (.env dosyasi)"
        )
    return cfg
