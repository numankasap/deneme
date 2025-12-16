#!/usr/bin/env python3
"""
📈 BIST 100 KAPSAMLI ANALİZ BOTU v2.0
=====================================
Borsa İstanbul için Gelişmiş Teknik ve Temel Analiz Botu

YENİ ÖZELLİKLER v2.0:
💰 GELİŞMİŞ TEMEL ANALİZ:
- Bilanço verileri analizi (son 4 çeyrek karşılaştırma)
- Gelir tablosu trend analizi
- Nakit akış analizi
- 25+ finansal oran hesaplama
- Şirket sağlık skoru (A'dan F'e)
- Ucuz/Pahalı değerlendirmesi
- Sektör karşılaştırması

📊 FİNANSAL ORANLAR:
- Karlılık: ROE, ROA, Net Kar Marjı, Brüt Kar Marjı
- Likidite: Cari Oran, Asit-Test Oranı, Nakit Oranı
- Borçluluk: Borç/Özkaynak, Borç/Aktif, Faiz Karşılama
- Verimlilik: Aktif Devir Hızı, Stok Devir Hızı
- Değerleme: F/K, PD/DD, FD/FAVÖK, F/S

⚠️ UYARI: Bu bot eğitim amaçlıdır, yatırım tavsiyesi içermez!
"""

import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
import time

# ══════════════════════════════════════════════════════════════════════════════
# API ANAHTARLARI
# ══════════════════════════════════════════════════════════════════════════════

GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

try:
    from google import genai
except ImportError:
    genai = None

# ══════════════════════════════════════════════════════════════════════════════
# BIST 100 HİSSE LİSTESİ VE SEKTÖRLER
# ══════════════════════════════════════════════════════════════════════════════

BIST100_STOCKS = [
    # Bankalar
    "AKBNK.IS", "GARAN.IS", "ISCTR.IS", "YKBNK.IS", "HALKB.IS", "VAKBN.IS",
    "QNBFB.IS", "TSKB.IS", "ALBRK.IS",
    # Holdingler
    "SAHOL.IS", "KCHOL.IS", "DOHOL.IS", "TAVHL.IS", "AGHOL.IS",
    # Sanayi
    "THYAO.IS", "ASELS.IS", "TOASO.IS", "FROTO.IS", "OTKAR.IS",
    "TUPRS.IS", "PETKM.IS", "SISE.IS", "EREGL.IS", "KRDMD.IS",
    # Perakende & Tüketim
    "BIMAS.IS", "MGROS.IS", "SOKM.IS", "ULKER.IS", "CCOLA.IS",
    "AEFES.IS", "MAVI.IS",
    # Teknoloji & İletişim
    "TCELL.IS", "TTKOM.IS", "NETAS.IS", "LOGO.IS", "INDES.IS",
    # Enerji
    "AKSEN.IS", "ENKAI.IS", "ODAS.IS", "AKENR.IS", "ZOREN.IS",
    # Diğer
    "KORDS.IS", "ARCLK.IS", "VESTL.IS", "KOZAL.IS", "KOZAA.IS",
    "PGSUS.IS", "CIMSA.IS", "AKCNS.IS", "TTRAK.IS", "BRYAT.IS",
]

# Sektör sınıflandırması ve benchmark değerleri
SECTOR_BENCHMARKS = {
    "Bankacılık": {
        "stocks": ["AKBNK.IS", "GARAN.IS", "ISCTR.IS", "YKBNK.IS", "HALKB.IS", "VAKBN.IS"],
        "avg_pe": 5.0, "avg_pb": 0.8, "avg_roe": 15.0
    },
    "Holding": {
        "stocks": ["SAHOL.IS", "KCHOL.IS", "DOHOL.IS", "TAVHL.IS"],
        "avg_pe": 8.0, "avg_pb": 1.2, "avg_roe": 12.0
    },
    "Havacılık": {
        "stocks": ["THYAO.IS", "PGSUS.IS"],
        "avg_pe": 6.0, "avg_pb": 2.0, "avg_roe": 25.0
    },
    "Otomotiv": {
        "stocks": ["TOASO.IS", "FROTO.IS", "OTKAR.IS"],
        "avg_pe": 8.0, "avg_pb": 2.5, "avg_roe": 20.0
    },
    "Savunma": {
        "stocks": ["ASELS.IS"],
        "avg_pe": 15.0, "avg_pb": 4.0, "avg_roe": 18.0
    },
    "Enerji": {
        "stocks": ["TUPRS.IS", "AKSEN.IS", "ENKAI.IS", "PETKM.IS"],
        "avg_pe": 6.0, "avg_pb": 1.5, "avg_roe": 15.0
    },
    "Perakende": {
        "stocks": ["BIMAS.IS", "MGROS.IS", "SOKM.IS"],
        "avg_pe": 12.0, "avg_pb": 3.0, "avg_roe": 20.0
    },
    "Telekomünikasyon": {
        "stocks": ["TCELL.IS", "TTKOM.IS"],
        "avg_pe": 8.0, "avg_pb": 2.0, "avg_roe": 15.0
    },
    "Demir-Çelik": {
        "stocks": ["EREGL.IS", "KRDMD.IS"],
        "avg_pe": 5.0, "avg_pb": 1.0, "avg_roe": 12.0
    },
    "Teknoloji": {
        "stocks": ["LOGO.IS", "INDES.IS", "NETAS.IS"],
        "avg_pe": 15.0, "avg_pb": 3.5, "avg_roe": 18.0
    },
    "Beyaz Eşya": {
        "stocks": ["ARCLK.IS", "VESTL.IS"],
        "avg_pe": 10.0, "avg_pb": 2.0, "avg_roe": 15.0
    },
    "Madencilik": {
        "stocks": ["KOZAL.IS", "KOZAA.IS"],
        "avg_pe": 8.0, "avg_pb": 2.5, "avg_roe": 20.0
    },
}

def get_stock_sector(symbol: str) -> str:
    """Hissenin sektörünü bul"""
    for sector, data in SECTOR_BENCHMARKS.items():
        if symbol in data["stocks"]:
            return sector
    return "Diğer"

# ══════════════════════════════════════════════════════════════════════════════
# TEKNİK ANALİZ FONKSİYONLARI
# ══════════════════════════════════════════════════════════════════════════════

def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """RSI hesapla"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD hesapla"""
    ema_fast = data.ewm(span=fast, adjust=False).mean()
    ema_slow = data.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(data: pd.Series, period: int = 20, std_dev: int = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bantları"""
    sma = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    return sma + (std_dev * std), sma, sma - (std_dev * std)

def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """Stokastik"""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    stoch_k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    stoch_d = stoch_k.rolling(window=d_period).mean()
    return stoch_k, stoch_d

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR"""
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# ══════════════════════════════════════════════════════════════════════════════
# GELİŞMİŞ TEMEL ANALİZ FONKSİYONLARI
# ══════════════════════════════════════════════════════════════════════════════

def get_financial_statements(symbol: str) -> Dict:
    """Finansal tabloları çek (Bilanço, Gelir Tablosu, Nakit Akış)"""
    try:
        stock = yf.Ticker(symbol)
        
        # Yıllık veriler
        balance_sheet = stock.balance_sheet
        income_stmt = stock.income_stmt
        cash_flow = stock.cashflow
        
        # Çeyreklik veriler
        quarterly_balance = stock.quarterly_balance_sheet
        quarterly_income = stock.quarterly_income_stmt
        quarterly_cashflow = stock.quarterly_cashflow
        
        return {
            'balance_sheet': balance_sheet,
            'income_stmt': income_stmt,
            'cash_flow': cash_flow,
            'quarterly_balance': quarterly_balance,
            'quarterly_income': quarterly_income,
            'quarterly_cashflow': quarterly_cashflow,
            'info': stock.info
        }
    except Exception as e:
        print(f"Finansal veri hatası ({symbol}): {e}")
        return {}

def safe_get(data: pd.DataFrame, key: str, period: int = 0) -> float:
    """DataFrame'den güvenli veri çekme"""
    try:
        if data is None or data.empty:
            return 0.0
        if key in data.index:
            val = data.iloc[:, period].get(key, 0)
            return float(val) if pd.notna(val) else 0.0
        return 0.0
    except:
        return 0.0

def calculate_profitability_ratios(financials: Dict) -> Dict:
    """Karlılık oranları hesapla"""
    ratios = {}
    
    try:
        income = financials.get('quarterly_income')
        balance = financials.get('quarterly_balance')
        info = financials.get('info', {})
        
        if income is None or income.empty:
            return ratios
        
        # Net Kar
        net_income = safe_get(income, 'Net Income')
        net_income_prev = safe_get(income, 'Net Income', 1)
        
        # Gelirler
        total_revenue = safe_get(income, 'Total Revenue')
        total_revenue_prev = safe_get(income, 'Total Revenue', 1)
        gross_profit = safe_get(income, 'Gross Profit')
        operating_income = safe_get(income, 'Operating Income')
        ebitda = safe_get(income, 'EBITDA')
        
        # Bilanço kalemleri
        total_assets = safe_get(balance, 'Total Assets') if balance is not None else 0
        total_assets_prev = safe_get(balance, 'Total Assets', 1) if balance is not None else 0
        total_equity = safe_get(balance, 'Stockholders Equity') if balance is not None else 0
        total_equity_prev = safe_get(balance, 'Stockholders Equity', 1) if balance is not None else 0
        
        # Ortalamalar (daha doğru hesaplama için)
        avg_assets = (total_assets + total_assets_prev) / 2 if total_assets_prev else total_assets
        avg_equity = (total_equity + total_equity_prev) / 2 if total_equity_prev else total_equity
        
        # KARLILIK ORANLARI
        
        # ROE (Özkaynak Karlılığı) - %15+ iyi
        if avg_equity > 0:
            ratios['roe'] = (net_income / avg_equity) * 100 * 4  # Yıllıklandır
        
        # ROA (Aktif Karlılığı) - %5+ iyi
        if avg_assets > 0:
            ratios['roa'] = (net_income / avg_assets) * 100 * 4
        
        # Net Kar Marjı - Sektöre göre değişir, %10+ genelde iyi
        if total_revenue > 0:
            ratios['net_profit_margin'] = (net_income / total_revenue) * 100
        
        # Brüt Kar Marjı - %20+ iyi
        if total_revenue > 0:
            ratios['gross_profit_margin'] = (gross_profit / total_revenue) * 100
        
        # Faaliyet Kar Marjı - %10+ iyi
        if total_revenue > 0:
            ratios['operating_margin'] = (operating_income / total_revenue) * 100
        
        # FAVÖK Marjı
        if total_revenue > 0 and ebitda > 0:
            ratios['ebitda_margin'] = (ebitda / total_revenue) * 100
        
        # Kar Büyümesi (QoQ)
        if net_income_prev != 0:
            ratios['profit_growth_qoq'] = ((net_income - net_income_prev) / abs(net_income_prev)) * 100
        
        # Gelir Büyümesi (QoQ)
        if total_revenue_prev > 0:
            ratios['revenue_growth_qoq'] = ((total_revenue - total_revenue_prev) / total_revenue_prev) * 100
        
    except Exception as e:
        print(f"Karlılık oranı hatası: {e}")
    
    return ratios

def calculate_liquidity_ratios(financials: Dict) -> Dict:
    """Likidite oranları hesapla"""
    ratios = {}
    
    try:
        balance = financials.get('quarterly_balance')
        if balance is None or balance.empty:
            return ratios
        
        # Dönen Varlıklar
        current_assets = safe_get(balance, 'Current Assets')
        cash = safe_get(balance, 'Cash And Cash Equivalents')
        receivables = safe_get(balance, 'Accounts Receivable')
        inventory = safe_get(balance, 'Inventory')
        
        # Kısa Vadeli Borçlar
        current_liabilities = safe_get(balance, 'Current Liabilities')
        
        # CARİ ORAN (Current Ratio) - 1.5-2.0 arası ideal
        if current_liabilities > 0:
            ratios['current_ratio'] = current_assets / current_liabilities
        
        # ASİT-TEST ORANI (Quick Ratio) - 1.0+ iyi
        if current_liabilities > 0:
            quick_assets = current_assets - inventory
            ratios['quick_ratio'] = quick_assets / current_liabilities
        
        # NAKİT ORANI (Cash Ratio) - 0.5+ iyi
        if current_liabilities > 0:
            ratios['cash_ratio'] = cash / current_liabilities
        
        # İşletme Sermayesi
        ratios['working_capital'] = current_assets - current_liabilities
        
    except Exception as e:
        print(f"Likidite oranı hatası: {e}")
    
    return ratios

def calculate_leverage_ratios(financials: Dict) -> Dict:
    """Borçluluk/Kaldıraç oranları hesapla"""
    ratios = {}
    
    try:
        balance = financials.get('quarterly_balance')
        income = financials.get('quarterly_income')
        
        if balance is None or balance.empty:
            return ratios
        
        # Bilanço kalemleri
        total_assets = safe_get(balance, 'Total Assets')
        total_debt = safe_get(balance, 'Total Debt')
        total_liabilities = safe_get(balance, 'Total Liabilities Net Minority Interest')
        total_equity = safe_get(balance, 'Stockholders Equity')
        long_term_debt = safe_get(balance, 'Long Term Debt')
        short_term_debt = safe_get(balance, 'Current Debt')
        
        # Gelir tablosu
        operating_income = safe_get(income, 'Operating Income') if income is not None else 0
        interest_expense = safe_get(income, 'Interest Expense') if income is not None else 0
        ebitda = safe_get(income, 'EBITDA') if income is not None else 0
        
        # BORÇ/ÖZKAYNAK ORANI - 1.0 altı iyi, 2.0+ riskli
        if total_equity > 0:
            ratios['debt_to_equity'] = total_debt / total_equity
        
        # BORÇ/AKTİF ORANI - %50 altı iyi
        if total_assets > 0:
            ratios['debt_to_assets'] = (total_debt / total_assets) * 100
        
        # TOPLAM BORÇ/AKTİF
        if total_assets > 0:
            ratios['total_liabilities_to_assets'] = (total_liabilities / total_assets) * 100
        
        # FAİZ KARŞILAMA ORANI - 3.0+ iyi
        if interest_expense > 0:
            ratios['interest_coverage'] = operating_income / abs(interest_expense)
        
        # NET BORÇ/FAVÖK - 3.0 altı iyi
        if ebitda > 0:
            cash = safe_get(balance, 'Cash And Cash Equivalents')
            net_debt = total_debt - cash
            ratios['net_debt_to_ebitda'] = net_debt / (ebitda * 4)  # Yıllıklandır
        
        # Finansal Kaldıraç
        if total_equity > 0:
            ratios['financial_leverage'] = total_assets / total_equity
        
    except Exception as e:
        print(f"Kaldıraç oranı hatası: {e}")
    
    return ratios

def calculate_efficiency_ratios(financials: Dict) -> Dict:
    """Verimlilik/Faaliyet oranları hesapla"""
    ratios = {}
    
    try:
        balance = financials.get('quarterly_balance')
        income = financials.get('quarterly_income')
        
        if balance is None or income is None:
            return ratios
        
        # Gelir tablosu
        total_revenue = safe_get(income, 'Total Revenue')
        cost_of_revenue = safe_get(income, 'Cost Of Revenue')
        
        # Bilanço
        total_assets = safe_get(balance, 'Total Assets')
        inventory = safe_get(balance, 'Inventory')
        receivables = safe_get(balance, 'Accounts Receivable')
        payables = safe_get(balance, 'Accounts Payable')
        fixed_assets = safe_get(balance, 'Net PPE')
        
        # AKTİF DEVİR HIZI - Yüksek iyi
        if total_assets > 0:
            ratios['asset_turnover'] = (total_revenue * 4) / total_assets  # Yıllıklandır
        
        # STOK DEVİR HIZI - Yüksek iyi (sektöre göre)
        if inventory > 0 and cost_of_revenue > 0:
            ratios['inventory_turnover'] = (cost_of_revenue * 4) / inventory
            ratios['days_inventory'] = 365 / ratios['inventory_turnover']
        
        # ALACAK DEVİR HIZI
        if receivables > 0:
            ratios['receivables_turnover'] = (total_revenue * 4) / receivables
            ratios['days_receivables'] = 365 / ratios['receivables_turnover']
        
        # BORÇ DEVİR HIZI
        if payables > 0 and cost_of_revenue > 0:
            ratios['payables_turnover'] = (cost_of_revenue * 4) / payables
            ratios['days_payables'] = 365 / ratios['payables_turnover']
        
        # NAKİT DÖNÜŞÜM SÜRESİ (Cash Conversion Cycle) - Düşük iyi
        if 'days_inventory' in ratios and 'days_receivables' in ratios and 'days_payables' in ratios:
            ratios['cash_conversion_cycle'] = ratios['days_inventory'] + ratios['days_receivables'] - ratios['days_payables']
        
    except Exception as e:
        print(f"Verimlilik oranı hatası: {e}")
    
    return ratios

def calculate_valuation_ratios(financials: Dict, current_price: float) -> Dict:
    """Değerleme oranları hesapla"""
    ratios = {}
    
    try:
        info = financials.get('info', {})
        balance = financials.get('quarterly_balance')
        income = financials.get('quarterly_income')
        
        # Info'dan direkt değerler
        market_cap = info.get('marketCap', 0)
        shares_outstanding = info.get('sharesOutstanding', 0)
        
        # Hesaplanmış değerler
        if income is not None and not income.empty:
            net_income = safe_get(income, 'Net Income') * 4  # Yıllıklandır
            total_revenue = safe_get(income, 'Total Revenue') * 4
            ebitda = safe_get(income, 'EBITDA') * 4
        else:
            net_income = total_revenue = ebitda = 0
        
        if balance is not None and not balance.empty:
            book_value = safe_get(balance, 'Stockholders Equity')
            total_debt = safe_get(balance, 'Total Debt')
            cash = safe_get(balance, 'Cash And Cash Equivalents')
        else:
            book_value = total_debt = cash = 0
        
        # F/K (P/E Ratio) - Sektöre göre, genelde 10-15 makul
        pe_ratio = info.get('trailingPE') or info.get('forwardPE')
        if pe_ratio:
            ratios['pe_ratio'] = pe_ratio
        elif market_cap > 0 and net_income > 0:
            ratios['pe_ratio'] = market_cap / net_income
        
        # PD/DD (P/B Ratio) - 1.0 altı ucuz olabilir
        pb_ratio = info.get('priceToBook')
        if pb_ratio:
            ratios['pb_ratio'] = pb_ratio
        elif market_cap > 0 and book_value > 0:
            ratios['pb_ratio'] = market_cap / book_value
        
        # F/S (P/S Ratio) - Düşük iyi
        ps_ratio = info.get('priceToSalesTrailing12Months')
        if ps_ratio:
            ratios['ps_ratio'] = ps_ratio
        elif market_cap > 0 and total_revenue > 0:
            ratios['ps_ratio'] = market_cap / total_revenue
        
        # FD/FAVÖK (EV/EBITDA) - 8-12 arası makul
        enterprise_value = info.get('enterpriseValue')
        if not enterprise_value and market_cap > 0:
            enterprise_value = market_cap + total_debt - cash
        
        if enterprise_value and ebitda > 0:
            ratios['ev_to_ebitda'] = enterprise_value / ebitda
        
        # HBK (EPS) - Hisse Başı Kar
        if shares_outstanding > 0 and net_income > 0:
            ratios['eps'] = net_income / shares_outstanding
        
        # Temettü Verimi
        dividend_yield = info.get('dividendYield')
        if dividend_yield:
            ratios['dividend_yield'] = dividend_yield * 100
        
        # PEG Ratio (Büyüme dahil F/K)
        peg = info.get('pegRatio')
        if peg:
            ratios['peg_ratio'] = peg
        
    except Exception as e:
        print(f"Değerleme oranı hatası: {e}")
    
    return ratios

def analyze_balance_sheet_trend(financials: Dict) -> Dict:
    """Bilanço trend analizi - son 4 çeyrek karşılaştırma"""
    trend = {
        'asset_growth': [],
        'equity_growth': [],
        'debt_trend': [],
        'cash_trend': [],
        'analysis': []
    }
    
    try:
        balance = financials.get('quarterly_balance')
        if balance is None or balance.empty or len(balance.columns) < 2:
            return trend
        
        periods = min(4, len(balance.columns))
        
        for i in range(periods):
            assets = safe_get(balance, 'Total Assets', i)
            equity = safe_get(balance, 'Stockholders Equity', i)
            debt = safe_get(balance, 'Total Debt', i)
            cash = safe_get(balance, 'Cash And Cash Equivalents', i)
            
            trend['asset_growth'].append(assets)
            trend['equity_growth'].append(equity)
            trend['debt_trend'].append(debt)
            trend['cash_trend'].append(cash)
        
        # Trend analizi
        if len(trend['asset_growth']) >= 2:
            latest_assets = trend['asset_growth'][0]
            oldest_assets = trend['asset_growth'][-1]
            
            if oldest_assets > 0:
                asset_change = ((latest_assets - oldest_assets) / oldest_assets) * 100
                if asset_change > 10:
                    trend['analysis'].append("📈 Aktifler büyüyor")
                elif asset_change < -10:
                    trend['analysis'].append("📉 Aktifler azalıyor")
            
            latest_equity = trend['equity_growth'][0]
            oldest_equity = trend['equity_growth'][-1]
            
            if oldest_equity > 0:
                equity_change = ((latest_equity - oldest_equity) / oldest_equity) * 100
                if equity_change > 10:
                    trend['analysis'].append("📈 Özkaynak büyüyor")
                elif equity_change < -10:
                    trend['analysis'].append("📉 Özkaynak eriyor ⚠️")
            
            latest_debt = trend['debt_trend'][0]
            oldest_debt = trend['debt_trend'][-1]
            
            if oldest_debt > 0:
                debt_change = ((latest_debt - oldest_debt) / oldest_debt) * 100
                if debt_change > 20:
                    trend['analysis'].append("⚠️ Borç hızla artıyor")
                elif debt_change < -10:
                    trend['analysis'].append("✅ Borç azalıyor")
            
            # Borç/Özkaynak trendi
            if latest_equity > 0 and oldest_equity > 0:
                latest_de = latest_debt / latest_equity
                oldest_de = oldest_debt / oldest_equity
                if latest_de > oldest_de * 1.2:
                    trend['analysis'].append("⚠️ Kaldıraç artıyor")
                elif latest_de < oldest_de * 0.8:
                    trend['analysis'].append("✅ Kaldıraç düşüyor")
        
    except Exception as e:
        print(f"Bilanço trend hatası: {e}")
    
    return trend

def analyze_income_trend(financials: Dict) -> Dict:
    """Gelir tablosu trend analizi"""
    trend = {
        'revenue_trend': [],
        'profit_trend': [],
        'margin_trend': [],
        'analysis': []
    }
    
    try:
        income = financials.get('quarterly_income')
        if income is None or income.empty or len(income.columns) < 2:
            return trend
        
        periods = min(4, len(income.columns))
        
        for i in range(periods):
            revenue = safe_get(income, 'Total Revenue', i)
            net_income = safe_get(income, 'Net Income', i)
            
            trend['revenue_trend'].append(revenue)
            trend['profit_trend'].append(net_income)
            
            if revenue > 0:
                margin = (net_income / revenue) * 100
                trend['margin_trend'].append(margin)
        
        # Analiz
        if len(trend['revenue_trend']) >= 2:
            latest_rev = trend['revenue_trend'][0]
            prev_rev = trend['revenue_trend'][1]
            
            if prev_rev > 0:
                rev_growth = ((latest_rev - prev_rev) / prev_rev) * 100
                if rev_growth > 15:
                    trend['analysis'].append(f"🚀 Güçlü gelir büyümesi: %{rev_growth:.1f}")
                elif rev_growth > 5:
                    trend['analysis'].append(f"📈 Gelir büyüyor: %{rev_growth:.1f}")
                elif rev_growth < -5:
                    trend['analysis'].append(f"📉 Gelir düşüyor: %{rev_growth:.1f}")
        
        if len(trend['profit_trend']) >= 2:
            latest_profit = trend['profit_trend'][0]
            prev_profit = trend['profit_trend'][1]
            
            if prev_profit != 0:
                profit_growth = ((latest_profit - prev_profit) / abs(prev_profit)) * 100
                if latest_profit > 0 and prev_profit < 0:
                    trend['analysis'].append("🎉 Kara geçiş!")
                elif latest_profit < 0 and prev_profit > 0:
                    trend['analysis'].append("⚠️ Zarara geçiş!")
                elif profit_growth > 20:
                    trend['analysis'].append(f"🚀 Güçlü kar büyümesi: %{profit_growth:.1f}")
                elif profit_growth < -20:
                    trend['analysis'].append(f"📉 Kar düşüyor: %{profit_growth:.1f}")
        
        # Marj trendi
        if len(trend['margin_trend']) >= 2:
            latest_margin = trend['margin_trend'][0]
            oldest_margin = trend['margin_trend'][-1]
            
            if latest_margin > oldest_margin + 2:
                trend['analysis'].append("📈 Kar marjı iyileşiyor")
            elif latest_margin < oldest_margin - 2:
                trend['analysis'].append("📉 Kar marjı daralıyor")
        
    except Exception as e:
        print(f"Gelir trend hatası: {e}")
    
    return trend

def calculate_company_health_score(profitability: Dict, liquidity: Dict, leverage: Dict, efficiency: Dict, valuation: Dict) -> Dict:
    """Şirket sağlık skoru hesapla (A'dan F'e)"""
    score = 0
    max_score = 0
    details = []
    
    # KARLILIK (30 puan)
    max_score += 30
    
    roe = profitability.get('roe', 0)
    if roe > 20:
        score += 10
        details.append("✅ ROE mükemmel (>20%)")
    elif roe > 15:
        score += 8
        details.append("✅ ROE iyi (>15%)")
    elif roe > 10:
        score += 5
        details.append("🟡 ROE orta (>10%)")
    elif roe > 0:
        score += 2
        details.append("🟠 ROE düşük")
    else:
        details.append("❌ ROE negatif")
    
    net_margin = profitability.get('net_profit_margin', 0)
    if net_margin > 15:
        score += 10
        details.append("✅ Kar marjı yüksek")
    elif net_margin > 8:
        score += 7
        details.append("✅ Kar marjı iyi")
    elif net_margin > 3:
        score += 4
        details.append("🟡 Kar marjı orta")
    elif net_margin > 0:
        score += 1
        details.append("🟠 Kar marjı düşük")
    else:
        details.append("❌ Zarar ediyor")
    
    profit_growth = profitability.get('profit_growth_qoq', 0)
    if profit_growth > 20:
        score += 10
        details.append("🚀 Kar büyümesi güçlü")
    elif profit_growth > 5:
        score += 7
    elif profit_growth > 0:
        score += 4
    elif profit_growth > -10:
        score += 2
    
    # LİKİDİTE (20 puan)
    max_score += 20
    
    current_ratio = liquidity.get('current_ratio', 0)
    if 1.5 <= current_ratio <= 3.0:
        score += 10
        details.append("✅ Cari oran ideal")
    elif current_ratio >= 1.0:
        score += 6
        details.append("🟡 Cari oran kabul edilebilir")
    elif current_ratio > 0.5:
        score += 3
        details.append("🟠 Cari oran düşük")
    else:
        details.append("❌ Likidite riski")
    
    quick_ratio = liquidity.get('quick_ratio', 0)
    if quick_ratio >= 1.0:
        score += 10
        details.append("✅ Asit-test oranı iyi")
    elif quick_ratio >= 0.5:
        score += 5
    else:
        details.append("🟠 Hızlı likidite düşük")
    
    # BORÇLULUK (25 puan)
    max_score += 25
    
    debt_to_equity = leverage.get('debt_to_equity', 999)
    if debt_to_equity < 0.5:
        score += 15
        details.append("✅ Düşük borç seviyesi")
    elif debt_to_equity < 1.0:
        score += 10
        details.append("✅ Borç makul seviyede")
    elif debt_to_equity < 2.0:
        score += 5
        details.append("🟡 Borç yüksek")
    else:
        details.append("❌ Aşırı borçlu")
    
    interest_coverage = leverage.get('interest_coverage', 0)
    if interest_coverage > 5:
        score += 10
        details.append("✅ Faiz karşılama güçlü")
    elif interest_coverage > 2:
        score += 6
    elif interest_coverage > 1:
        score += 3
        details.append("🟠 Faiz karşılama zayıf")
    else:
        details.append("❌ Faiz karşılama riski")
    
    # VERİMLİLİK (15 puan)
    max_score += 15
    
    asset_turnover = efficiency.get('asset_turnover', 0)
    if asset_turnover > 1.5:
        score += 8
        details.append("✅ Aktif kullanımı verimli")
    elif asset_turnover > 0.8:
        score += 5
    elif asset_turnover > 0.3:
        score += 2
    
    ccc = efficiency.get('cash_conversion_cycle', 999)
    if ccc < 30:
        score += 7
        details.append("✅ Nakit döngüsü hızlı")
    elif ccc < 60:
        score += 5
    elif ccc < 90:
        score += 2
    
    # DEĞERLEME (10 puan)
    max_score += 10
    
    pe = valuation.get('pe_ratio', 0)
    if 0 < pe < 10:
        score += 5
        details.append("💰 F/K düşük (ucuz olabilir)")
    elif 10 <= pe <= 20:
        score += 3
        details.append("🟡 F/K makul")
    elif pe > 30:
        details.append("⚠️ F/K yüksek (pahalı olabilir)")
    
    pb = valuation.get('pb_ratio', 0)
    if 0 < pb < 1:
        score += 5
        details.append("💰 PD/DD düşük (ucuz olabilir)")
    elif 1 <= pb <= 3:
        score += 3
    elif pb > 5:
        details.append("⚠️ PD/DD yüksek")
    
    # Skor hesaplama
    percentage = (score / max_score) * 100 if max_score > 0 else 0
    
    if percentage >= 80:
        grade = "A"
        health_status = "🟢 Mükemmel"
    elif percentage >= 65:
        grade = "B"
        health_status = "🟢 İyi"
    elif percentage >= 50:
        grade = "C"
        health_status = "🟡 Orta"
    elif percentage >= 35:
        grade = "D"
        health_status = "🟠 Zayıf"
    else:
        grade = "F"
        health_status = "🔴 Riskli"
    
    return {
        'score': score,
        'max_score': max_score,
        'percentage': percentage,
        'grade': grade,
        'health_status': health_status,
        'details': details
    }

def evaluate_valuation(valuation: Dict, sector: str) -> Dict:
    """Hisse ucuz mu pahalı mı değerlendir"""
    evaluation = {
        'verdict': '',
        'confidence': '',
        'reasons': [],
        'score': 0  # -3 (çok pahalı) ile +3 (çok ucuz) arası
    }
    
    # Sektör ortalamaları
    sector_data = SECTOR_BENCHMARKS.get(sector, {
        'avg_pe': 10.0, 'avg_pb': 1.5, 'avg_roe': 15.0
    })
    
    pe = valuation.get('pe_ratio', 0)
    pb = valuation.get('pb_ratio', 0)
    ps = valuation.get('ps_ratio', 0)
    ev_ebitda = valuation.get('ev_to_ebitda', 0)
    peg = valuation.get('peg_ratio', 0)
    
    # F/K Analizi
    if pe > 0:
        sector_pe = sector_data.get('avg_pe', 10)
        if pe < sector_pe * 0.6:
            evaluation['score'] += 1
            evaluation['reasons'].append(f"✅ F/K ({pe:.1f}) sektör ortalamasının ({sector_pe}) çok altında")
        elif pe < sector_pe * 0.85:
            evaluation['score'] += 0.5
            evaluation['reasons'].append(f"✅ F/K ({pe:.1f}) sektör ortalamasının altında")
        elif pe > sector_pe * 1.5:
            evaluation['score'] -= 1
            evaluation['reasons'].append(f"⚠️ F/K ({pe:.1f}) sektör ortalamasının çok üstünde")
        elif pe > sector_pe * 1.15:
            evaluation['score'] -= 0.5
            evaluation['reasons'].append(f"🟡 F/K ({pe:.1f}) sektör ortalamasının üstünde")
    
    # PD/DD Analizi
    if pb > 0:
        sector_pb = sector_data.get('avg_pb', 1.5)
        if pb < 1.0:
            evaluation['score'] += 1
            evaluation['reasons'].append(f"✅ PD/DD ({pb:.2f}) defter değerinin altında (değer fırsatı)")
        elif pb < sector_pb * 0.7:
            evaluation['score'] += 0.5
            evaluation['reasons'].append(f"✅ PD/DD ({pb:.2f}) sektöre göre düşük")
        elif pb > sector_pb * 1.5:
            evaluation['score'] -= 0.5
            evaluation['reasons'].append(f"🟡 PD/DD ({pb:.2f}) sektöre göre yüksek")
    
    # FD/FAVÖK Analizi
    if ev_ebitda > 0:
        if ev_ebitda < 6:
            evaluation['score'] += 0.5
            evaluation['reasons'].append(f"✅ FD/FAVÖK ({ev_ebitda:.1f}) düşük")
        elif ev_ebitda > 15:
            evaluation['score'] -= 0.5
            evaluation['reasons'].append(f"⚠️ FD/FAVÖK ({ev_ebitda:.1f}) yüksek")
    
    # PEG Analizi
    if peg > 0:
        if peg < 1:
            evaluation['score'] += 0.5
            evaluation['reasons'].append(f"✅ PEG ({peg:.2f}) < 1 (büyümeye göre ucuz)")
        elif peg > 2:
            evaluation['score'] -= 0.5
            evaluation['reasons'].append(f"⚠️ PEG ({peg:.2f}) > 2 (büyümeye göre pahalı)")
    
    # Sonuç
    if evaluation['score'] >= 2:
        evaluation['verdict'] = "💰 UCUZ"
        evaluation['confidence'] = "Yüksek"
    elif evaluation['score'] >= 1:
        evaluation['verdict'] = "💚 UYGUN FİYATLI"
        evaluation['confidence'] = "Orta"
    elif evaluation['score'] >= -0.5:
        evaluation['verdict'] = "🟡 MAKUL FİYATLI"
        evaluation['confidence'] = "Orta"
    elif evaluation['score'] >= -1.5:
        evaluation['verdict'] = "🟠 BİRAZ PAHALI"
        evaluation['confidence'] = "Orta"
    else:
        evaluation['verdict'] = "🔴 PAHALI"
        evaluation['confidence'] = "Yüksek"
    
    return evaluation

# ══════════════════════════════════════════════════════════════════════════════
# KAPSAMLI HİSSE ANALİZİ
# ══════════════════════════════════════════════════════════════════════════════

def comprehensive_stock_analysis(symbol: str) -> Optional[Dict]:
    """Kapsamlı hisse analizi (Teknik + Temel)"""
    
    print(f"  📊 {symbol} analiz ediliyor...")
    
    # Fiyat verisi çek
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="6mo")
        if data.empty or len(data) < 50:
            return None
    except:
        return None
    
    close = data['Close']
    high = data['High']
    low = data['Low']
    volume = data['Volume']
    current_price = close.iloc[-1]
    
    # Finansal tablolar
    financials = get_financial_statements(symbol)
    
    # ══════════════════════════════════════════════════════════════════
    # TEKNİK ANALİZ - 12 GÖSTERGE
    # ══════════════════════════════════════════════════════════════════
    
    # 1. RSI (14)
    rsi = calculate_rsi(close)
    rsi_val = rsi.iloc[-1]
    
    # 2. MACD
    macd_line, signal_line, macd_hist = calculate_macd(close)
    
    # 3. Bollinger Bands
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close)
    
    # 4. Stokastik
    stoch_k, stoch_d = calculate_stochastic(high, low, close)
    
    # 5. ATR (Volatilite)
    atr = calculate_atr(high, low, close)
    atr_val = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
    atr_percent = (atr_val / current_price) * 100
    
    # 6. EMA 20
    ema_20 = close.ewm(span=20, adjust=False).mean()
    
    # 7. EMA 50
    ema_50 = close.ewm(span=50, adjust=False).mean()
    
    # 8. SMA 200
    sma_200 = close.rolling(window=200).mean() if len(close) >= 200 else close.rolling(window=100).mean()
    sma_200_val = sma_200.iloc[-1] if not pd.isna(sma_200.iloc[-1]) else ema_50.iloc[-1]
    
    # 9. ADX (Trend Gücü)
    try:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr_14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr_14)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(14).mean()
        adx_val = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0
    except:
        adx_val = 0
    
    # 10. CCI
    try:
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(20).mean()
        mean_dev = typical_price.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (typical_price - sma_tp) / (0.015 * mean_dev)
        cci_val = cci.iloc[-1] if not pd.isna(cci.iloc[-1]) else 0
    except:
        cci_val = 0
    
    # 11. SuperTrend (Basitleştirilmiş)
    try:
        atr_st = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0
        hl2 = (high + low) / 2
        upper_band = hl2 + (3 * atr)
        lower_band = hl2 - (3 * atr)
        supertrend_direction = 1 if current_price > lower_band.iloc[-1] else -1
    except:
        supertrend_direction = 0
    
    # 12. Destek / Direnç (Pivot)
    pivot = (high.iloc[-1] + low.iloc[-1] + close.iloc[-1]) / 3
    r1 = 2 * pivot - low.iloc[-1]
    s1 = 2 * pivot - high.iloc[-1]
    r2 = pivot + (high.iloc[-1] - low.iloc[-1])
    s2 = pivot - (high.iloc[-1] - low.iloc[-1])
    
    # Hacim analizi
    avg_volume = volume.tail(20).mean()
    current_volume = volume.iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
    
    # ══════════════════════════════════════════════════════════════════
    # TEKNİK SİNYAL HESAPLAMA
    # ══════════════════════════════════════════════════════════════════
    
    tech_score = 0
    tech_signals = []
    
    # RSI Sinyalleri
    if rsi_val < 30:
        tech_score += 2
        tech_signals.append("🟢 RSI aşırı satım (<30)")
    elif rsi_val < 40:
        tech_score += 1
        tech_signals.append("🟢 RSI düşük bölgede")
    elif rsi_val > 70:
        tech_score -= 2
        tech_signals.append("🔴 RSI aşırı alım (>70)")
    elif rsi_val > 60:
        tech_score -= 1
        tech_signals.append("🟡 RSI yüksek bölgede")
    
    # MACD Sinyalleri
    if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
        tech_score += 2
        tech_signals.append("🟢 MACD yukarı kesişim (AL)")
    elif macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
        tech_score -= 2
        tech_signals.append("🔴 MACD aşağı kesişim (SAT)")
    elif macd_line.iloc[-1] > signal_line.iloc[-1]:
        tech_score += 0.5
        tech_signals.append("🟢 MACD pozitif")
    else:
        tech_score -= 0.5
        tech_signals.append("🔴 MACD negatif")
    
    # Bollinger Band Sinyalleri
    if current_price <= bb_lower.iloc[-1]:
        tech_score += 1.5
        tech_signals.append("🟢 Fiyat alt BB'de (potansiyel AL)")
    elif current_price >= bb_upper.iloc[-1]:
        tech_score -= 1.5
        tech_signals.append("🔴 Fiyat üst BB'de (potansiyel SAT)")
    
    # Stokastik Sinyalleri
    stoch_k_val = stoch_k.iloc[-1]
    stoch_d_val = stoch_d.iloc[-1]
    if stoch_k_val < 20:
        tech_score += 1
        tech_signals.append("🟢 Stokastik aşırı satım")
    elif stoch_k_val > 80:
        tech_score -= 1
        tech_signals.append("🔴 Stokastik aşırı alım")
    
    # Stokastik kesişim
    if stoch_k_val > stoch_d_val and stoch_k.iloc[-2] <= stoch_d.iloc[-2]:
        tech_score += 1
        tech_signals.append("🟢 Stokastik yukarı kesişim")
    elif stoch_k_val < stoch_d_val and stoch_k.iloc[-2] >= stoch_d.iloc[-2]:
        tech_score -= 1
        tech_signals.append("🔴 Stokastik aşağı kesişim")
    
    # EMA Trend Sinyalleri
    if current_price > ema_20.iloc[-1] > ema_50.iloc[-1]:
        tech_score += 1
        tech_signals.append("🟢 Güçlü yükseliş trendi (Fiyat>EMA20>EMA50)")
    elif current_price < ema_20.iloc[-1] < ema_50.iloc[-1]:
        tech_score -= 1
        tech_signals.append("🔴 Güçlü düşüş trendi (Fiyat<EMA20<EMA50)")
    
    # EMA Kesişimleri
    if ema_20.iloc[-1] > ema_50.iloc[-1] and ema_20.iloc[-2] <= ema_50.iloc[-2]:
        tech_score += 2
        tech_signals.append("🟢 Altın Kesişim (EMA20 > EMA50)")
    elif ema_20.iloc[-1] < ema_50.iloc[-1] and ema_20.iloc[-2] >= ema_50.iloc[-2]:
        tech_score -= 2
        tech_signals.append("🔴 Ölüm Kesişimi (EMA20 < EMA50)")
    
    # SMA 200 (Uzun vade trend)
    if current_price > sma_200_val:
        tech_score += 0.5
        tech_signals.append("🟢 Fiyat SMA200 üzerinde (uzun vade yükseliş)")
    else:
        tech_score -= 0.5
        tech_signals.append("🔴 Fiyat SMA200 altında (uzun vade düşüş)")
    
    # ADX (Trend Gücü)
    if adx_val > 25:
        if current_price > ema_20.iloc[-1]:
            tech_signals.append(f"📊 Güçlü YÜKSELİŞ trendi (ADX: {adx_val:.0f})")
        else:
            tech_signals.append(f"📊 Güçlü DÜŞÜŞ trendi (ADX: {adx_val:.0f})")
    elif adx_val > 0:
        tech_signals.append(f"📊 Zayıf trend (ADX: {adx_val:.0f})")
    
    # CCI Sinyalleri
    if cci_val < -100:
        tech_score += 1
        tech_signals.append("🟢 CCI aşırı satım")
    elif cci_val > 100:
        tech_score -= 1
        tech_signals.append("🔴 CCI aşırı alım")
    
    # SuperTrend
    if supertrend_direction == 1:
        tech_score += 0.5
        tech_signals.append("🟢 SuperTrend yükseliş")
    elif supertrend_direction == -1:
        tech_score -= 0.5
        tech_signals.append("🔴 SuperTrend düşüş")
    
    # Hacim Sinyali
    if volume_ratio > 2:
        tech_signals.append(f"📈 Çok yüksek hacim ({volume_ratio:.1f}x)")
    elif volume_ratio > 1.5:
        tech_signals.append(f"📈 Yüksek hacim ({volume_ratio:.1f}x)")
    elif volume_ratio < 0.5:
        tech_signals.append(f"📉 Düşük hacim ({volume_ratio:.1f}x)")
    
    # Destek/Direnç Mesafesi
    dist_to_support = ((current_price - s1) / current_price) * 100
    dist_to_resistance = ((r1 - current_price) / current_price) * 100
    
    if dist_to_support < 2:
        tech_signals.append(f"📍 Desteğe yakın (S1: {s1:.2f})")
    if dist_to_resistance < 2:
        tech_signals.append(f"📍 Dirence yakın (R1: {r1:.2f})")
    
    # Genel teknik sinyal
    if tech_score >= 4:
        overall_tech = "🟢 GÜÇLÜ AL"
    elif tech_score >= 2:
        overall_tech = "🟢 AL"
    elif tech_score <= -4:
        overall_tech = "🔴 GÜÇLÜ SAT"
    elif tech_score <= -2:
        overall_tech = "🔴 SAT"
    else:
        overall_tech = "🟡 TUT"
    
    # ══════════════════════════════════════════════════════════════════
    # TEMEL ANALİZ
    # ══════════════════════════════════════════════════════════════════
    
    sector = get_stock_sector(symbol)
    
    profitability = calculate_profitability_ratios(financials)
    liquidity = calculate_liquidity_ratios(financials)
    leverage = calculate_leverage_ratios(financials)
    efficiency = calculate_efficiency_ratios(financials)
    valuation = calculate_valuation_ratios(financials, current_price)
    
    balance_trend = analyze_balance_sheet_trend(financials)
    income_trend = analyze_income_trend(financials)
    
    health = calculate_company_health_score(profitability, liquidity, leverage, efficiency, valuation)
    valuation_eval = evaluate_valuation(valuation, sector)
    
    # Genel değerlendirme
    info = financials.get('info', {})
    
    daily_change = ((current_price - close.iloc[-2]) / close.iloc[-2]) * 100
    
    return {
        'symbol': symbol.replace('.IS', ''),
        'company_name': info.get('longName', symbol.replace('.IS', '')),
        'sector': sector,
        'current_price': round(current_price, 2),
        'daily_change': round(daily_change, 2),
        
        # Teknik (12 Gösterge)
        'technical': {
            'rsi': round(rsi_val, 1),
            'macd': round(macd_line.iloc[-1], 4),
            'macd_signal': round(signal_line.iloc[-1], 4),
            'macd_hist': round(macd_hist.iloc[-1], 4),
            'stoch_k': round(stoch_k_val, 1),
            'stoch_d': round(stoch_d_val, 1),
            'ema_20': round(ema_20.iloc[-1], 2),
            'ema_50': round(ema_50.iloc[-1], 2),
            'sma_200': round(sma_200_val, 2),
            'bb_upper': round(bb_upper.iloc[-1], 2),
            'bb_middle': round(bb_middle.iloc[-1], 2),
            'bb_lower': round(bb_lower.iloc[-1], 2),
            'atr': round(atr_val, 2),
            'atr_percent': round(atr_percent, 2),
            'adx': round(adx_val, 1),
            'cci': round(cci_val, 1),
            'supertrend': supertrend_direction,
            'pivot': round(pivot, 2),
            'r1': round(r1, 2),
            'r2': round(r2, 2),
            's1': round(s1, 2),
            's2': round(s2, 2),
            'volume_ratio': round(volume_ratio, 2),
            'score': round(tech_score, 1),
            'overall_signal': overall_tech,
            'signals': tech_signals
        },
        
        # Temel
        'fundamental': {
            'profitability': profitability,
            'liquidity': liquidity,
            'leverage': leverage,
            'efficiency': efficiency,
            'valuation': valuation,
            'balance_trend': balance_trend,
            'income_trend': income_trend,
        },
        
        # Sağlık ve Değerleme
        'health': health,
        'valuation_eval': valuation_eval,
        
        # Info
        'market_cap': info.get('marketCap', 0),
        'fifty_two_week_high': info.get('fiftyTwoWeekHigh', 0),
        'fifty_two_week_low': info.get('fiftyTwoWeekLow', 0),
    }

# ══════════════════════════════════════════════════════════════════════════════
# AI ANALİZİ
# ══════════════════════════════════════════════════════════════════════════════

def generate_ai_fundamental_analysis(analysis: Dict) -> str:
    """AI ile kapsamlı temel analiz yorumu"""
    if not GEMINI_KEY or not genai:
        return ""
    
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        
        fund = analysis['fundamental']
        health = analysis['health']
        val_eval = analysis['valuation_eval']
        
        prompt = f"""Sen deneyimli bir finansal analist ve değer yatırımcısısın. Aşağıdaki şirket verilerini analiz et.

ŞİRKET: {analysis['symbol']} ({analysis.get('company_name', '')})
SEKTÖR: {analysis['sector']}
FİYAT: {analysis['current_price']} TL

═══ KARLILIK ═══
• ROE: {fund['profitability'].get('roe', 'N/A'):.1f}%
• ROA: {fund['profitability'].get('roa', 'N/A'):.1f}%
• Net Kar Marjı: {fund['profitability'].get('net_profit_margin', 'N/A'):.1f}%
• Kar Büyümesi (QoQ): {fund['profitability'].get('profit_growth_qoq', 'N/A'):.1f}%
• Gelir Büyümesi (QoQ): {fund['profitability'].get('revenue_growth_qoq', 'N/A'):.1f}%

═══ LİKİDİTE ═══
• Cari Oran: {fund['liquidity'].get('current_ratio', 'N/A'):.2f}
• Asit-Test: {fund['liquidity'].get('quick_ratio', 'N/A'):.2f}
• Nakit Oran: {fund['liquidity'].get('cash_ratio', 'N/A'):.2f}

═══ BORÇLULUK ═══
• Borç/Özkaynak: {fund['leverage'].get('debt_to_equity', 'N/A'):.2f}
• Faiz Karşılama: {fund['leverage'].get('interest_coverage', 'N/A'):.1f}x
• Net Borç/FAVÖK: {fund['leverage'].get('net_debt_to_ebitda', 'N/A'):.1f}

═══ DEĞERLEME ═══
• F/K: {fund['valuation'].get('pe_ratio', 'N/A')}
• PD/DD: {fund['valuation'].get('pb_ratio', 'N/A')}
• FD/FAVÖK: {fund['valuation'].get('ev_to_ebitda', 'N/A')}

═══ BİLANÇO TRENDİ ═══
{', '.join(fund['balance_trend'].get('analysis', ['Veri yok']))}

═══ GELİR TRENDİ ═══
{', '.join(fund['income_trend'].get('analysis', ['Veri yok']))}

═══ SAĞLIK SKORU ═══
Not: {health['grade']} ({health['percentage']:.0f}/100)
Durum: {health['health_status']}

═══ FİYAT DEĞERLENDİRMESİ ═══
Sonuç: {val_eval['verdict']}
Nedenler: {', '.join(val_eval['reasons'][:3])}

GÖREV: Yukarıdaki verileri analiz ederek Türkçe kısa ve öz bir rapor hazırla:

1. 📊 BİLANÇO SAĞLIĞI (2 cümle)
   - Aktif kalitesi, borç durumu, özkaynak yapısı
   
2. 💰 KARLILIK DEĞERLENDİRMESİ (2 cümle)
   - Karlılık trendi, marjlar, büyüme
   
3. 💵 UCUZ MU PAHALI MI? (2 cümle)
   - Değerleme çarpanları analizi
   - Sektör karşılaştırması
   
4. ⚠️ RİSKLER (1-2 madde)
   
5. 🎯 SONUÇ (1 cümle)
   - Genel değerlendirme

NOT: Yatırım tavsiyesi değildir. Profesyonel ve özlü ol."""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"AI analiz hatası: {e}")
        return ""

# ══════════════════════════════════════════════════════════════════════════════
# RAPOR OLUŞTURMA
# ══════════════════════════════════════════════════════════════════════════════

def generate_comprehensive_report(stock_count: int = 20) -> str:
    """Kapsamlı analiz raporu oluştur"""
    report = []
    
    today = datetime.now()
    report.append("═" * 55)
    report.append("📈 BIST 100 KAPSAMLI ANALİZ RAPORU v2.1")
    report.append(f"📅 {today.strftime('%d %B %Y, %A')}")
    report.append("═" * 55)
    report.append("")
    
    # Analizleri topla
    all_analyses = []
    for i, symbol in enumerate(BIST100_STOCKS[:stock_count]):
        analysis = comprehensive_stock_analysis(symbol)
        if analysis:
            all_analyses.append(analysis)
        time.sleep(0.3)
    
    if not all_analyses:
        report.append("❌ Veri alınamadı")
        return '\n'.join(report)
    
    # ══════════════════════════════════════════════════════════════════
    # TEKNİK ANALİZ BÖLÜMÜ
    # ══════════════════════════════════════════════════════════════════
    
    # Teknik skora göre sırala
    tech_sorted = sorted(all_analyses, key=lambda x: x['technical']['score'], reverse=True)
    
    # GÜÇLÜ AL SİNYALLERİ (Teknik)
    strong_buy_tech = [a for a in tech_sorted if a['technical']['score'] >= 3]
    buy_tech = [a for a in tech_sorted if 1 <= a['technical']['score'] < 3]
    sell_tech = [a for a in tech_sorted if a['technical']['score'] <= -2]
    
    if strong_buy_tech:
        report.append("━" * 55)
        report.append("📊 TEKNİK ANALİZ - GÜÇLÜ AL SİNYALLERİ")
        report.append("━" * 55)
        
        for stock in strong_buy_tech[:5]:
            t = stock['technical']
            report.append(f"\n🟢 {stock['symbol']} - {stock['current_price']:.2f} TL (%{stock['daily_change']:.1f})")
            report.append(f"   📊 RSI: {t['rsi']:.0f} | Stok: {t['stoch_k']:.0f}")
            report.append(f"   📈 MACD: {'↑ Yukarı' if t['macd'] > t['macd_signal'] else '↓ Aşağı'}")
            report.append(f"   📍 EMA20: {t['ema_20']:.2f} | EMA50: {t['ema_50']:.2f}")
            report.append(f"   🎯 BB: {t['bb_lower']:.2f} - {t['bb_upper']:.2f}")
            for sig in t['signals'][:3]:
                report.append(f"   {sig}")
        report.append("")
    
    if buy_tech:
        report.append("━" * 55)
        report.append("📊 TEKNİK ANALİZ - AL SİNYALLERİ")
        report.append("━" * 55)
        
        for stock in buy_tech[:5]:
            t = stock['technical']
            report.append(f"\n🟢 {stock['symbol']} - {stock['current_price']:.2f} TL")
            report.append(f"   📊 RSI: {t['rsi']:.0f} | MACD: {'↑' if t['macd'] > t['macd_signal'] else '↓'} | Skor: {t['score']}")
            for sig in t['signals'][:2]:
                report.append(f"   {sig}")
        report.append("")
    
    if sell_tech:
        report.append("━" * 55)
        report.append("📊 TEKNİK ANALİZ - SAT SİNYALLERİ")
        report.append("━" * 55)
        
        for stock in sell_tech[:5]:
            t = stock['technical']
            report.append(f"\n🔴 {stock['symbol']} - {stock['current_price']:.2f} TL")
            report.append(f"   📊 RSI: {t['rsi']:.0f} | MACD: {'↑' if t['macd'] > t['macd_signal'] else '↓'} | Skor: {t['score']}")
            for sig in t['signals'][:2]:
                report.append(f"   {sig}")
        report.append("")
    
    # AŞIRI ALIM/SATIM
    oversold = [a for a in all_analyses if a['technical']['rsi'] < 30]
    overbought = [a for a in all_analyses if a['technical']['rsi'] > 70]
    
    if oversold:
        report.append("━" * 55)
        report.append("📉 AŞIRI SATIM BÖLGESİ (RSI < 30)")
        report.append("━" * 55)
        for stock in oversold[:5]:
            t = stock['technical']
            report.append(f"• {stock['symbol']}: RSI {t['rsi']:.0f} | Stok {t['stoch_k']:.0f} - Potansiyel dip!")
        report.append("")
    
    if overbought:
        report.append("━" * 55)
        report.append("📈 AŞIRI ALIM BÖLGESİ (RSI > 70)")
        report.append("━" * 55)
        for stock in overbought[:5]:
            t = stock['technical']
            report.append(f"• {stock['symbol']}: RSI {t['rsi']:.0f} | Stok {t['stoch_k']:.0f} - Dikkat!")
        report.append("")
    
    # ══════════════════════════════════════════════════════════════════
    # TEMEL ANALİZ BÖLÜMÜ
    # ══════════════════════════════════════════════════════════════════
    
    # Sağlık skoruna göre sırala
    all_analyses.sort(key=lambda x: x['health']['percentage'], reverse=True)
    
    # EN SAĞLIKLI ŞİRKETLER
    healthy = [a for a in all_analyses if a['health']['grade'] in ['A', 'B']]
    if healthy:
        report.append("━" * 55)
        report.append("🏆 TEMEL ANALİZ - EN SAĞLIKLI ŞİRKETLER (A-B)")
        report.append("━" * 55)
        
        for stock in healthy[:5]:
            h = stock['health']
            v = stock['valuation_eval']
            f = stock['fundamental']
            t = stock['technical']
            
            report.append(f"\n💎 {stock['symbol']} - {stock['current_price']:.2f} TL")
            report.append(f"   📊 Sağlık: {h['grade']} ({h['percentage']:.0f}/100) {h['health_status']}")
            report.append(f"   💰 Değerleme: {v['verdict']}")
            
            # Temel oranlar
            prof = f['profitability']
            lev = f['leverage']
            if prof.get('roe'):
                report.append(f"   📈 ROE: %{prof['roe']:.1f} | Kar Marjı: %{prof.get('net_profit_margin', 0):.1f}")
            if lev.get('debt_to_equity'):
                report.append(f"   📉 Borç/Özkaynak: {lev['debt_to_equity']:.2f}")
            
            # Teknik durum
            tech_status = "🟢 AL" if t['score'] >= 1 else ("🔴 SAT" if t['score'] <= -1 else "🟡 TUT")
            report.append(f"   🔧 Teknik: {tech_status} | RSI: {t['rsi']:.0f}")
            
            # Trend
            trends = f['income_trend'].get('analysis', [])
            if trends:
                report.append(f"   📊 {trends[0]}")
        report.append("")
    
    # UCUZ HİSSELER
    cheap = [a for a in all_analyses if a['valuation_eval']['score'] >= 1]
    if cheap:
        report.append("━" * 55)
        report.append("💰 UCUZ GÖRÜNEN HİSSELER")
        report.append("━" * 55)
        
        for stock in cheap[:5]:
            v = stock['valuation_eval']
            val = stock['fundamental']['valuation']
            
            report.append(f"\n💚 {stock['symbol']} - {stock['current_price']:.2f} TL")
            report.append(f"   {v['verdict']} (Güven: {v['confidence']})")
            
            pe = val.get('pe_ratio', 0)
            pb = val.get('pb_ratio', 0)
            if pe > 0:
                report.append(f"   📊 F/K: {pe:.1f} | PD/DD: {pb:.2f}")
            
            for reason in v['reasons'][:2]:
                report.append(f"   {reason}")
        report.append("")
    
    # PAHALI HİSSELER
    expensive = [a for a in all_analyses if a['valuation_eval']['score'] <= -1]
    if expensive:
        report.append("━" * 55)
        report.append("⚠️ PAHALI GÖRÜNEN HİSSELER")
        report.append("━" * 55)
        
        for stock in expensive[:5]:
            v = stock['valuation_eval']
            val = stock['fundamental']['valuation']
            
            report.append(f"\n🔴 {stock['symbol']} - {stock['current_price']:.2f} TL")
            report.append(f"   {v['verdict']}")
            
            pe = val.get('pe_ratio', 0)
            pb = val.get('pb_ratio', 0)
            if pe > 0:
                report.append(f"   📊 F/K: {pe:.1f} | PD/DD: {pb:.2f}")
        report.append("")
    
    # RİSKLİ ŞİRKETLER
    risky = [a for a in all_analyses if a['health']['grade'] in ['D', 'F']]
    if risky:
        report.append("━" * 55)
        report.append("🚨 DİKKAT EDİLMESİ GEREKEN ŞİRKETLER (D-F Notu)")
        report.append("━" * 55)
        
        for stock in risky[:5]:
            h = stock['health']
            lev = stock['fundamental']['leverage']
            
            report.append(f"\n⚠️ {stock['symbol']} - {h['grade']} ({h['percentage']:.0f}/100)")
            
            # Risk nedenleri
            debt_to_equity = lev.get('debt_to_equity', 0)
            if debt_to_equity > 2:
                report.append(f"   ❌ Yüksek borç: Borç/Özkaynak {debt_to_equity:.2f}")
            
            interest_cov = lev.get('interest_coverage', 0)
            if interest_cov < 2 and interest_cov > 0:
                report.append(f"   ❌ Düşük faiz karşılama: {interest_cov:.1f}x")
        report.append("")
    
    # GÜÇLÜ BİLANÇO TRENDİ
    growing = [a for a in all_analyses 
               if any('büyüyor' in t.lower() or 'güçlü' in t.lower() 
                     for t in a['fundamental']['income_trend'].get('analysis', []))]
    if growing:
        report.append("━" * 55)
        report.append("📈 GÜÇLÜ BÜYÜME TRENDİ")
        report.append("━" * 55)
        
        for stock in growing[:5]:
            trends = stock['fundamental']['income_trend']['analysis']
            report.append(f"\n🚀 {stock['symbol']}")
            for t in trends[:2]:
                report.append(f"   {t}")
        report.append("")
    
    # ══════════════════════════════════════════════════════════════════
    # KOMBİNASYON ANALİZİ (Teknik + Temel birlikte güçlü)
    # ══════════════════════════════════════════════════════════════════
    
    # Hem teknik hem temel olarak güçlü hisseler
    combo_strong = [a for a in all_analyses 
                   if a['technical']['score'] >= 2 
                   and a['health']['grade'] in ['A', 'B', 'C']
                   and a['valuation_eval']['score'] >= 0]
    
    if combo_strong:
        report.append("━" * 55)
        report.append("⭐ KOMBİNASYON ANALİZİ - EN İYİ FIRSATLAR")
        report.append("(Teknik AL + Sağlıklı Bilanço + Makul Fiyat)")
        report.append("━" * 55)
        
        # Kombine skora göre sırala
        combo_strong.sort(key=lambda x: x['technical']['score'] + (x['health']['percentage']/20) + x['valuation_eval']['score'], reverse=True)
        
        for stock in combo_strong[:5]:
            t = stock['technical']
            h = stock['health']
            v = stock['valuation_eval']
            f = stock['fundamental']
            
            report.append(f"\n⭐ {stock['symbol']} - {stock['current_price']:.2f} TL")
            report.append(f"   🔧 Teknik: {t['overall_signal']} (Skor: {t['score']:.1f})")
            report.append(f"   📊 Temel: {h['grade']} ({h['percentage']:.0f}/100)")
            report.append(f"   💰 Değerleme: {v['verdict']}")
            
            # En önemli sinyaller
            report.append(f"   📈 RSI: {t['rsi']:.0f} | ADX: {t['adx']:.0f} | ROE: %{f['profitability'].get('roe', 0):.1f}")
            
            # Destek/Direnç
            report.append(f"   📍 Destek: {t['s1']:.2f} | Direnç: {t['r1']:.2f}")
        report.append("")
    
    # Teknik + Temel uyumsuz (dikkat edilmesi gereken)
    divergence = [a for a in all_analyses 
                  if (a['technical']['score'] >= 2 and a['health']['grade'] in ['D', 'F'])
                  or (a['technical']['score'] <= -2 and a['health']['grade'] in ['A', 'B'])]
    
    if divergence:
        report.append("━" * 55)
        report.append("⚠️ TEKNİK-TEMEL UYUMSUZLUĞU")
        report.append("━" * 55)
        
        for stock in divergence[:3]:
            t = stock['technical']
            h = stock['health']
            
            if t['score'] >= 2 and h['grade'] in ['D', 'F']:
                report.append(f"• {stock['symbol']}: Teknik AL ama bilanço zayıf ({h['grade']}) - DİKKAT!")
            else:
                report.append(f"• {stock['symbol']}: Teknik SAT ama bilanço güçlü ({h['grade']}) - Fırsat olabilir?")
        report.append("")
    
    # ══════════════════════════════════════════════════════════════════
    # TEKNİK ÖZET TABLOSU
    # ══════════════════════════════════════════════════════════════════
    
    report.append("━" * 55)
    report.append("📊 TEKNİK GÖSTERGE ÖZETİ")
    report.append("━" * 55)
    
    # İstatistikler
    rsi_oversold = len([a for a in all_analyses if a['technical']['rsi'] < 30])
    rsi_overbought = len([a for a in all_analyses if a['technical']['rsi'] > 70])
    macd_bullish = len([a for a in all_analyses if a['technical']['macd'] > a['technical']['macd_signal']])
    macd_bearish = len(all_analyses) - macd_bullish
    above_ema20 = len([a for a in all_analyses if a['current_price'] > a['technical']['ema_20']])
    strong_trend = len([a for a in all_analyses if a['technical']['adx'] > 25])
    
    report.append(f"• RSI: {rsi_oversold} aşırı satım | {rsi_overbought} aşırı alım")
    report.append(f"• MACD: {macd_bullish} yükseliş | {macd_bearish} düşüş")
    report.append(f"• EMA20 Üzeri: {above_ema20}/{len(all_analyses)} hisse")
    report.append(f"• Güçlü Trend (ADX>25): {strong_trend} hisse")
    
    # Genel piyasa sentiment
    avg_tech_score = sum([a['technical']['score'] for a in all_analyses]) / len(all_analyses)
    if avg_tech_score > 1:
        market_sentiment = "🟢 YÜKSELIŞ EĞİLİMİ"
    elif avg_tech_score < -1:
        market_sentiment = "🔴 DÜŞÜŞ EĞİLİMİ"
    else:
        market_sentiment = "🟡 YATAY/KARARSIZ"
    
    report.append(f"• Genel Piyasa: {market_sentiment} (Ort. Skor: {avg_tech_score:.1f})")
    report.append("")
    
    # AI ANALİZİ (En sağlıklı için)
    if healthy and GEMINI_KEY:
        print("🤖 AI analizi oluşturuluyor...")
        ai_report = generate_ai_fundamental_analysis(healthy[0])
        if ai_report:
            report.append("━" * 55)
            report.append(f"🤖 AI TEMEL ANALİZ: {healthy[0]['symbol']}")
            report.append("━" * 55)
            report.append(ai_report)
            report.append("")
    
    # SEKTÖR ÖZETİ
    report.append("━" * 55)
    report.append("📊 SEKTÖR BAZLI ÖZET")
    report.append("━" * 55)
    
    sector_summary = {}
    for a in all_analyses:
        sector = a['sector']
        if sector not in sector_summary:
            sector_summary[sector] = {'count': 0, 'avg_health': 0, 'cheap': 0, 'tech_buy': 0}
        sector_summary[sector]['count'] += 1
        sector_summary[sector]['avg_health'] += a['health']['percentage']
        if a['valuation_eval']['score'] >= 1:
            sector_summary[sector]['cheap'] += 1
        if a['technical']['score'] >= 1:
            sector_summary[sector]['tech_buy'] += 1
    
    for sector, data in sector_summary.items():
        avg = data['avg_health'] / data['count']
        report.append(f"• {sector}: Sağlık %{avg:.0f} | Ucuz: {data['cheap']}/{data['count']} | Teknik AL: {data['tech_buy']}/{data['count']}")
    report.append("")
    
    # UYARI
    report.append("═" * 55)
    report.append("⚠️ YASAL UYARI")
    report.append("Bu rapor eğitim amaçlıdır. Yatırım tavsiyesi")
    report.append("değildir. Kararlarınızı almadan önce lisanslı")
    report.append("yatırım danışmanlarına başvurunuz.")
    report.append("═" * 55)
    report.append(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    
    return '\n'.join(report)

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram_message(message: str) -> bool:
    """Telegram'a mesaj gönder"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    try:
        max_length = 4000
        parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        
        for part in parts:
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': part,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            requests.post(url, json=payload, timeout=30)
            time.sleep(1)
        
        return True
    except Exception as e:
        print(f"Telegram hatası: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("📈 BIST 100 KAPSAMLI ANALİZ BOTU v2.1")
    print("   Teknik (12 Gösterge) + Temel Analiz")
    print("=" * 55)
    print()
    
    report = generate_comprehensive_report(stock_count=30)
    print("\n" + report)
    
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_message(report)
        print("\n✅ Telegram'a gönderildi!")

if __name__ == "__main__":
    main()
