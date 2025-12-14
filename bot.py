import os
import json
import requests
import pandas as pd
import numpy as np
import instructor
from google import genai
from supabase import create_client
from pydantic import BaseModel, Field

# --- ORTAM DEĞİŞKENLERİ (GitHub Secrets'tan gelecek) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- AYARLAR ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT'] # İzlenecek coinler

# --- KURULUMLAR ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Instructor ile Gemini'yi güçlendiriyoruz (yeni syntax)
client_ai = instructor.from_genai(
    client=genai.Client(api_key=GEMINI_KEY),
    mode=instructor.Mode.GEMINI_JSON,
)

# --- VERİ MODELİ (AI ÇIKTISI İÇİN) ---
class MarketReport(BaseModel):
    trend: str = Field(description="Genel piyasa yönü: 'YÜKSELİŞ', 'DÜŞÜŞ' veya 'YATAY'")
    risk_score: int = Field(description="1 (Çok Güvenli) ile 10 (Çok Riskli) arası risk puanı")
    recommendation: str = Field(description="Yatırımcıya tavsiye: 'AL', 'SAT', 'BEKLE'")
    brief_reason: str = Field(description="Analizin 1 cümlelik özeti.")

# --- MANUEL TEKNİK İNDİKATÖRLER ---

def calculate_rsi(prices, period=14):
    """RSI hesaplama (pandas ile)"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_sma(prices, period=50):
    """Basit Hareketli Ortalama"""
    return prices.rolling(window=period).mean()

def calculate_ema(prices, period=20):
    """Üstel Hareketli Ortalama"""
    return prices.ewm(span=period, adjust=False).mean()

# --- FONKSİYONLAR ---

def get_technical_data(symbol):
    """
    Fiyatı çeker ve RSI, SMA gibi indikatörleri hesaplar.
    """
    try:
        # CoinCap coin ID'leri
        coin_map = {
            'BTC/USDT': 'bitcoin',
            'ETH/USDT': 'ethereum'
        }
        coin_id = coin_map.get(symbol)
        
        if not coin_id:
            print(f"Coin bulunamadı: {symbol}")
            return None
        
        # CoinCap'ten saatlik veri (ücretsiz, API key gereksiz)
        url = f"https://api.coincap.io/v2/assets/{coin_id}/history"
        params = {'interval': 'h1'}  # 1 saatlik
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            print(f"CoinCap hatası: {response.status_code}")
            print(f"Response: {response.text}")
            return None
        
        data = response.json()['data']
        
        # DataFrame oluştur
        prices = [float(d['priceUsd']) for d in data[-100:]]  # Son 100 saat
        df = pd.DataFrame({'close': prices})
        df['volume'] = 1000000  # Volume verisi yok, sabit değer
        
        # Teknik İndikatörler
        df['rsi'] = calculate_rsi(df['close'], period=14)
        df['sma_50'] = calculate_sma(df['close'], period=50)
        df['ema_20'] = calculate_ema(df['close'], period=20)
        
        last_row = df.iloc[-1]
        
        return {
            "price": float(last_row['close']),
            "rsi": round(float(last_row['rsi']), 2) if not pd.isna(last_row['rsi']) else 50,
            "sma_50": round(float(last_row['sma_50']), 2) if not pd.isna(last_row['sma_50']) else last_row['close'],
            "price_vs_sma": "Üstünde" if last_row['close'] > last_row['sma_50'] else "Altında",
            "volume_change": "Normal"  # Volume verisi yok
        }
    except Exception as e:
        print(f"Veri hatası ({symbol}): {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_market(symbol, tech_data):
    """
    Teknik verileri AI'a yorumlatır.
    """
    prompt = f"""
    Sen uzman bir kripto türev analistisin. {symbol} paritesi için aşağıdaki teknik verileri analiz et.
    
    GÜNCEL VERİLER:
    - Fiyat: {tech_data['price']}
    - RSI (14): {tech_data['rsi']} (30 altı aşırı satım, 70 üstü aşırı alım)
    - 50 Günlük Ort (SMA): {tech_data['sma_50']} (Fiyat bunun {tech_data['price_vs_sma']})
    - Hacim Durumu: {tech_data['volume_change']}
    
    GÖREV:
    Bu verilere dayanarak kısa vadeli (1-4 saat) bir yön tahmini yap.
    Duygusal olma, sadece sayılara bak.
    """
    
    try:
        return client_ai.messages.create(
            messages=[{"role": "user", "content": prompt}],
            response_model=MarketReport,
        )
    except Exception as e:
        print(f"AI Hatası: {e}")
        return None

def send_telegram(msg, with_button=False):
    """Telegram'a mesaj gönder, opsiyonel butonla"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": msg, 
        "parse_mode": "Markdown"
    }
    
    # Buton ekle (inline keyboard)
    if with_button:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "📊 Piyasa Raporu", "callback_data": "get_report"}]
            ]
        }
    
    requests.post(url, json=payload)

def save_to_db(symbol, tech_data, analysis: MarketReport):
    data = {
        "symbol": symbol,
        "price": tech_data['price'],
        "trend": analysis.trend,
        "risk_score": analysis.risk_score,
        "ai_comment": analysis.brief_reason,
        "technical_data": tech_data
    }
    supabase.table('market_analysis').insert(data).execute()

# --- ANA DÖNGÜ ---
if __name__ == "__main__":
    print("🚀 Analiz Başlıyor...")
    
    full_report = "📊 *Piyasa Raporu*\n\n"
    
    for symbol in SYMBOLS:
        print(f"İnceleniyor: {symbol}")
        tech = get_technical_data(symbol)
        
        if tech:
            analysis = analyze_market(symbol, tech)
            if analysis:
                save_to_db(symbol, tech, analysis)
                
                # Sinyal ikonu belirle
                icon = "🟢" if analysis.recommendation == "AL" else "🔴" if analysis.recommendation == "SAT" else "⚪"
                
                full_report += f"*{symbol}*\n"
                full_report += f"💰 Fiyat: ${tech['price']:,.2f}\n"
                full_report += f"{icon} Sinyal: *{analysis.recommendation}* (Risk: {analysis.risk_score}/10)\n"
                full_report += f"📈 RSI: {tech['rsi']}\n"
                full_report += f"💬 _{analysis.brief_reason}_\n\n"
    
    full_report += f"⏰ Son Güncelleme: {pd.Timestamp.now().strftime('%H:%M')}"
    
    # Raporu Telegram'a gönder (butonlu)
    send_telegram(full_report, with_button=True)

    print("✅ İşlem Tamam.")
