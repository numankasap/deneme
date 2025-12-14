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
exchange = ccxt.binance()

# ==========================================
# BÖLÜM 1: VERİ MODELLERİ (AI ÇIKTILARI)
# ==========================================

# 1. Major Coin Rapor Modeli
class MajorReport(BaseModel):
    market_sentiment_score: int = Field(description="0-100 arası puan.")
    sentiment_summary: str = Field(description="Haberlerin özeti (TÜRKÇE).")
    macro_outlook: str = Field(description="Makro durum yorumu (TÜRKÇE).")
    final_action: str = Field(description="Karar: 'GÜÇLÜ AL', 'AL', 'BEKLE', 'SAT', 'GÜÇLÜ SAT'.")
    logic_explanation: str = Field(description="Kararın detaylı mantığı (TÜRKÇE).")

# 2. Gem (Altcoin) Rapor Modeli
class GemPick(BaseModel):
    coin_name: str = Field(description="Coin Sembolü.")
    setup_type: str = Field(description="Fırsat Tipi: 'BALİNA GİRİŞİ', 'TREND DÖNÜŞÜ' veya 'HYPE'.")
    score: int = Field(description="Potansiyel puanı (1-100).")
    reason: str = Field(description="Neden seçildi? (TÜRKÇE).")
    levels: str = Field(description="Giriş ve hedef seviyeleri.")

class GemStrategyReport(BaseModel):
    market_summary: str = Field(description="Altcoin piyasası genel durumu.")
    picks: list[GemPick] = Field(description="En iyi 3 coin seçimi.")

# ==========================================
# BÖLÜM 2: ORTAK FONKSİYONLAR
# ==========================================

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

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# ==========================================
# BÖLÜM 3: MAJOR ANALİZ MODÜLÜ (BTC/ETH)
# ==========================================

def get_macro_data():
    try:
        tickers = ["DX-Y.NYB", "^GSPC"]
        data = yf.download(tickers, period="5d", interval="1d", progress=False)['Close']
        dxy_change = ((data['DX-Y.NYB'].iloc[-1] - data['DX-Y.NYB'].iloc[-2]) / data['DX-Y.NYB'].iloc[-2]) * 100
        sp_change = ((data['^GSPC'].iloc[-1] - data['^GSPC'].iloc[-2]) / data['^GSPC'].iloc[-2]) * 100
        
        status = "Nötr"
        if dxy_change > 0.3: status = "Negatif (Dolar Güçleniyor)"
        elif sp_change < -0.5: status = "Negatif (Borsa Düşüyor)"
        elif dxy_change < -0.3 and sp_change > 0.3: status = "Pozitif (Risk İştahı Yüksek)"
        return {"dxy": round(float(dxy_change), 2), "sp500": round(float(sp_change), 2), "status": status}
    except:
        return {"dxy": 0, "sp500": 0, "status": "Veri Yok"}

def get_crypto_news():
    try:
        feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
        return [entry.title for entry in feed.entries[:5]]
    except:
        return ["Haber verisi alınamadı."]

def get_fear_and_greed():
    trans = {"Extreme Fear": "Aşırı Korku 😱", "Fear": "Korku 😨", "Neutral": "Nötr 😐", "Greed": "Açgözlülük 🤑", "Extreme Greed": "Aşırı Açgözlülük 🚀"}
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        val = int(r['data'][0]['value'])
        label = r['data'][0]['value_classification']
        return val, trans.get(label, label)
    except:
        return 50, "Nötr"

def get_major_market_data(symbol):
    try:
        coin = symbol.split('/')[0]
        url = f"https://min-api.cryptocompare.com/data/v2/histohour?fsym={coin}&tsym=USD&limit=100"
        res = requests.get(url, timeout=10).json()
        if res.get('Response') != 'Success': return None
        
        df = pd.DataFrame(res['Data']['Data'])
        df['close'] = df['close'].astype(float)
        df['volumeto'] = df['volumeto'].astype(float)
        
        df['rsi'] = calculate_rsi(df['close'])
        df['bb_upper'], df['bb_lower'] = calculate_bollinger(df['close'])
        
        last = df.iloc[-1]
        prev_24h = df.iloc[-24]
        change_24h = ((last['close'] - prev_24h['close']) / prev_24h['close']) * 100
        avg_vol = df['volumeto'].mean()
        
        return {
            "price": last['close'],
            "change_24h": round(change_24h, 2),
            "rsi": round(last['rsi'], 2),
            "bb_pos": "Bant Dışı" if last['close'] > last['bb_upper'] or last['close'] < last['bb_lower'] else "Bant İçi",
            "whale": "EVET" if last['volumeto'] > (avg_vol * 1.5) else "HAYIR"
        }
    except:
        return None

def analyze_major_with_gemini(symbol, data, macro, news, fng):
    prompt = f"""
    Sen Türk bir Kripto Fon Yöneticisisin. {symbol} için:
    VERİLER: Korku Endeksi: {fng} (0-100), Makro: {macro['status']}, Haberler: {news}, 
    Fiyat: ${data['price']:,.2f}, Değişim: %{data['change_24h']}, RSI: {data['rsi']}, Balina: {data['whale']}.
    
    KURALLAR:
    1. YANIT %100 TÜRKÇE OLSUN.
    2. Karar sadece: 'GÜÇLÜ AL', 'AL', 'BEKLE', 'SAT', 'GÜÇLÜ SAT'.
    3. Eğer fiyat düşmüşse ama haberler iyiyse "Fırsat" vurgusu yap.
    """
    try:
        return client_ai.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=[{"role": "user", "content": prompt}],
            response_model=MajorReport,
        )
    except: return None

# ==========================================
# BÖLÜM 4: GEM AVCISI MODÜLÜ (ALTCOIN SCANNER)
# ==========================================

def scan_binance_market():
    print("📡 Binance Altcoin Taraması Başlıyor...")
    try:
        tickers = exchange.fetch_tickers()
        valid_pairs = [s for s in tickers if s.endswith('/USDT') and tickers[s]['quoteVolume'] > 2000000] # 2M$ altı hacmi ele
        
        candidates = []
        # Ön Eleme: %3 ile %15 arası artanlar veya %5 düşenler (Hareketli coinler)
        for s in valid_pairs:
            chg = tickers[s]['percentage']
            if (chg > 3 and chg < 15) or (chg < -5):
                candidates.append(s)
        
        # En yüksek hacimli 15 adayı seç
        candidates = sorted(candidates, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:15]
        
        results = []
        for s in candidates:
            try:
                ohlcv = exchange.fetch_ohlcv(s, '1h', limit=48)
                df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
                rsi = calculate_rsi(df['c']).iloc[-1]
                vol_ratio = df['v'].iloc[-1] / df['v'].mean()
                
                # Sinyal Filtresi
                is_whale = vol_ratio > 3 and df['c'].iloc[-1] > df['o'].iloc[-1] # Hacim patlaması + Yeşil mum
                is_dip = rsi < 30 # Aşırı satım
                
                if is_whale or is_dip:
                    results.append({"symbol": s, "price": df['c'].iloc[-1], "rsi": round(rsi,2), "vol_x": round(vol_ratio,1), "type": "Balina 🐳" if is_whale else "Dip 🌤️"})
            except: continue
        return results
    except Exception as e:
        print(f"Tarama Hatası: {e}")
        return []

def get_trending_coins():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=5).json()
        return [i['item']['symbol'] for i in r['coins'][:5]]
    except: return []

def analyze_gems_with_gemini(gems, trending):
    gems_text = "\n".join([f"- {g['symbol']}: Fiyat {g['price']}, RSI {g['rsi']}, Hacim {g['vol_x']}x, Tip: {g['type']}" for g in gems])
    
    prompt = f"""
    Sen Kripto Altcoin Avcısısın. Aşağıdaki teknik tarama sonuçlarını ve trendleri analiz et.
    
    TARAMA SONUÇLARI:
    {gems_text}
    
    POPÜLER TRENDLER (HİKAYE):
    {trending}
    
    GÖREV:
    Bu listeden EN İYİ 3 potansiyeli seç.
    - Teknik olarak "Balina" girişi olanlara öncelik ver.
    - Eğer teknik sinyal veren coin Trend listesindeyse bu çok güçlüdür.
    - Yanıt %100 TÜRKÇE olsun.
    """
    try:
        return client_ai.chat.completions.create(
            model="gemini-2.0-flash-exp",
            messages=[{"role": "user", "content": prompt}],
            response_model=GemStrategyReport,
        )
    except: return None

# ==========================================
# BÖLÜM 5: ANA AKIŞ
# ==========================================

def main_flow():
    # --- AŞAMA 1: MAJOR ANALİZ (BTC/ETH) ---
    print("1️⃣ Major Coin Analizi Yapılıyor...")
    macro = get_macro_data()
    news = get_crypto_news()
    fng, fng_lbl = get_fear_and_greed()
    
    report_major = f"🌍 *Piyasa Raporu* ({fng_lbl})\n💵 Makro: {macro['status']}\n\n"
    
    for s in MAJOR_SYMBOLS:
        d = get_major_market_data(s)
        if d:
            ai = analyze_major_with_gemini(s, d, macro, news, fng)
            if ai:
                # DB Kayıt (Major)
                try:
                    supabase.table('market_analysis').insert({
                        "symbol": s, "price": d['price'], "trend": ai.final_action, 
                        "risk_score": 100-ai.market_sentiment_score, "ai_comment": ai.logic_explanation,
                        "technical_data": {"macro": ai.macro_outlook}
                    }).execute()
                except: pass
                
                icon = "🟢" if "AL" in ai.final_action else "🔴" if "SAT" in ai.final_action else "⚪"
                report_major += f"*{s}* ${d['price']:,.2f}\n"
                report_major += f"{icon} Karar: *{ai.final_action}*\n"
                report_major += f"💡 _{ai.logic_explanation}_\n\n"
    
    send_telegram(report_major)
    
    # --- AŞAMA 2: GEM TARAMASI (ALTCOINS) ---
    print("2️⃣ Altcoin Taraması Yapılıyor...")
    gems = scan_binance_market()
    trends = get_trending_coins()
    
    if gems:
        ai_gems = analyze_gems_with_gemini(gems, trends)
        if ai_gems:
            report_gems = f"💎 **GEM AVCISI RADARI**\n"
            report_gems += f"ℹ️ _Piyasa Notu: {ai_gems.market_summary}_\n\n"
            
            for p in ai_gems.picks:
                report_gems += f"🚀 **{p.coin_name}** ({p.setup_type})\n"
                report_gems += f"Puan: {p.score}/100\n"
                report_gems += f"Neden: _{p.reason}_\n"
                report_gems += f"🎯 {p.levels}\n\n"
            
            report_gems += f"🔥 **Hype Olanlar:** {', '.join(trends)}"
            send_telegram(report_gems)
    else:
        print("Uygun gem bulunamadı.")

if __name__ == "__main__":
    main_flow()
    print("✅ Tüm İşlemler Tamamlandı.")
