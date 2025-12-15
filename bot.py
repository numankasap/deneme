#!/usr/bin/env python3
"""
📚 EĞİTİM GÜNDEM TAKİP BOTU v1.0
================================
LGS/YKS Öğrenci ve Öğretmenler için Günlük Haber & Gündem Botu

Özellikler:
- MEB'den son haberler
- LGS/YKS sınav takvimi ve geri sayım
- Eğitim gündemi (Türkiye)
- Matematik alanındaki gelişmeler
- Yapay zeka ve eğitim haberleri (Dünya)
- Öğrenci gündemi (trending konular)

Geliştirici: Numan Hoca için Claude tarafından oluşturuldu
Tarih: Aralık 2024
"""

import os
import requests
import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import json
import re
import locale

# Türkçe tarih formatı için
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Turkish_Turkey.1254')
    except:
        pass  # Locale ayarlanamadıysa varsayılan kullan

# Türkçe ay ve gün isimleri (locale çalışmazsa)
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
# SINAV TAKVİMİ VE GERİ SAYIM
# ══════════════════════════════════════════════════════════════════════════════

def get_exam_countdown() -> Dict:
    """
    LGS ve YKS sınav tarihleri ve geri sayım
    2025 yılı tahmini tarihleri (resmi tarihler açıklandığında güncellenmeli)
    """
    today = datetime.now()
    
    # 2025-2026 Sınav Tarihleri (Tahmini - ÖSYM/MEB açıklamasına göre güncellenmeli)
    exams = {
        # 2026 Sınavları
        'LGS 2026': {
            'date': datetime(2026, 6, 7),  # Tahmini: Haziran ilk pazar
            'name': '📚 LGS (Liselere Geçiş Sınavı)',
            'description': '8. sınıf merkezi sınavı'
        },
        'TYT 2026': {
            'date': datetime(2026, 6, 13),  # Tahmini
            'name': '📝 TYT (Temel Yeterlilik Testi)',
            'description': 'YKS 1. Oturum'
        },
        'AYT 2026': {
            'date': datetime(2026, 6, 14),  # Tahmini
            'name': '📖 AYT (Alan Yeterlilik Testi)',
            'description': 'YKS 2. Oturum'
        },
        'YDT 2026': {
            'date': datetime(2026, 6, 14),  # Tahmini
            'name': '🌍 YDT (Yabancı Dil Testi)',
            'description': 'YKS 3. Oturum'
        },
        # Yarıyıl tatili 2025-2026
        'Yarıyıl Tatili': {
            'date': datetime(2026, 1, 19),  # Tahmini
            'name': '🏖️ Yarıyıl Tatili Başlangıcı',
            'description': '2 hafta tatil'
        },
        # 2. Dönem
        '2. Dönem Başlangıcı': {
            'date': datetime(2026, 2, 2),  # Tahmini
            'name': '🏫 2. Dönem Başlangıcı',
            'description': 'Okula dönüş'
        },
        # Yaz tatili
        'Yaz Tatili': {
            'date': datetime(2026, 6, 19),  # Tahmini
            'name': '☀️ Yaz Tatili Başlangıcı',
            'description': 'Okulların kapanışı'
        }
    }
    
    countdown_list = []
    
    for exam_key, exam_info in exams.items():
        exam_date = exam_info['date']
        days_left = (exam_date.date() - today.date()).days
        
        if days_left >= 0:
            # Hafta ve gün hesapla
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
    
    # Gün sayısına göre sırala
    countdown_list = sorted(countdown_list, key=lambda x: x['days_left'])
    
    return {
        'today': format_turkish_date(today, include_day=True),
        'countdowns': countdown_list
    }

# ══════════════════════════════════════════════════════════════════════════════
# MEB HABERLERİ
# ══════════════════════════════════════════════════════════════════════════════

def get_meb_news() -> List[Dict]:
    """
    MEB'den son haberler (web scraping)
    Kaynak: meb.gov.tr
    """
    news = []
    
    try:
        # MEB ana sayfa haberleri
        url = "https://www.meb.gov.tr"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Haber başlıklarını bul
            # MEB sitesinin yapısına göre selector'ları güncelle
            news_items = soup.find_all('a', class_='news-item') or \
                        soup.find_all('div', class_='haber') or \
                        soup.find_all('article')
            
            for item in news_items[:10]:
                title = item.get_text(strip=True)[:150]
                link = item.get('href', '')
                if link and not link.startswith('http'):
                    link = url + link
                
                if title and len(title) > 20:
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
    """
    Türkiye eğitim haberleri
    Çoklu kaynak: Haber siteleri RSS
    """
    news = []
    
    # Türkiye haber kaynakları (eğitim kategorisi)
    sources = [
        # Genel haber siteleri eğitim kategorisi
        ('https://www.hurriyet.com.tr/rss/egitim', 'Hürriyet'),
        ('https://www.milliyet.com.tr/rss/rssNew/egitimRss.xml', 'Milliyet'),
        ('https://www.sabah.com.tr/rss/egitim.xml', 'Sabah'),
        ('https://www.cumhuriyet.com.tr/rss/egitim', 'Cumhuriyet'),
        # Eğitim özel siteleri
        ('https://www.ogretmenler.net/feed/', 'Öğretmenler.net'),
        ('https://www.egitimhane.com/rss.xml', 'Eğitimhane'),
    ]
    
    # LGS/YKS ile ilgili anahtar kelimeler
    important_keywords = [
        'lgs', 'yks', 'tyt', 'ayt', 'ösym', 'meb', 'sınav', 'müfredat',
        'öğretmen', 'atama', 'maaş', 'tatil', 'okul', 'ders', 'not',
        'bakan', 'eğitim', 'öğrenci', 'üniversite', 'lise', 'ortaokul',
        'beceri temelli', 'maarif modeli', 'pisa', 'timss'
    ]
    
    for rss_url, source in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:200] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')[:20] if entry.get('published') else ''
                
                # Önemli haber mi?
                text = (title + ' ' + summary).lower()
                is_important = any(kw in text for kw in important_keywords)
                
                # LGS/YKS odaklı mı?
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
    
    # Önce sınav haberleri, sonra önemli haberler
    news = sorted(news, key=lambda x: (x['is_exam_related'], x['is_important']), reverse=True)
    
    return news[:15]

# ══════════════════════════════════════════════════════════════════════════════
# MATEMATİK HABERLERİ
# ══════════════════════════════════════════════════════════════════════════════

def get_math_news() -> List[Dict]:
    """
    Matematik alanındaki son gelişmeler
    Türkiye ve Dünya
    """
    news = []
    
    # Dünya matematik haberleri kaynakları
    world_sources = [
        ('https://www.quantamagazine.org/mathematics/feed/', 'Quanta Magazine'),
        ('https://www.sciencedaily.com/rss/computers_math/mathematics.xml', 'Science Daily'),
        ('https://phys.org/rss-feed/mathematics-news/', 'Phys.org'),
        ('https://www.ams.org/rss/mathfeed.xml', 'AMS (American Mathematical Society)'),
    ]
    
    # Matematik anahtar kelimeleri
    math_keywords = [
        'theorem', 'proof', 'conjecture', 'algorithm', 'geometry', 'algebra',
        'calculus', 'topology', 'number theory', 'statistics', 'probability',
        'machine learning', 'ai', 'neural network', 'optimization',
        'riemann', 'prime', 'fibonacci', 'euler', 'fields medal',
        'matematik', 'teorem', 'ispat', 'geometri', 'cebir', 'istatistik'
    ]
    
    for rss_url, source in world_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:3]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                link = entry.get('link', '')
                
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
    
    return news[:10]

# ══════════════════════════════════════════════════════════════════════════════
# YAPAY ZEKA VE EĞİTİM HABERLERİ
# ══════════════════════════════════════════════════════════════════════════════

def get_ai_education_news() -> List[Dict]:
    """
    Yapay zeka ve eğitim haberleri
    EdTech gelişmeleri - Genişletilmiş kaynak listesi
    """
    news = []
    
    # ══════════════════════════════════════════════════════════════════════
    # BÜYÜK EDTECH & AI EĞİTİM HABER KAYNAKLARI
    # ══════════════════════════════════════════════════════════════════════
    
    sources = [
        # === ANA KAYNAKLAR (Yüksek Kalite) ===
        ('https://www.edsurge.com/articles_rss', 'EdSurge', 'Ana'),
        ('https://www.edweek.org/rss/technology.xml', 'Education Week', 'Ana'),
        ('https://www.the74million.org/feed/', 'The 74 Million', 'Ana'),
        ('https://www.eschoolnews.com/feed/', 'eSchool News', 'Ana'),
        ('https://edtechmagazine.com/k12/rss.xml', 'EdTech Magazine K12', 'Ana'),
        ('https://edtechmagazine.com/higher/rss.xml', 'EdTech Magazine Higher Ed', 'Ana'),
        
        # === EDTECH BLOG & ARAŞTIRMA ===
        ('https://www.techlearning.com/rss.xml', 'Tech & Learning', 'EdTech'),
        ('https://www.edtechreview.in/feed/', 'EdTech Review', 'EdTech'),
        ('https://classtechtips.com/feed/', 'Class Tech Tips', 'EdTech'),
        ('https://teachercast.net/feed/', 'TeacherCast', 'EdTech'),
        ('https://alicekeeler.com/feed/', 'Alice Keeler', 'EdTech'),
        ('https://www.freetech4teachers.com/feeds/posts/default', 'Free Tech 4 Teachers', 'EdTech'),
        ('https://www.coolcatteacher.com/feed/', 'Cool Cat Teacher', 'EdTech'),
        ('https://ditchthattextbook.com/feed/', 'Ditch That Textbook', 'EdTech'),
        ('https://shakeuplearning.com/feed/', 'Shake Up Learning', 'EdTech'),
        
        # === AI & MACHINE LEARNING EĞİTİM ===
        ('https://hai.stanford.edu/news/rss.xml', 'Stanford HAI', 'AI'),
        ('https://www.technologyreview.com/feed/', 'MIT Technology Review', 'AI'),
        ('https://openai.com/blog/rss.xml', 'OpenAI Blog', 'AI'),
        ('https://blog.google/technology/ai/rss/', 'Google AI Blog', 'AI'),
        ('https://www.anthropic.com/feed.xml', 'Anthropic', 'AI'),
        ('https://deepmind.com/blog/feed/basic/', 'DeepMind', 'AI'),
        
        # === ÖĞRENME BİLİMİ & ARAŞTIRMA ===
        ('https://www.gettingsmart.com/feed/', 'Getting Smart', 'Araştırma'),
        ('https://www.iste.org/feed', 'ISTE', 'Araştırma'),
        ('https://www.educause.edu/rss-feeds/all', 'EDUCAUSE', 'Araştırma'),
        ('https://www.insidehighered.com/rss.xml', 'Inside Higher Ed', 'Araştırma'),
        
        # === KÜRESEL EĞİTİM ===
        ('https://www.weforum.org/agenda/feed', 'World Economic Forum', 'Global'),
        ('https://en.unesco.org/news/feed', 'UNESCO Education', 'Global'),
        ('https://www.oecd.org/education/rss.xml', 'OECD Education', 'Global'),
        
        # === ÖĞRETİM TASARIMI & ÖĞRETİM ===
        ('https://www.facultyfocus.com/feed/', 'Faculty Focus', 'Öğretim'),
        ('https://www.elearningindustry.com/feed', 'eLearning Industry', 'Öğretim'),
        ('https://www.learningguild.com/rss/', 'Learning Guild', 'Öğretim'),
        
        # === STEM & KODLAMA ===
        ('https://www.codeorg.org/blog/feed', 'Code.org', 'STEM'),
        ('https://scratch.mit.edu/discuss/feeds/newest/', 'Scratch MIT', 'STEM'),
        
        # === TÜRKÇE KAYNAKLAR ===
        ('https://www.ogretmenler.net/feed/', 'Öğretmenler.net', 'TR'),
        ('https://www.egitimhane.com/rss.xml', 'Eğitimhane', 'TR'),
    ]
    
    # AI/EdTech anahtar kelimeleri - genişletilmiş
    ai_keywords = [
        # Yapay Zeka Temel
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'neural network', 'nlp', 'natural language', 'computer vision',
        # Generative AI
        'chatgpt', 'gpt', 'gpt-4', 'gpt-5', 'claude', 'gemini', 'copilot',
        'generative ai', 'genai', 'large language model', 'llm',
        'midjourney', 'dall-e', 'stable diffusion',
        # EdTech Araçları
        'edtech', 'education technology', 'learning platform',
        'adaptive learning', 'personalized learning', 'intelligent tutoring',
        'learning management', 'lms', 'mooc', 'online learning',
        # Spesifik Platformlar
        'khan academy', 'khanmigo', 'duolingo', 'coursera', 'edx',
        'canvas', 'blackboard', 'google classroom', 'microsoft teams',
        'nearpod', 'kahoot', 'quizlet', 'brainly',
        # Eğitim Uygulamaları
        'ai tutor', 'ai teacher', 'ai grading', 'ai assessment',
        'automated feedback', 'intelligent tutoring system',
        'learning analytics', 'educational data mining',
        'ai plagiarism', 'ai detection', 'ai writing',
        # Trendler
        'future of education', 'digital transformation', 'hybrid learning',
        'blended learning', 'flipped classroom', 'gamification',
        'virtual reality', 'vr education', 'ar education', 'metaverse',
        # Politika & Etik
        'ai policy', 'ai ethics', 'ai regulation', 'ai safety',
        'digital literacy', 'ai literacy', 'computational thinking',
        # Türkçe
        'yapay zeka', 'makine öğrenmesi', 'dijital öğrenme',
        'uzaktan eğitim', 'eğitim teknolojisi', 'akıllı öğretim'
    ]
    
    # Yüksek öncelikli anahtar kelimeler
    high_priority_keywords = [
        'chatgpt', 'ai tutor', 'ai teacher', 'khanmigo', 'generative ai',
        'ai classroom', 'ai education policy', 'ai literacy', 'llm education',
        'personalized learning ai', 'adaptive ai', 'intelligent tutoring'
    ]
    
    for rss_url, source, category in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:400] if entry.get('summary') else ''
                link = entry.get('link', '')
                published = entry.get('published', '')[:20] if entry.get('published') else ''
                
                # AI ile ilgili mi kontrol et
                text = (title + ' ' + summary).lower()
                is_ai_related = any(kw in text for kw in ai_keywords)
                is_high_priority = any(kw in text for kw in high_priority_keywords)
                
                if is_ai_related:
                    news.append({
                        'title': title[:150],
                        'summary': summary[:200],
                        'source': source,
                        'category': category,
                        'link': link,
                        'published': published,
                        'is_ai_related': True,
                        'is_high_priority': is_high_priority,
                        'needs_translation': source not in ['Öğretmenler.net', 'Eğitimhane']
                    })
        except Exception as e:
            continue
    
    # Önce yüksek öncelikli, sonra tarihe göre sırala
    news = sorted(news, key=lambda x: (x.get('is_high_priority', False)), reverse=True)
    
    return news[:15]

# ══════════════════════════════════════════════════════════════════════════════
# ÖĞRENCİ GÜNDEMİ (TRENDING KONULAR)
# ══════════════════════════════════════════════════════════════════════════════

def get_student_trending_topics() -> List[Dict]:
    """
    Öğrencilerin gündemindeki konular
    Ekşi Sözlük, Reddit Türkiye, Twitter trends (simüle)
    """
    # Not: Gerçek API'ler için authentication gerekebilir
    # Bu fonksiyon örnek trending konular döndürür
    
    trending = []
    
    # Ekşi Sözlük gündem (simüle - gerçek scraping için BeautifulSoup kullanılabilir)
    try:
        url = "https://eksisozluk.com/basliklar/gundem"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Eğitim ile ilgili başlıkları filtrele
            education_keywords = [
                'lgs', 'yks', 'tyt', 'ayt', 'ösym', 'sınav', 'okul', 'ders',
                'öğretmen', 'öğrenci', 'üniversite', 'lise', 'matematik',
                'fizik', 'kimya', 'biyoloji', 'türkçe', 'tarih', 'coğrafya',
                'müfredat', 'meb', 'eğitim', 'kpss', 'ales', 'yds'
            ]
            
            topics = soup.find_all('a', class_='topic-list-item') or soup.find_all('li')
            
            for topic in topics[:30]:
                title = topic.get_text(strip=True)
                if any(kw in title.lower() for kw in education_keywords):
                    entry_count = topic.find('small')
                    count = entry_count.get_text(strip=True) if entry_count else ''
                    
                    trending.append({
                        'topic': title[:100],
                        'source': 'Ekşi Sözlük',
                        'entry_count': count,
                        'category': 'Eğitim'
                    })
    except Exception as e:
        print(f"Trending topics hatası: {e}")
    
    # Eğer gerçek veri alınamazsa, sık sorulan konuları döndür
    if not trending:
        common_topics = [
            {'topic': '2025 LGS ne zaman?', 'category': 'Sınav Takvimi'},
            {'topic': 'YKS başvuruları ne zaman?', 'category': 'Sınav Takvimi'},
            {'topic': 'Yeni müfredat değişiklikleri', 'category': 'Müfredat'},
            {'topic': 'Beceri temelli sorular nasıl çözülür?', 'category': 'Çalışma'},
            {'topic': 'TYT Matematik konuları', 'category': 'Konu Listesi'},
            {'topic': 'LGS Matematik soru tipleri', 'category': 'Soru Analizi'},
            {'topic': 'Verimli ders çalışma yöntemleri', 'category': 'Motivasyon'},
            {'topic': 'Pomodoro tekniği nasıl uygulanır?', 'category': 'Çalışma'},
        ]
        trending = common_topics
    
    return trending[:10]

# ══════════════════════════════════════════════════════════════════════════════
# GÜNÜN MOTİVASYON MESAJI
# ══════════════════════════════════════════════════════════════════════════════

def get_daily_motivation() -> Dict:
    """
    Günün motivasyon mesajı ve çalışma önerisi
    Gemini API ile dinamik üretim
    """
    today = datetime.now()
    day_of_week = today.strftime('%A')
    
    # Haftanın gününe göre farklı temalar
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
    
    # Gemini ile motivasyon mesajı üret
    if GEMINI_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_KEY)
            
            prompt = f"""LGS veya YKS'ye hazırlanan bir öğrenci için kısa ve motive edici bir mesaj yaz.

Tema: {theme}
Gün: {day_of_week}

Kurallar:
1. Maksimum 2-3 cümle olsun
2. Samimi ve cesaretlendirici ol
3. Somut bir çalışma önerisi içersin
4. Emoji kullan
5. Türkçe yaz

Örnek format:
💪 [Motivasyon mesajı]
📚 Bugünkü öneri: [Somut çalışma önerisi]"""

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
            print(f"Motivasyon mesajı hatası: {e}")
    
    # Varsayılan mesajlar
    default_messages = [
        "💪 Her gün bir adım daha ileri! Bugün de elinden gelenin en iyisini yap.\n📚 Bugünkü öneri: 25 dakika odaklanarak çalış, 5 dakika mola ver.",
        "🌟 Başarı, her gün yapılan küçük adımların toplamıdır.\n📚 Bugünkü öneri: Zayıf olduğun bir konuyu tekrar et.",
        "🎯 Hedefe odaklan, engellere değil. Sen başarabilirsin!\n📚 Bugünkü öneri: Bugün en az 20 soru çöz.",
        "⭐ Dünden daha iyi olmak yeterli. Kendini geçmişle kıyasla!\n📚 Bugünkü öneri: Dün çözdüğün yanlışları tekrar incele.",
        "🚀 Çalışmak şansı yaratır. Bugün de üretken bir gün olsun!\n📚 Bugünkü öneri: Yeni bir konu öğren, not al."
    ]
    
    import random
    return {
        'message': random.choice(default_messages),
        'theme': theme,
        'generated': False
    }

# ══════════════════════════════════════════════════════════════════════════════
# ÇEVİRİ FONKSİYONU
# ══════════════════════════════════════════════════════════════════════════════

def translate_to_turkish(text: str, is_headline: bool = True) -> str:
    """
    Gemini API ile İngilizce metni Türkçeye çevir
    """
    if not text or not GEMINI_KEY or not genai:
        return text
    
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        
        if is_headline:
            prompt = f"""Aşağıdaki eğitim/bilim haber başlığını Türkçeye çevir.

Kurallar:
1. Tam ve eksiksiz çeviri yap
2. Anlaşılır ve akıcı Türkçe kullan
3. Teknik terimleri olduğu gibi bırak: AI, Machine Learning, EdTech, STEM, PISA vb.
4. Kurum isimlerini çevirme: Khan Academy, MIT, UNESCO vb.
5. Sadece çeviriyi yaz

İngilizce: {text}

Türkçe:"""
        else:
            prompt = f"""Aşağıdaki eğitim/bilim haberini Türkçeye çevir.

Kurallar:
1. Tam ve detaylı çeviri yap
2. Anlaşılır Türkçe kullan
3. Teknik terimleri olduğu gibi bırak
4. Sadece çeviriyi yaz

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
    except Exception as e:
        print(f"Çeviri hatası: {e}")
        return text

# ══════════════════════════════════════════════════════════════════════════════
# GÜNÜN ÖZETİ (AI DESTEKLİ)
# ══════════════════════════════════════════════════════════════════════════════

def generate_daily_summary(all_news: Dict) -> str:
    """
    Gemini ile günün özeti oluştur
    """
    if not GEMINI_KEY or not genai:
        return ""
    
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        
        # Haberleri özetle
        news_text = ""
        
        if all_news.get('meb_news'):
            news_text += "MEB Haberleri:\n"
            for n in all_news['meb_news'][:3]:
                news_text += f"- {n['title']}\n"
        
        if all_news.get('education_news'):
            news_text += "\nEğitim Haberleri:\n"
            for n in all_news['education_news'][:3]:
                news_text += f"- {n['title']}\n"
        
        if all_news.get('ai_news'):
            news_text += "\nYapay Zeka & Eğitim:\n"
            for n in all_news['ai_news'][:3]:
                news_text += f"- {n['title']}\n"
        
        prompt = f"""Aşağıdaki eğitim haberlerini okuyarak öğretmenler ve öğrenciler için 3-4 cümlelik kısa bir günlük özet yaz.

{news_text}

Kurallar:
1. En önemli 2-3 konuyu vurgula
2. Öğrenci ve öğretmenlere ne anlama geldiğini açıkla
3. Kısa ve öz tut
4. Türkçe yaz
5. Emoji kullanma

Özet:"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"Özet oluşturma hatası: {e}")
        return ""

# ══════════════════════════════════════════════════════════════════════════════
# RAPOR OLUŞTURMA
# ══════════════════════════════════════════════════════════════════════════════

def generate_report() -> str:
    """
    Günlük eğitim raporu oluştur
    """
    report = []
    
    # Başlık
    today = datetime.now()
    report.append("═" * 50)
    report.append("📚 EĞİTİM GÜNDEM RAPORU")
    report.append(f"📅 {format_turkish_date(today, include_day=True)}")
    report.append("═" * 50)
    report.append("")
    
    # 1. SINAV TAKVİMİ VE GERİ SAYIM
    print("📅 Sınav takvimi hazırlanıyor...")
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
    
    # 2. MEB HABERLERİ
    print("📰 MEB haberleri çekiliyor...")
    meb_news = get_meb_news()
    education_news = get_education_news_turkey()
    
    report.append("━" * 50)
    report.append("🏛 MEB & TÜRKİYE EĞİTİM GÜNDEMİ")
    report.append("━" * 50)
    
    # Önce MEB haberleri
    if meb_news:
        report.append("\n📢 MEB'DEN:")
        for news in meb_news[:3]:
            prefix = "🔴" if news.get('is_important') else "•"
            report.append(f"{prefix} {news['title']}")
    
    # Sonra genel eğitim haberleri
    if education_news:
        report.append("\n📰 GÜNDEM:")
        for news in education_news[:5]:
            prefix = "🔴" if news.get('is_exam_related') else "📌" if news.get('is_important') else "•"
            report.append(f"{prefix} {news['title']}")
            report.append(f"   📍 {news['source']}")
    
    report.append("")
    
    # 3. YAPAY ZEKA VE EĞİTİM
    print("🤖 Yapay zeka haberleri çekiliyor...")
    ai_news = get_ai_education_news()
    
    report.append("━" * 50)
    report.append("🤖 YAPAY ZEKA & EĞİTİM TEKNOLOJİSİ")
    report.append("━" * 50)
    
    if ai_news:
        # Önce yüksek öncelikli haberler
        high_priority = [n for n in ai_news if n.get('is_high_priority')]
        regular = [n for n in ai_news if not n.get('is_high_priority')]
        
        translate_count = 0
        
        # Kritik AI haberleri
        if high_priority:
            report.append("\n🔥 ÖNE ÇIKAN GELİŞMELER:")
            for news in high_priority[:3]:
                if news.get('needs_translation') and translate_count < 5:
                    title_tr = translate_to_turkish(news['title'], is_headline=True)
                    translate_count += 1
                    import time
                    time.sleep(0.3)
                else:
                    title_tr = news['title']
                
                report.append(f"\n🚀 {title_tr}")
                report.append(f"   📍 {news['source']} [{news.get('category', '')}]")
        
        # Diğer haberler - kategoriye göre grupla
        if regular:
            # Kategorilere ayır
            categories = {}
            for news in regular[:10]:
                cat = news.get('category', 'Diğer')
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(news)
            
            # Her kategoriden max 2 haber göster
            category_emojis = {
                'Ana': '📰', 'EdTech': '💻', 'AI': '🧠', 
                'Araştırma': '🔬', 'Global': '🌍', 'Öğretim': '📚',
                'STEM': '🔢', 'TR': '🇹🇷', 'Diğer': '📌'
            }
            
            for cat, items in categories.items():
                if items and len(items) > 0:
                    emoji = category_emojis.get(cat, '📌')
                    report.append(f"\n{emoji} {cat.upper()}:")
                    
                    for news in items[:2]:
                        if news.get('needs_translation') and translate_count < 8:
                            title_tr = translate_to_turkish(news['title'], is_headline=True)
                            translate_count += 1
                            import time
                            time.sleep(0.3)
                        else:
                            title_tr = news['title']
                        
                        report.append(f"• {title_tr[:100]}")
                        report.append(f"  📍 {news['source']}")
    else:
        report.append("\n• Henüz yeni haber yok")
    
    report.append("")
    
    # 4. MATEMATİK HABERLERİ
    print("➕ Matematik haberleri çekiliyor...")
    math_news = get_math_news()
    
    report.append("━" * 50)
    report.append("➕ MATEMATİK DÜNYASINDAN")
    report.append("━" * 50)
    
    if math_news:
        translate_count = 0
        for news in math_news[:4]:
            # İlk 2 haberi çevir
            if news.get('needs_translation') and translate_count < 2:
                title_tr = translate_to_turkish(news['title'], is_headline=True)
                translate_count += 1
                import time
                time.sleep(0.3)
            else:
                title_tr = news['title']
            
            report.append(f"\n🔬 {title_tr}")
            report.append(f"   📍 {news['source']} ({news.get('region', 'Dünya')})")
    else:
        report.append("• Henüz yeni haber yok")
    
    report.append("")
    
    # 5. ÖĞRENCİ GÜNDEMİ
    print("🔥 Öğrenci gündemi hazırlanıyor...")
    trending = get_student_trending_topics()
    
    report.append("━" * 50)
    report.append("🔥 ÖĞRENCİ GÜNDEMİ (Sık Sorulanlar)")
    report.append("━" * 50)
    
    if trending:
        for topic in trending[:6]:
            category = topic.get('category', '')
            category_str = f" [{category}]" if category else ""
            report.append(f"• {topic['topic']}{category_str}")
    
    report.append("")
    
    # 6. GÜNÜN MOTİVASYONU
    print("💪 Motivasyon mesajı hazırlanıyor...")
    motivation = get_daily_motivation()
    
    report.append("━" * 50)
    report.append("💪 GÜNÜN MOTİVASYONU")
    report.append("━" * 50)
    report.append("")
    report.append(motivation['message'])
    report.append("")
    
    # 7. GÜNÜN ÖZETİ (AI)
    print("📝 Günün özeti oluşturuluyor...")
    all_news = {
        'meb_news': meb_news,
        'education_news': education_news,
        'ai_news': ai_news,
        'math_news': math_news
    }
    summary = generate_daily_summary(all_news)
    
    if summary:
        report.append("━" * 50)
        report.append("📝 GÜNÜN ÖZETİ")
        report.append("━" * 50)
        report.append("")
        report.append(summary)
        report.append("")
    
    # Son
    report.append("═" * 50)
    report.append("📚 İyi çalışmalar! Başarılar dileriz. 🌟")
    report.append("═" * 50)
    report.append("")
    report.append(f"⏰ Rapor oluşturma: {datetime.now().strftime('%H:%M:%S')}")
    
    return '\n'.join(report)

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM GÖNDERİM
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram_message(message: str) -> bool:
    """
    Telegram'a mesaj gönder
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram ayarları eksik!")
        return False
    
    try:
        # Mesajı parçalara böl (Telegram 4096 karakter limiti)
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
        
        # Her parçayı gönder
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        
        for i, part in enumerate(parts):
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': part,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ Telegram hatası (parça {i+1}): {response.text}")
                return False
            
            # Rate limit için bekle
            if i < len(parts) - 1:
                import time
                time.sleep(1)
        
        print(f"✅ Telegram'a {len(parts)} parça gönderildi")
        return True
        
    except Exception as e:
        print(f"❌ Telegram gönderim hatası: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ANA PROGRAM
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Ana program
    """
    print("=" * 50)
    print("📚 EĞİTİM GÜNDEM TAKİP BOTU v1.0")
    print("=" * 50)
    print("")
    
    # Rapor oluştur
    report = generate_report()
    
    # Konsola yazdır
    print("\n" + report)
    
    # Telegram'a gönder
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        print("\n📤 Telegram'a gönderiliyor...")
        send_telegram_message(report)
    else:
        print("\n⚠️ Telegram ayarları yapılmamış. Sadece konsola yazdırıldı.")
    
    print("\n✅ Bot çalışması tamamlandı!")

if __name__ == "__main__":
    main()
