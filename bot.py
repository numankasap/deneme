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

# Binance yerine Gate.io kullanıyoruz (GitHub Actions IP'sini bloklamaz)
exchange = ccxt.gateio() 

# --- VERİ MODELİ ---
class MarketReport(BaseModel):
    market_sentiment_score: int = Field(description="0-100 arası puan.")
    sentiment_summary: str = Field(description="Haberlerin özeti (TÜRKÇE).")
    macro_outlook: str = Field(description="Makro durum yorumu (TÜRKÇE).")
    final_action: str = Field(description="Karar: 'GÜÇLÜ AL', 'AL', 'BEKLE', 'SAT', 'GÜÇLÜ SAT' (TÜRKÇE).")
    logic_explanation: str = Field(description="Kararın mantığı. Çelişkili durumlarda Makro veriyi baz al. (TÜRKÇE).")

# --- 1. MAKRO VERİLER ---
def get_macro_data():
    try:
        tickers = ["DX-Y.NYB", "^GSPC"]
        # auto_adjust=True ekledik, uyarıyı kaldırmak için
        data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=True)['Close']
        
        dxy_change = ((data['DX-Y.NYB'].iloc[-1] - data['DX-Y.NYB'].iloc[-2]) / data['DX-Y.NYB'].iloc[-2]) * 100
        sp_change = ((data['^GSPC'].iloc[-1] - data['^GSPC'].iloc[-2]) / data['^GSPC'].iloc[-2]) * 100
        
        status = "Nötr"
        if dxy_change > 0.3: status = "Negatif (Dolar Güçleniyor)"
        elif sp_change < -0.5: status = "Negatif (Borsa Düşüyor)"
        elif dxy_change < -0.3 and sp_change > 0.3: status = "Pozitif (Risk İştahı Yüksek)"
        
        return {
            "dxy_change": round(float(dxy_change), 2),
            "sp500_change": round(float(sp_change), 2),
            "status": status
        }
    except:
        return {"dxy_change": 0, "sp500_change": 0, "status": "Veri Yok"}

# --- 2. HABER VE DUYGU ---
def get_crypto_news():
    try:
        feed_url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
        feed = feedparser.parse(feed_url)
        headlines = [entry.title for entry in feed.entries[:5]]
        return headlines
    except:
        return ["Haber verisi alınamadı."]

def get_fear_and_greed():
    translation = {
        "Extreme Fear": "Aşırı Korku 😱", "Fear": "Korku 😨",
        "Neutral": "Nötr 😐", "Greed": "Açgözlülük 🤑", "Extreme Greed": "Aşırı Açgözlülük 🚀"
    }
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = r.json()
        val = int(data['data'][0]['value'])
        label_en = data['data'][0]['value_classification']
        return val, translation.get(label_en, label_en)
    except:
        return 50, "Nötr"

# --- 3. TEKNİK HESAPLAMALAR ---
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

def get_market_data(symbol, timeframe='1h', limit=100):
    try:
        # ccxt üzerinden Gate.io verisi çekiyoruz (Daha güvenilir)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['rsi'] = calculate_rsi(df['close'])
        df['bb_upper'], df['bb_lower'] = calculate_bollinger(df['close'])
        
        last = df.iloc[-1]
        prev_24h = df.iloc[-24]
        change_24h = ((last['close'] - prev_24h['close']) / prev_24h['close']) * 100
        
        avg_vol = df['volume'].mean()
        whale_alert = "EVET" if last['volume'] > (avg_vol * 1.5) else "HAYIR"
        
        return {
            "price": last['close'],
            "change_24h": round(change_24h, 2),
            "rsi": round(last['rsi'], 2),
            "bb_pos": "Üst Bandı Deldi" if last['close'] > last['bb_upper'] else "Alt Bandı Deldi" if last['close'] < last['bb_lower'] else "Bant İçi",
            "whale_activity": whale_alert
        }
    except Exception as e:
        print(f"Veri Hatası ({symbol}): {e}")
        return None

# --- 4. ALTCOIN TARAMASI (GEM BULUCU) ---
def scan_gems():
    """Gate.io'da RSI < 30 olan ve Hacmi Patlayan coinleri bulur"""
    try:
        print("💎 Gem Taraması Başlıyor (Gate.io)...")
        tickers = exchange.fetch_tickers()
        gems = []
        
        # Sadece USDT pariteleri ve Hacmi yüksek olanlar
        symbols = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 1000000]
        
        # İlk 20 coini tara (Hız için sınırlı)
        for sym in symbols[:20]: 
            try:
                ohlcv = exchange.fetch_ohlcv(sym, '1h', limit=20)
                df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                rsi = calculate_rsi(df['c']).iloc[-1]
                
                # Kriter: RSI düşük VE Son mum hacmi ortalamanın 2 katı
                if rsi < 35 and df['v'].iloc[-1] > (df['v'].mean() * 2):
                    gems.append(f"💎 {sym} (RSI: {rsi:.1f})")
            except:
                continue
        return gems
    except Exception as e:
        print(f"Tarama Hatası: {e}")
        return []

# --- 5. GEMINI ANALİZİ (GÜNCELLENMİŞ MANTIK) ---
def analyze_with_gemini(symbol, market_data, macro_data, news, fng_score):
    
    prompt = f"""
    Sen Türk bir Kripto Stratejistisin. {symbol} verilerini analiz et.
    
    VERİLER:
    - Korku Endeksi: {fng_score}
    - Makro Durum: {macro_data['status']}
    - Haberler: {news}
    - Fiyat: ${market_data['price']:,.2f} (%{market_data['change_24h']})
    - RSI: {market_data['rsi']}
    
    KARAR KURALI (HIYERARŞİ):
    1. EĞER Makro Durum "Negatif" İSE -> Teknik göstergeler (RSI) "Ucuz" dese bile, 
       bunu "Ayı Tuzağı" olarak yorumla ve "BEKLE" veya "SAT" ver. Asla "AL" deme.
    2. EĞER Makro "Pozitif" veya "Nötr" İSE -> Teknik verilere göre "AL" verebilirsin.
    
    ÇIKTI KURALLARI:
    - %100 Türkçe konuş.
    - 'final_action' sadece: 'GÜÇLÜ AL', 'AL', 'BEKLE', 'SAT', 'GÜÇLÜ SAT'.
    - Mantık kısmında bu çelişkiyi açıkla (Örn: RSI düşük ama Makro kötü olduğu için bekle).
    """
    
    try:
        return client_ai.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=[{"role": "user", "content": prompt}],
            response_model=MarketReport,
        )
    except Exception as e:
        print(f"AI Hatası: {e}")
        return None

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def save_db(symbol, price, report):
    data = {
        "symbol": symbol,
        "price": price,
        "trend": report.final_action,
        "risk_score": 100 - report.market_sentiment_score,
        "ai_comment": report.logic_explanation,
        "technical_data": {"macro": report.macro_outlook}
    }
    try:
        supabase.table('market_analysis').insert(data).execute()
    except:
        pass

# --- ANA PROGRAM ---
if __name__ == "__main__":
    print("🚀 Analiz Başlıyor...")
    
    macro = get_macro_data()
    news = get_crypto_news()
    fng_val, fng_label = get_fear_and_greed()
    
    report_msg = f"🌍 *Piyasa Özeti*\n"
    report_msg += f"💵 Makro: {macro['status']}\n"
    report_msg += f"🎭 Hissiyat: {fng_val} ({fng_label})\n\n"
    
    # 1. Major Coin Analizi
    for symbol in MAJOR_SYMBOLS:
        market_data = get_market_data(symbol)
        if market_data:
            analysis = analyze_with_gemini(symbol, market_data, macro, news, fng_val)
            if analysis:
                save_db(symbol, market_data['price'], analysis)
                
                icon = "🟢" if "AL" in analysis.final_action else "🔴" if "SAT" in analysis.final_action else "⚪"
                
                report_msg += f"*{symbol}* ${market_data['price']:,.2f}\n"
                report_msg += f"Değişim: %{market_data['change_24h']} | RSI: {market_data['rsi']}\n"
                report_msg += f"{icon} Karar: *{analysis.final_action}*\n"
                report_msg += f"🧠 Mantık: _{analysis.logic_explanation}_\n\n"
    
    # 2. Gem Taraması Sonuçları
    gems = scan_gems()
    if gems:
        report_msg += "💎 *Potansiyel Fırsatlar (Gate.io)*\n" + "\n".join(gems)
    
    send_telegram(report_msg)
    print("✅ Bitti.")
