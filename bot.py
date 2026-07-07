#!/usr/bin/env python3
"""Binance trade botu - giris noktasi.

Kullanim:
    python bot.py                # config.yaml ile calisir
    python bot.py --config x.yaml
"""

import argparse
import logging
import sys

from trading_bot.config import load_config
from trading_bot.trader import Trader


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log", encoding="utf-8"),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Binance spot trade botu")
    parser.add_argument("--config", default="config.yaml", help="yapilandirma dosyasi")
    args = parser.parse_args()

    setup_logging()
    log = logging.getLogger("bot")

    try:
        cfg = load_config(args.config)
    except ValueError as e:
        log.error("Yapilandirma hatasi: %s", e)
        sys.exit(1)

    if not cfg.testnet and not cfg.dry_run:
        print("=" * 60)
        print("UYARI: GERCEK HESAPTA GERCEK EMIRLER verilecek!")
        print("Devam etmek icin 'EVET' yazin:")
        print("=" * 60)
        if input("> ").strip() != "EVET":
            print("Iptal edildi.")
            sys.exit(0)

    trader = Trader(cfg)
    try:
        trader.run_forever()
    except KeyboardInterrupt:
        log.info("Bot durduruldu (Ctrl+C)")


if __name__ == "__main__":
    main()
