"""
🚀 ADVANCED CRYPTO ANALYSIS BOT v2.0
=====================================
Entegre Özellikler:
- Teknik Analiz: MACD, RSI, Bollinger, Ichimoku, Fibonacci, Stochastic RSI, ADX, VWAP, EMA/SMA
- Pattern Recognition: Candlestick Patterns (TA-Lib), Pivot Points
- Sentiment: Fear & Greed Index, Reddit Sentiment (PRAW), CryptoPanic News
- On-Chain: Whale Alert, DeFiLlama TVL, Exchange Flow tahmini
- Multi-Timeframe: Scalping (15m) + Swing Trading (4H) analizi
- Akıllı Sinyal Sistemi: Ağırlıklı çoklu faktör skorlaması
"""

import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import feedparser
import ccxt
import instructor
from google import genai
from supabase import create_client
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================
# ORTAM DEĞİŞKENLERİ
# ============================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Opsiyonel API Anahtarları (ücretsiz tier'lar)
CRYPTOPANIC_API = os.environ.get("CRYPTOPANIC_API", "")  # Ücretsiz, opsiyonel
WHALE_ALERT_API = os.environ.get("WHALE_ALERT_API", "")  # Ücretsiz tier: 10 req/min
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# ============================================
# AYARLAR
# ============================================
MAJOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT']
ALTCOIN_SCAN_LIMIT = 50  # Taranacak altcoin sayısı
MIN_VOLUME_USD = 500000  # Minimum 24h hacim

# Sinyal Ağırlıkları
SIGNAL_WEIGHTS = {
    'technical': 0.40,      # Teknik göstergeler
    'sentiment': 0.30,      # Duygu analizi
    'onchain': 0.15,        # On-chain veriler
    'pattern': 0.15         # Pattern recognition
}

# ============================================
# KURULUMLAR
# ============================================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client_ai = instructor.from_genai(
    client=genai.Client(api_key=GEMINI_KEY),
    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
)
exchange = ccxt.gateio()

# ============================================
# VERİ MODELLERİ
# ============================================
class TechnicalSignals(BaseModel):
    """Teknik gösterge sinyalleri"""
    rsi: float = Field(description="RSI değeri (0-100)")
    rsi_signal: str = Field(description="RSI sinyali: OVERSOLD, NEUTRAL, OVERBOUGHT")
    macd_signal: str = Field(description="MACD sinyali: BULLISH, NEUTRAL, BEARISH")
    macd_histogram: float = Field(description="MACD histogram değeri")
    bb_position: str = Field(description="Bollinger pozisyonu")
    ichimoku_signal: str = Field(description="Ichimoku bulut sinyali")
    adx_trend: str = Field(description="ADX trend gücü")
    stoch_rsi: float = Field(description="Stochastic RSI (0-100)")
    ema_trend: str = Field(description="EMA trend yönü")
    fibonacci_level: str = Field(description="En yakın Fibonacci seviyesi")

class SentimentData(BaseModel):
    """Sentiment verileri"""
    fear_greed_value: int = Field(description="Fear & Greed değeri (0-100)")
    fear_greed_label: str = Field(description="Fear & Greed etiketi")
    news_sentiment: float = Field(description="Haber sentiment skoru (-1 ile 1)")
    reddit_sentiment: float = Field(description="Reddit sentiment skoru (-1 ile 1)")
    social_buzz: str = Field(description="Sosyal medya aktivitesi: LOW, NORMAL, HIGH")

class OnChainData(BaseModel):
    """On-chain verileri"""
    whale_activity: str = Field(description="Balina aktivitesi: LOW, NORMAL, HIGH")
    exchange_flow: str = Field(description="Borsa akışı: INFLOW, NEUTRAL, OUTFLOW")
    volume_anomaly: bool = Field(description="Hacim anomalisi var mı")
    defi_tvl_change: float = Field(description="DeFi TVL değişimi %")

class PatternSignal(BaseModel):
    """Pattern tanıma sinyalleri"""
    candlestick_patterns: List[str] = Field(description="Tespit edilen mum formasyonları")
    chart_pattern: str = Field(description="Grafik formasyonu")
    support_level: float = Field(description="Destek seviyesi")
    resistance_level: float = Field(description="Direnç seviyesi")

class AggregateSignal(BaseModel):
    """Toplam sinyal skoru"""
    total_score: float = Field(description="Toplam sinyal skoru (-100 ile 100)")
    confidence: float = Field(description="Güven seviyesi (0-100)")
    action: str = Field(description="GÜÇLÜ AL, AL, BEKLE, SAT, GÜÇLÜ SAT")
    timeframe: str = Field(description="Önerilen işlem süresi")
    risk_level: str = Field(description="Risk seviyesi: DÜŞÜK, ORTA, YÜKSEK")

class MarketReport(BaseModel):
    """Gemini AI rapor modeli"""
    market_sentiment_score: int = Field(description="0-100 arası puan.")
    sentiment_summary: str = Field(description="Piyasa özeti (TÜRKÇE, 2-3 cümle).")
    technical_analysis: str = Field(description="Teknik analiz yorumu (TÜRKÇE).")
    key_levels: str = Field(description="Kritik destek/direnç seviyeleri.")
    final_action: str = Field(description="Karar: 'GÜÇLÜ AL', 'AL', 'BEKLE', 'SAT', 'GÜÇLÜ SAT'")
    confidence_pct: int = Field(description="Güven yüzdesi (0-100)")
    logic_explanation: str = Field(description="Kararın mantığı (TÜRKÇE, detaylı).")
    risk_warning: str = Field(description="Risk uyarısı (TÜRKÇE).")
    scalping_signal: str = Field(description="Kısa vadeli sinyal (15m-1H)")
    swing_signal: str = Field(description="Orta vadeli sinyal (4H-1D)")

# ============================================
# TEKNİK ANALİZ FONKSİYONLARI
# ============================================

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI hesaplama - Wilder's smoothing method"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_stochastic_rsi(series: pd.Series, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
    """Stochastic RSI hesaplama"""
    rsi = calculate_rsi(series, rsi_period)
    rsi_min = rsi.rolling(window=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min) * 100
    return stoch_rsi.fillna(50)

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """MACD hesaplama"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return {
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    }

def calculate_bollinger(series: pd.Series, period: int = 20, std: int = 2) -> Dict:
    """Bollinger Bands hesaplama"""
    sma = series.rolling(window=period).mean()
    rstd = series.rolling(window=period).std()
    upper = sma + (rstd * std)
    lower = sma - (rstd * std)
    bandwidth = (upper - lower) / sma * 100
    
    return {
        'upper': upper,
        'middle': sma,
        'lower': lower,
        'bandwidth': bandwidth
    }

def calculate_ichimoku(df: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52) -> Dict:
    """
    Ichimoku Cloud hesaplama
    Kripto için optimize: 10, 30, 60 da kullanılabilir
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Tenkan-sen (Conversion Line)
    tenkan_sen = (high.rolling(window=tenkan).max() + low.rolling(window=tenkan).min()) / 2
    
    # Kijun-sen (Base Line)
    kijun_sen = (high.rolling(window=kijun).max() + low.rolling(window=kijun).min()) / 2
    
    # Senkou Span A (Leading Span A)
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)
    
    # Senkou Span B (Leading Span B)
    senkou_span_b = ((high.rolling(window=senkou_b).max() + low.rolling(window=senkou_b).min()) / 2).shift(kijun)
    
    # Chikou Span (Lagging Span)
    chikou_span = close.shift(-kijun)
    
    return {
        'tenkan': tenkan_sen,
        'kijun': kijun_sen,
        'senkou_a': senkou_span_a,
        'senkou_b': senkou_span_b,
        'chikou': chikou_span
    }

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX (Average Directional Index) hesaplama - Trend gücü"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    # Directional Movement
    up_move = high - high.shift()
    down_move = low.shift() - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    plus_di = 100 * pd.Series(plus_dm).rolling(window=period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(window=period).mean() / atr
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    return adx.fillna(25)

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP (Volume Weighted Average Price) hesaplama"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    return vwap

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """EMA hesaplama"""
    return series.ewm(span=period, adjust=False).mean()

def calculate_fibonacci_levels(df: pd.DataFrame, lookback: int = 50) -> Dict:
    """Fibonacci Retracement seviyeleri"""
    high = df['high'].rolling(window=lookback).max().iloc[-1]
    low = df['low'].rolling(window=lookback).min().iloc[-1]
    diff = high - low
    
    return {
        'high': high,
        'low': low,
        'level_236': high - (diff * 0.236),
        'level_382': high - (diff * 0.382),
        'level_500': high - (diff * 0.500),
        'level_618': high - (diff * 0.618),
        'level_786': high - (diff * 0.786)
    }

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR (Average True Range) hesaplama - Volatilite"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    return tr.rolling(window=period).mean()

def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R hesaplama"""
    highest_high = df['high'].rolling(window=period).max()
    lowest_low = df['low'].rolling(window=period).min()
    wr = -100 * (highest_high - df['close']) / (highest_high - lowest_low)
    return wr

def calculate_cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """CCI (Commodity Channel Index) hesaplama"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    sma = typical_price.rolling(window=period).mean()
    mad = typical_price.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (typical_price - sma) / (0.015 * mad)
    return cci

def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """OBV (On-Balance Volume) hesaplama"""
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.append(obv[-1] + df['volume'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.append(obv[-1] - df['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index)

# ============================================
# PATTERN RECOGNITION
# ============================================

def detect_candlestick_patterns(df: pd.DataFrame) -> List[str]:
    """
    Mum formasyonlarını tespit et
    TA-Lib olmadan basit pattern tanıma
    """
    patterns = []
    
    if len(df) < 3:
        return patterns
    
    o = df['open'].iloc[-1]
    h = df['high'].iloc[-1]
    l = df['low'].iloc[-1]
    c = df['close'].iloc[-1]
    
    o_prev = df['open'].iloc[-2]
    h_prev = df['high'].iloc[-2]
    l_prev = df['low'].iloc[-2]
    c_prev = df['close'].iloc[-2]
    
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    body_prev = abs(c_prev - o_prev)
    
    # Doji
    if body < (h - l) * 0.1:
        patterns.append("DOJI")
    
    # Hammer (Çekiç) - Bullish
    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and c > o:
        patterns.append("HAMMER 🔨")
    
    # Shooting Star - Bearish
    if upper_shadow > body * 2 and lower_shadow < body * 0.5 and c < o:
        patterns.append("SHOOTING_STAR ⭐")
    
    # Bullish Engulfing
    if c_prev < o_prev and c > o and o <= c_prev and c >= o_prev:
        patterns.append("BULLISH_ENGULFING 🟢")
    
    # Bearish Engulfing
    if c_prev > o_prev and c < o and o >= c_prev and c <= o_prev:
        patterns.append("BEARISH_ENGULFING 🔴")
    
    # Morning Star (3 mum gerekli)
    if len(df) >= 3:
        o_2 = df['open'].iloc[-3]
        c_2 = df['close'].iloc[-3]
        if c_2 < o_2 and body_prev < body * 0.3 and c > o and c > (o_2 + c_2) / 2:
            patterns.append("MORNING_STAR 🌅")
    
    # Evening Star
    if len(df) >= 3:
        o_2 = df['open'].iloc[-3]
        c_2 = df['close'].iloc[-3]
        if c_2 > o_2 and body_prev < body * 0.3 and c < o and c < (o_2 + c_2) / 2:
            patterns.append("EVENING_STAR 🌆")
    
    return patterns if patterns else ["YOK"]

def find_support_resistance(df: pd.DataFrame, lookback: int = 50) -> Dict:
    """Destek ve direnç seviyelerini bul"""
    recent = df.tail(lookback)
    
    # Pivot noktaları
    highs = recent['high'].nlargest(5).mean()
    lows = recent['low'].nsmallest(5).mean()
    
    return {
        'resistance': round(highs, 2),
        'support': round(lows, 2),
        'pivot': round((highs + lows + recent['close'].iloc[-1]) / 3, 2)
    }

# ============================================
# SENTIMENT ANALİZİ
# ============================================

def get_fear_and_greed() -> tuple:
    """Fear & Greed Index - Ücretsiz API"""
    tr_labels = {
        "Extreme Fear": "Aşırı Korku 😱",
        "Fear": "Korku 😨",
        "Neutral": "Nötr 😐",
        "Greed": "Açgözlülük 🤑",
        "Extreme Greed": "Aşırı Açgözlülük 🚀"
    }
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10).json()
        current = r['data'][0]
        value = int(current['value'])
        label = tr_labels.get(current['value_classification'], "Nötr")
        
        # 7 günlük trend
        values = [int(d['value']) for d in r['data']]
        trend = "YUKARI" if values[0] > values[-1] else "AŞAĞI" if values[0] < values[-1] else "YATAY"
        
        return value, label, trend
    except:
        return 50, "Nötr 😐", "YATAY"

def get_crypto_news_sentiment() -> Dict:
    """CoinDesk RSS + Basit sentiment analizi"""
    positive_words = ['surge', 'rally', 'bull', 'gain', 'up', 'high', 'record', 'soar', 'jump', 'boost', 'grow']
    negative_words = ['crash', 'bear', 'drop', 'fall', 'down', 'low', 'plunge', 'sink', 'decline', 'loss', 'fear']
    
    try:
        # CoinDesk RSS
        feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
        titles = [entry.title.lower() for entry in feed.entries[:10]]
        
        # CoinTelegraph RSS
        feed2 = feedparser.parse("https://cointelegraph.com/rss")
        titles.extend([entry.title.lower() for entry in feed2.entries[:10]])
        
        all_text = " ".join(titles)
        
        pos_count = sum(1 for word in positive_words if word in all_text)
        neg_count = sum(1 for word in negative_words if word in all_text)
        
        if pos_count + neg_count == 0:
            sentiment = 0
        else:
            sentiment = (pos_count - neg_count) / (pos_count + neg_count)
        
        return {
            'sentiment_score': round(sentiment, 2),
            'headlines': [entry.title for entry in feed.entries[:5]],
            'positive_signals': pos_count,
            'negative_signals': neg_count
        }
    except:
        return {'sentiment_score': 0, 'headlines': [], 'positive_signals': 0, 'negative_signals': 0}

def get_cryptopanic_sentiment() -> float:
    """CryptoPanic API - Ücretsiz tier (opsiyonel)"""
    if not CRYPTOPANIC_API:
        return 0.0
    
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API}&filter=hot&currencies=BTC,ETH"
        r = requests.get(url, timeout=10).json()
        
        sentiments = []
        for post in r.get('results', [])[:20]:
            votes = post.get('votes', {})
            pos = votes.get('positive', 0)
            neg = votes.get('negative', 0)
            if pos + neg > 0:
                sentiments.append((pos - neg) / (pos + neg))
        
        return sum(sentiments) / len(sentiments) if sentiments else 0.0
    except:
        return 0.0

def get_reddit_sentiment() -> Dict:
    """
    Reddit sentiment analizi - PRAW kullanarak
    Not: API key olmadan çalışmaz, opsiyonel
    """
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return {'sentiment': 0.0, 'posts_analyzed': 0, 'buzz': 'UNKNOWN'}
    
    try:
        import praw
        
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent='CryptoBot/2.0'
        )
        
        subreddits = ['cryptocurrency', 'bitcoin', 'ethereum']
        all_sentiments = []
        total_engagement = 0
        
        positive_words = ['moon', 'bullish', 'buy', 'pump', 'long', 'hodl', 'ath', 'breakout']
        negative_words = ['crash', 'bearish', 'sell', 'dump', 'short', 'rekt', 'scam', 'dead']
        
        for sub_name in subreddits:
            sub = reddit.subreddit(sub_name)
            for post in sub.hot(limit=10):
                text = (post.title + " " + (post.selftext or "")).lower()
                
                pos = sum(1 for w in positive_words if w in text)
                neg = sum(1 for w in negative_words if w in text)
                
                if pos + neg > 0:
                    sentiment = (pos - neg) / (pos + neg)
                    all_sentiments.append(sentiment)
                
                total_engagement += post.score + post.num_comments
        
        avg_sentiment = sum(all_sentiments) / len(all_sentiments) if all_sentiments else 0
        
        # Buzz seviyesi
        buzz = 'HIGH' if total_engagement > 50000 else 'NORMAL' if total_engagement > 10000 else 'LOW'
        
        return {
            'sentiment': round(avg_sentiment, 2),
            'posts_analyzed': len(all_sentiments),
            'buzz': buzz,
            'engagement': total_engagement
        }
    except:
        return {'sentiment': 0.0, 'posts_analyzed': 0, 'buzz': 'UNKNOWN'}

# ============================================
# ON-CHAIN VERİLER
# ============================================

def get_whale_activity() -> Dict:
    """
    Whale Alert API - Ücretsiz tier
    Büyük işlemleri takip et
    """
    if not WHALE_ALERT_API:
        return {'activity': 'UNKNOWN', 'large_txs': 0, 'net_flow': 'NEUTRAL'}
    
    try:
        import time
        start_time = int(time.time() - 3600)  # Son 1 saat
        
        url = f"https://api.whale-alert.io/v1/transactions?api_key={WHALE_ALERT_API}&min_value=1000000&start={start_time}"
        r = requests.get(url, timeout=10).json()
        
        transactions = r.get('transactions', [])
        
        exchange_inflow = 0
        exchange_outflow = 0
        large_txs = len(transactions)
        
        for tx in transactions:
            amount_usd = tx.get('amount_usd', 0)
            to_type = tx.get('to', {}).get('owner_type', '')
            from_type = tx.get('from', {}).get('owner_type', '')
            
            if to_type == 'exchange':
                exchange_inflow += amount_usd
            if from_type == 'exchange':
                exchange_outflow += amount_usd
        
        net_flow = exchange_inflow - exchange_outflow
        flow_label = 'INFLOW' if net_flow > 1000000 else 'OUTFLOW' if net_flow < -1000000 else 'NEUTRAL'
        activity = 'HIGH' if large_txs > 20 else 'NORMAL' if large_txs > 5 else 'LOW'
        
        return {
            'activity': activity,
            'large_txs': large_txs,
            'net_flow': flow_label,
            'inflow_usd': exchange_inflow,
            'outflow_usd': exchange_outflow
        }
    except:
        return {'activity': 'UNKNOWN', 'large_txs': 0, 'net_flow': 'NEUTRAL'}

def get_defi_tvl() -> Dict:
    """DeFiLlama API - Tamamen ücretsiz"""
    try:
        # Global DeFi TVL
        r = requests.get("https://api.llama.fi/v2/protocols", timeout=10).json()
        
        # Top protokoller
        top_protocols = sorted(r, key=lambda x: x.get('tvl', 0), reverse=True)[:10]
        total_tvl = sum(p.get('tvl', 0) for p in top_protocols)
        
        # TVL değişimi
        r2 = requests.get("https://api.llama.fi/v2/historicalChainTvl", timeout=10).json()
        if len(r2) >= 2:
            tvl_change = ((r2[-1].get('tvl', 0) - r2[-2].get('tvl', 0)) / r2[-2].get('tvl', 1)) * 100
        else:
            tvl_change = 0
        
        return {
            'total_tvl_billions': round(total_tvl / 1e9, 2),
            'tvl_change_24h': round(tvl_change, 2),
            'top_protocols': [p.get('name', '') for p in top_protocols[:5]]
        }
    except:
        return {'total_tvl_billions': 0, 'tvl_change_24h': 0, 'top_protocols': []}

def estimate_exchange_flow(df: pd.DataFrame) -> str:
    """
    Volume anomali analizi ile borsa akışı tahmini
    Yüksek hacim + düşen fiyat = potansiyel satış baskısı
    """
    avg_volume = df['volume'].mean()
    last_volume = df['volume'].iloc[-1]
    price_change = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100
    
    volume_ratio = last_volume / avg_volume
    
    if volume_ratio > 2 and price_change < -2:
        return "YÜKSEK SATIŞ BASKISI 📉"
    elif volume_ratio > 2 and price_change > 2:
        return "YÜKSEK ALIM İLGİSİ 📈"
    elif volume_ratio > 1.5:
        return "HACİM ARTIŞI ⚠️"
    else:
        return "NORMAL"

# ============================================
# MAKRO VERİLER
# ============================================

def get_macro_data() -> Dict:
    """Makroekonomik veriler - DXY, S&P 500, Gold"""
    try:
        tickers = ["DX-Y.NYB", "^GSPC", "GC=F", "^VIX"]
        data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=True)['Close']
        
        results = {}
        
        # DXY (Dolar Endeksi)
        if 'DX-Y.NYB' in data.columns:
            dxy = data['DX-Y.NYB'].dropna()
            if len(dxy) >= 2:
                results['dxy_change'] = round(((dxy.iloc[-1] - dxy.iloc[-2]) / dxy.iloc[-2]) * 100, 2)
            else:
                results['dxy_change'] = 0
        
        # S&P 500
        if '^GSPC' in data.columns:
            sp = data['^GSPC'].dropna()
            if len(sp) >= 2:
                results['sp500_change'] = round(((sp.iloc[-1] - sp.iloc[-2]) / sp.iloc[-2]) * 100, 2)
            else:
                results['sp500_change'] = 0
        
        # Altın
        if 'GC=F' in data.columns:
            gold = data['GC=F'].dropna()
            if len(gold) >= 2:
                results['gold_change'] = round(((gold.iloc[-1] - gold.iloc[-2]) / gold.iloc[-2]) * 100, 2)
            else:
                results['gold_change'] = 0
        
        # VIX (Volatilite)
        if '^VIX' in data.columns:
            vix = data['^VIX'].dropna()
            if len(vix) >= 1:
                results['vix'] = round(float(vix.iloc[-1]), 2)
            else:
                results['vix'] = 20
        
        # Makro durum değerlendirmesi
        dxy_chg = results.get('dxy_change', 0)
        sp_chg = results.get('sp500_change', 0)
        vix_val = results.get('vix', 20)
        
        if dxy_chg > 0.5 or vix_val > 30:
            results['status'] = "⛔ RİSKLİ (Güvenli Liman Talebi)"
        elif dxy_chg < -0.3 and sp_chg > 0.3:
            results['status'] = "✅ POZİTİF (Risk İştahı Yüksek)"
        elif sp_chg < -1:
            results['status'] = "⚠️ DİKKATLİ (Piyasa Baskısı)"
        else:
            results['status'] = "➖ NÖTR"
        
        return results
    except Exception as e:
        print(f"Makro veri hatası: {e}")
        return {'dxy_change': 0, 'sp500_change': 0, 'gold_change': 0, 'vix': 20, 'status': 'Veri Yok'}

# ============================================
# ANA VERİ ÇEKME VE ANALİZ
# ============================================

def get_comprehensive_market_data(symbol: str, timeframe: str = '1h', limit: int = 100) -> Dict:
    """Kapsamlı piyasa verisi çek ve tüm göstergeleri hesapla"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Temel hesaplamalar
        last = df.iloc[-1]
        change_24h = ((last['close'] - df.iloc[-24]['close']) / df.iloc[-24]['close']) * 100 if len(df) >= 24 else 0
        
        # RSI
        df['rsi'] = calculate_rsi(df['close'])
        rsi_value = df['rsi'].iloc[-1]
        rsi_signal = "AŞIRI SATIM 🟢" if rsi_value < 30 else "AŞIRI ALIM 🔴" if rsi_value > 70 else "NÖTR"
        
        # Stochastic RSI
        df['stoch_rsi'] = calculate_stochastic_rsi(df['close'])
        stoch_value = df['stoch_rsi'].iloc[-1]
        
        # MACD
        macd_data = calculate_macd(df['close'])
        macd_value = macd_data['macd'].iloc[-1]
        signal_value = macd_data['signal'].iloc[-1]
        histogram = macd_data['histogram'].iloc[-1]
        macd_signal = "YUKARI KESİŞİM 🟢" if macd_value > signal_value and macd_data['macd'].iloc[-2] <= macd_data['signal'].iloc[-2] else \
                      "AŞAĞI KESİŞİM 🔴" if macd_value < signal_value and macd_data['macd'].iloc[-2] >= macd_data['signal'].iloc[-2] else \
                      "BULLISH" if histogram > 0 else "BEARISH"
        
        # Bollinger Bands
        bb_data = calculate_bollinger(df['close'])
        bb_upper = bb_data['upper'].iloc[-1]
        bb_lower = bb_data['lower'].iloc[-1]
        bb_middle = bb_data['middle'].iloc[-1]
        bb_position = "ÜST BANTI DELDİ 🔴" if last['close'] > bb_upper else \
                      "ALT BANTI DELDİ 🟢" if last['close'] < bb_lower else \
                      "BANT ÜST" if last['close'] > bb_middle else "BANT ALT"
        
        # Ichimoku
        ichimoku = calculate_ichimoku(df)
        kumo_top = max(ichimoku['senkou_a'].iloc[-1], ichimoku['senkou_b'].iloc[-1])
        kumo_bottom = min(ichimoku['senkou_a'].iloc[-1], ichimoku['senkou_b'].iloc[-1])
        ichimoku_signal = "BULUT ÜSTÜ 🟢" if last['close'] > kumo_top else \
                          "BULUT ALTI 🔴" if last['close'] < kumo_bottom else "BULUT İÇİ ⚪"
        
        # ADX
        df['adx'] = calculate_adx(df)
        adx_value = df['adx'].iloc[-1]
        adx_trend = "GÜÇLÜ TREND 💪" if adx_value > 25 else "ZAYIF TREND" if adx_value > 20 else "YATAY PİYASA"
        
        # EMA Trend
        df['ema_9'] = calculate_ema(df['close'], 9)
        df['ema_21'] = calculate_ema(df['close'], 21)
        df['ema_50'] = calculate_ema(df['close'], 50)
        ema_trend = "YUKARI 📈" if df['ema_9'].iloc[-1] > df['ema_21'].iloc[-1] > df['ema_50'].iloc[-1] else \
                    "AŞAĞI 📉" if df['ema_9'].iloc[-1] < df['ema_21'].iloc[-1] < df['ema_50'].iloc[-1] else "KARIŞIK"
        
        # VWAP
        df['vwap'] = calculate_vwap(df)
        vwap_position = "VWAP ÜSTÜ 🟢" if last['close'] > df['vwap'].iloc[-1] else "VWAP ALTI 🔴"
        
        # Williams %R
        df['williams_r'] = calculate_williams_r(df)
        wr_value = df['williams_r'].iloc[-1]
        
        # CCI
        df['cci'] = calculate_cci(df)
        cci_value = df['cci'].iloc[-1]
        
        # Fibonacci
        fib_levels = calculate_fibonacci_levels(df)
        current_price = last['close']
        closest_fib = min(fib_levels.items(), key=lambda x: abs(x[1] - current_price) if isinstance(x[1], (int, float)) else float('inf'))
        
        # ATR
        df['atr'] = calculate_atr(df)
        atr_value = df['atr'].iloc[-1]
        atr_pct = (atr_value / last['close']) * 100
        
        # OBV
        df['obv'] = calculate_obv(df)
        obv_trend = "ARTAN" if df['obv'].iloc[-1] > df['obv'].iloc[-5] else "AZALAN"
        
        # Volume analizi
        avg_volume = df['volume'].mean()
        volume_ratio = last['volume'] / avg_volume
        volume_signal = "PATLAMA 🚀" if volume_ratio > 2 else "YÜKSEK" if volume_ratio > 1.5 else "NORMAL"
        
        # Pattern Recognition
        patterns = detect_candlestick_patterns(df)
        
        # Support/Resistance
        sr_levels = find_support_resistance(df)
        
        # Exchange flow tahmini
        exchange_flow = estimate_exchange_flow(df)
        
        return {
            'symbol': symbol,
            'price': last['close'],
            'change_24h': round(change_24h, 2),
            'volume_usd': last['volume'] * last['close'],
            
            # RSI
            'rsi': round(rsi_value, 1),
            'rsi_signal': rsi_signal,
            
            # Stochastic RSI
            'stoch_rsi': round(stoch_value, 1),
            
            # MACD
            'macd': round(macd_value, 4),
            'macd_signal_line': round(signal_value, 4),
            'macd_histogram': round(histogram, 4),
            'macd_signal': macd_signal,
            
            # Bollinger
            'bb_upper': round(bb_upper, 2),
            'bb_lower': round(bb_lower, 2),
            'bb_position': bb_position,
            
            # Ichimoku
            'ichimoku_signal': ichimoku_signal,
            'kumo_top': round(kumo_top, 2),
            'kumo_bottom': round(kumo_bottom, 2),
            
            # ADX
            'adx': round(adx_value, 1),
            'adx_trend': adx_trend,
            
            # EMA
            'ema_9': round(df['ema_9'].iloc[-1], 2),
            'ema_21': round(df['ema_21'].iloc[-1], 2),
            'ema_50': round(df['ema_50'].iloc[-1], 2),
            'ema_trend': ema_trend,
            
            # VWAP
            'vwap': round(df['vwap'].iloc[-1], 2),
            'vwap_position': vwap_position,
            
            # Williams %R
            'williams_r': round(wr_value, 1),
            
            # CCI
            'cci': round(cci_value, 1),
            
            # ATR
            'atr': round(atr_value, 2),
            'atr_pct': round(atr_pct, 2),
            
            # OBV
            'obv_trend': obv_trend,
            
            # Volume
            'volume_ratio': round(volume_ratio, 2),
            'volume_signal': volume_signal,
            
            # Fibonacci
            'fib_levels': fib_levels,
            'closest_fib': f"{closest_fib[0]}: ${closest_fib[1]:,.2f}",
            
            # Patterns
            'candlestick_patterns': patterns,
            
            # Support/Resistance
            'support': sr_levels['support'],
            'resistance': sr_levels['resistance'],
            'pivot': sr_levels['pivot'],
            
            # Exchange Flow
            'exchange_flow': exchange_flow
        }
    except Exception as e:
        print(f"Veri çekme hatası ({symbol}): {e}")
        return None

# ============================================
# SİNYAL SKORLAMA SİSTEMİ
# ============================================

def calculate_technical_score(data: Dict) -> float:
    """Teknik gösterge skoru (-100 ile 100)"""
    score = 0
    signals = 0
    
    # RSI (Ağırlık: 15)
    rsi = data.get('rsi', 50)
    if rsi < 30:
        score += 15
    elif rsi < 40:
        score += 8
    elif rsi > 70:
        score -= 15
    elif rsi > 60:
        score -= 8
    signals += 1
    
    # Stochastic RSI (Ağırlık: 10)
    stoch = data.get('stoch_rsi', 50)
    if stoch < 20:
        score += 10
    elif stoch > 80:
        score -= 10
    signals += 1
    
    # MACD (Ağırlık: 20)
    macd_sig = data.get('macd_signal', '')
    if 'KESİŞİM 🟢' in macd_sig:
        score += 20
    elif 'KESİŞİM 🔴' in macd_sig:
        score -= 20
    elif 'BULLISH' in macd_sig:
        score += 10
    elif 'BEARISH' in macd_sig:
        score -= 10
    signals += 1
    
    # Bollinger (Ağırlık: 10)
    bb = data.get('bb_position', '')
    if 'ALT' in bb and 'DELDİ' in bb:
        score += 10
    elif 'ÜST' in bb and 'DELDİ' in bb:
        score -= 10
    signals += 1
    
    # Ichimoku (Ağırlık: 15)
    ichi = data.get('ichimoku_signal', '')
    if 'ÜSTÜ 🟢' in ichi:
        score += 15
    elif 'ALTI 🔴' in ichi:
        score -= 15
    signals += 1
    
    # EMA Trend (Ağırlık: 15)
    ema = data.get('ema_trend', '')
    if 'YUKARI' in ema:
        score += 15
    elif 'AŞAĞI' in ema:
        score -= 15
    signals += 1
    
    # VWAP (Ağırlık: 10)
    vwap = data.get('vwap_position', '')
    if 'ÜSTÜ 🟢' in vwap:
        score += 10
    elif 'ALTI 🔴' in vwap:
        score -= 10
    signals += 1
    
    # ADX (Güç çarpanı)
    adx = data.get('adx', 20)
    if adx > 25:
        score = score * 1.2  # Güçlü trend varsa sinyali güçlendir
    
    return max(-100, min(100, score))

def calculate_sentiment_score(fng_value: int, news_sentiment: float, reddit_sentiment: float = 0) -> float:
    """Sentiment skoru (-100 ile 100)"""
    # Fear & Greed (Ağırlık: 60)
    # Aşırı korku = alım fırsatı, aşırı açgözlülük = satış sinyali
    fng_score = (fng_value - 50) * -1.2  # Ters çevir: korku pozitif, açgözlülük negatif
    
    # Haber sentiment (Ağırlık: 30)
    news_score = news_sentiment * 30
    
    # Reddit sentiment (Ağırlık: 10)
    reddit_score = reddit_sentiment * 10
    
    total = (fng_score * 0.6) + (news_score) + (reddit_score)
    return max(-100, min(100, total))

def calculate_onchain_score(whale_data: Dict, defi_data: Dict, exchange_flow: str) -> float:
    """On-chain skoru (-100 ile 100)"""
    score = 0
    
    # Whale aktivitesi
    activity = whale_data.get('activity', 'UNKNOWN')
    net_flow = whale_data.get('net_flow', 'NEUTRAL')
    
    if activity == 'HIGH':
        if net_flow == 'OUTFLOW':
            score += 20  # Borsadan çıkış = HODL
        elif net_flow == 'INFLOW':
            score -= 20  # Borsaya giriş = satış baskısı
    
    # DeFi TVL
    tvl_change = defi_data.get('tvl_change_24h', 0)
    if tvl_change > 2:
        score += 15
    elif tvl_change < -2:
        score -= 15
    
    # Exchange flow tahmini
    if 'ALIM' in exchange_flow:
        score += 15
    elif 'SATIŞ' in exchange_flow:
        score -= 15
    
    return max(-100, min(100, score))

def calculate_pattern_score(patterns: List[str]) -> float:
    """Pattern skoru (-100 ile 100)"""
    bullish_patterns = ['HAMMER', 'BULLISH_ENGULFING', 'MORNING_STAR', 'THREE_WHITE_SOLDIERS']
    bearish_patterns = ['SHOOTING_STAR', 'BEARISH_ENGULFING', 'EVENING_STAR', 'THREE_BLACK_CROWS']
    
    score = 0
    for pattern in patterns:
        if any(bp in pattern for bp in bullish_patterns):
            score += 25
        elif any(bp in pattern for bp in bearish_patterns):
            score -= 25
    
    return max(-100, min(100, score))

def calculate_aggregate_signal(
    technical_score: float,
    sentiment_score: float,
    onchain_score: float,
    pattern_score: float
) -> Dict:
    """Ağırlıklı toplam sinyal"""
    
    weighted_score = (
        technical_score * SIGNAL_WEIGHTS['technical'] +
        sentiment_score * SIGNAL_WEIGHTS['sentiment'] +
        onchain_score * SIGNAL_WEIGHTS['onchain'] +
        pattern_score * SIGNAL_WEIGHTS['pattern']
    )
    
    # Güven seviyesi (tüm sinyallerin aynı yönde olması)
    signs = [
        1 if technical_score > 0 else -1 if technical_score < 0 else 0,
        1 if sentiment_score > 0 else -1 if sentiment_score < 0 else 0,
        1 if onchain_score > 0 else -1 if onchain_score < 0 else 0,
        1 if pattern_score > 0 else -1 if pattern_score < 0 else 0
    ]
    agreement = abs(sum(signs)) / len([s for s in signs if s != 0]) if any(signs) else 0
    confidence = agreement * 100
    
    # Karar
    if weighted_score > 40:
        action = "GÜÇLÜ AL 🟢🟢"
    elif weighted_score > 20:
        action = "AL 🟢"
    elif weighted_score > -20:
        action = "BEKLE ⚪"
    elif weighted_score > -40:
        action = "SAT 🔴"
    else:
        action = "GÜÇLÜ SAT 🔴🔴"
    
    # Risk seviyesi
    if confidence > 70:
        risk = "DÜŞÜK"
    elif confidence > 40:
        risk = "ORTA"
    else:
        risk = "YÜKSEK"
    
    return {
        'total_score': round(weighted_score, 1),
        'confidence': round(confidence, 1),
        'action': action,
        'risk': risk,
        'breakdown': {
            'technical': round(technical_score, 1),
            'sentiment': round(sentiment_score, 1),
            'onchain': round(onchain_score, 1),
            'pattern': round(pattern_score, 1)
        }
    }

# ============================================
# GEM AVCISI (GELİŞMİŞ ALTCOİN TARAMA)
# ============================================

def scan_gems_advanced() -> List[Dict]:
    """Gelişmiş altcoin tarama - Çoklu kriterlere göre"""
    print("💎 Gelişmiş Gem Taraması Başlıyor...")
    gems = []
    
    try:
        tickers = exchange.fetch_tickers()
        
        # Filtrele: USDT paritesi, minimum hacim
        symbols = [
            s for s in tickers 
            if s.endswith('/USDT') 
            and tickers[s].get('quoteVolume', 0) > MIN_VOLUME_USD
            and s not in MAJOR_SYMBOLS
        ]
        
        # Hacme göre sırala
        sorted_symbols = sorted(
            symbols, 
            key=lambda x: tickers[x].get('quoteVolume', 0), 
            reverse=True
        )[:ALTCOIN_SCAN_LIMIT]
        
        for sym in sorted_symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(sym, '1h', limit=50)
                if not ohlcv or len(ohlcv) < 20:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['t', 'open', 'high', 'low', 'close', 'volume'])
                
                # Göstergeler
                rsi = calculate_rsi(df['close']).iloc[-1]
                stoch_rsi = calculate_stochastic_rsi(df['close']).iloc[-1]
                macd_data = calculate_macd(df['close'])
                macd_hist = macd_data['histogram'].iloc[-1]
                
                avg_vol = df['volume'].mean()
                cur_vol = df['volume'].iloc[-1]
                vol_ratio = cur_vol / avg_vol
                
                price_change_24h = ((df['close'].iloc[-1] - df['close'].iloc[-24]) / df['close'].iloc[-24]) * 100 if len(df) >= 24 else 0
                
                # Pattern
                patterns = detect_candlestick_patterns(df)
                
                # GEM KRİTERLERİ
                is_gem = False
                gem_reason = []
                gem_score = 0
                
                # Kriter 1: RSI Dip + Hacim Patlaması
                if rsi < 35 and vol_ratio > 1.5:
                    is_gem = True
                    gem_reason.append(f"RSI Dip ({rsi:.0f})")
                    gem_score += 30
                
                # Kriter 2: Stochastic RSI Aşırı Satım
                if stoch_rsi < 20:
                    gem_reason.append(f"StochRSI Dip ({stoch_rsi:.0f})")
                    gem_score += 20
                
                # Kriter 3: MACD Dönüş
                if macd_hist > 0 and macd_data['histogram'].iloc[-2] < 0:
                    is_gem = True
                    gem_reason.append("MACD Dönüşü")
                    gem_score += 25
                
                # Kriter 4: Hacim Patlaması
                if vol_ratio > 2:
                    gem_reason.append(f"Hacim x{vol_ratio:.1f}")
                    gem_score += 15
                
                # Kriter 5: Bullish Pattern
                bullish_patterns = ['HAMMER', 'BULLISH_ENGULFING', 'MORNING_STAR']
                if any(bp in str(patterns) for bp in bullish_patterns):
                    is_gem = True
                    gem_reason.append(f"Pattern: {patterns[0]}")
                    gem_score += 20
                
                if is_gem and gem_score >= 40:
                    gems.append({
                        'symbol': sym,
                        'price': df['close'].iloc[-1],
                        'change_24h': round(price_change_24h, 2),
                        'rsi': round(rsi, 1),
                        'stoch_rsi': round(stoch_rsi, 1),
                        'volume_ratio': round(vol_ratio, 1),
                        'score': gem_score,
                        'reasons': gem_reason
                    })
                    
            except Exception as e:
                continue
        
        # Skora göre sırala
        gems = sorted(gems, key=lambda x: x['score'], reverse=True)[:10]
        
    except Exception as e:
        print(f"Gem tarama hatası: {e}")
    
    return gems

# ============================================
# GEMİNİ AI ANALİZ
# ============================================

def analyze_with_gemini_advanced(
    symbol: str,
    market_data: Dict,
    macro_data: Dict,
    sentiment_data: Dict,
    aggregate_signal: Dict
) -> Optional[MarketReport]:
    """Gemini AI ile gelişmiş analiz"""
    
    prompt = f"""
Sen deneyimli bir Türk Kripto Stratejistisin. Aşağıdaki kapsamlı verileri analiz ederek profesyonel bir değerlendirme yap.

📊 **{symbol} ANALİZ VERİLERİ**

💰 **FİYAT BİLGİSİ:**
- Anlık Fiyat: ${market_data['price']:,.2f}
- 24s Değişim: %{market_data['change_24h']}
- Hacim Sinyali: {market_data.get('volume_signal', 'N/A')}

📈 **TEKNİK GÖSTERGELER:**
- RSI(14): {market_data['rsi']} → {market_data['rsi_signal']}
- Stochastic RSI: {market_data.get('stoch_rsi', 'N/A')}
- MACD: {market_data['macd_signal']} (Histogram: {market_data.get('macd_histogram', 0)})
- Bollinger: {market_data['bb_position']}
- Ichimoku: {market_data['ichimoku_signal']}
- ADX: {market_data.get('adx', 0)} → {market_data.get('adx_trend', 'N/A')}
- EMA Trend: {market_data.get('ema_trend', 'N/A')}
- VWAP: {market_data.get('vwap_position', 'N/A')}
- Williams %R: {market_data.get('williams_r', 'N/A')}
- CCI: {market_data.get('cci', 'N/A')}

🔮 **FİBONACCİ SEVİYELERİ:**
- En Yakın Seviye: {market_data.get('closest_fib', 'N/A')}
- Destek: ${market_data.get('support', 0):,.2f}
- Direnç: ${market_data.get('resistance', 0):,.2f}

🕯️ **MUM FORMASYONLARI:**
{', '.join(market_data.get('candlestick_patterns', ['YOK']))}

🌍 **MAKRO DURUM:**
- DXY Değişim: %{macro_data.get('dxy_change', 0)}
- S&P 500: %{macro_data.get('sp500_change', 0)}
- VIX: {macro_data.get('vix', 'N/A')}
- Genel Durum: {macro_data.get('status', 'N/A')}

😊 **DUYGU ANALİZİ:**
- Korku/Açgözlülük: {sentiment_data.get('fng_value', 50)} ({sentiment_data.get('fng_label', 'Nötr')})
- Haber Sentiment: {sentiment_data.get('news_sentiment', 0):.2f}
- Borsa Akışı: {market_data.get('exchange_flow', 'N/A')}

🎯 **BOT SİNYAL SİSTEMİ:**
- Toplam Skor: {aggregate_signal['total_score']}
- Güven: %{aggregate_signal['confidence']}
- Önerilen: {aggregate_signal['action']}
- Risk: {aggregate_signal['risk']}
- Detay: Teknik({aggregate_signal['breakdown']['technical']}), Sentiment({aggregate_signal['breakdown']['sentiment']}), OnChain({aggregate_signal['breakdown']['onchain']}), Pattern({aggregate_signal['breakdown']['pattern']})

📋 **KARAR KURALLARI:**
1. Makro "RİSKLİ" ise → Sadece "BEKLE" veya "SAT" de
2. Makro "POZİTİF" + Teknik güçlü ise → "AL" veya "GÜÇLÜ AL"
3. RSI < 30 + MACD Dönüşü + Volume Spike ise → "GÜÇLÜ AL"
4. RSI > 70 + MACD Aşağı + Ichimoku Kırmızı ise → "GÜÇLÜ SAT"
5. Çelişkili sinyallerde → "BEKLE" de ve riski vurgula
6. Bot sinyal sistemi ile uyumlu karar ver

🗣️ Tüm yanıtlar %100 Türkçe olmalı. Profesyonel ama anlaşılır bir dil kullan.
"""

    try:
        return client_ai.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=[{"role": "user", "content": prompt}],
            response_model=MarketReport,
        )
    except Exception as e:
        print(f"Gemini API hatası: {e}")
        return None

# ============================================
# TELEGRAM MESAJ GÖNDERİMİ
# ============================================

def send_telegram(msg: str, parse_mode: str = "Markdown"):
    """Telegram mesajı gönder"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        
        # Mesaj çok uzunsa böl
        max_length = 4096
        if len(msg) > max_length:
            parts = [msg[i:i+max_length] for i in range(0, len(msg), max_length)]
            for part in parts:
                requests.post(url, json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": part,
                    "parse_mode": parse_mode
                })
        else:
            requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": parse_mode
            })
    except Exception as e:
        print(f"Telegram hatası: {e}")

def format_report_message(
    symbol: str,
    market_data: Dict,
    aggregate_signal: Dict,
    ai_report: Optional[MarketReport]
) -> str:
    """Telegram rapor mesajını formatla"""
    
    msg = f"{'='*30}\n"
    msg += f"📊 *{symbol}*\n"
    msg += f"💰 ${market_data['price']:,.2f} ({market_data['change_24h']:+.2f}%)\n"
    msg += f"{'='*30}\n\n"
    
    # Teknik özet
    msg += "📈 *TEKNİK ÖZET:*\n"
    msg += f"• RSI: {market_data['rsi']} {market_data['rsi_signal']}\n"
    msg += f"• MACD: {market_data['macd_signal']}\n"
    msg += f"• Ichimoku: {market_data['ichimoku_signal']}\n"
    msg += f"• EMA: {market_data.get('ema_trend', 'N/A')}\n"
    msg += f"• Hacim: {market_data.get('volume_signal', 'N/A')}\n\n"
    
    # Seviyeler
    msg += "🎯 *SEVİYELER:*\n"
    msg += f"• Destek: ${market_data.get('support', 0):,.2f}\n"
    msg += f"• Direnç: ${market_data.get('resistance', 0):,.2f}\n"
    msg += f"• Fib: {market_data.get('closest_fib', 'N/A')}\n\n"
    
    # Bot sinyali
    msg += "🤖 *BOT SİNYALİ:*\n"
    msg += f"• Skor: {aggregate_signal['total_score']}/100\n"
    msg += f"• Güven: %{aggregate_signal['confidence']}\n"
    msg += f"• Karar: *{aggregate_signal['action']}*\n"
    msg += f"• Risk: {aggregate_signal['risk']}\n\n"
    
    # AI analizi
    if ai_report:
        msg += "🧠 *AI ANALİZİ:*\n"
        msg += f"• Karar: *{ai_report.final_action}* (Güven: %{ai_report.confidence_pct})\n"
        msg += f"• {ai_report.logic_explanation}\n\n"
        msg += f"⏱ Scalping: {ai_report.scalping_signal}\n"
        msg += f"📅 Swing: {ai_report.swing_signal}\n\n"
        msg += f"⚠️ _{ai_report.risk_warning}_\n"
    
    return msg

# ============================================
# ANA PROGRAM
# ============================================

if __name__ == "__main__":
    print("🚀 Advanced Crypto Analysis Bot v2.0 Başlatılıyor...")
    print("="*50)
    
    # 1. Sentiment ve Makro Veriler
    print("\n1️⃣ Sentiment ve Makro Veriler Çekiliyor...")
    
    fng_value, fng_label, fng_trend = get_fear_and_greed()
    news_data = get_crypto_news_sentiment()
    reddit_data = get_reddit_sentiment()
    macro_data = get_macro_data()
    whale_data = get_whale_activity()
    defi_data = get_defi_tvl()
    
    sentiment_data = {
        'fng_value': fng_value,
        'fng_label': fng_label,
        'fng_trend': fng_trend,
        'news_sentiment': news_data['sentiment_score'],
        'reddit_sentiment': reddit_data.get('sentiment', 0)
    }
    
    print(f"   ✓ Fear & Greed: {fng_value} ({fng_label})")
    print(f"   ✓ Makro: {macro_data.get('status', 'N/A')}")
    print(f"   ✓ Whale: {whale_data.get('activity', 'N/A')}")
    
    # 2. Ana rapor başlığı
    report_msg = "🌍 *KAPSAMLI PİYASA RAPORU*\n"
    report_msg += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC\n\n"
    
    report_msg += f"😊 *DUYGU DURUMU:* {fng_label} (Trend: {fng_trend})\n"
    report_msg += f"💵 *MAKRO:* {macro_data.get('status', 'N/A')}\n"
    report_msg += f"🐋 *BALİNA:* {whale_data.get('activity', 'N/A')} | {whale_data.get('net_flow', 'N/A')}\n"
    report_msg += f"📺 *HABER:* {'Pozitif' if news_data['sentiment_score'] > 0 else 'Negatif' if news_data['sentiment_score'] < 0 else 'Nötr'}\n\n"
    
    # 3. Major Coin Analizi
    print("\n2️⃣ Major Coin Analizi Yapılıyor...")
    
    for symbol in MAJOR_SYMBOLS:
        print(f"   📊 {symbol} analiz ediliyor...")
        
        market_data = get_comprehensive_market_data(symbol)
        
        if market_data:
            # Skorları hesapla
            tech_score = calculate_technical_score(market_data)
            sent_score = calculate_sentiment_score(
                fng_value, 
                news_data['sentiment_score'],
                reddit_data.get('sentiment', 0)
            )
            onchain_score = calculate_onchain_score(
                whale_data, 
                defi_data,
                market_data.get('exchange_flow', 'NEUTRAL')
            )
            pattern_score = calculate_pattern_score(market_data.get('candlestick_patterns', []))
            
            aggregate = calculate_aggregate_signal(tech_score, sent_score, onchain_score, pattern_score)
            
            # AI Analizi
            ai_report = analyze_with_gemini_advanced(
                symbol, market_data, macro_data, sentiment_data, aggregate
            )
            
            # Mesajı formatla
            report_msg += format_report_message(symbol, market_data, aggregate, ai_report)
            report_msg += "\n"
            
            print(f"   ✓ {symbol}: {aggregate['action']} (Skor: {aggregate['total_score']})")
    
    # 4. Gem Taraması
    print("\n3️⃣ Altcoin Gem Taraması Yapılıyor...")
    
    gems = scan_gems_advanced()
    
    if gems:
        report_msg += "\n💎 *FIRSAT ALTCOİNLER (GEM)*\n"
        report_msg += "─"*25 + "\n"
        
        for gem in gems[:5]:  # İlk 5 gem
            report_msg += f"\n*{gem['symbol']}* (Skor: {gem['score']})\n"
            report_msg += f"💰 ${gem['price']:,.4f} ({gem['change_24h']:+.1f}%)\n"
            report_msg += f"📊 RSI: {gem['rsi']} | Hacim: x{gem['volume_ratio']}\n"
            report_msg += f"🔍 {', '.join(gem['reasons'][:3])}\n"
        
        print(f"   ✓ {len(gems)} potansiyel gem bulundu")
    else:
        report_msg += "\n💎 *GEM TARAMASI:* Kriterlere uyan altcoin bulunamadı.\n"
        print("   ℹ️ Uygun gem bulunamadı")
    
    # 5. Son notlar
    report_msg += "\n" + "─"*30 + "\n"
    report_msg += "⚠️ _Bu analiz yatırım tavsiyesi değildir._\n"
    report_msg += "🤖 _Advanced Crypto Bot v2.0_"
    
    # 6. Telegram gönder
    print("\n4️⃣ Telegram'a Gönderiliyor...")
    send_telegram(report_msg)
    
    print("\n" + "="*50)
    print("✅ Tüm İşlemler Tamamlandı!")
