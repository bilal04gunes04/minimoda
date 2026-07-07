"""Telegram kontrol paneli: botu telefondan izleme ve yonetme.

Komutlar:
    /durum    - bot durumu, acik pozisyonlar, gunluk K/Z
    /duraklat - yeni alimlari durdur (acik pozisyonlar yonetilmeye devam eder)
    /devam    - alimlari tekrar baslat
    /kapat SEMBOL - pozisyonu hemen piyasa fiyatindan kapat (orn: /kapat BTCUSDT)
    /rapor    - gunluk islem raporu
    /yardim   - komut listesi
"""

import logging
import threading

import requests

log = logging.getLogger(__name__)

HELP_TEXT = (
    "📖 Komutlar:\n"
    "/durum - bot durumu ve acik pozisyonlar\n"
    "/duraklat - yeni alimlari durdur\n"
    "/devam - alimlari tekrar baslat\n"
    "/kapat SEMBOL - pozisyonu kapat (orn: /kapat BTCUSDT)\n"
    "/rapor - gunluk islem raporu\n"
    "/yardim - bu liste"
)


class TelegramBot(threading.Thread):
    """Ayri bir is parcaciginda Telegram'i dinler, komutlari Trader'a iletir."""

    def __init__(self, token: str, chat_id: str, trader):
        super().__init__(daemon=True, name="telegram")
        self.api = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self.trader = trader
        self.offset = 0

    # ---------- gonderme ----------

    def send(self, text: str):
        try:
            requests.post(
                f"{self.api}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=10,
            )
        except requests.RequestException as e:
            log.warning("Telegram mesaji gonderilemedi: %s", e)

    # ---------- komut isleme ----------

    def dispatch(self, text: str) -> str:
        """Komutu isler ve cevap metnini dondurur."""
        parts = text.strip().split()
        if not parts:
            return HELP_TEXT
        cmd = parts[0].lower().split("@")[0]  # "/durum@BotAdi" bicimini de destekle

        if cmd in ("/durum", "/status", "/start"):
            return self.trader.status_text()

        if cmd == "/duraklat":
            self.trader.paused = True
            return "⏸ Bot duraklatildi. Yeni alim yapilmayacak; acik pozisyonlar yonetilmeye devam edecek."

        if cmd == "/devam":
            self.trader.paused = False
            return "▶️ Bot devam ediyor, alimlar tekrar acik."

        if cmd == "/kapat":
            if len(parts) < 2:
                open_syms = ", ".join(self.trader.positions) or "yok"
                return f"Kullanim: /kapat SEMBOL\nAcik pozisyonlar: {open_syms}"
            return self.trader.close_position(parts[1].upper())

        if cmd == "/rapor":
            d = self.trader.daily
            losses = d.trades - d.wins
            win_rate = (d.wins / d.trades * 100) if d.trades else 0.0
            target = self.trader.cfg.daily.capital * self.trader.cfg.daily.profit_target_pct / 100
            return (
                f"📊 Gunluk rapor ({d.day})\n"
                f"K/Z: {d.realized_pnl:+.2f} USDT (hedef {target:.2f})\n"
                f"Islem: {d.trades} | Kazanan: {d.wins} | Kaybeden: {losses}\n"
                f"Kazanma orani: %{win_rate:.0f}"
            )

        return HELP_TEXT

    # ---------- dinleme dongusu ----------

    def run(self):
        log.info("Telegram kontrol paneli dinlemede")
        while True:
            try:
                resp = requests.get(
                    f"{self.api}/getUpdates",
                    params={"offset": self.offset, "timeout": 30},
                    timeout=40,
                )
                for update in resp.json().get("result", []):
                    self.offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    text = msg.get("text", "")
                    sender = str(msg.get("chat", {}).get("id", ""))
                    if sender != self.chat_id:
                        log.warning("Yetkisiz Telegram kullanicisi engellendi: %s", sender)
                        continue
                    if text:
                        log.info("Telegram komutu: %s", text)
                        self.send(self.dispatch(text))
            except requests.RequestException as e:
                log.warning("Telegram baglanti hatasi: %s", e)
            except Exception:
                log.exception("Telegram dongusunde beklenmeyen hata")
