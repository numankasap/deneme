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

# --- ORTAM DEĞİŞKENLERİ ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- AYARLAR ---
MAJOR_SYMBOLS = ['BTC/USDT', 'ETH/USDT']

# --- KURULUMLAR ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client_ai = instructor.from_genai(
    client=genai.Client(api_key=GEMINI_KEY),
    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
)

# Gate.io (ABD Dostu)
exchange = ccxt.gateio()

# --- VERİ MODELİ ---
class MarketReport(BaseModel):
    market_sentiment_score: int = Field(description="0-100 arası puan.")
    sentiment_summary: str = Field(description="Haberlerin özeti (TÜRKÇE).")
    macro_outlook: str = Field(description="Makro durum yorumu (TÜRKÇE).")
    final_action: str = Field(description="Karar: 'GÜÇLÜ AL', 'AL', 'BEKLE', 'SAT', 'GÜÇLÜ SAT' (TÜRKÇE).")
    logic_explanation: str = Field(description="Kararın mantığı. Çelişkili durumlarda Makro veriyi baz al. (TÜRKÇE).")

# --- YARDIMCI FONKSİYONLAR ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger(series, period=20, std=2):
    sma = series.rolling(window=period).mean()
    rstd = series.rolling(window=period).std()
    upper = sma + (rstd * std)
    lower = sma - (rstd * std)
    return upper, lower

# --- 1. MAKRO & HABER ---
def get_macro_data():
    try:
        tickers = ["DX-Y.NYB", "^GSPC"]
        data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=True)['Close']
        dxy_change = ((data['DX-Y.NYB'].iloc[-1] - data['DX-Y.NYB'].iloc[-2]) / data['DX-Y.NYB'].iloc[-2]) * 100
        sp_change = ((data['^GSPC'].iloc[-1] - data['^GSPC'].iloc[-2]) / data['^GSPC'].iloc[-2]) * 100
        
        status = "Nötr"
        if dxy_change > 0.3: status = "Negatif (Dolar Güçleniyor)"
        elif sp_change < -0.5: status = "Negatif (Borsa Düşüyor)"
        elif dxy_change < -0.3 and sp_change > 0.3: status = "Pozitif (Risk İştahı Yüksek)"
        return {"dxy_change": round(float(dxy_change), 2), "sp500_change": round(float(sp_change), 2), "status": status}
    except:
        return {"dxy_change": 0, "sp500_change": 0, "status": "Veri Yok"}

def get_crypto_news():
    try:
        feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
        return [entry.title for entry in feed.entries[:5]]
    except:
        return ["Haber yok."]

def get_fear_and_greed():
    tr = {"Extreme Fear": "Aşırı Korku 😱", "Fear": "Korku 😨", "Neutral": "Nötr 😐", "Greed": "Açgözlülük 🤑", "Extreme Greed": "Aşırı Açgözlülük 🚀"}
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        return int(r['data'][0]['value']), tr.get(r['data'][0]['value_classification'], "Nötr")
    except:
        return 50, "Nötr"

# --- 2. VERİ ÇEKME ---
def get_market_data(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['rsi'] = calculate_rsi(df['close'])
        df['bb_upper'], df['bb_lower'] = calculate_bollinger(df['close'])
        
        last = df.iloc[-1]
        change_24h = ((last['close'] - df.iloc[-24]['close']) / df.iloc[-24]['close']) * 100
        whale_alert = "EVET" if last['volume'] > (df['volume'].mean() * 1.5) else "HAYIR"
        
        return {
            "price": last['close'],
            "change_24h": round(change_24h, 2),
            "rsi": round(last['rsi'], 2),
            "bb_pos": "Üst Bandı Deldi" if last['close'] > last['bb_upper'] else "Alt Bandı Deldi" if last['close'] < last['bb_lower'] else "Bant İçi",
            "whale_activity": whale_alert
        }
    except:
        return None

# --- 3. GEM AVCI (ALTCOIN TARAMA) ---
def scan_gems():
    print("💎 Gem Taraması Başlıyor (Gate.io)...")
    gems = []
    try:
        tickers = exchange.fetch_tickers()
        # Hacmi 500k$'dan büyük USDT paritelerini al
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 500000]
        
        # Hacme göre sırala ve ilk 50'ye bak
        sorted_symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]
        
        for sym in sorted_symbols:
            if sym in MAJOR_SYMBOLS: continue # BTC/ETH'yi atla
            
            try:
                ohlcv = exchange.fetch_ohlcv(sym, '1h', limit=20)
                if not ohlcv: continue
                
                df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                rsi = calculate_rsi(df['c']).iloc[-1]
                avg_vol = df['v'].mean()
                cur_vol = df['v'].iloc[-1]
                
                # GEVŞETİLMİŞ KRİTERLER: RSI < 40 VE Hacim > 1.5x Ortalama
                if rsi < 40 and cur_vol > (avg_vol * 1.5):
                    gem_msg = f"💎 *{sym}*\n   RSI: {rsi:.1f} (DİP) | 📊 Hacim: {cur_vol/avg_vol:.1f}x Patlama!"
                    gems.append(gem_msg)
            except:
                continue
    except Exception as e:
        print(f"Tarama Hatası: {e}")
    
    return gems

# --- 4. ANALİZ VE RAPOR ---
def analyze_with_gemini(symbol, market_data, macro_data, news, fng_score):
    prompt = f"""
    Sen Türk bir Kripto Stratejistisin. {symbol} verilerini analiz et.
    
    VERİLER:
    - Korku Endeksi: {fng_score}
    - Makro Durum: {macro_data['status']}
    - Haberler: {news}
    - Fiyat: ${market_data['price']:,.2f} (%{market_data['change_24h']})
    - RSI: {market_data['rsi']}
    
    KARAR KURALI:
    1. Makro "Negatif" ise "AL" deme, "BEKLE" de.
    2. Makro "Pozitif" ise teknik veriye güven.
    
    %100 Türkçe konuş.
    """
    try:
        return client_ai.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=[{"role": "user", "content": prompt}],
            response_model=MarketReport,
        )
    except:
        return None

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- ANA PROGRAM ---
if __name__ == "__main__":
    print("1️⃣ Major Coin Analizi Yapılıyor...")
    macro = get_macro_data()
    news = get_crypto_news()
    fng_val, fng_label = get_fear_and_greed()
    
    report_msg = f"🌍 *Piyasa Raporu* ({fng_label})\n"
    report_msg += f"💵 Makro: {macro['status']}\n\n"
    
    # BTC & ETH
    for symbol in MAJOR_SYMBOLS:
        data = get_market_data(symbol)
        if data:
            ai = analyze_with_gemini(symbol, data, macro, news, fng_val)
            if ai:
                icon = "🟢" if "AL" in ai.final_action else "🔴" if "SAT" in ai.final_action else "⚪"
                report_msg += f"*{symbol}* ${data['price']:,.2f}\n"
                report_msg += f"{icon} Karar: *{ai.final_action}*\n"
                report_msg += f"💡 {ai.logic_explanation}\n\n"

    print("2️⃣ Altcoin Taraması Yapılıyor...")
    found_gems = scan_gems()
    
    if found_gems:
        report_msg += "🚀 *Fırsat Altcoinler (Gem)*\n" + "\n".join(found_gems)
    else:
        report_msg += "👀 *Uygun gem bulunamadı.* (RSI < 40 kriterine uyan yok)"

    send_telegram(report_msg)
    print("✅ Tüm İşlemler Tamamlandı.")
