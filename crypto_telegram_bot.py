"""
Kripto Teknik Analiz Telegram Botu v1.0
=======================================
BTC ve ETH icin 4 saatlik teknik analiz ve tavsiyeler.

OZELLIKLER:
- RSI (14 periyot)
- MACD (12, 26, 9)
- Bollinger Bands (20, 2)
- Stochastic Oscillator (14, 3, 3)
- EMA Kesisimleri (9/21, 50/200)
- Hacim Analizi
- Fibonacci Seviyeleri
- Otomatik 4 saatlik bildirimler

KULLANIM:
1. TELEGRAM_TOKEN environment variable'i ayarla (egitim botu ile ayni)
2. TELEGRAM_CHAT_ID environment variable'i ayarla (egitim botu ile ayni)
3. Botu calistir: python crypto_telegram_bot.py

GitHub Actions ile otomatik calistirilabilir.
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

import requests
import numpy as np
import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Logging yapilandirmasi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== YAPILANDIRMA ==============

class Config:
    """Bot yapilandirma ayarlari"""
    # Egitim botu ile ayni environment variable'lar
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

    # CoinGecko API (ucretsiz, API key gerektirmez, bolgesel kisitlama yok)
    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

    # Analiz edilecek coinler
    SYMBOLS = ['BTCUSDT', 'ETHUSDT']

    # Zaman dilimi
    TIMEFRAME = '4h'
    KLINE_LIMIT = 200  # Son 200 mum (yeterli veri icin)

    # Indikatör parametreleri
    RSI_PERIOD = 14
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    BB_PERIOD = 20
    BB_STD = 2
    STOCH_K = 14
    STOCH_D = 3
    STOCH_SMOOTH = 3
    EMA_SHORT = 9
    EMA_MEDIUM = 21
    EMA_50 = 50
    EMA_200 = 200

    # Scheduler - Her 4 saatte bir (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)
    SCHEDULE_HOURS = [0, 4, 8, 12, 16, 20]


# ============== SINYAL TIPLERI ==============

class SignalType(Enum):
    """Sinyal tipleri"""
    STRONG_BUY = "GUCLU ALIS"
    BUY = "ALIS"
    NEUTRAL = "NOTR"
    SELL = "SATIS"
    STRONG_SELL = "GUCLU SATIS"


@dataclass
class TechnicalIndicators:
    """Teknik indikator sonuclari"""
    # RSI
    rsi: float
    rsi_signal: str

    # MACD
    macd: float
    macd_signal: float
    macd_histogram: float
    macd_trend: str

    # Bollinger Bands
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: str
    bb_bandwidth: float

    # Stochastic
    stoch_k: float
    stoch_d: float
    stoch_signal: str

    # EMA
    ema_9: float
    ema_21: float
    ema_50: float
    ema_200: float
    ema_trend: str
    golden_cross: bool
    death_cross: bool

    # Hacim
    volume_change: float
    volume_signal: str

    # Fiyat
    current_price: float
    price_change_24h: float

    # Fibonacci
    fib_levels: Dict[str, float]


@dataclass
class AnalysisResult:
    """Analiz sonucu"""
    symbol: str
    timestamp: datetime
    indicators: TechnicalIndicators
    overall_signal: SignalType
    confidence: float
    recommendation: str
    key_levels: Dict[str, float]


# ============== COINGECKO API ==============

class CoinGeckoAPI:
    """CoinGecko API istemcisi - Ucretsiz, API key gerektirmez"""

    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        # CoinGecko coin ID'leri
        self.coin_ids = {
            'BTCUSDT': 'bitcoin',
            'ETHUSDT': 'ethereum'
        }

    def get_klines(self, symbol: str, interval: str = '4h', limit: int = 200) -> pd.DataFrame:
        """OHLCV verilerini cek - CoinGecko OHLC endpoint"""
        coin_id = self.coin_ids.get(symbol, symbol.lower().replace('usdt', ''))

        # CoinGecko OHLC endpoint - days=30 4 saatlik mumlar verir
        url = f"{self.base_url}/coins/{coin_id}/ohlc"
        params = {
            'vs_currency': 'usd',
            'days': '30'  # 30 gun = 4 saatlik mumlar
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # CoinGecko format: [[timestamp, open, high, low, close], ...]
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])

            # Veri tiplerini duzelt
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Hacim verisi icin ayri endpoint (market_chart)
            df['volume'] = self._get_volume_data(coin_id, len(df))

            logger.info(f"CoinGecko'dan {len(df)} mum verisi alindi: {symbol}")
            return df

        except Exception as e:
            logger.error(f"CoinGecko API hatasi ({symbol}): {e}")
            raise

    def _get_volume_data(self, coin_id: str, length: int) -> pd.Series:
        """Hacim verilerini cek"""
        url = f"{self.base_url}/coins/{coin_id}/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': '30'
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            volumes = [v[1] for v in data.get('total_volumes', [])]

            # OHLC ile ayni uzunluga getir
            if len(volumes) > length:
                # Her N. eleman al
                step = len(volumes) // length
                volumes = volumes[::step][:length]
            elif len(volumes) < length:
                # Eksik olanlari son degerle doldur
                volumes.extend([volumes[-1]] * (length - len(volumes)))

            return pd.Series(volumes[:length])

        except Exception as e:
            logger.warning(f"Hacim verisi alinamadi: {e}")
            return pd.Series([0] * length)

    def get_24h_ticker(self, symbol: str) -> Dict:
        """24 saatlik fiyat degisimi"""
        coin_id = self.coin_ids.get(symbol, symbol.lower().replace('usdt', ''))

        url = f"{self.base_url}/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true',
            'include_24hr_vol': 'true'
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            coin_data = data.get(coin_id, {})
            return {
                'priceChangePercent': coin_data.get('usd_24h_change', 0),
                'lastPrice': coin_data.get('usd', 0),
                'volume': coin_data.get('usd_24h_vol', 0)
            }

        except Exception as e:
            logger.error(f"24h ticker hatasi ({symbol}): {e}")
            return {'priceChangePercent': 0}


# ============== TEKNIK ANALIZ ==============

class TechnicalAnalyzer:
    """Teknik analiz hesaplayicisi"""

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._calculate_all()

    def _calculate_all(self):
        """Tum indikatorleri hesapla"""
        self._calculate_rsi()
        self._calculate_macd()
        self._calculate_bollinger()
        self._calculate_stochastic()
        self._calculate_emas()
        self._calculate_volume_ma()

    def _calculate_rsi(self, period: int = 14):
        """RSI hesapla"""
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        self.df['rsi'] = 100 - (100 / (1 + rs))

    def _calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD hesapla"""
        ema_fast = self.df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = self.df['close'].ewm(span=slow, adjust=False).mean()

        self.df['macd'] = ema_fast - ema_slow
        self.df['macd_signal'] = self.df['macd'].ewm(span=signal, adjust=False).mean()
        self.df['macd_histogram'] = self.df['macd'] - self.df['macd_signal']

    def _calculate_bollinger(self, period: int = 20, std: int = 2):
        """Bollinger Bands hesapla"""
        self.df['bb_middle'] = self.df['close'].rolling(window=period).mean()
        bb_std = self.df['close'].rolling(window=period).std()

        self.df['bb_upper'] = self.df['bb_middle'] + (bb_std * std)
        self.df['bb_lower'] = self.df['bb_middle'] - (bb_std * std)
        self.df['bb_bandwidth'] = (self.df['bb_upper'] - self.df['bb_lower']) / self.df['bb_middle'] * 100

    def _calculate_stochastic(self, k_period: int = 14, d_period: int = 3, smooth: int = 3):
        """Stochastic Oscillator hesapla"""
        low_min = self.df['low'].rolling(window=k_period).min()
        high_max = self.df['high'].rolling(window=k_period).max()

        self.df['stoch_k'] = ((self.df['close'] - low_min) / (high_max - low_min)) * 100
        self.df['stoch_k'] = self.df['stoch_k'].rolling(window=smooth).mean()
        self.df['stoch_d'] = self.df['stoch_k'].rolling(window=d_period).mean()

    def _calculate_emas(self):
        """EMA'lari hesapla"""
        self.df['ema_9'] = self.df['close'].ewm(span=9, adjust=False).mean()
        self.df['ema_21'] = self.df['close'].ewm(span=21, adjust=False).mean()
        self.df['ema_50'] = self.df['close'].ewm(span=50, adjust=False).mean()
        self.df['ema_200'] = self.df['close'].ewm(span=200, adjust=False).mean()

    def _calculate_volume_ma(self, period: int = 20):
        """Hacim hareketli ortalamasi"""
        self.df['volume_ma'] = self.df['volume'].rolling(window=period).mean()

    def get_fibonacci_levels(self, lookback: int = 50) -> Dict[str, float]:
        """Fibonacci geri cekilme seviyelerini hesapla"""
        recent = self.df.tail(lookback)
        high = recent['high'].max()
        low = recent['low'].min()
        diff = high - low

        return {
            '0.0': high,
            '23.6': high - (diff * 0.236),
            '38.2': high - (diff * 0.382),
            '50.0': high - (diff * 0.5),
            '61.8': high - (diff * 0.618),
            '78.6': high - (diff * 0.786),
            '100.0': low,
            # Extension levels
            '127.2': low - (diff * 0.272),
            '161.8': low - (diff * 0.618),
        }

    def get_indicators(self, price_change_24h: float = 0) -> TechnicalIndicators:
        """Tum indikator degerlerini al"""
        last = self.df.iloc[-1]
        prev = self.df.iloc[-2]

        # RSI sinyali
        rsi = last['rsi']
        if rsi < 30:
            rsi_signal = "ASIRI SATIM - Alis firsati"
        elif rsi < 40:
            rsi_signal = "Dusuk - Potansiyel alis"
        elif rsi > 70:
            rsi_signal = "ASIRI ALIM - Satis firsati"
        elif rsi > 60:
            rsi_signal = "Yuksek - Dikkatli ol"
        else:
            rsi_signal = "Notr bolge"

        # MACD sinyali
        macd = last['macd']
        macd_signal = last['macd_signal']
        macd_hist = last['macd_histogram']
        prev_hist = prev['macd_histogram']

        if macd > macd_signal and prev['macd'] <= prev['macd_signal']:
            macd_trend = "BULLISH CROSSOVER - Alis sinyali"
        elif macd < macd_signal and prev['macd'] >= prev['macd_signal']:
            macd_trend = "BEARISH CROSSOVER - Satis sinyali"
        elif macd_hist > 0 and macd_hist > prev_hist:
            macd_trend = "Yukselis momentumu artiyor"
        elif macd_hist < 0 and macd_hist < prev_hist:
            macd_trend = "Dusus momentumu artiyor"
        elif macd_hist > 0:
            macd_trend = "Pozitif momentum"
        else:
            macd_trend = "Negatif momentum"

        # Bollinger pozisyonu
        close = last['close']
        bb_upper = last['bb_upper']
        bb_lower = last['bb_lower']
        bb_middle = last['bb_middle']

        if close >= bb_upper:
            bb_position = "UST BANT - Asiri alim bolgesi"
        elif close <= bb_lower:
            bb_position = "ALT BANT - Asiri satim bolgesi"
        elif close > bb_middle:
            bb_position = "Orta bandin ustunde"
        else:
            bb_position = "Orta bandin altinda"

        # Stochastic sinyali
        stoch_k = last['stoch_k']
        stoch_d = last['stoch_d']
        prev_k = prev['stoch_k']
        prev_d = prev['stoch_d']

        if stoch_k < 20 and stoch_d < 20:
            if stoch_k > stoch_d and prev_k <= prev_d:
                stoch_signal = "BULLISH CROSS (asiri satim) - Guclu alis"
            else:
                stoch_signal = "Asiri satim bolgesi"
        elif stoch_k > 80 and stoch_d > 80:
            if stoch_k < stoch_d and prev_k >= prev_d:
                stoch_signal = "BEARISH CROSS (asiri alim) - Guclu satis"
            else:
                stoch_signal = "Asiri alim bolgesi"
        elif stoch_k > stoch_d:
            stoch_signal = "Yukselis yonlu"
        else:
            stoch_signal = "Dusus yonlu"

        # EMA trend analizi
        ema_9 = last['ema_9']
        ema_21 = last['ema_21']
        ema_50 = last['ema_50']
        ema_200 = last['ema_200']

        # Golden/Death Cross kontrolu (son 5 mumda)
        recent = self.df.tail(5)
        golden_cross = False
        death_cross = False

        for i in range(1, len(recent)):
            if (recent.iloc[i]['ema_50'] > recent.iloc[i]['ema_200'] and
                recent.iloc[i-1]['ema_50'] <= recent.iloc[i-1]['ema_200']):
                golden_cross = True
            if (recent.iloc[i]['ema_50'] < recent.iloc[i]['ema_200'] and
                recent.iloc[i-1]['ema_50'] >= recent.iloc[i-1]['ema_200']):
                death_cross = True

        if close > ema_200 and ema_50 > ema_200:
            ema_trend = "GUCLU YUKSELIS TRENDI"
        elif close > ema_200:
            ema_trend = "Yukselis trendi"
        elif close < ema_200 and ema_50 < ema_200:
            ema_trend = "GUCLU DUSUS TRENDI"
        elif close < ema_200:
            ema_trend = "Dusus trendi"
        else:
            ema_trend = "Kararsiz"

        # Hacim analizi
        volume = last['volume']
        volume_ma = last['volume_ma']
        volume_change = ((volume - volume_ma) / volume_ma) * 100

        if volume_change > 50:
            volume_signal = "COK YUKSEK HACIM - Guclu hareket"
        elif volume_change > 25:
            volume_signal = "Yuksek hacim - Trend onayi"
        elif volume_change < -25:
            volume_signal = "Dusuk hacim - Zayif hareket"
        else:
            volume_signal = "Normal hacim"

        # Fibonacci seviyeleri
        fib_levels = self.get_fibonacci_levels()

        return TechnicalIndicators(
            rsi=rsi,
            rsi_signal=rsi_signal,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            macd_trend=macd_trend,
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            bb_position=bb_position,
            bb_bandwidth=last['bb_bandwidth'],
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            stoch_signal=stoch_signal,
            ema_9=ema_9,
            ema_21=ema_21,
            ema_50=ema_50,
            ema_200=ema_200,
            ema_trend=ema_trend,
            golden_cross=golden_cross,
            death_cross=death_cross,
            volume_change=volume_change,
            volume_signal=volume_signal,
            current_price=close,
            price_change_24h=price_change_24h,
            fib_levels=fib_levels
        )


# ============== SINYAL URETICI ==============

class SignalGenerator:
    """Sinyal ve tavsiye uretici"""

    @staticmethod
    def generate_signal(indicators: TechnicalIndicators) -> Tuple[SignalType, float, str]:
        """Genel sinyal uret"""
        buy_score = 0
        sell_score = 0
        reasons = []

        # RSI (max 2 puan)
        if indicators.rsi < 30:
            buy_score += 2
            reasons.append("RSI asiri satim bolgesi")
        elif indicators.rsi < 40:
            buy_score += 1
        elif indicators.rsi > 70:
            sell_score += 2
            reasons.append("RSI asiri alim bolgesi")
        elif indicators.rsi > 60:
            sell_score += 1

        # MACD (max 2 puan)
        if "BULLISH CROSSOVER" in indicators.macd_trend:
            buy_score += 2
            reasons.append("MACD bullish crossover")
        elif "BEARISH CROSSOVER" in indicators.macd_trend:
            sell_score += 2
            reasons.append("MACD bearish crossover")
        elif indicators.macd_histogram > 0:
            buy_score += 1
        else:
            sell_score += 1

        # Bollinger (max 2 puan)
        if "ALT BANT" in indicators.bb_position:
            buy_score += 2
            reasons.append("Fiyat Bollinger alt bandinda")
        elif "UST BANT" in indicators.bb_position:
            sell_score += 2
            reasons.append("Fiyat Bollinger ust bandinda")

        # Stochastic (max 2 puan)
        if "BULLISH CROSS" in indicators.stoch_signal:
            buy_score += 2
            reasons.append("Stochastic bullish cross")
        elif "BEARISH CROSS" in indicators.stoch_signal:
            sell_score += 2
            reasons.append("Stochastic bearish cross")
        elif indicators.stoch_k < 20:
            buy_score += 1
        elif indicators.stoch_k > 80:
            sell_score += 1

        # EMA Trend (max 2 puan)
        if "GUCLU YUKSELIS" in indicators.ema_trend:
            buy_score += 2
            reasons.append("Guclu yukselis trendi")
        elif "GUCLU DUSUS" in indicators.ema_trend:
            sell_score += 2
            reasons.append("Guclu dusus trendi")
        elif "Yukselis" in indicators.ema_trend:
            buy_score += 1
        elif "Dusus" in indicators.ema_trend:
            sell_score += 1

        # Golden/Death Cross (bonus 2 puan)
        if indicators.golden_cross:
            buy_score += 2
            reasons.append("GOLDEN CROSS olusumu!")
        if indicators.death_cross:
            sell_score += 2
            reasons.append("DEATH CROSS olusumu!")

        # Hacim onayi (max 1 puan)
        if indicators.volume_change > 25:
            if buy_score > sell_score:
                buy_score += 1
                reasons.append("Yuksek hacim ile onay")
            elif sell_score > buy_score:
                sell_score += 1
                reasons.append("Yuksek hacim ile onay")

        # Toplam skor hesapla
        total = buy_score + sell_score
        if total == 0:
            confidence = 0.5
        else:
            confidence = max(buy_score, sell_score) / total

        # Sinyal tipi belirle
        net_score = buy_score - sell_score

        if net_score >= 5:
            signal = SignalType.STRONG_BUY
        elif net_score >= 2:
            signal = SignalType.BUY
        elif net_score <= -5:
            signal = SignalType.STRONG_SELL
        elif net_score <= -2:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL

        # Tavsiye olustur
        if signal == SignalType.STRONG_BUY:
            recommendation = f"GUCLU ALIS FIRSATI! {', '.join(reasons[:3])}"
        elif signal == SignalType.BUY:
            recommendation = f"Alis yonlu beklenti. {', '.join(reasons[:2])}"
        elif signal == SignalType.STRONG_SELL:
            recommendation = f"GUCLU SATIS SINYALI! {', '.join(reasons[:3])}"
        elif signal == SignalType.SELL:
            recommendation = f"Satis yonlu beklenti. {', '.join(reasons[:2])}"
        else:
            recommendation = "Piyasa kararsiz, bekle-gor stratejisi uygun. Net sinyal icin sabir."

        return signal, confidence, recommendation


# ============== MESAJ FORMATLAYICI ==============

class MessageFormatter:
    """Telegram mesaj formatlayicisi"""

    @staticmethod
    def format_analysis(result: AnalysisResult) -> str:
        """Analiz sonucunu formatla"""
        ind = result.indicators

        # Sembol adi
        symbol_name = "BITCOIN (BTC)" if "BTC" in result.symbol else "ETHEREUM (ETH)"

        # Sinyal emojisi
        signal_emoji = {
            SignalType.STRONG_BUY: "🟢🟢",
            SignalType.BUY: "🟢",
            SignalType.NEUTRAL: "🟡",
            SignalType.SELL: "🔴",
            SignalType.STRONG_SELL: "🔴🔴"
        }

        # Trend emojisi
        trend_emoji = "📈" if ind.price_change_24h > 0 else "📉"

        msg = f"""
━━━━━━━━━━━━━━━━━━━━━━
{signal_emoji[result.overall_signal]} *{symbol_name}* {signal_emoji[result.overall_signal]}
━━━━━━━━━━━━━━━━━━━━━━

💰 *FIYAT BILGISI*
├ Guncel: `${ind.current_price:,.2f}`
├ 24s Degisim: `{ind.price_change_24h:+.2f}%` {trend_emoji}
└ Hacim: {ind.volume_signal}

📊 *TEKNIK INDIKATÖRLER*

*RSI (14):* `{ind.rsi:.1f}`
└ {ind.rsi_signal}

*MACD:*
├ MACD: `{ind.macd:.4f}`
├ Sinyal: `{ind.macd_signal:.4f}`
├ Histogram: `{ind.macd_histogram:.4f}`
└ {ind.macd_trend}

*Bollinger Bands (20,2):*
├ Üst: `${ind.bb_upper:,.2f}`
├ Orta: `${ind.bb_middle:,.2f}`
├ Alt: `${ind.bb_lower:,.2f}`
├ Genislik: `{ind.bb_bandwidth:.2f}%`
└ {ind.bb_position}

*Stochastic (14,3,3):*
├ %K: `{ind.stoch_k:.1f}`
├ %D: `{ind.stoch_d:.1f}`
└ {ind.stoch_signal}

*EMA Analizi:*
├ EMA 9: `${ind.ema_9:,.2f}`
├ EMA 21: `${ind.ema_21:,.2f}`
├ EMA 50: `${ind.ema_50:,.2f}`
├ EMA 200: `${ind.ema_200:,.2f}`
└ {ind.ema_trend}
{"🌟 GOLDEN CROSS ALGILANDI!" if ind.golden_cross else ""}{"⚠️ DEATH CROSS ALGILANDI!" if ind.death_cross else ""}

📐 *FIBONACCI SEVIYELERI*
├ %23.6: `${ind.fib_levels['23.6']:,.2f}`
├ %38.2: `${ind.fib_levels['38.2']:,.2f}`
├ %50.0: `${ind.fib_levels['50.0']:,.2f}`
├ %61.8: `${ind.fib_levels['61.8']:,.2f}` (Golden Ratio)
└ %78.6: `${ind.fib_levels['78.6']:,.2f}`

━━━━━━━━━━━━━━━━━━━━━━
{signal_emoji[result.overall_signal]} *GENEL DEGERLENDIRME*
━━━━━━━━━━━━━━━━━━━━━━

*Sinyal:* `{result.overall_signal.value}`
*Guven:* `{result.confidence*100:.0f}%`

📝 *TAVSIYE:*
{result.recommendation}

*Onemli Seviyeler:*
├ Destek: `${ind.bb_lower:,.2f}` (BB Alt)
├ Direnç: `${ind.bb_upper:,.2f}` (BB Üst)
├ Pivot: `${ind.bb_middle:,.2f}` (BB Orta)
└ EMA 200: `${ind.ema_200:,.2f}` (Trend cizgisi)

⏰ Analiz Zamani: {result.timestamp.strftime('%Y-%m-%d %H:%M UTC')}
📊 Zaman Dilimi: 4 Saatlik (4H)

⚠️ *YASAL UYARI:* Bu analiz yatirim tavsiyesi degildir.
Kripto piyasalari yuksek risk icerir. DYOR!
"""
        return msg

    @staticmethod
    def format_summary(results: List[AnalysisResult]) -> str:
        """Ozet mesaj formatla"""
        msg = f"""
🔔 *4 SAATLIK KRIPTO TEKNIK ANALIZ*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        for result in results:
            symbol = "BTC" if "BTC" in result.symbol else "ETH"
            signal_emoji = {
                SignalType.STRONG_BUY: "🟢🟢",
                SignalType.BUY: "🟢",
                SignalType.NEUTRAL: "🟡",
                SignalType.SELL: "🔴",
                SignalType.STRONG_SELL: "🔴🔴"
            }
            trend = "📈" if result.indicators.price_change_24h > 0 else "📉"

            msg += f"""*{symbol}:* ${result.indicators.current_price:,.2f} ({result.indicators.price_change_24h:+.2f}%) {trend}
{signal_emoji[result.overall_signal]} {result.overall_signal.value} | Güven: {result.confidence*100:.0f}%

"""

        msg += """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detayli analizler asagida 👇
"""
        return msg


# ============== ANA BOT SINIFI ==============

class CryptoAnalysisBot:
    """Ana bot sinifi"""

    def __init__(self):
        self.api = CoinGeckoAPI()
        self.scheduler = None

    async def analyze_symbol(self, symbol: str) -> Optional[AnalysisResult]:
        """Tek bir sembol icin analiz yap"""
        try:
            logger.info(f"Analiz basliyor: {symbol}")

            # Veri cek
            df = self.api.get_klines(symbol, Config.TIMEFRAME, Config.KLINE_LIMIT)
            ticker = self.api.get_24h_ticker(symbol)
            price_change = float(ticker.get('priceChangePercent', 0))

            # Teknik analiz
            analyzer = TechnicalAnalyzer(df)
            indicators = analyzer.get_indicators(price_change)

            # Sinyal uret
            signal, confidence, recommendation = SignalGenerator.generate_signal(indicators)

            # Sonuc olustur
            result = AnalysisResult(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                indicators=indicators,
                overall_signal=signal,
                confidence=confidence,
                recommendation=recommendation,
                key_levels={
                    'support': indicators.bb_lower,
                    'resistance': indicators.bb_upper,
                    'pivot': indicators.bb_middle,
                    'trend_line': indicators.ema_200
                }
            )

            logger.info(f"Analiz tamamlandi: {symbol} - {signal.value}")
            return result

        except Exception as e:
            logger.error(f"Analiz hatasi ({symbol}): {e}")
            return None

    def send_telegram_message(self, text: str) -> bool:
        """Telegram mesaji gonder - egitim botu ile ayni yontem"""
        if not Config.TELEGRAM_TOKEN or not Config.TELEGRAM_CHAT_ID:
            logger.warning("Telegram yapilandirmasi eksik, mesaj konsola yazilacak")
            print(text)
            return False

        try:
            # Uzun mesajlari parcala (Telegram limiti 4096 karakter)
            max_length = 4000
            parts = []

            if len(text) <= max_length:
                parts = [text]
            else:
                lines = text.split('\n')
                current_part = ""

                for line in lines:
                    if len(current_part) + len(line) + 1 <= max_length:
                        current_part += line + '\n'
                    else:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = line + '\n'

                if current_part:
                    parts.append(current_part.strip())

            url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"

            for part in parts:
                payload = {
                    'chat_id': Config.TELEGRAM_CHAT_ID,
                    'text': part,
                    'disable_web_page_preview': True
                }

                response = requests.post(url, json=payload, timeout=30)

                if response.status_code != 200:
                    logger.error(f"Telegram API hatasi: {response.status_code} - {response.text}")
                    return False

                import time
                time.sleep(0.5)  # Rate limit icin kisa bekleme

            logger.info("Telegram mesaji gonderildi")
            return True

        except Exception as e:
            logger.error(f"Telegram mesaj hatasi: {e}")
            return False

    async def run_analysis(self):
        """Tum sembolleri analiz et ve bildir"""
        logger.info("=" * 50)
        logger.info("4 Saatlik Analiz Basladi")
        logger.info("=" * 50)

        results = []

        for symbol in Config.SYMBOLS:
            result = await self.analyze_symbol(symbol)
            if result:
                results.append(result)

        if not results:
            logger.error("Hicbir analiz sonucu alinamadi")
            return

        # Ozet mesaj gonder
        summary = MessageFormatter.format_summary(results)
        self.send_telegram_message(summary)

        # Her coin icin detayli analiz gonder
        for result in results:
            detailed = MessageFormatter.format_analysis(result)
            self.send_telegram_message(detailed)
            await asyncio.sleep(1)  # Rate limit icin kisa bekleme

        logger.info("Tum analizler tamamlandi ve gonderildi")

    def setup_scheduler(self):
        """4 saatlik zamanlayici kur"""
        self.scheduler = AsyncIOScheduler()

        # Her 4 saatte bir calistir (00:05, 04:05, 08:05, 12:05, 16:05, 20:05 UTC)
        # 5 dakika gecikme ile Binance mumlarinin kapanmasini bekle
        for hour in Config.SCHEDULE_HOURS:
            self.scheduler.add_job(
                self.run_analysis,
                CronTrigger(hour=hour, minute=5),
                id=f'analysis_{hour}',
                name=f'Crypto Analysis at {hour}:05 UTC'
            )

        logger.info("Zamanlayici ayarlandi: Her 4 saatte bir analiz yapilacak")
        logger.info(f"Saat dilimi: UTC | Saatler: {Config.SCHEDULE_HOURS}")

    async def start(self, run_once: bool = False):
        """Botu baslat"""
        logger.info("Kripto Teknik Analiz Botu Baslatiliyor...")

        if run_once:
            # Tek seferlik calistir
            await self.run_analysis()
        else:
            # Scheduler ile surekli calistir
            self.setup_scheduler()
            self.scheduler.start()

            # Baslangicta bir kez calistir
            await self.run_analysis()

            # Sonsuza kadar calis
            try:
                while True:
                    await asyncio.sleep(3600)  # Her saat kontrol
            except (KeyboardInterrupt, SystemExit):
                logger.info("Bot durduruluyor...")
                self.scheduler.shutdown()


# ============== GITHUB ACTIONS ICIN ==============

async def run_github_action():
    """GitHub Actions icin tek seferlik calistirma"""
    bot = CryptoAnalysisBot()
    await bot.start(run_once=True)


# ============== ANA GIRIS ==============

def main():
    """Ana fonksiyon"""
    # Environment kontrol
    if not Config.TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN ayarlanmamis - Mesajlar konsola yazdirilacak")
    if not Config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID ayarlanmamis - Mesajlar konsola yazdirilacak")

    # Calistirma modu
    run_once = os.environ.get('RUN_ONCE', 'false').lower() == 'true'

    bot = CryptoAnalysisBot()
    asyncio.run(bot.start(run_once=run_once))


if __name__ == "__main__":
    main()
