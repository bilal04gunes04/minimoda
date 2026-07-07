# Binance Trade Botu

EMA kesişimi + RSI filtresi stratejisiyle çalışan, Python ile yazılmış bir Binance **spot** trade botu.

## Özellikler

- **Çoklu coin desteği**: aynı anda birden fazla paritede işlem (varsayılan: BTC, ETH, SOL)
- **EMA(9/21) kesişimi + RSI(14) filtresi** stratejisi (parametreler ayarlanabilir)
- **4 katmanlı sinyal onay filtresi**: hacim onayı, order book (emir defteri) dengesi, Fear & Greed piyasa rejimi, balina emir akışı — zayıf sinyalleri işleme dönüşmeden eler
- **Trailing stop (iz süren stop)**: kâr belli bir seviyeye ulaşınca devreye girer, tepe fiyatı takip eder — kârı kilitler, yükseliş sürdükçe satmaz
- **Telegram kontrol paneli**: telefondan durum izleme, duraklat/devam, pozisyon kapatma, günlük rapor + her işlemde anlık bildirim
- **Backtest modülü**: stratejiyi gerçek geçmiş verilerle test edin, kazanma oranını görün
- **Otomatik VPS kurulumu**: tek komutla sunucuya kurulum, 7/24 kesintisiz çalışma
- **Günlük kâr hedefi**: hedefe (örn. ana paranın %10'u) ulaşınca bot o gün yeni işlem açmaz
- **Günlük zarar limiti**: limit aşılırsa bot o gün durur, ana parayı korur
- **Kağıt işlem (dry-run)** ve **testnet** modları — varsayılan olarak açık, risksiz test
- Pozisyonlar `state.json`'a kaydedilir; bot yeniden başlasa da unutmaz

## Kurulum

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

API anahtarlarınızı girin (kağıt işlem modu için gerekmez):

```bash
cp .env.example .env
# .env dosyasini duzenleyip anahtarlarinizi yazin
```

> Testnet anahtarı almak için: https://testnet.binance.vision/ (GitHub hesabıyla ücretsiz giriş)

## Çalıştırma

```bash
python bot.py
```

Bot varsayılan olarak **testnet + kağıt işlem** modunda başlar; hiçbir gerçek emir gönderilmez.

## Backtest (stratejiyi geçmişle test etme)

Gerçek geçmiş fiyat verisini indirip stratejiyi üzerinde çalıştırır:

```bash
python backtest.py                                  # config'deki ilk coin, son 1000 mum
python backtest.py --symbol ETHUSDT --candles 5000  # daha uzun gecmis
python backtest.py --interval 5m --candles 3000     # farkli mum araligi
```

Rapor: toplam işlem, kazanma oranı, komisyon dahil net getiri, maksimum düşüş ve al-ve-tut karşılaştırması. **Gerçek paraya geçmeden önce mutlaka backtest yapın.**

## Telegram kontrol paneli

1. Telegram'da **@BotFather**'a `/newbot` yazıp bir bot oluşturun, verdiği **token**'ı kopyalayın.
2. **@userinfobot**'a herhangi bir mesaj atın, size **chat ID**'nizi söyler.
3. İkisini `.env` dosyasına yazın (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
4. `config.yaml`'da `telegram.enabled: true` yapın ve botu başlatın.

| Komut | İşlev |
|---|---|
| `/durum` | Bot durumu, açık pozisyonlar, günlük K/Z |
| `/duraklat` | Yeni alımları durdur (açık pozisyonlar yönetilmeye devam eder) |
| `/devam` | Alımları tekrar başlat |
| `/kapat BTCUSDT` | Pozisyonu hemen piyasa fiyatından kapat |
| `/rapor` | Günlük işlem raporu (kazanma oranı dahil) |
| `/yardim` | Komut listesi |

Ayrıca her alım/satımda ve gün sonunda otomatik bildirim gelir. Sadece sizin chat ID'nizden gelen komutlar kabul edilir.

## VPS'e kurulum (7/24 çalıştırma)

Ubuntu/Debian bir sunucuda (DigitalOcean, Hetzner, Oracle Cloud vb.):

```bash
git clone https://github.com/bilal04gunes04/minimoda.git
cd minimoda
git checkout claude/binance-trading-bot-gw89nz
chmod +x setup_vps.sh
./setup_vps.sh
```

Betik her şeyi kurar ve botu **systemd servisi** olarak başlatır: sunucu yeniden başlasa da bot otomatik açılır, çökerse 10 saniyede kendini yeniden başlatır.

```bash
sudo systemctl status tradebot     # durum
sudo journalctl -u tradebot -f     # canli log
sudo systemctl stop tradebot       # durdur
nano .env && sudo systemctl restart tradebot   # anahtar girip yeniden baslat
```

## Yapılandırma (`config.yaml`)

| Ayar | Açıklama | Varsayılan |
|---|---|---|
| `testnet` | `true` = testnet, `false` = gerçek hesap | `true` |
| `dry_run` | `true` = emirler sadece simüle edilir | `true` |
| `symbols` | İşlem çiftleri listesi | BTC, ETH, SOL |
| `interval` | Mum aralığı (`1m`, `5m`, `15m`, `1h`...) | `1m` |
| `strategy.ema_fast` / `ema_slow` | EMA periyotları | `9` / `21` |
| `strategy.rsi_period` | RSI periyodu | `14` |
| `risk.quote_per_trade` | İşlem başına USDT | `100` |
| `risk.max_open_positions` | Tüm coinlerde toplam açık pozisyon | `2` |
| `risk.stop_loss_pct` | % sabit zarar durdur | `0.5` |
| `risk.take_profit_pct` | % sabit kâr al (`0` = kapalı, trailing kullanılır) | `0` |
| `risk.trailing_activation_pct` | Trailing'in devreye girdiği kâr yüzdesi | `0.4` |
| `risk.trailing_stop_pct` | Tepeden bu kadar düşünce sat | `0.3` |
| `daily.capital` | Ana para (USDT) | `1000` |
| `daily.profit_target_pct` | Günlük kâr hedefi (%, ulaşılınca durur) | `10` |
| `daily.max_loss_pct` | Günlük zarar limiti (%, aşılırsa durur) | `3` |
| `telegram.enabled` | Telegram paneli | `false` |
| `poll_seconds` | Kontrol aralığı (saniye) | `15` |

## Sinyal onay filtreleri

Strateji AL dediğinde işlem hemen açılmaz; sinyal 4 filtreden geçer. Herhangi biri "hayır" derse işlem iptal olur (log'da sebebiyle görünür). Hepsi ücretsiz API kullanır, `config.yaml`'ın `filters` bölümünden tek tek açılıp kapanabilir:

| Filtre | Ne kontrol eder | Neyi engeller |
|---|---|---|
| **Hacim onayı** | Kesişim mumunun hacmi son 20 mumun ortalamasının ≥1.2 katı mı? | Düşük hacimli sahte kesişimler |
| **Order book** | Emir defterinde alış tarafının payı ≥%55 mi? | Satış duvarına doğru alım yapmak |
| **Fear & Greed** | Piyasa endeksi 20-85 bandında mı? (1 saat önbellekli) | Panik çöküşte veya balon tepesinde alım |
| **Balina akışı** | Son işlemlerdeki 50k$+ emirlerde satış oranı ≤%65 mi? | Büyük oyuncular satarken alım yapmak |

API hatasında filtre atlanır (bot kilitlenmez), log'a uyarı düşer. Backtest hacim filtresini de uygular; diğer üçü geçmişe dönük test edilemez (tarihsel order book verisi yoktur).

## Strateji ve çıkış mantığı

- **AL**: Hızlı EMA yavaş EMA'yı yukarı keser **ve** RSI aşırı alım bölgesinde (≥70) değildir.
- **SAT** (hangisi önce gelirse):
  1. **Sabit stop**: fiyat girişten `stop_loss_pct` kadar düşerse.
  2. **Trailing stop**: kâr `trailing_activation_pct`'ye ulaştıktan sonra fiyat tepeden `trailing_stop_pct` kadar düşerse — yükseliş sürdükçe satmaz, kârı kilitler.
  3. **Strateji sinyali**: EMA aşağı kesişim veya RSI ≥ 70.

## Günlük kâr hedefi nasıl çalışır?

- Bot gün içinde kapanan her işlemin gerçekleşen kâr/zararını (USDT) toplar.
- Toplam, `daily.capital × daily.profit_target_pct / 100` değerine ulaşırsa bot **o gün yeni pozisyon açmaz** (açık pozisyonlar yönetilmeye devam eder).
- Toplam zarar `daily.max_loss_pct` limitini aşarsa bot yine durur.
- Gece yarısı sayaç sıfırlanır ve bot ertesi gün yeniden başlar.

> **Önemli:** `profit_target_pct` bir *durdurma eşiğidir*, kazanç garantisi değildir. Piyasa uygun sinyal üretmezse bot o gün hedefe ulaşamayabilir; hiçbir strateji düzenli olarak günlük %10 kazandıramaz.

## Gerçek hesapla kullanım

1. Önce **backtest** yapın, sonra **testnet'te** en az 1-2 hafta izleyin.
2. `config.yaml` içinde `testnet: false` ve `dry_run: false` yapın.
3. `.env` dosyasına **gerçek** API anahtarlarınızı yazın (API anahtarında *sadece spot trade* yetkisi verin, **para çekme yetkisi vermeyin**).
4. Bot başlarken sizden `EVET` yazarak onay ister.

## ⚠️ Risk uyarısı

Bu bot eğitim amaçlıdır ve kâr garantisi vermez. Kripto para ticareti yüksek risk içerir; kaybetmeyi göze alamayacağınız parayla işlem yapmayın. Gerçek hesapta çalıştırmadan önce stratejinizi backtest, testnet ve kağıt işlem modunda uzun süre test edin.
