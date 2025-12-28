#!/usr/bin/env python3
"""
📚 EĞİTİM GÜNDEM TAKİP BOTU v4.0 - YOUTUBE AI EDİTION
======================================================
LGS/YKS Öğrenci ve Öğretmenler için Günlük Haber & Gündem Botu

🆕 v4.0 YENİLİKLER:
- 🎬 YOUTUBE AI VİDEOLARI: Popüler AI kanallarından son videolar
  • AI Explained, Two Minute Papers, Yannic Kilcher
  • Matt Wolfe, The AI Advantage, AI Jason
  • Fireship, bycloud, Prompt Engineering
  • Ve daha fazlası...
- 📺 Video özetleri ve doğrudan linkler
- 🔥 Trend AI içerikleri
- Tüm v3.0 özellikleri korundu

v3.0 ÖZELLİKLER:
- PISA liderlerinden eğitim haberleri (Makao, Singapur, Estonya, Japonya, Kore...)
- Son 48 saat filtresi - taze haberler
- Yinelenen haber filtreleme
- Güncellenmiş sınav tarihleri (2026)
- Genişletilmiş akademik kaynaklar (ERIC, Semantic Scholar, OECD)
- Uluslararası değerlendirme raporları (PISA, TIMSS)
- Makro eğitim politikası haberleri
- ArXiv rate limit bypass stratejisi
- Türkiye ulusal izleme araştırmaları

Geliştirici: Numan Hoca için Claude tarafından oluşturuldu
Tarih: Aralık 2025
"""

import os
import requests
import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup
import json
import re
import locale
import hashlib
import time
from urllib.parse import quote_plus

# Türkçe tarih formatı için
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Turkish_Turkey.1254')
    except:
        pass

# Türkçe ay ve gün isimleri
TURKISH_MONTHS = {
    'January': 'Ocak', 'February': 'Şubat', 'March': 'Mart',
    'April': 'Nisan', 'May': 'Mayıs', 'June': 'Haziran',
    'July': 'Temmuz', 'August': 'Ağustos', 'September': 'Eylül',
    'October': 'Ekim', 'November': 'Kasım', 'December': 'Aralık'
}

TURKISH_DAYS = {
    'Monday': 'Pazartesi', 'Tuesday': 'Salı', 'Wednesday': 'Çarşamba',
    'Thursday': 'Perşembe', 'Friday': 'Cuma', 'Saturday': 'Cumartesi',
    'Sunday': 'Pazar'
}

def format_turkish_date(dt: datetime, include_day: bool = True) -> str:
    """Tarihi Türkçe formatta döndür"""
    day = dt.day
    month = TURKISH_MONTHS.get(dt.strftime('%B'), dt.strftime('%B'))
    year = dt.year
    
    if include_day:
        weekday = TURKISH_DAYS.get(dt.strftime('%A'), dt.strftime('%A'))
        return f"{day} {month} {year}, {weekday}"
    return f"{day} {month} {year}"

# ══════════════════════════════════════════════════════════════════════════════
# API ANAHTARLARI
# ══════════════════════════════════════════════════════════════════════════════

GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Gemini API için
try:
    from google import genai
except ImportError:
    genai = None

# ══════════════════════════════════════════════════════════════════════════════
# YİNELENEN HABER FİLTRELEME
# ══════════════════════════════════════════════════════════════════════════════

class NewsDeduplicator:
    """Yinelenen haberleri filtrele"""
    
    def __init__(self):
        self.seen_titles: Set[str] = set()
        self.seen_hashes: Set[str] = set()
    
    def _normalize_title(self, title: str) -> str:
        """Başlığı normalize et"""
        # Küçük harf, gereksiz karakterleri kaldır
        normalized = title.lower()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _get_hash(self, title: str) -> str:
        """Başlık hash'i oluştur"""
        normalized = self._normalize_title(title)
        return hashlib.md5(normalized.encode()).hexdigest()[:10]
    
    def is_duplicate(self, title: str, threshold: float = 0.7) -> bool:
        """Başlık tekrar mı kontrol et"""
        if not title:
            return True
        
        title_hash = self._get_hash(title)
        
        # Tam eşleşme
        if title_hash in self.seen_hashes:
            return True
        
        # Benzerlik kontrolü (basit kelime örtüşmesi)
        normalized = self._normalize_title(title)
        words = set(normalized.split())
        
        for seen in self.seen_titles:
            seen_words = set(seen.split())
            if len(words) > 0 and len(seen_words) > 0:
                overlap = len(words & seen_words) / max(len(words), len(seen_words))
                if overlap > threshold:
                    return True
        
        # Yeni başlık - kaydet
        self.seen_hashes.add(title_hash)
        self.seen_titles.add(normalized)
        return False
    
    def reset(self):
        """Filtreyi sıfırla"""
        self.seen_titles.clear()
        self.seen_hashes.clear()

# Global deduplicator
deduplicator = NewsDeduplicator()

# ══════════════════════════════════════════════════════════════════════════════
# TARİH FİLTRELEME - SON 48 SAAT
# ══════════════════════════════════════════════════════════════════════════════

def parse_date(date_str: str) -> Optional[datetime]:
    """Farklı tarih formatlarını parse et"""
    if not date_str:
        return None
    
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%d %b %Y %H:%M:%S',
        '%Y-%m-%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            continue
    
    return None

def is_recent(date_str: str, hours: int = 48) -> bool:
    """Haber son X saat içinde mi?"""
    if not date_str:
        return True  # Tarih yoksa kabul et
    
    parsed = parse_date(date_str)
    if not parsed:
        return True
    
    # Timezone-aware karşılaştırma
    now = datetime.now()
    try:
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
    except:
        pass
    
    diff = now - parsed
    return diff.total_seconds() < (hours * 3600)

# ══════════════════════════════════════════════════════════════════════════════
# SINAV TAKVİMİ VE GERİ SAYIM - GÜNCELLENMİŞ TARİHLER
# ══════════════════════════════════════════════════════════════════════════════

def get_exam_countdown() -> Dict:
    """
    LGS ve YKS sınav tarihleri ve geri sayım
    2026 RESMİ TARİHLER
    """
    today = datetime.now()
    
    # 2026 SINAV TARİHLERİ - GÜNCEL
    exams = {
        'LGS 2026': {
            'date': datetime(2026, 6, 14),  # 14 Haziran 2026 Pazar
            'name': '📚 LGS (Liselere Geçiş Sınavı)',
            'description': '8. sınıf merkezi sınavı'
        },
        'TYT 2026': {
            'date': datetime(2026, 6, 20),  # 20 Haziran 2026 Cumartesi
            'name': '📝 TYT (Temel Yeterlilik Testi)',
            'description': 'YKS 1. Oturum'
        },
        'AYT 2026': {
            'date': datetime(2026, 6, 21),  # 21 Haziran 2026 Pazar
            'name': '📖 AYT (Alan Yeterlilik Testi)',
            'description': 'YKS 2. Oturum'
        },
        'YDT 2026': {
            'date': datetime(2026, 6, 21),  # 21 Haziran 2026 Pazar (AYT ile aynı gün)
            'name': '🌍 YDT (Yabancı Dil Testi)',
            'description': 'YKS 3. Oturum'
        },
        # Yarıyıl tatili 2025-2026
        'Yarıyıl Tatili': {
            'date': datetime(2026, 1, 19),
            'name': '🏖️ Yarıyıl Tatili Başlangıcı',
            'description': '2 hafta tatil'
        },
        # 2. Dönem
        '2. Dönem Başlangıcı': {
            'date': datetime(2026, 2, 2),
            'name': '🏫 2. Dönem Başlangıcı',
            'description': 'Okula dönüş'
        },
        # Yaz tatili
        'Yaz Tatili': {
            'date': datetime(2026, 6, 19),
            'name': '☀️ Yaz Tatili Başlangıcı',
            'description': 'Okulların kapanışı'
        }
    }
    
    countdown_list = []
    
    for exam_key, exam_info in exams.items():
        exam_date = exam_info['date']
        days_left = (exam_date.date() - today.date()).days
        
        if days_left >= 0:
            weeks = days_left // 7
            remaining_days = days_left % 7
            
            if days_left == 0:
                time_str = "🔴 BUGÜN!"
            elif days_left == 1:
                time_str = "🟡 YARIN!"
            elif days_left <= 7:
                time_str = f"🟠 {days_left} gün"
            elif days_left <= 30:
                time_str = f"🟡 {weeks} hafta {remaining_days} gün"
            else:
                months = days_left // 30
                time_str = f"📅 {months} ay {days_left % 30} gün ({days_left} gün)"
            
            countdown_list.append({
                'name': exam_info['name'],
                'description': exam_info['description'],
                'date': format_turkish_date(exam_date, include_day=False),
                'days_left': days_left,
                'time_str': time_str,
                'is_exam': 'Sınav' in exam_info['name'] or 'Test' in exam_info['name']
            })
    
    countdown_list = sorted(countdown_list, key=lambda x: x['days_left'])
    
    return {
        'today': format_turkish_date(today, include_day=True),
        'countdowns': countdown_list
    }

# ══════════════════════════════════════════════════════════════════════════════
# MEB HABERLERİ
# ══════════════════════════════════════════════════════════════════════════════

def get_meb_news() -> List[Dict]:
    """MEB'den son haberler"""
    news = []
    
    try:
        url = "https://www.meb.gov.tr"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            
            news_items = soup.find_all('a', class_='news-item') or \
                        soup.find_all('div', class_='haber') or \
                        soup.find_all('article')
            
            for item in news_items[:10]:
                title = item.get_text(strip=True)[:150]
                link = item.get('href', '')
                if link and not link.startswith('http'):
                    link = url + link
                
                if title and len(title) > 20 and not deduplicator.is_duplicate(title):
                    news.append({
                        'title': title,
                        'source': 'MEB',
                        'link': link,
                        'is_important': any(kw in title.lower() for kw in [
                            'lgs', 'yks', 'sınav', 'müfredat', 'öğretmen', 
                            'tatil', 'bakan', 'atama', 'maaş'
                        ])
                    })
    except Exception as e:
        print(f"MEB haber hatası: {e}")
    
    return news

def get_education_news_turkey() -> List[Dict]:
    """Türkiye eğitim haberleri - yinelenmesiz, güncel"""
    news = []
    
    sources = [
        ('https://www.hurriyet.com.tr/rss/egitim', 'Hürriyet'),
        ('https://www.milliyet.com.tr/rss/rssNew/egitimRss.xml', 'Milliyet'),
        ('https://www.sabah.com.tr/rss/egitim.xml', 'Sabah'),
        ('https://www.cumhuriyet.com.tr/rss/egitim', 'Cumhuriyet'),
        ('https://www.ntv.com.tr/egitim.rss', 'NTV'),
        ('https://www.haberturk.com/rss/egitim.xml', 'Habertürk'),
    ]
    
    important_keywords = [
        'lgs', 'yks', 'tyt', 'ayt', 'ösym', 'meb', 'sınav', 'müfredat',
        'öğretmen', 'atama', 'maaş', 'tatil', 'okul', 'ders', 'not',
        'bakan', 'eğitim', 'öğrenci', 'üniversite', 'lise', 'ortaokul',
        'beceri temelli', 'maarif modeli', 'pisa', 'timss'
    ]
    
    for rss_url, source in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:8]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:200] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')
                
                # Tarih kontrolü - son 48 saat
                if not is_recent(published, hours=48):
                    continue
                
                # Yineleme kontrolü
                if deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_important = any(kw in text for kw in important_keywords)
                is_exam_related = any(kw in text for kw in ['lgs', 'yks', 'tyt', 'ayt', 'ösym', 'sınav'])
                
                news.append({
                    'title': title[:120],
                    'summary': summary,
                    'source': source,
                    'link': link,
                    'published': published,
                    'is_important': is_important,
                    'is_exam_related': is_exam_related
                })
        except Exception as e:
            continue
    
    news = sorted(news, key=lambda x: (x['is_exam_related'], x['is_important']), reverse=True)
    return news[:12]

# ══════════════════════════════════════════════════════════════════════════════
# MATEMATİK HABERLERİ - GÜNCELLENMİŞ
# ══════════════════════════════════════════════════════════════════════════════

def get_math_news() -> List[Dict]:
    """Matematik alanındaki son gelişmeler - son 48 saat"""
    news = []
    
    world_sources = [
        ('https://www.quantamagazine.org/mathematics/feed/', 'Quanta Magazine'),
        ('https://www.sciencedaily.com/rss/computers_math/mathematics.xml', 'Science Daily'),
        ('https://phys.org/rss-feed/mathematics-news/', 'Phys.org'),
        ('https://www.ams.org/rss/mathfeed.xml', 'AMS'),
        ('https://www.maa.org/rss.xml', 'MAA'),
        ('https://plus.maths.org/content/rss.xml', 'Plus Magazine'),
    ]
    
    for rss_url, source in world_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')
                
                if not is_recent(published, hours=72):  # Matematik için 72 saat
                    continue
                
                if deduplicator.is_duplicate(title):
                    continue
                
                news.append({
                    'title': title[:150],
                    'summary': summary,
                    'source': source,
                    'link': link,
                    'region': 'Dünya',
                    'needs_translation': True
                })
        except Exception as e:
            continue
    
    return news[:8]

# ══════════════════════════════════════════════════════════════════════════════
# YAPAY ZEKA VE EĞİTİM HABERLERİ - GENİŞLETİLMİŞ
# ══════════════════════════════════════════════════════════════════════════════

def get_ai_education_news() -> List[Dict]:
    """
    Yapay zeka, LLM gelişmeleri ve eğitim teknolojisi haberleri
    Çoklu kaynak - tek kaynağa bağımlı değil
    """
    news = []
    
    # ═══════════════════════════════════════════════════════════════
    # 1. BÜYÜK DİL MODELLERİ (LLM) VE AI GELİŞMELERİ
    # ═══════════════════════════════════════════════════════════════
    
    llm_sources = [
        # Ana AI şirket blogları
        ('https://openai.com/blog/rss/', 'OpenAI', 'LLM'),
        ('https://www.anthropic.com/rss.xml', 'Anthropic', 'LLM'),
        ('https://blog.google/technology/ai/rss/', 'Google AI', 'LLM'),
        ('https://ai.meta.com/blog/rss/', 'Meta AI', 'LLM'),
        ('https://blogs.microsoft.com/ai/feed/', 'Microsoft AI', 'LLM'),
        
        # AI Haber siteleri
        ('https://www.artificialintelligence-news.com/feed/', 'AI News', 'AI Haber'),
        ('https://venturebeat.com/category/ai/feed/', 'VentureBeat AI', 'AI Haber'),
        ('https://www.technologyreview.com/feed/', 'MIT Tech Review', 'AI Haber'),
        ('https://techcrunch.com/category/artificial-intelligence/feed/', 'TechCrunch AI', 'AI Haber'),
        ('https://www.wired.com/feed/tag/ai/latest/rss', 'WIRED AI', 'AI Haber'),
        ('https://www.theverge.com/rss/ai-artificial-intelligence/index.xml', 'The Verge AI', 'AI Haber'),
        ('https://arstechnica.com/tag/artificial-intelligence/feed/', 'Ars Technica AI', 'AI Haber'),
        
        # AI Araştırma
        ('https://deepmind.google/blog/rss.xml', 'DeepMind', 'Araştırma'),
        ('https://bair.berkeley.edu/blog/feed.xml', 'Berkeley AI', 'Araştırma'),
        ('https://huggingface.co/blog/feed.xml', 'Hugging Face', 'Araştırma'),
    ]
    
    # LLM ve AI anahtar kelimeleri
    llm_keywords = [
        # Model isimleri
        'gpt', 'gpt-4', 'gpt-5', 'chatgpt', 'claude', 'gemini', 'llama', 'mistral',
        'copilot', 'deepseek', 'qwen', 'phi', 'o1', 'o3', 'sonnet', 'opus', 'haiku',
        # Teknik terimler
        'large language model', 'llm', 'transformer', 'neural network',
        'machine learning', 'deep learning', 'artificial intelligence',
        'generative ai', 'genai', 'foundation model', 'multimodal',
        'fine-tuning', 'prompt', 'reasoning', 'chain of thought',
        'rag', 'retrieval', 'embedding', 'context window', 'token',
        # Yetenekler
        'coding', 'code generation', 'text generation', 'image generation',
        'voice', 'speech', 'vision', 'video', 'agent', 'tool use', 'agentic',
        # Şirketler
        'openai', 'anthropic', 'google ai', 'meta ai', 'microsoft ai',
        'deepmind', 'hugging face', 'stability ai', 'midjourney', 'perplexity'
    ]
    
    for rss_url, source, category in llm_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')
                
                if not title:
                    continue
                
                if not is_recent(published, hours=96):  # 4 gün
                    continue
                
                if deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_ai_related = any(kw in text for kw in llm_keywords)
                
                if is_ai_related:
                    news.append({
                        'title': title[:150],
                        'summary': summary[:200],
                        'source': source,
                        'category': category,
                        'link': link,
                        'is_llm': category == 'LLM',
                        'needs_translation': True
                    })
        except Exception as e:
            continue
    
    # ═══════════════════════════════════════════════════════════════
    # 2. EĞİTİM TEKNOLOJİSİ (EdTech) HABERLERİ
    # ═══════════════════════════════════════════════════════════════
    
    edtech_sources = [
        ('https://www.edsurge.com/articles_rss', 'EdSurge', 'EdTech'),
        ('https://www.the74million.org/feed/', 'The 74', 'EdTech'),
        ('https://www.eschoolnews.com/feed/', 'eSchool News', 'EdTech'),
        ('https://edtechmagazine.com/k12/rss.xml', 'EdTech Magazine', 'EdTech'),
        ('https://www.techlearning.com/rss.xml', 'Tech & Learning', 'EdTech'),
        ('https://www.elearningindustry.com/feed', 'eLearning Industry', 'EdTech'),
        ('https://www.insidehighered.com/rss.xml', 'Inside Higher Ed', 'Yükseköğretim'),
    ]
    
    edtech_keywords = [
        'ai tutor', 'ai teacher', 'ai classroom', 'ai education', 'ai learning',
        'chatgpt education', 'chatgpt school', 'chatgpt student', 'chatgpt teacher',
        'adaptive learning', 'personalized learning', 'intelligent tutoring',
        'learning analytics', 'educational technology', 'edtech',
        'online learning', 'digital learning', 'khanmigo', 'duolingo',
        'assessment', 'grading', 'feedback', 'cheating', 'plagiarism',
        'ai policy', 'ai ban', 'ai literacy'
    ]
    
    for rss_url, source, category in edtech_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:4]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:200] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')
                
                if not title:
                    continue
                
                if not is_recent(published, hours=72):
                    continue
                
                if deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_relevant = any(kw in text for kw in edtech_keywords)
                
                if is_relevant:
                    news.append({
                        'title': title[:150],
                        'summary': summary[:200],
                        'source': source,
                        'category': category,
                        'link': link,
                        'is_llm': False,
                        'needs_translation': True
                    })
        except Exception as e:
            continue
    
    # Önce LLM haberleri, sonra EdTech
    news = sorted(news, key=lambda x: (x.get('is_llm', False)), reverse=True)
    
    # Kaynak çeşitliliği sağla - her kaynaktan max 2
    final_news = []
    source_counts = {}
    
    for item in news:
        source = item.get('source', '')
        if source not in source_counts:
            source_counts[source] = 0
        
        if source_counts[source] < 2:
            final_news.append(item)
            source_counts[source] += 1
        
        if len(final_news) >= 12:
            break
    
    return final_news

# ══════════════════════════════════════════════════════════════════════════════
# 🎬 YOUTUBE AI VİDEOLARI - POPÜLER KANALLAR
# ══════════════════════════════════════════════════════════════════════════════

def get_youtube_ai_videos() -> List[Dict]:
    """
    Popüler AI YouTube kanallarından son videolar
    
    NOT: YouTube RSS doğrudan erişilemeyebilir (network kısıtlamaları)
    Bu durumda curated/statik liste kullanılır
    """
    videos = []
    
    # ═══════════════════════════════════════════════════════════════
    # POPÜLER AI YOUTUBE KANALLARI VERİTABANI
    # Bu liste düzenli olarak güncellenebilir
    # ═══════════════════════════════════════════════════════════════
    
    ai_youtube_channels = [
        # ─── TIER 1: EN POPÜLER AI KANALLARI (1M+ Abone) ───
        {
            'channel_id': 'UCbfYPyITQ-7l4upoX8nvctg',
            'name': 'Two Minute Papers',
            'subscribers': '1.5M+',
            'category': 'AI Araştırma',
            'description': 'Akademik AI makalelerinin kısa özetleri',
            'url': 'https://www.youtube.com/@TwoMinutePapers',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCZHmQk67mSJgfCCTn7xBfew',
            'name': 'Fireship',
            'subscribers': '3M+',
            'category': 'Tech/AI',
            'description': 'Hızlı tech ve AI açıklamaları, "100 seconds" serisi',
            'url': 'https://www.youtube.com/@Fireship',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCYO_jab_esuFRV4b17AJtAw',
            'name': '3Blue1Brown',
            'subscribers': '6M+',
            'category': 'Matematik/AI',
            'description': 'Neural network ve matematik görselleştirmeleri',
            'url': 'https://www.youtube.com/@3blue1brown',
            'lang': 'EN'
        },
        
        # ─── TIER 2: AI HABER VE ANALİZ KANALLARI (500K-1M) ───
        {
            'channel_id': 'UCLXo7UDZvByw2ixzpQCufnA',
            'name': 'Matt Wolfe',
            'subscribers': '650K+',
            'category': 'AI Araçlar',
            'description': 'Haftalık AI araçları ve haberleri',
            'url': 'https://www.youtube.com/@maboroshi_studio',
            'lang': 'EN'
        },
        {
            'channel_id': 'UC5sYcThBEkKrLQqo_v1m4VQ',
            'name': 'AI Explained',
            'subscribers': '400K+',
            'category': 'AI Analiz',
            'description': 'Derinlemesine AI analizleri ve karşılaştırmaları',
            'url': 'https://www.youtube.com/@aiaborovere',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCUyeluBRhGPCW4rPe_UvBZQ',
            'name': 'The AI Advantage',
            'subscribers': '500K+',
            'category': 'AI Araçlar',
            'description': 'AI araçları kullanım rehberleri',
            'url': 'https://www.youtube.com/@aiadvantage',
            'lang': 'EN'
        },
        
        # ─── TIER 3: TEKNİK AI KANALLARI (200K-500K) ───
        {
            'channel_id': 'UCeYvMMZLnoqOzphJJ1Ozf_Q',
            'name': 'Yannic Kilcher',
            'subscribers': '280K+',
            'category': 'AI Araştırma',
            'description': 'AI paper incelemeleri ve teknik analizler',
            'url': 'https://www.youtube.com/@YannicKilcher',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCsbr_wOE4DMjcBW4',
            'name': 'bycloud',
            'subscribers': '350K+',
            'category': 'AI Araştırma',
            'description': 'AI paper açıklamaları, teknik içerik',
            'url': 'https://www.youtube.com/@bycloudAI',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCbXgNpp0jedKWcQiULLbDTA',
            'name': 'AI Foundations',
            'subscribers': '200K+',
            'category': 'AI Eğitim',
            'description': 'AI temelleri ve öğretici içerikler',
            'url': 'https://www.youtube.com/@ai-foundations',
            'lang': 'EN'
        },
        
        # ─── TIER 4: AI UYGULAMA VE PROMPT KANALLARI ───
        {
            'channel_id': 'UC4L2IXqZvLxZdaXcvfje2OQ',
            'name': 'AI Jason',
            'subscribers': '250K+',
            'category': 'AI Prompt',
            'description': 'Prompt engineering ve AI ipuçları',
            'url': 'https://www.youtube.com/@AIJasonZ',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCb-bmaFpSPnJMwJJJlU2kbQ',
            'name': 'All About AI',
            'subscribers': '400K+',
            'category': 'AI Araçlar',
            'description': 'Kapsamlı AI araç incelemeleri',
            'url': 'https://www.youtube.com/@AllAboutAI',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCWv7vMbMWH4-V0ZXdmDpPBA',
            'name': 'Prompt Engineering',
            'subscribers': '180K+',
            'category': 'AI Prompt',
            'description': 'ChatGPT ve Claude prompt teknikleri',
            'url': 'https://www.youtube.com/@engineerprompt',
            'lang': 'EN'
        },
        
        # ─── TIER 5: ŞİRKET VE PODCAST KANALLARI ───
        {
            'channel_id': 'UCXZCJLdBC09xxGZ6gcdrc6A',
            'name': 'OpenAI',
            'subscribers': '600K+',
            'category': 'Resmi',
            'description': 'ChatGPT, GPT-4, Sora resmi duyuruları',
            'url': 'https://www.youtube.com/@OpenAI',
            'lang': 'EN'
        },
        {
            'channel_id': 'UC_x5XG1OV2P6uZZ5FSM9Ttw',
            'name': 'Google',
            'subscribers': '14M+',
            'category': 'Resmi',
            'description': 'Google AI, Gemini haberleri',
            'url': 'https://www.youtube.com/@Google',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCVHFbqXqoYvEWM1Ddxl0QKg',
            'name': 'Lex Fridman',
            'subscribers': '4.5M+',
            'category': 'AI Podcast',
            'description': 'AI liderleriyle uzun röportajlar',
            'url': 'https://www.youtube.com/@lexfridman',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCxg7CAgk4sDJ9p3EE',
            'name': 'Andrej Karpathy',
            'subscribers': '600K+',
            'category': 'AI Araştırma',
            'description': 'Eski Tesla AI direktörü, teknik dersler',
            'url': 'https://www.youtube.com/@AndrejKarpathy',
            'lang': 'EN'
        },
        {
            'channel_id': 'UCJlfH_QMvSCUvgGW4JAbSPQ',
            'name': 'Anthropic',
            'subscribers': '50K+',
            'category': 'Resmi',
            'description': 'Claude AI resmi duyuruları',
            'url': 'https://www.youtube.com/@AnthropicAI',
            'lang': 'EN'
        },
        
        # ─── TÜRKÇE AI KANALLARI ───
        {
            'channel_id': 'UCnjbfvqJKgqSMtNNaPJHrqg',
            'name': 'Kodlama Zamanı',
            'subscribers': '200K+',
            'category': 'Türkçe AI',
            'description': 'Türkçe AI ve programlama dersleri',
            'url': 'https://www.youtube.com/@KodlamaZamani',
            'lang': 'TR'
        },
        {
            'channel_id': 'UCBTYKH9Rh3l4',
            'name': 'Sadi Evren Şeker',
            'subscribers': '500K+',
            'category': 'Türkçe AI',
            'description': 'Yapay zeka ve veri bilimi Türkçe',
            'url': 'https://www.youtube.com/@sadievrenseker',
            'lang': 'TR'
        },
    ]
    
    # Önce RSS feed'den çekmeyi dene
    ai_keywords = [
        'gpt', 'gpt-4', 'gpt-5', 'chatgpt', 'claude', 'gemini', 'llama', 'mistral',
        'copilot', 'deepseek', 'qwen', 'o1', 'o3', 'sonnet', 'opus', 'sora',
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'llm', 'large language model', 'transformer',
        'generative', 'diffusion', 'multimodal', 'agent', 'rag',
        'openai', 'anthropic', 'google ai', 'meta ai', 'microsoft',
        'prompt', 'fine-tuning', 'embedding', 'reasoning', 'coding',
        'yapay zeka', 'dil modeli'
    ]
    
    rss_success = False
    
    for channel in ai_youtube_channels:
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
            feed = feedparser.parse(rss_url)
            
            if feed.entries:
                rss_success = True
                for entry in feed.entries[:3]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    published = entry.get('published', '')
                    
                    video_id = ''
                    if 'yt:videoId' in entry:
                        video_id = entry['yt:videoId']
                    elif link and 'watch?v=' in link:
                        video_id = link.split('watch?v=')[-1].split('&')[0]
                    
                    if not is_recent(published, hours=168):
                        continue
                    
                    if deduplicator.is_duplicate(title):
                        continue
                    
                    title_lower = title.lower()
                    is_ai_related = any(kw in title_lower for kw in ai_keywords)
                    
                    ai_focused_channels = ['Two Minute Papers', 'AI Explained', 'Matt Wolfe', 
                                           'The AI Advantage', 'AI Jason', 'Yannic Kilcher',
                                           'All About AI', 'Prompt Engineering', 'OpenAI', 
                                           'bycloud', 'Anthropic', 'Andrej Karpathy']
                    
                    if channel['name'] in ai_focused_channels or is_ai_related:
                        videos.append({
                            'title': title[:120],
                            'channel': channel['name'],
                            'subscribers': channel['subscribers'],
                            'category': channel['category'],
                            'link': link,
                            'video_id': video_id,
                            'published': published,
                            'lang': channel['lang'],
                            'source': 'rss'
                        })
                        
        except Exception as e:
            continue
    
    # RSS çalışmadıysa, curated kanal listesini döndür
    if not rss_success or len(videos) < 3:
        print("   📋 RSS erişilemiyor, kanal listesi kullanılıyor...")
        
        # Curated güncel video önerileri (manuel güncelleme gerektirir)
        curated_videos = [
            {
                'title': '🔥 Two Minute Papers - En son AI araştırmaları',
                'channel': 'Two Minute Papers',
                'subscribers': '1.5M+',
                'category': 'AI Araştırma',
                'link': 'https://www.youtube.com/@TwoMinutePapers',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 Fireship - AI in 100 Seconds serisi',
                'channel': 'Fireship',
                'subscribers': '3M+',
                'category': 'Tech/AI',
                'link': 'https://www.youtube.com/@Fireship',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 Matt Wolfe - Haftalık AI araç incelemeleri',
                'channel': 'Matt Wolfe',
                'subscribers': '650K+',
                'category': 'AI Araçlar',
                'link': 'https://www.youtube.com/@maboroshi_studio',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 AI Explained - GPT, Claude, Gemini karşılaştırmaları',
                'channel': 'AI Explained',
                'subscribers': '400K+',
                'category': 'AI Analiz',
                'link': 'https://www.youtube.com/@aiexplained-official',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 The AI Advantage - Pratik AI kullanım rehberleri',
                'channel': 'The AI Advantage',
                'subscribers': '500K+',
                'category': 'AI Araçlar',
                'link': 'https://www.youtube.com/@aiadvantage',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 Yannic Kilcher - Detaylı AI paper incelemeleri',
                'channel': 'Yannic Kilcher',
                'subscribers': '280K+',
                'category': 'AI Araştırma',
                'link': 'https://www.youtube.com/@YannicKilcher',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 3Blue1Brown - Neural Network görselleştirmeleri',
                'channel': '3Blue1Brown',
                'subscribers': '6M+',
                'category': 'Matematik/AI',
                'link': 'https://www.youtube.com/@3blue1brown',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 Lex Fridman - AI liderlerle röportajlar',
                'channel': 'Lex Fridman',
                'subscribers': '4.5M+',
                'category': 'AI Podcast',
                'link': 'https://www.youtube.com/@lexfridman',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 Andrej Karpathy - Neural network dersleri',
                'channel': 'Andrej Karpathy',
                'subscribers': '600K+',
                'category': 'AI Araştırma',
                'link': 'https://www.youtube.com/@AndrejKarpathy',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 OpenAI - Resmi duyurular (GPT, Sora)',
                'channel': 'OpenAI',
                'subscribers': '600K+',
                'category': 'Resmi',
                'link': 'https://www.youtube.com/@OpenAI',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 Anthropic - Claude AI resmi kanal',
                'channel': 'Anthropic',
                'subscribers': '50K+',
                'category': 'Resmi',
                'link': 'https://www.youtube.com/@AnthropicAI',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 All About AI - Kapsamlı AI araç demoları',
                'channel': 'All About AI',
                'subscribers': '400K+',
                'category': 'AI Araçlar',
                'link': 'https://www.youtube.com/@AllAboutAI',
                'lang': 'EN',
                'source': 'curated'
            },
            {
                'title': '🔥 AI Jason - Prompt engineering teknikleri',
                'channel': 'AI Jason',
                'subscribers': '250K+',
                'category': 'AI Prompt',
                'link': 'https://www.youtube.com/@AIJasonZ',
                'lang': 'EN',
                'source': 'curated'
            },
        ]
        
        videos = curated_videos
    
    # Kanal çeşitliliği sağla
    final_videos = []
    channel_counts = {}
    
    for video in videos:
        ch = video.get('channel', '')
        if ch not in channel_counts:
            channel_counts[ch] = 0
        
        if channel_counts[ch] < 2:
            final_videos.append(video)
            channel_counts[ch] += 1
        
        if len(final_videos) >= 15:
            break
    
    return final_videos


def get_ai_channel_recommendations() -> List[Dict]:
    """
    Takip edilmesi önerilen AI YouTube kanalları
    Kategorize edilmiş liste
    """
    return [
        # Araştırma
        {'name': 'Two Minute Papers', 'url': 'youtube.com/@TwoMinutePapers', 'focus': 'Paper özetleri', 'subs': '1.5M'},
        {'name': 'Yannic Kilcher', 'url': 'youtube.com/@YannicKilcher', 'focus': 'Detaylı paper analizi', 'subs': '280K'},
        {'name': 'Andrej Karpathy', 'url': 'youtube.com/@AndrejKarpathy', 'focus': 'Teknik dersler', 'subs': '600K'},
        
        # Araçlar
        {'name': 'Matt Wolfe', 'url': 'youtube.com/@maboroshi_studio', 'focus': 'Haftalık AI araçları', 'subs': '650K'},
        {'name': 'The AI Advantage', 'url': 'youtube.com/@aiadvantage', 'focus': 'Pratik rehberler', 'subs': '500K'},
        {'name': 'All About AI', 'url': 'youtube.com/@AllAboutAI', 'focus': 'Araç demoları', 'subs': '400K'},
        
        # Haber & Analiz
        {'name': 'AI Explained', 'url': 'youtube.com/@aiexplained-official', 'focus': 'Derin analizler', 'subs': '400K'},
        {'name': 'Fireship', 'url': 'youtube.com/@Fireship', 'focus': 'Hızlı güncellemeler', 'subs': '3M'},
        
        # Podcast & Röportaj
        {'name': 'Lex Fridman', 'url': 'youtube.com/@lexfridman', 'focus': 'AI lider röportajları', 'subs': '4.5M'},
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 🏆 PISA LİDERLERİNDEN EĞİTİM HABERLERİ
# ══════════════════════════════════════════════════════════════════════════════

def get_pisa_leaders_news() -> Dict[str, List[Dict]]:
    """
    PISA 2022'de en başarılı ülkelerden eğitim haberleri
    SADECE eğitim politikası ve okul haberleri - çok sıkı filtreleme
    """
    
    # PISA 2022 Top Performers
    pisa_leaders = {
        'singapore': {
            'flag': '🇸🇬',
            'name': 'Singapur',
            'rank': '#1-2 PISA',
            'sources': [
                ('https://www.straitstimes.com/singapore/parenting-education', 'Straits Times Education'),
                ('https://www.channelnewsasia.com/rss/latest_news.xml', 'CNA'),
            ],
            # SADECE bu kelimeler geçerse al
            'must_have': ['school', 'education', 'student', 'teacher', 'exam', 'curriculum', 
                         'university', 'moe', 'psle', 'o level', 'a level', 'learning', 
                         'classroom', 'tuition', 'polytechnic'],
        },
        'japan': {
            'flag': '🇯🇵',
            'name': 'Japonya',
            'rank': '#4-5 PISA',
            'sources': [
                ('https://www.japantimes.co.jp/feed/', 'Japan Times'),
                ('https://english.kyodonews.net/rss/all.xml', 'Kyodo News'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university', 
                         'mext', 'exam', 'curriculum', 'juku', 'learning', 'classroom',
                         'elementary', 'high school', 'college'],
        },
        'korea': {
            'flag': '🇰🇷',
            'name': 'Güney Kore',
            'rank': '#6 PISA',
            'sources': [
                ('https://en.yna.co.kr/RSS/news.xml', 'Yonhap'),
                ('https://www.koreaherald.com/rss/023.xml', 'Korea Herald'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university',
                         'suneung', 'csat', 'hagwon', 'curriculum', 'learning',
                         'college', 'exam', 'classroom'],
        },
        'estonia': {
            'flag': '🇪🇪',
            'name': 'Estonya',
            'rank': '#3 PISA Fen',
            'sources': [
                ('https://news.err.ee/rss', 'ERR News'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university',
                         'curriculum', 'learning', 'classroom', 'exam', 'digital education',
                         'e-school', 'gymnasium'],
        },
        'hong_kong': {
            'flag': '🇭🇰',
            'name': 'Hong Kong',
            'rank': '#5 PISA',
            'sources': [
                ('https://www.scmp.com/rss/91/feed', 'SCMP'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university',
                         'dse', 'curriculum', 'learning', 'classroom', 'exam',
                         'education bureau'],
        },
        'chinese_taipei': {
            'flag': '🇹🇼',
            'name': 'Tayvan',
            'rank': '#8 PISA',
            'sources': [
                ('https://focustaiwan.tw/rss', 'Focus Taiwan'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university',
                         'curriculum', 'learning', 'exam', 'college', 'ministry of education'],
        },
        'finland': {
            'flag': '🇫🇮',
            'name': 'Finlandiya',
            'rank': '#12 PISA',
            'sources': [
                ('https://yle.fi/rss/uutiset.rss', 'YLE'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university',
                         'curriculum', 'learning', 'classroom', 'pisa', 'finnish education'],
        },
        'canada': {
            'flag': '🇨🇦',
            'name': 'Kanada',
            'rank': '#9 PISA',
            'sources': [
                ('https://www.cbc.ca/cmlink/rss-canada', 'CBC'),
            ],
            'must_have': ['school', 'education', 'student', 'teacher', 'university',
                         'curriculum', 'learning', 'classroom', 'college', 'provincial education'],
        },
    }
    
    # Kesinlikle ALMAYACAĞIMIZ konular (eğitimle alakasız)
    exclude_keywords = [
        'prison', 'jail', 'crime', 'murder', 'police', 'court', 'arrested',
        'skating', 'ice rink', 'tourist', 'hotel', 'restaurant', 'food',
        'weather', 'storm', 'earthquake', 'flood', 'fire', 'accident',
        'sports', 'football', 'basketball', 'soccer', 'olympics', 'athlete',
        'entertainment', 'movie', 'celebrity', 'concert', 'festival',
        'stock', 'market', 'business', 'trade', 'export', 'import',
        'military', 'war', 'army', 'navy', 'defense', 'weapon',
        'smoking', 'cigarette', 'alcohol', 'drug', 'casino', 'gambling',
        'covid', 'virus', 'pandemic', 'vaccine', 'hospital', 'health crisis'
    ]
    
    all_news = {}
    
    for country_code, country_info in pisa_leaders.items():
        country_news = []
        
        for source_url, source_name in country_info['sources']:
            try:
                feed = feedparser.parse(source_url)
                for entry in feed.entries[:15]:  # Daha fazla entry tara, filtreleyeceğiz
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                    published = entry.get('published', '')
                    
                    if not title:
                        continue
                    
                    # Tarih kontrolü
                    if not is_recent(published, hours=96):
                        continue
                    
                    # Yineleme kontrolü
                    if deduplicator.is_duplicate(title):
                        continue
                    
                    text = (title + ' ' + summary).lower()
                    
                    # 1. ZORUNLU: En az bir eğitim kelimesi İÇERMELİ
                    has_education_keyword = any(kw in text for kw in country_info['must_have'])
                    
                    if not has_education_keyword:
                        continue
                    
                    # 2. YASAK: Hiçbir yasak kelime İÇERMEMELİ
                    has_excluded = any(kw in text for kw in exclude_keywords)
                    
                    if has_excluded:
                        continue
                    
                    # Filtreleri geçti - ekle
                    country_news.append({
                        'title': title[:150],
                        'source': source_name,
                        'link': link,
                        'country': country_info['name'],
                        'flag': country_info['flag'],
                        'rank': country_info['rank'],
                        'needs_translation': True
                    })
                    
                    # Her ülkeden max 2 haber
                    if len(country_news) >= 2:
                        break
                
                if len(country_news) >= 2:
                    break
                    
            except Exception as e:
                print(f"   ⚠️ {country_info['name']} RSS hatası: {e}")
                continue
        
        if country_news:
            all_news[country_code] = country_news
    
    return all_news

# ══════════════════════════════════════════════════════════════════════════════
# 🌍 DÜNYADAN MAKRO EĞİTİM HABERLERİ
# ══════════════════════════════════════════════════════════════════════════════

def get_global_macro_education_news() -> List[Dict]:
    """
    Global eğitim politikası ve reform haberleri
    Mikro değil makro seviye
    """
    news = []
    
    # Uluslararası kuruluşlar
    global_sources = [
        ('https://www.unesco.org/en/rss.xml', 'UNESCO', 'Uluslararası'),
        ('https://blogs.worldbank.org/education/rss.xml', 'World Bank Education', 'Uluslararası'),
        ('https://www.oecd-ilibrary.org/rss/content/subject/education.xml', 'OECD', 'Uluslararası'),
        ('https://www.weforum.org/agenda/feed', 'World Economic Forum', 'Global'),
        ('https://www.brookings.edu/topic/education/feed/', 'Brookings', 'Policy'),
        ('https://www.theguardian.com/education/rss', 'Guardian Education', 'UK'),
        ('https://www.nytimes.com/svc/collections/v1/publish/www.nytimes.com/section/education/rss.xml', 'NYT Education', 'US'),
    ]
    
    macro_keywords = [
        'education policy', 'education reform', 'curriculum reform',
        'national assessment', 'pisa', 'timss', 'international comparison',
        'education budget', 'teacher shortage', 'education crisis',
        'ai in education', 'digital transformation', 'education inequality',
        'higher education', 'vocational training', 'lifelong learning',
        'education minister', 'education law', 'education system'
    ]
    
    for rss_url, source, category in global_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:6]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                published = entry.get('published', '')
                summary = entry.get('summary', '')[:200] if entry.get('summary') else ''
                
                if not is_recent(published, hours=72):
                    continue
                
                if deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_macro = any(kw in text for kw in macro_keywords)
                
                if is_macro:
                    news.append({
                        'title': title[:150],
                        'source': source,
                        'category': category,
                        'link': link,
                        'needs_translation': True
                    })
        except Exception as e:
            continue
    
    return news[:8]

# ══════════════════════════════════════════════════════════════════════════════
# 📚 BİLİMSEL MAKALELER - GENİŞLETİLMİŞ KAYNAKLAR
# ══════════════════════════════════════════════════════════════════════════════

def get_arxiv_papers_safe() -> List[Dict]:
    """
    arXiv'den makaleler - RSS ile (API key gerektirmez)
    Rate limit için bekleme süreli
    """
    papers = []
    
    # arXiv RSS kategorileri - eğitim odaklı
    arxiv_categories = [
        ('http://export.arxiv.org/rss/cs.CY', 'cs.CY', 'Bilgisayar & Toplum'),  # Education papers here
        ('http://export.arxiv.org/rss/cs.AI', 'cs.AI', 'Yapay Zeka'),
        ('http://export.arxiv.org/rss/cs.CL', 'cs.CL', 'Doğal Dil İşleme'),
        ('http://export.arxiv.org/rss/cs.LG', 'cs.LG', 'Makine Öğrenmesi'),
    ]
    
    # Eğitim ile ilgili anahtar kelimeler
    education_keywords = [
        'education', 'learning', 'student', 'teacher', 'classroom',
        'tutoring', 'assessment', 'curriculum', 'pedagogy', 'school',
        'adaptive learning', 'intelligent tutoring', 'educational',
        'e-learning', 'mooc', 'personalized learning', 'teaching'
    ]
    
    for rss_url, category, category_name in arxiv_categories:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:8]:
                title = entry.get('title', '').replace('\n', ' ')
                summary = entry.get('summary', '')[:500] if entry.get('summary') else ''
                link = entry.get('link', '')
                
                if not title or deduplicator.is_duplicate(title):
                    continue
                
                # Eğitim ile ilgili mi kontrol et
                text = (title + ' ' + summary).lower()
                is_education_related = any(kw in text for kw in education_keywords)
                
                papers.append({
                    'title': title[:200],
                    'summary': summary[:300],
                    'link': link,
                    'category': category_name,
                    'arxiv_cat': category,
                    'is_education_related': is_education_related,
                    'source': 'arXiv',
                    'needs_translation': True
                })
            
            time.sleep(2)  # Rate limit için bekleme
            
        except Exception as e:
            print(f"arXiv RSS hatası ({category}): {e}")
            continue
    
    # Eğitim ile ilgili olanları öne al
    papers = sorted(papers, key=lambda x: x.get('is_education_related', False), reverse=True)
    
    return papers[:8]

def get_eric_papers() -> List[Dict]:
    """
    ERIC benzeri kaynaklar - RSS ile (API key gerektirmez)
    Eğitim araştırma dergileri
    """
    papers = []
    
    # Eğitim araştırma dergileri RSS (ERIC yerine)
    sources = [
        ('https://bera-journals.onlinelibrary.wiley.com/feed/14678535/most-recent', 'British Journal of Educational Technology'),
        ('https://www.tandfonline.com/feed/rss/cjem20', 'Journal of Education for Teaching'),
        ('https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=10648&channel-name=Educational+Psychology+Review', 'Educational Psychology Review'),
        ('https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=rera&type=etoc&feed=rss', 'Review of Educational Research'),
    ]
    
    education_keywords = [
        'education', 'learning', 'student', 'teacher', 'assessment',
        'curriculum', 'pedagogy', 'instruction', 'classroom', 'school',
        'achievement', 'performance', 'technology', 'digital', 'online'
    ]
    
    for rss_url, source_name in sources:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                link = entry.get('link', '')
                
                if not title or deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_relevant = any(kw in text for kw in education_keywords)
                
                if is_relevant:
                    papers.append({
                        'title': title[:200],
                        'summary': summary,
                        'link': link,
                        'source': source_name,
                        'category': 'Eğitim Araştırması',
                        'needs_translation': True
                    })
        except Exception as e:
            print(f"Eğitim dergisi RSS hatası ({source_name}): {e}")
            continue
    
    return papers[:5]

def get_semantic_scholar_papers() -> List[Dict]:
    """
    AI & Eğitim makaleleri - RSS kaynakları ile (API key gerektirmez)
    """
    papers = []
    
    # AI ve Eğitim odaklı RSS kaynakları
    sources = [
        ('https://www.jair.org/index.php/jair/gateway/plugin/WebFeedGatewayPlugin/rss2', 'Journal of AI Research'),
        ('https://ieeexplore.ieee.org/rss/TOC42.XML', 'IEEE Transactions on Learning Technologies'),
        ('https://educationaltechnologyjournal.springeropen.com/articles/most-recent/rss.xml', 'Educational Technology Research'),
        ('https://aied.pub/index.php/IJAIED/gateway/plugin/WebFeedGatewayPlugin/rss2', 'Int. Journal of AI in Education'),
    ]
    
    ai_education_keywords = [
        'artificial intelligence', 'machine learning', 'deep learning',
        'intelligent tutoring', 'adaptive learning', 'personalized',
        'educational data mining', 'learning analytics', 'chatbot',
        'natural language', 'computer vision', 'neural network'
    ]
    
    for rss_url, source_name in sources:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:4]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                link = entry.get('link', '')
                
                if not title or deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_relevant = any(kw in text for kw in ai_education_keywords)
                
                if is_relevant:
                    papers.append({
                        'title': title[:200],
                        'summary': summary,
                        'link': link,
                        'source': source_name,
                        'category': 'AI & Eğitim',
                        'needs_translation': True
                    })
        except Exception as e:
            print(f"AI Education RSS hatası ({source_name}): {e}")
            continue
    
    return papers[:5]

def get_research_papers() -> List[Dict]:
    """
    Akademik araştırma makaleleri - SADECE eğitim, matematik, AI ile ilgili
    Çeşitli kaynaklar
    """
    papers = []
    
    # Eğitim odaklı kaynaklar
    education_sources = [
        ('https://www.frontiersin.org/journals/education/rss', 'Frontiers in Education'),
        ('https://educationaltechnologyjournal.springeropen.com/articles/most-recent/rss.xml', 'Ed Tech Research'),
        ('https://www.tandfonline.com/feed/rss/cede20', 'Educational Research'),
    ]
    
    # Matematik odaklı kaynaklar
    math_sources = [
        ('https://www.frontiersin.org/journals/applied-mathematics-and-statistics/rss', 'Frontiers Applied Math'),
    ]
    
    # AI odaklı kaynaklar
    ai_sources = [
        ('https://www.nature.com/natmachintell.rss', 'Nature Machine Intelligence'),
        ('http://feeds.nature.com/srep/rss/current', 'Nature Scientific Reports'),
    ]
    
    # Eğitim anahtar kelimeleri
    education_keywords = [
        'education', 'learning', 'student', 'teacher', 'school', 'classroom',
        'curriculum', 'pedagogy', 'instruction', 'assessment', 'teaching',
        'academic', 'educational', 'cognitive', 'achievement', 'performance',
        'literacy', 'numeracy', 'stem', 'mathematics education', 'science education',
        'pisa', 'timss', 'evaluation'
    ]
    
    # Matematik anahtar kelimeleri
    math_keywords = [
        'mathematics', 'mathematical', 'algebra', 'geometry', 'calculus',
        'statistics', 'probability', 'theorem', 'proof', 'equation',
        'algorithm', 'computation', 'optimization', 'numerical'
    ]
    
    # AI anahtar kelimeleri
    ai_keywords = [
        'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'nlp', 'natural language', 'computer vision',
        'reinforcement learning', 'transformer', 'large language model'
    ]
    
    # Kesinlikle istemediğimiz konular
    exclude_keywords = [
        'cancer', 'tumor', 'disease', 'clinical', 'patient', 'medical',
        'drug', 'therapy', 'cell', 'protein', 'gene', 'virus', 'bacteria',
        'mouse', 'rat', 'animal', 'plant', 'ecology', 'ocean', 'bridge',
        'earthquake', 'geology', 'thyroid', 'seismic', 'fire', 'flood'
    ]
    
    all_sources = education_sources + math_sources + ai_sources
    
    for rss_url, source_name in all_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:8]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:400] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')
                
                if not title:
                    continue
                
                if not is_recent(published, hours=168):  # 1 hafta
                    continue
                
                if deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                
                # En az bir ilgili anahtar kelime içermeli
                is_education = any(kw in text for kw in education_keywords)
                is_math = any(kw in text for kw in math_keywords)
                is_ai = any(kw in text for kw in ai_keywords)
                
                # Dışlanan konular içermemeli
                is_excluded = any(kw in text for kw in exclude_keywords)
                
                if (is_education or is_math or is_ai) and not is_excluded:
                    # Kategori belirle
                    if is_education:
                        category = 'Eğitim'
                    elif is_math:
                        category = 'Matematik'
                    else:
                        category = 'AI'
                    
                    papers.append({
                        'title': title[:200],
                        'summary': summary[:300],
                        'link': link,
                        'source': source_name,
                        'category': category,
                        'needs_translation': True
                    })
        except Exception as e:
            continue
    
    # Kaynak çeşitliliği
    final_papers = []
    source_counts = {}
    
    for paper in papers:
        source = paper.get('source', '')
        if source not in source_counts:
            source_counts[source] = 0
        
        if source_counts[source] < 2:
            final_papers.append(paper)
            source_counts[source] += 1
        
        if len(final_papers) >= 8:
            break
    
    return final_papers

# ══════════════════════════════════════════════════════════════════════════════
# 📊 ULUSLARARASI DEĞERLENDİRME RAPORLARI (PISA, TIMSS)
# ══════════════════════════════════════════════════════════════════════════════

def get_international_assessment_news() -> List[Dict]:
    """
    PISA, TIMSS ve uluslararası değerlendirme haberleri - RSS tabanlı
    """
    news = []
    
    # OECD Eğitim RSS
    oecd_sources = [
        ('https://www.oecd.org/education/rss/', 'OECD Education'),
        ('https://oecdedutoday.com/feed/', 'OECD Education Today'),
    ]
    
    pisa_timss_keywords = [
        'pisa', 'timss', 'pirls', 'talis', 'international assessment',
        'student achievement', 'education ranking', 'oecd education',
        'learning outcomes', 'education performance', 'education comparison'
    ]
    
    for rss_url, source in oecd_sources:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:6]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                summary = entry.get('summary', '')[:200] if entry.get('summary') else ''
                
                if not title or deduplicator.is_duplicate(title):
                    continue
                
                text = (title + ' ' + summary).lower()
                is_relevant = any(kw in text for kw in pisa_timss_keywords)
                
                if is_relevant:
                    news.append({
                        'title': title[:150],
                        'source': source,
                        'link': link,
                        'type': 'Uluslararası Değerlendirme',
                        'needs_translation': True
                    })
        except Exception as e:
            print(f"OECD RSS hatası ({source}): {e}")
            continue
    
    # Eğitim karşılaştırma haberleri
    comparison_sources = [
        ('https://www.brookings.edu/topic/global-education/feed/', 'Brookings Global Education'),
        ('https://gemreportunesco.wordpress.com/feed/', 'UNESCO GEM Report'),
    ]
    
    for rss_url, source in comparison_sources:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:4]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                
                if not title or deduplicator.is_duplicate(title):
                    continue
                
                news.append({
                    'title': title[:150],
                    'source': source,
                    'link': link,
                    'type': 'Global Eğitim',
                    'needs_translation': True
                })
        except:
            continue
    
    return news[:6]

def get_turkey_assessment_research() -> List[Dict]:
    """
    Türkiye ulusal izleme ve değerlendirme araştırmaları - RSS tabanlı
    """
    research = []
    
    # Türkiye akademik dergileri RSS
    sources = [
        ('https://dergipark.org.tr/tr/pub/egam/rss', 'Eğitimde ve Psikolojide Ölçme'),
        ('https://dergipark.org.tr/tr/pub/kefdergi/rss', 'Kastamonu Eğitim'),
        ('https://dergipark.org.tr/tr/pub/aod/rss', 'Anadolu Öğretmen'),
        ('https://dergipark.org.tr/tr/pub/ted/rss', 'Türk Eğitim Bilimleri'),
    ]
    
    keywords = [
        'pisa', 'timss', 'abide', 'lgs', 'yks', 'ölçme', 'değerlendirme',
        'başarı', 'performans', 'matematik', 'fen', 'okuma', 'ulusal'
    ]
    
    for rss_url, source in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                
                if not title or deduplicator.is_duplicate(title):
                    continue
                
                text = title.lower()
                is_relevant = any(kw in text for kw in keywords)
                
                if is_relevant:
                    research.append({
                        'title': title[:150],
                        'source': source,
                        'link': link,
                        'type': 'Türkiye Araştırma'
                    })
        except Exception as e:
            continue
    
    # Sabit önemli kaynaklar
    static_sources = [
        {
            'title': 'ABİDE - MEB Akademik Becerilerin İzlenmesi ve Değerlendirilmesi',
            'source': 'MEB',
            'link': 'https://abide.meb.gov.tr',
            'type': 'Ulusal İzleme'
        },
        {
            'title': 'TEDMEM Eğitim Değerlendirme Raporları',
            'source': 'TEDMEM',
            'link': 'https://tedmem.org',
            'type': 'Araştırma Merkezi'
        },
        {
            'title': 'ERG Eğitim İzleme Raporu',
            'source': 'Eğitim Reformu Girişimi',
            'link': 'https://www.egitimreformugirisimi.org',
            'type': 'İzleme Raporu'
        }
    ]
    
    # Statik kaynakları da ekle (yineleme yoksa)
    for item in static_sources:
        if not deduplicator.is_duplicate(item['title']):
            research.append(item)
    
    return research[:6]

# ══════════════════════════════════════════════════════════════════════════════
# 📖 EĞİTİM DERGİ VE KİTAPLARI
# ══════════════════════════════════════════════════════════════════════════════

def get_education_journals() -> List[Dict]:
    """
    Eğitim dergileri ve yeni kitaplar
    """
    journals = []
    
    # Önemli eğitim dergileri RSS
    sources = [
        ('https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=rera&type=etoc&feed=rss', 'Review of Educational Research'),
        ('https://www.tandfonline.com/feed/rss/tedp20', 'Educational Psychologist'),
        ('https://www.journals.elsevier.com/computers-and-education/rss', 'Computers & Education'),
        ('https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=11423&channel-name=Educational+Technology+Research+and+Development', 'ETR&D'),
    ]
    
    for rss_url, source in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:3]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                
                if title and not deduplicator.is_duplicate(title):
                    journals.append({
                        'title': title[:150],
                        'source': source,
                        'link': link,
                        'type': 'Dergi Makalesi',
                        'needs_translation': True
                    })
        except:
            continue
    
    return journals[:6]

# ══════════════════════════════════════════════════════════════════════════════
# ÖĞRENCİ GÜNDEMİ - DİNAMİK (Gerçek Trend Veriler)
# ══════════════════════════════════════════════════════════════════════════════

def get_student_trending_topics() -> List[Dict]:
    """
    Öğrencilerin gerçekten konuştuğu konular
    Kaynaklar: Ekşi Sözlük, Reddit, Öğrenci Forumları, Twitter/X trendleri
    """
    trending = []
    
    # Eğitim ile ilgili anahtar kelimeler
    education_keywords = [
        'lgs', 'yks', 'tyt', 'ayt', 'ösym', 'sınav', 'okul', 'ders',
        'öğretmen', 'öğrenci', 'üniversite', 'lise', 'matematik',
        'fizik', 'kimya', 'biyoloji', 'türkçe', 'tarih', 'coğrafya',
        'müfredat', 'meb', 'eğitim', 'kpss', 'ales', 'yds', 'dgs',
        'sınıf', 'not', 'karne', 'tatil', 'burs', 'yurt', 'kredi',
        'deneme', 'soru', 'konu', 'tercih', 'puan', 'sıralama',
        'dershane', 'kurs', 'ödev', 'proje', 'staj', 'mezuniyet'
    ]
    
    # 1. EKŞİ SÖZLÜK - Gündem
    print("   📱 Ekşi Sözlük taranıyor...")
    try:
        urls = [
            "https://eksisozluk.com/basliklar/gundem",
            "https://eksisozluk.com/basliklar/debe",  # Dünün en beğenilen entryleri
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    
                    # Başlık listesini bul
                    topic_links = soup.select('ul.topic-list li a') or soup.select('a.topic-title')
                    
                    for link in topic_links[:30]:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        
                        # Entry sayısını bul
                        small = link.find('small')
                        entry_count = small.get_text(strip=True) if small else ''
                        
                        if title and len(title) > 3 and len(title) < 100:
                            # Eğitim ile ilgili mi?
                            if any(kw in title.lower() for kw in education_keywords):
                                if not any(t['topic'].lower() == title.lower() for t in trending):
                                    trending.append({
                                        'topic': title[:80],
                                        'source': 'Ekşi Sözlük',
                                        'entry_count': entry_count,
                                        'category': 'Gündem',
                                        'link': f"https://eksisozluk.com{href}" if href.startswith('/') else href
                                    })
                time.sleep(0.5)
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Ekşi Sözlük hatası: {e}")
    
    # 2. REDDIT - r/Turkey, r/KGBTR (öğrenci paylaşımları)
    print("   📱 Reddit taranıyor...")
    try:
        subreddits = [
            'https://www.reddit.com/r/Turkey/hot.json',
            'https://www.reddit.com/r/KGBTR/hot.json',
        ]
        
        headers = {
            'User-Agent': 'EducationBot/3.0 (Educational News Aggregator)'
        }
        
        for subreddit_url in subreddits:
            try:
                r = requests.get(subreddit_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    posts = data.get('data', {}).get('children', [])
                    
                    for post in posts[:25]:
                        post_data = post.get('data', {})
                        title = post_data.get('title', '')
                        score = post_data.get('score', 0)
                        permalink = post_data.get('permalink', '')
                        
                        if title and any(kw in title.lower() for kw in education_keywords):
                            if not any(t['topic'].lower() == title.lower()[:50] for t in trending):
                                trending.append({
                                    'topic': title[:80],
                                    'source': 'Reddit',
                                    'score': f"⬆️ {score}",
                                    'category': 'Sosyal Medya',
                                    'link': f"https://reddit.com{permalink}"
                                })
                time.sleep(0.5)
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Reddit hatası: {e}")
    
    # 3. ÖĞRENCİ FORUMLARI
    print("   📱 Öğrenci forumları taranıyor...")
    try:
        forums = [
            ('https://www.memurlar.net/haber/egitim/rss/', 'Memurlar.net'),
            ('https://www.kamubiz.com/feed/', 'KamuBiz'),
        ]
        
        for forum_url, forum_name in forums:
            try:
                feed = feedparser.parse(forum_url)
                for entry in feed.entries[:10]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    
                    if title and any(kw in title.lower() for kw in education_keywords):
                        if not any(t['topic'].lower() == title.lower()[:50] for t in trending):
                            trending.append({
                                'topic': title[:80],
                                'source': forum_name,
                                'category': 'Forum',
                                'link': link
                            })
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Forum hatası: {e}")
    
    # 4. TWITTER/X TRENDLERİ - Eğitim hashtagleri
    print("   📱 Twitter trendleri taranıyor...")
    try:
        # Nitter instance'ları (Twitter alternatifi - API gerektirmez)
        nitter_urls = [
            'https://nitter.poast.org/search?f=tweets&q=%23LGS',
            'https://nitter.poast.org/search?f=tweets&q=%23YKS',
            'https://nitter.poast.org/search?f=tweets&q=%23TYT',
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        for nitter_url in nitter_urls[:2]:
            try:
                r = requests.get(nitter_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    tweets = soup.select('.tweet-content') or soup.select('.timeline-item')
                    
                    for tweet in tweets[:5]:
                        text = tweet.get_text(strip=True)[:100]
                        if text and len(text) > 20:
                            if not any(t['topic'].lower() == text.lower()[:40] for t in trending):
                                trending.append({
                                    'topic': text[:80],
                                    'source': 'Twitter/X',
                                    'category': 'Sosyal Medya'
                                })
                time.sleep(0.5)
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Twitter hatası: {e}")
    
    # 5. YOUTUBE - Eğitim trendleri
    print("   📱 YouTube trendleri taranıyor...")
    try:
        # YouTube RSS - Popüler eğitim kanalları
        youtube_channels = [
            ('https://www.youtube.com/feeds/videos.xml?channel_id=UCvMZ2d5r47nGVNPzI6hGX8A', 'Tonguç Akademi'),
            ('https://www.youtube.com/feeds/videos.xml?channel_id=UC6JYy4gZQaoNLbXxBn4cFjg', 'Hocalara Geldik'),
        ]
        
        for channel_url, channel_name in youtube_channels:
            try:
                feed = feedparser.parse(channel_url)
                for entry in feed.entries[:3]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    
                    if title:
                        if not any(t['topic'].lower() == title.lower()[:40] for t in trending):
                            trending.append({
                                'topic': title[:80],
                                'source': f'YouTube - {channel_name}',
                                'category': 'Video',
                                'link': link
                            })
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ YouTube hatası: {e}")
    
    # 6. GOOGLE TRENDS - Türkiye eğitim aramaları
    print("   📱 Google Trends kontrol ediliyor...")
    try:
        # Google Trends RSS (varsa)
        trends_url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=TR"
        feed = feedparser.parse(trends_url)
        
        for entry in feed.entries[:20]:
            title = entry.get('title', '')
            
            if title and any(kw in title.lower() for kw in education_keywords):
                if not any(t['topic'].lower() == title.lower() for t in trending):
                    trending.append({
                        'topic': title[:80],
                        'source': 'Google Trends',
                        'category': 'Arama Trendi'
                    })
    except Exception as e:
        print(f"   ⚠️ Google Trends hatası: {e}")
    
    # 7. DONANIM HABER / TEKNOLOJİ FORUMLARI (Öğrenci paylaşımları)
    print("   📱 Teknoloji forumları taranıyor...")
    try:
        tech_forums = [
            ('https://forum.donanimhaber.com/rss.ashx?CategoryID=35', 'Donanım Haber'),
        ]
        
        for forum_url, forum_name in tech_forums:
            try:
                feed = feedparser.parse(forum_url)
                for entry in feed.entries[:10]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    
                    if title and any(kw in title.lower() for kw in education_keywords):
                        if not any(t['topic'].lower() == title.lower()[:40] for t in trending):
                            trending.append({
                                'topic': title[:80],
                                'source': forum_name,
                                'category': 'Forum',
                                'link': link
                            })
            except:
                continue
    except Exception as e:
        print(f"   ⚠️ Forum hatası: {e}")
    
    # Sonuçları sırala - kaynak çeşitliliğine göre
    # Her kaynaktan en fazla 2 tane al
    final_trending = []
    source_counts = {}
    
    for item in trending:
        source = item.get('source', 'Diğer')
        if source not in source_counts:
            source_counts[source] = 0
        
        if source_counts[source] < 2:
            final_trending.append(item)
            source_counts[source] += 1
        
        if len(final_trending) >= 10:
            break
    
    # Eğer yeterli veri gelmezse fallback
    if len(final_trending) < 3:
        print("   ⚠️ Yeterli trend bulunamadı, alternatif konular ekleniyor...")
        today = datetime.now()
        
        fallback_topics = [
            {'topic': f'LGS 2026 hazırlık stratejileri', 'source': 'Öneri', 'category': 'LGS'},
            {'topic': f'YKS tercih döneminde dikkat edilecekler', 'source': 'Öneri', 'category': 'YKS'},
            {'topic': 'Sınav kaygısı ile başa çıkma', 'source': 'Öneri', 'category': 'Motivasyon'},
        ]
        
        for topic in fallback_topics:
            if len(final_trending) < 8:
                final_trending.append(topic)
    
    return final_trending[:10]

# ══════════════════════════════════════════════════════════════════════════════
# MOTİVASYON MESAJI
# ══════════════════════════════════════════════════════════════════════════════

def get_daily_motivation() -> Dict:
    """Günün motivasyon mesajı"""
    today = datetime.now()
    day_of_week = today.strftime('%A')
    
    themes = {
        'Monday': 'Hafta başı enerjisi',
        'Tuesday': 'Hedef belirleme',
        'Wednesday': 'Yarı yol motivasyonu',
        'Thursday': 'Azim ve kararlılık',
        'Friday': 'Hafta sonu öncesi sprint',
        'Saturday': 'Verimli hafta sonu',
        'Sunday': 'Dinlenme ve planlama'
    }
    
    theme = themes.get(day_of_week, 'Başarı')
    
    if GEMINI_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_KEY)
            
            # Sınava kalan gün hesapla
            lgs_date = datetime(2026, 6, 14)
            days_left = (lgs_date.date() - today.date()).days
            
            prompt = f"""LGS veya YKS'ye hazırlanan bir öğrenci için kısa ve motive edici bir mesaj yaz.

Tema: {theme}
LGS'ye kalan gün: {days_left}

Kurallar:
1. Maksimum 2-3 cümle
2. Samimi ve cesaretlendirici
3. Somut çalışma önerisi içersin
4. Emoji kullan
5. Türkçe yaz"""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            return {
                'message': response.text.strip(),
                'theme': theme,
                'generated': True
            }
        except Exception as e:
            print(f"Motivasyon hatası: {e}")
    
    # Varsayılan
    import random
    messages = [
        "💪 Her gün bir adım daha ileri! Bugün de elinden gelenin en iyisini yap.\n📚 Öneri: 25 dakika odaklanarak çalış.",
        "🌟 Başarı, her gün yapılan küçük adımların toplamıdır.\n📚 Öneri: Zayıf bir konuyu tekrar et.",
        "🎯 Hedefe odaklan! Sen başarabilirsin!\n📚 Öneri: Bugün en az 20 soru çöz.",
    ]
    
    return {
        'message': random.choice(messages),
        'theme': theme,
        'generated': False
    }

# ══════════════════════════════════════════════════════════════════════════════
# ÇEVİRİ FONKSİYONU
# ══════════════════════════════════════════════════════════════════════════════

def translate_to_turkish(text: str, is_headline: bool = True) -> str:
    """Gemini ile çeviri"""
    if not text or not GEMINI_KEY or not genai:
        return text
    
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        
        prompt = f"""Aşağıdaki haber başlığını Türkçeye çevir.
Teknik terimleri (AI, PISA, STEM, OECD) olduğu gibi bırak.
Sadece çeviriyi yaz.

İngilizce: {text}
Türkçe:"""
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        translated = response.text.strip()
        if translated.lower().startswith("türkçe"):
            translated = translated.split(":", 1)[-1].strip()
        
        return translated if translated else text
    except:
        return text

# ══════════════════════════════════════════════════════════════════════════════
# GÜNÜN ÖZETİ (AI)
# ══════════════════════════════════════════════════════════════════════════════

def generate_daily_summary(all_news: Dict) -> str:
    """Gemini ile günlük analiz"""
    if not GEMINI_KEY or not genai:
        return ""
    
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        
        news_text = ""
        
        # Haberleri topla
        if all_news.get('turkey_news'):
            news_text += "=== TÜRKİYE ===\n"
            for n in all_news['turkey_news'][:5]:
                news_text += f"- {n['title']}\n"
        
        if all_news.get('ai_news'):
            news_text += "\n=== AI & EDTECH ===\n"
            for n in all_news['ai_news'][:4]:
                news_text += f"- {n['title']}\n"
        
        if all_news.get('pisa_news'):
            news_text += "\n=== PISA ÜLKELERİ ===\n"
            for country, items in all_news['pisa_news'].items():
                for n in items[:2]:
                    news_text += f"- [{n['country']}] {n['title']}\n"
        
        if all_news.get('papers'):
            news_text += "\n=== ARAŞTIRMALAR ===\n"
            for p in all_news['papers'][:3]:
                news_text += f"- {p['title']}\n"
        
        prompt = f"""Deneyimli bir eğitim analisti olarak aşağıdaki haberleri analiz et:

{news_text}

GÖREV: Öğretmen ve öğrenciler için kısa bir günlük brifing hazırla:

🇹🇷 TÜRKİYE'DE BUGÜN: (2-3 madde)
🤖 AI & TEKNOLOJİ: (2 madde)
🌍 DÜNYADAN: (2 madde - PISA ülkelerinden dersler)
💡 PRATİK ÖNERİ: (1 madde)

Kurallar:
- Her madde 1 cümle
- Haberleri yorumla, sadece özetleme
- Türkçe, akıcı dil
- Toplam 200 kelime"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"Özet hatası: {e}")
        return ""

# ══════════════════════════════════════════════════════════════════════════════
# RAPOR OLUŞTURMA
# ══════════════════════════════════════════════════════════════════════════════

def generate_report() -> str:
    """Günlük eğitim raporu"""
    
    # Her raporda deduplicator'ı sıfırla
    deduplicator.reset()
    
    report = []
    today = datetime.now()
    
    # Başlık
    report.append("═" * 50)
    report.append("📚 EĞİTİM GÜNDEM RAPORU v3.0")
    report.append(f"📅 {format_turkish_date(today, include_day=True)}")
    report.append("═" * 50)
    report.append("")
    
    # 1. SINAV TAKVİMİ
    print("📅 Sınav takvimi...")
    countdown = get_exam_countdown()
    
    report.append("━" * 50)
    report.append("⏰ SINAV TAKVİMİ & GERİ SAYIM")
    report.append("━" * 50)
    
    for item in countdown['countdowns']:
        if item['is_exam']:
            report.append(f"\n{item['name']}")
            report.append(f"   📆 {item['date']}")
            report.append(f"   ⏳ {item['time_str']}")
    
    report.append("")
    
    # 2. TÜRKİYE EĞİTİM GÜNDEMİ
    print("🇹🇷 Türkiye haberleri...")
    meb_news = get_meb_news()
    turkey_news = get_education_news_turkey()
    
    report.append("━" * 50)
    report.append("🏛️ MEB & TÜRKİYE EĞİTİM GÜNDEMİ")
    report.append("━" * 50)
    
    all_turkey = meb_news + turkey_news
    shown = 0
    for news in all_turkey[:8]:
        if shown >= 6:
            break
        icon = "🔴" if news.get('is_exam_related') else "📰"
        report.append(f"\n{icon} {news['title']}")
        report.append(f"   📍 {news['source']}")
        if news.get('link'):
            report.append(f"   🔗 {news.get('link', '')}")
        shown += 1
    
    report.append("")
    
    # 3. YAPAY ZEKA & EĞİTİM TEKNOLOJİSİ
    print("🤖 AI haberleri...")
    ai_news = get_ai_education_news()
    
    report.append("━" * 50)
    report.append("🤖 YAPAY ZEKA & EĞİTİM TEKNOLOJİSİ")
    report.append("━" * 50)
    
    # LLM ve AI gelişmelerini ayır
    llm_news = [n for n in ai_news if n.get('is_llm') or n.get('category') in ['LLM', 'AI Haber', 'Araştırma']]
    edtech_news = [n for n in ai_news if n.get('category') in ['EdTech', 'Yükseköğretim']]
    
    translate_count = 0
    
    # LLM Gelişmeleri
    if llm_news:
        report.append("\n🧠 BÜYÜK DİL MODELLERİ & AI GELİŞMELERİ:")
        for news in llm_news[:4]:
            if news.get('needs_translation') and translate_count < 4:
                title_tr = translate_to_turkish(news['title'])
                translate_count += 1
                time.sleep(0.3)
            else:
                title_tr = news['title']
            
            category_icon = {
                'LLM': '🔮',
                'AI Haber': '📰',
                'Araştırma': '🔬'
            }.get(news.get('category', ''), '🔹')
            
            report.append(f"\n{category_icon} {title_tr[:90]}")
            report.append(f"   📍 {news['source']} ({news.get('category', '')})")
            if news.get('link'):
                report.append(f"   🔗 {news.get('link', '')}")
    
    # EdTech Haberleri
    if edtech_news:
        report.append("\n📱 EĞİTİM TEKNOLOJİSİ (EdTech):")
        for news in edtech_news[:3]:
            if news.get('needs_translation') and translate_count < 6:
                title_tr = translate_to_turkish(news['title'])
                translate_count += 1
                time.sleep(0.3)
            else:
                title_tr = news['title']
            
            report.append(f"\n🔹 {title_tr[:90]}")
            report.append(f"   📍 {news['source']}")
            if news.get('link'):
                report.append(f"   🔗 {news.get('link', '')}")
    
    # Gemini ile AI gelişmelerinin eğitimde kullanım analizi
    if ai_news and GEMINI_KEY and genai:
        print("   🤖 AI gelişmeleri eğitim analizi yapılıyor...")
        try:
            client = genai.Client(api_key=GEMINI_KEY)
            
            # Haberleri topla
            news_titles = [n['title'] for n in ai_news[:6]]
            news_text = "\n".join([f"- {t}" for t in news_titles])
            
            prompt = f"""Aşağıdaki yapay zeka ve eğitim teknolojisi haberlerini analiz et:

{news_text}

GÖREV: Bu gelişmelerin Türkiye'deki öğretmen ve öğrenciler için pratik uygulamalarını 3-4 maddede özetle.

Format:
💡 [Kısa başlık]: [1 cümle açıklama]

Kurallar:
- Her madde 1-2 cümle
- Pratik ve uygulanabilir öneriler
- Türkçe yaz
- Toplam 100 kelime"""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if response.text:
                report.append("\n📊 EĞİTİMDE KULLANIM ANALİZİ (Gemini):")
                report.append(response.text.strip())
        except Exception as e:
            print(f"   ⚠️ AI analiz hatası: {e}")
    
    report.append("")
    
    # 4. MATEMATİK DÜNYASINDAN
    print("➕ Matematik haberleri...")
    math_news = get_math_news()
    
    report.append("━" * 50)
    report.append("➕ MATEMATİK DÜNYASINDAN")
    report.append("━" * 50)
    
    for news in math_news[:4]:
        if news.get('needs_translation') and translate_count < 5:
            title_tr = translate_to_turkish(news['title'])
            translate_count += 1
            time.sleep(0.3)
        else:
            title_tr = news['title']
        
        report.append(f"\n📐 {title_tr[:90]}")
        report.append(f"   📍 {news['source']}")
        if news.get('link'):
            report.append(f"   🔗 {news['link']}")
    
    report.append("")
    
    # 4.5. 🎬 YOUTUBE AI VİDEOLARI - YENİ BÖLÜM
    print("🎬 YouTube AI videoları çekiliyor...")
    youtube_videos = get_youtube_ai_videos()
    
    report.append("━" * 50)
    report.append("🎬 YOUTUBE'DA AI KANALLARI")
    report.append("━" * 50)
    report.append("📺 Takip edilmesi önerilen popüler AI kanalları:")
    
    if youtube_videos:
        # Kaynak türüne göre kontrol
        is_curated = any(v.get('source') == 'curated' for v in youtube_videos)
        
        if is_curated:
            # Curated liste - kategorilere göre grupla
            report.append("\n🔬 ARAŞTIRMA & TEKNİK:")
            research = [v for v in youtube_videos if v.get('category') in ['AI Araştırma', 'Matematik/AI']]
            for video in research[:4]:
                report.append(f"\n▶️ {video['channel']} ({video['subscribers']})")
                report.append(f"   📝 {video.get('title', '').replace('🔥 ', '')}")
                report.append(f"   🔗 {video['link']}")
            
            report.append("\n🛠️ AI ARAÇLAR & PRATİK:")
            tools = [v for v in youtube_videos if v.get('category') in ['AI Araçlar', 'AI Prompt']]
            for video in tools[:3]:
                report.append(f"\n▶️ {video['channel']} ({video['subscribers']})")
                report.append(f"   📝 {video.get('title', '').replace('🔥 ', '')}")
                report.append(f"   🔗 {video['link']}")
            
            report.append("\n📰 HABER & ANALİZ:")
            news = [v for v in youtube_videos if v.get('category') in ['AI Analiz', 'Tech/AI', 'AI Podcast']]
            for video in news[:3]:
                report.append(f"\n▶️ {video['channel']} ({video['subscribers']})")
                report.append(f"   📝 {video.get('title', '').replace('🔥 ', '')}")
                report.append(f"   🔗 {video['link']}")
            
            report.append("\n🏢 RESMİ KANALLAR:")
            official = [v for v in youtube_videos if v.get('category') == 'Resmi']
            for video in official[:2]:
                report.append(f"\n▶️ {video['channel']} ({video['subscribers']})")
                report.append(f"   📝 {video.get('title', '').replace('🔥 ', '')}")
                report.append(f"   🔗 {video['link']}")
            
            report.append(f"\n💡 Bu kanalları YouTube'da takip ederek AI dünyasındaki")
            report.append(f"   son gelişmelerden haberdar olabilirsiniz!")
        else:
            # RSS'den çekilen gerçek videolar
            report.append("\n📹 SON YAYINLANAN AI VİDEOLARI:")
            
            research_videos = [v for v in youtube_videos if v.get('category') in ['AI Araştırma', 'Matematik/AI']]
            tools_videos = [v for v in youtube_videos if v.get('category') in ['AI Araçlar', 'AI Prompt']]
            news_videos = [v for v in youtube_videos if v.get('category') in ['AI Analiz', 'Tech/AI', 'AI Podcast']]
            official_videos = [v for v in youtube_videos if v.get('category') == 'Resmi']
            
            if research_videos:
                report.append("\n🔬 ARAŞTIRMA & TEKNİK:")
                for video in research_videos[:3]:
                    report.append(f"\n▶️ {video['title']}")
                    report.append(f"   📺 {video['channel']} ({video['subscribers']})")
                    report.append(f"   🔗 {video['link']}")
            
            if tools_videos:
                report.append("\n🛠️ AI ARAÇLAR & PRATİK:")
                for video in tools_videos[:3]:
                    report.append(f"\n▶️ {video['title']}")
                    report.append(f"   📺 {video['channel']} ({video['subscribers']})")
                    report.append(f"   🔗 {video['link']}")
            
            if news_videos:
                report.append("\n📰 HABER & ANALİZ:")
                for video in news_videos[:3]:
                    report.append(f"\n▶️ {video['title']}")
                    report.append(f"   📺 {video['channel']} ({video['subscribers']})")
                    report.append(f"   🔗 {video['link']}")
            
            if official_videos:
                report.append("\n🏢 RESMİ DUYURULAR:")
                for video in official_videos[:2]:
                    report.append(f"\n▶️ {video['title']}")
                    report.append(f"   📺 {video['channel']}")
                    report.append(f"   🔗 {video['link']}")
            
            report.append(f"\n📊 Toplam {len(youtube_videos)} yeni AI videosu bulundu")
    else:
        report.append("\n• Şu an yeni AI videosu bulunamadı")
    
    report.append("")
    
    # 5. PISA LİDERLERİNDEN
    print("🏆 PISA liderleri haberleri...")
    pisa_news = get_pisa_leaders_news()
    
    report.append("━" * 50)
    report.append("🏆 PISA LİDERLERİNDEN EĞİTİM HABERLERİ")
    report.append("━" * 50)
    
    for country_code, news_list in pisa_news.items():
        for news in news_list[:2]:
            if translate_count < 8:
                title_tr = translate_to_turkish(news['title'])
                translate_count += 1
                time.sleep(0.3)
            else:
                title_tr = news['title']
            
            report.append(f"\n{news['flag']} {news['country']} ({news['rank']})")
            report.append(f"   {title_tr[:85]}")
            report.append(f"   📍 {news['source']}")
            if news.get('link'):
                report.append(f"   🔗 {news.get('link', '')}")
    
    report.append("")
    
    # 6. GLOBAL MAKRO HABERLER
    print("🌍 Global haberler...")
    global_news = get_global_macro_education_news()
    
    report.append("━" * 50)
    report.append("🌍 DÜNYADAN EĞİTİM POLİTİKALARI")
    report.append("━" * 50)
    
    for news in global_news[:4]:
        if translate_count < 10:
            title_tr = translate_to_turkish(news['title'])
            translate_count += 1
            time.sleep(0.3)
        else:
            title_tr = news['title']
        
        report.append(f"\n🔸 {title_tr[:90]}")
        report.append(f"   📍 {news['source']} ({news.get('category', '')})")
    
    report.append("")
    
    # 7. BİLİMSEL MAKALELER
    print("📄 Bilimsel makaleler...")
    arxiv_papers = get_arxiv_papers_safe()
    eric_papers = get_eric_papers()
    research_papers = get_research_papers()
    
    report.append("━" * 50)
    report.append("📄 BİLİMSEL MAKALELER & ARAŞTIRMALAR")
    report.append("━" * 50)
    
    # arXiv
    if arxiv_papers:
        report.append("\n🎓 arXiv - EĞİTİM & AI:")
        for paper in arxiv_papers[:3]:
            if translate_count < 12:
                title_tr = translate_to_turkish(paper['title'])
                translate_count += 1
                time.sleep(0.3)
            else:
                title_tr = paper['title']
            report.append(f"\n📑 {title_tr[:100]}")
            if paper.get('link'):
                report.append(f"   🔗 {paper['link']}")
    
    # ERIC
    if eric_papers:
        report.append("\n📚 EĞİTİM ARAŞTIRMALARI:")
        for paper in eric_papers[:2]:
            if translate_count < 14:
                title_tr = translate_to_turkish(paper['title'])
                translate_count += 1
                time.sleep(0.3)
            else:
                title_tr = paper['title']
            report.append(f"\n📖 {title_tr[:100]}")
            if paper.get('link'):
                report.append(f"   🔗 {paper['link']}")
    
    # Research papers - kategoriye göre grupla
    if research_papers:
        # Kategorilere ayır
        edu_papers = [p for p in research_papers if p.get('category') == 'Eğitim']
        math_papers = [p for p in research_papers if p.get('category') == 'Matematik']
        ai_papers = [p for p in research_papers if p.get('category') == 'AI']
        
        if edu_papers:
            report.append("\n🎓 EĞİTİM BİLİMLERİ:")
            for paper in edu_papers[:2]:
                if translate_count < 16:
                    title_tr = translate_to_turkish(paper['title'])
                    translate_count += 1
                    time.sleep(0.3)
                else:
                    title_tr = paper['title']
                report.append(f"\n📖 {title_tr[:100]}")
                report.append(f"   📍 {paper['source']}")
        
        if math_papers:
            report.append("\n📐 MATEMATİK ARAŞTIRMALARI:")
            for paper in math_papers[:2]:
                if translate_count < 18:
                    title_tr = translate_to_turkish(paper['title'])
                    translate_count += 1
                    time.sleep(0.3)
                else:
                    title_tr = paper['title']
                report.append(f"\n📖 {title_tr[:100]}")
                report.append(f"   📍 {paper['source']}")
        
        if ai_papers:
            report.append("\n🤖 YAPAY ZEKA ARAŞTIRMALARI:")
            for paper in ai_papers[:2]:
                if translate_count < 20:
                    title_tr = translate_to_turkish(paper['title'])
                    translate_count += 1
                    time.sleep(0.3)
                else:
                    title_tr = paper['title']
                report.append(f"\n📖 {title_tr[:100]}")
                report.append(f"   📍 {paper['source']}")
    
    report.append("")
    
    # 8. ULUSLARARASI DEĞERLENDİRME
    print("📊 Uluslararası değerlendirme...")
    assessment_news = get_international_assessment_news()
    turkey_research = get_turkey_assessment_research()
    
    report.append("━" * 50)
    report.append("📊 ULUSLARARASI DEĞERLENDİRME (PISA/TIMSS)")
    report.append("━" * 50)
    
    if assessment_news:
        for item in assessment_news[:3]:
            report.append(f"\n📈 {item['title'][:90]}")
            report.append(f"   📍 {item['source']} ({item.get('type', '')})")
    
    if turkey_research:
        report.append("\n🇹🇷 TÜRKİYE ULUSAL İZLEME:")
        for item in turkey_research[:2]:
            report.append(f"\n📋 {item['title'][:90]}")
            report.append(f"   📍 {item['source']}")
    
    report.append("")
    
    # 9. ÖĞRENCİ GÜNDEMİ
    print("🔥 Öğrenci gündemi (sosyal medya, forumlar)...")
    trending = get_student_trending_topics()
    
    report.append("━" * 50)
    report.append("🔥 ÖĞRENCİ GÜNDEMİ (Trend Konular)")
    report.append("━" * 50)
    
    if trending:
        for topic in trending[:8]:
            source = topic.get('source', '')
            category = topic.get('category', '')
            score = topic.get('score', '')
            entry_count = topic.get('entry_count', '')
            link = topic.get('link', '')
            
            # Kaynak ikonu
            source_icon = {
                'Ekşi Sözlük': '📗',
                'Reddit': '🔴',
                'Twitter/X': '🐦',
                'YouTube': '▶️',
                'Google Trends': '📈',
                'Forum': '💬',
            }.get(topic.get('source', '').split(' - ')[0], '📌')
            
            line = f"\n{source_icon} {topic['topic']}"
            
            # Meta bilgiler
            meta = []
            if source:
                meta.append(source)
            if entry_count:
                meta.append(f"{entry_count} entry")
            if score:
                meta.append(score)
            if category:
                meta.append(f"[{category}]")
            
            if meta:
                report.append(line)
                report.append(f"   📍 {' | '.join(meta)}")
                if link:
                    report.append(f"   🔗 {link}")
            else:
                report.append(line)
    else:
        report.append("\n• Şu an aktif trend konusu bulunamadı")
    
    report.append("")
    
    # 10. MOTİVASYON
    print("💪 Motivasyon...")
    motivation = get_daily_motivation()
    
    report.append("━" * 50)
    report.append("💪 GÜNÜN MOTİVASYONU")
    report.append("━" * 50)
    report.append("")
    report.append(motivation['message'])
    report.append("")
    
    # 11. GÜNÜN ÖZETİ
    print("📝 Günün özeti...")
    all_news_data = {
        'turkey_news': meb_news + turkey_news,
        'ai_news': ai_news,
        'pisa_news': pisa_news,
        'papers': arxiv_papers + eric_papers + research_papers
    }
    summary = generate_daily_summary(all_news_data)
    
    if summary:
        report.append("━" * 50)
        report.append("📊 GÜNÜN ANALİZİ")
        report.append("━" * 50)
        report.append("")
        report.append(summary)
        report.append("")
    
    # Son
    report.append("═" * 50)
    report.append("📚 İyi çalışmalar! Başarılar dileriz. 🌟")
    report.append("═" * 50)
    report.append(f"⏰ Rapor: {datetime.now().strftime('%H:%M:%S')}")
    
    return '\n'.join(report)

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM GÖNDERİM
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram_message(message: str) -> bool:
    """Telegram'a mesaj gönder - HTML tagları temizlenmiş"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram ayarları eksik!")
        return False
    
    try:
        # HTML taglarını temizle (Telegram sadece belirli tagları destekler)
        # Desteklenen: <b>, <i>, <u>, <s>, <code>, <pre>, <a>
        # Desteklenmeyen tagları kaldır
        import re
        
        def clean_html(text):
            # Desteklenmeyen HTML taglarını kaldır
            unsupported_tags = [
                'cite', 'span', 'div', 'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'img', 'figure', 'figcaption',
                'blockquote', 'em', 'strong', 'small', 'sub', 'sup', 'mark', 'del', 'ins',
                'article', 'section', 'header', 'footer', 'nav', 'aside', 'main'
            ]
            
            for tag in unsupported_tags:
                # Açılış ve kapanış taglarını kaldır
                text = re.sub(f'<{tag}[^>]*>', '', text, flags=re.IGNORECASE)
                text = re.sub(f'</{tag}>', '', text, flags=re.IGNORECASE)
            
            # Kalan HTML entity'leri düzelt
            text = text.replace('&nbsp;', ' ')
            text = text.replace('&amp;', '&')
            text = text.replace('&lt;', '<')
            text = text.replace('&gt;', '>')
            text = text.replace('&quot;', '"')
            
            # Birden fazla boşluğu tek boşluğa indir
            text = re.sub(r' +', ' ', text)
            
            return text
        
        # Mesajı temizle
        message = clean_html(message)
        
        max_length = 4000
        parts = []
        
        if len(message) <= max_length:
            parts = [message]
        else:
            lines = message.split('\n')
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
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        
        for i, part in enumerate(parts):
            # HTML parse modunu kapat - düz metin gönder
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': part,
                'disable_web_page_preview': True
                # parse_mode kaldırıldı - düz metin olarak gönder
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ Telegram hatası (parça {i+1}): {response.text}")
                # HTML ile tekrar dene
                payload['parse_mode'] = 'HTML'
                payload['text'] = clean_html(part)
                response = requests.post(url, json=payload, timeout=30)
                
                if response.status_code != 200:
                    print(f"❌ Telegram HTML hatası: {response.text}")
                    return False
            
            if i < len(parts) - 1:
                time.sleep(1)
        
        print(f"✅ Telegram'a {len(parts)} parça gönderildi")
        return True
        
    except Exception as e:
        print(f"❌ Telegram hatası: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ANA PROGRAM
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Ana program"""
    print("=" * 50)
    print("📚 EĞİTİM GÜNDEM TAKİP BOTU v4.0 - YouTube AI Edition")
    print("=" * 50)
    print("")
    
    report = generate_report()
    print("\n" + report)
    
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        print("\n📤 Telegram'a gönderiliyor...")
        send_telegram_message(report)
    else:
        print("\n⚠️ Telegram ayarları yapılmamış.")
    
    print("\n✅ Bot tamamlandı!")

if __name__ == "__main__":
    main()
