import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import feedparser
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
SYMBOLS = ['BTC/USDT', 'ETH/USDT']

# --- KURULUMLAR ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client_ai = instructor.from_genai(
    client=genai.Client(api_key=GEMINI_KEY),
    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
)

# --- VERİ MODELİ ---
class MarketReport(BaseModel):
    market_sentiment_score: int = Field(description="0 (Aşırı Korku) ile 100 (Aşırı Açgözlülük) arasında puan.")
    sentiment_summary: str = Field(description="Haberlerin ve makro verilerin piyasaya etkisinin özeti.")
    macro_outlook: str = Field(description="Dolar (DXY) ve Borsa (SP500) durumunun kriptoya etkisi.")
    technical_signal: str = Field(description="Sadece grafiğe dayalı sinyal: 'AL', 'SAT', 'NÖTR'")
    final_action: str = Field(description="Tüm verilerin (Teknik + Temel) birleşimiyle nihai karar.")
    logic_explanation: str = Field(description="Kararın mantığı. (Örn: 'Fiyat düştü ama haberler çok iyi, bu bir alım fırsatıdır')")

# --- 1. MAKRO VERİLER (DXY & SP500) ---
def get_macro_data():
    try:
        # DXY (Dolar) ve S&P 500
        tickers = ["DX-Y.NYB", "^GSPC"]
        data = yf.download(tickers, period="5d", interval="1d", progress=False)['Close']
        
        # Son değişim yüzdeleri
        dxy_last = data['DX-Y.NYB'].iloc[-1]
        dxy_prev = data['DX-Y.NYB'].iloc[-2]
        dxy_change = ((dxy_last - dxy_prev) / dxy_prev) * 100
        
        sp_last = data['^GSPC'].iloc[-1]
        sp_prev = data['^GSPC'].iloc[-2]
        sp_change = ((sp_last - sp_prev) / sp_prev) * 100
        
        status = "Nötr"
        if dxy_change > 0.3: status = "Negatif (Dolar Güçleniyor)"
        elif sp_change < -0.5: status = "Negatif (Borsa Düşüyor)"
        elif dxy_change < -0.3 and sp_change > 0.3: status = "Pozitif (Risk İştahı Yüksek)"
        
        return {
            "dxy_change": round(float(dxy_change), 2),
            "sp500_change": round(float(sp_change), 2),
            "status": status
        }
    except Exception as e:
        print(f"Makro Veri Hatası: {e}")
        return {"dxy_change": 0, "sp500_change": 0, "status": "Veri Yok"}

# --- 2. HABER VE DUYGU ANALİZİ ---
def get_crypto_news():
    """CoinDesk RSS beslemesinden son haberleri çeker"""
    try:
        feed_url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
        feed = feedparser.parse(feed_url)
        headlines = [entry.title for entry in feed.entries[:5]] # Son 5 başlık
        return headlines
    except Exception as e:
        print(f"Haber Hatası: {e}")
        return ["Haber verisi alınamadı."]

def get_fear_and_greed():
    """Alternative.me API'den Korku ve Açgözlülük Endeksini çeker"""
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = r.json()
        return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except:
        return 50, "Neutral"

# --- 3. TEKNİK HESAPLAMALAR (Manuel Pandas) ---
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

def get_market_data(symbol):
    try:
        coin_map = {'BTC/USDT': 'BTC', 'ETH/USDT': 'ETH'}
        coin = coin_map.get(symbol)
        
        # Cryptocompare API
        url = f"https://min-api.cryptocompare.com/data/v2/histohour?fsym={coin}&tsym=USD&limit=100"
        res = requests.get(url, timeout=10).json()
        
        if res.get('Response') != 'Success': return None
        
        df = pd.DataFrame(res['Data']['Data'])
        df['close'] = df['close'].astype(float)
        df['volumeto'] = df['volumeto'].astype(float)
        
        # İndikatörler
        df['rsi'] = calculate_rsi(df['close'])
        df['bb_upper'], df['bb_lower'] = calculate_bollinger(df['close'])
        
        # Son veriler
        last = df.iloc[-1]
        prev_24h = df.iloc[-24] # 24 saat önceki mum
        
        # Değişim
        change_24h = ((last['close'] - prev_24h['close']) / prev_24h['close']) * 100
        
        # Balina Aktivitesi (Hacim Anormalliği)
        avg_vol = df['volumeto'].mean()
        whale_alert = "EVET" if last['volumeto'] > (avg_vol * 1.5) else "HAYIR"
        
        return {
            "price": last['close'],
            "change_24h": round(change_24h, 2),
            "rsi": round(last['rsi'], 2),
            "bb_pos": "Üst Bandı Deldi" if last['close'] > last['bb_upper'] else "Alt Bandı Deldi" if last['close'] < last['bb_lower'] else "Bant İçi",
            "whale_activity": whale_alert
        }
    except Exception as e:
        print(f"Borsa Veri Hatası ({symbol}): {e}")
        return None

# --- 4. GEMINI ANALİZİ ---
def analyze_with_gemini(symbol, market_data, macro_data, news, fng_score):
    
    prompt = f"""
    Sen Dünyanın en iyi Hedge Fon Yöneticisisin. {symbol} için aşağıdaki verileri sentezle.
    
    1. TEMEL VE MAKRO VERİLER:
    - Korku/Açgözlülük Endeksi: {fng_score} (0=Aşırı Korku, 100=Aşırı Açgözlülük)
    - Makro Durum: {macro_data['status']} (DXY Değişimi: %{macro_data['dxy_change']})
    - Son Haber Başlıkları: {news}
    
    2. TEKNİK VERİLER:
    - Fiyat: ${market_data['price']:,.2f}
    - 24 Saatlik Değişim: %{market_data['change_24h']}
    - RSI (14): {market_data['rsi']}
    - Bollinger Konumu: {market_data['bb_pos']}
    - Balina Aktivitesi (Hacim): {market_data['whale_activity']}
    
    ÖZEL MANTIK GÖREVİ (BUY THE DIP):
    Eğer Fiyat %3'ten fazla düşmüşse (change_24h < -3) AMA Haberler/Makro olumluysa ve FNG Endeksi düşükse (Korku), 
    bunu "DİPTEN ALIM FIRSATI" olarak değerlendir.
    
    Eğer Balina aktivitesi varsa ve fiyat düşüyorsa "SATIŞ BASKISI" uyarısı ver.
    
    Bu verileri harmanlayarak yatırım kararı ver.
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
        "risk_score": 100 - report.market_sentiment_score, # Basit risk hesabı
        "ai_comment": report.logic_explanation,
        "technical_data": {"macro": report.macro_outlook, "news": report.sentiment_summary}
    }
    try:
        supabase.table('market_analysis').insert(data).execute()
    except Exception as e:
        print(f"DB Hatası: {e}")

# --- ANA PROGRAM ---
if __name__ == "__main__":
    print("🌍 Global Analiz Başlatılıyor...")
    
    # 1. Genel Verileri Çek
    macro = get_macro_data()
    news = get_crypto_news()
    fng_val, fng_label = get_fear_and_greed()
    
    report_msg = f"🌍 *Piyasa Özeti*\n"
    report_msg += f"💵 Makro: {macro['status']}\n"
    report_msg += f"🎭 Hissiyat: {fng_val} ({fng_label})\n\n"
    
    for symbol in SYMBOLS:
        print(f"İnceleniyor: {symbol}")
        market_data = get_market_data(symbol)
        
        if market_data:
            analysis = analyze_with_gemini(symbol, market_data, macro, news, fng_val)
            
            if analysis:
                save_db(symbol, market_data['price'], analysis)
                
                icon = "🟢" if "AL" in analysis.final_action else "🔴" if "SAT" in analysis.final_action else "⚪"
                if "FIRSAT" in analysis.logic_explanation.upper(): icon = "💎" # Fırsat ikonu
                
                report_msg += f"*{symbol}* ${market_data['price']:,.2f}\n"
                report_msg += f"Değişim: %{market_data['change_24h']} | RSI: {market_data['rsi']}\n"
                report_msg += f"{icon} Karar: *{analysis.final_action}*\n"
                report_msg += f"🧠 Mantık: _{analysis.logic_explanation}_\n\n"
    
    send_telegram(report_msg)
    print("✅ Bitti.")
