# Binance Trade Botu

EMA kesişimi + RSI filtresi stratejisiyle çalışan, Python ile yazılmış basit bir Binance **spot** trade botu.

## Özellikler

- **EMA(9/21) kesişimi + RSI(14) filtresi** stratejisi (parametreler ayarlanabilir)
- **Scalping modu**: kısa mum aralığı (5 dk) ve küçük kâr/zarar eşikleriyle sık işlem
- **Günlük kâr hedefi**: hedefe (örn. ana paranın %10'u) ulaşınca bot o gün yeni işlem açmaz
- **Günlük zarar limiti**: limit aşılırsa bot o gün durur, ana parayı korur
- **Zarar durdur (stop-loss)** ve **kâr al (take-profit)** risk yönetimi
- **Kağıt işlem (dry-run) modu**: emirler borsaya gönderilmeden simüle edilir — varsayılan olarak açık
- **Testnet desteği**: sahte parayla güvenle test edin — varsayılan olarak açık
- Pozisyon durumu `state.json` dosyasına kaydedilir; bot yeniden başlasa da açık pozisyonunu hatırlar
- Harici SDK yok; sadece `requests`, `PyYAML` ve `python-dotenv`

## Kurulum

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

API anahtarlarınızı girin:

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

## Yapılandırma (`config.yaml`)

| Ayar | Açıklama | Varsayılan |
|---|---|---|
| `testnet` | `true` = testnet, `false` = gerçek hesap | `true` |
| `dry_run` | `true` = emirler sadece simüle edilir | `true` |
| `symbol` | İşlem çifti | `BTCUSDT` |
| `interval` | Mum aralığı (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`...) | `1m` |
| `strategy.ema_fast` / `ema_slow` | EMA periyotları | `9` / `21` |
| `strategy.rsi_period` | RSI periyodu | `14` |
| `risk.quote_per_trade` | İşlem başına USDT | `100` |
| `risk.stop_loss_pct` | % zarar durdur (işlem başına) | `0.5` |
| `risk.take_profit_pct` | % kâr al (işlem başına) | `0.8` |
| `daily.capital` | Ana para (USDT) | `1000` |
| `daily.profit_target_pct` | Günlük kâr hedefi (%, ulaşılınca durur) | `10` |
| `daily.max_loss_pct` | Günlük zarar limiti (%, aşılırsa durur) | `3` |
| `poll_seconds` | Kontrol aralığı (saniye) | `15` |

## Strateji

- **AL**: Hızlı EMA yavaş EMA'yı yukarı keser **ve** RSI aşırı alım bölgesinde (≥70) değildir.
- **SAT**: Hızlı EMA yavaş EMA'yı aşağı keser **veya** RSI ≥ 70 olur.
- Açık pozisyonda fiyat, giriş fiyatına göre `stop_loss_pct` kadar düşerse veya `take_profit_pct` kadar yükselirse pozisyon otomatik kapatılır.

## Gerçek hesapla kullanım

1. `config.yaml` içinde `testnet: false` ve `dry_run: false` yapın.
2. `.env` dosyasına **gerçek** API anahtarlarınızı yazın (API anahtarında *sadece spot trade* yetkisi verin, **para çekme yetkisi vermeyin**).
3. Bot başlarken sizden `EVET` yazarak onay ister.

## Günlük kâr hedefi nasıl çalışır?

- Bot gün içinde kapanan her işlemin gerçekleşen kâr/zararını (USDT) toplar.
- Toplam, `daily.capital × daily.profit_target_pct / 100` değerine ulaşırsa bot **o gün yeni pozisyon açmaz** (açık pozisyon varsa yönetilmeye devam eder).
- Toplam zarar `daily.max_loss_pct` limitini aşarsa bot yine durur — kötü bir günde ana paranın erimesini engeller.
- Gece yarısı sayaç sıfırlanır ve bot ertesi gün yeniden işlem yapmaya başlar.

> **Önemli:** `profit_target_pct` bir *durdurma eşiğidir*, kazanç garantisi değildir. Piyasa uygun sinyal üretmezse bot o gün hedefe ulaşamayabilir; hiçbir strateji düzenli olarak günlük %10 kazandıramaz. Hedefi ne kadar yüksek tutarsanız, o hedefe ulaşılamayan gün sayısı o kadar artar.

## ⚠️ Risk uyarısı

Bu bot eğitim amaçlıdır ve kâr garantisi vermez. Kripto para ticareti yüksek risk içerir; kaybetmeyi göze alamayacağınız parayla işlem yapmayın. Gerçek hesapta çalıştırmadan önce stratejinizi testnet ve kağıt işlem modunda uzun süre test edin.
