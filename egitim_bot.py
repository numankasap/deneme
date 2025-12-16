#!/usr/bin/env python3
"""
📚 EĞİTİM GÜNDEM TAKİP BOTU v2.0 - GLOBAL EDİTION
=================================================
LGS/YKS Öğrenci ve Öğretmenler için Günlük Haber & Gündem Botu

Özellikler:
- MEB'den son haberler
- LGS/YKS sınav takvimi ve geri sayım
- Eğitim gündemi (Türkiye)
- Matematik alanındaki gelişmeler

🌍 GLOBAL HABERLER (v2.0):
- 🇨🇳 Çin: AI eğitim devrimi, DeepSeek, dijital sınıflar
- 🇯🇵 Japonya: Robotik eğitim, STEM inovasyonu
- 🇰🇷 Güney Kore: AI müfredat, EdTech yatırımları
- 🇫🇮 Finlandiya: Eğitim reformları, öğretmen eğitimi
- 🇸🇬 Singapur: Smart Nation, kişiselleştirilmiş öğrenme
- 🇷🇺 Rusya: Matematik olimpiyatları, bilim eğitimi
- 🇮🇱 İsrail: Startup eğitimi, teknoloji entegrasyonu
- 🇮🇳 Hindistan: EdTech unicorn'ları, dijital dönüşüm
- 🇪🇪 Estonya: Dijital vatandaşlık, kodlama eğitimi

📄 BİLİMSEL MAKALELER:
- arXiv: AI, Makine Öğrenmesi, Eğitim Teknolojisi
- ERIC: Eğitim araştırmaları
- Google Scholar: Güncel akademik çalışmalar

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
    # ÇALIŞAN EDTECH & AI EĞİTİM HABER KAYNAKLARI
    # ══════════════════════════════════════════════════════════════════════
    
    sources = [
        # === ANA KAYNAKLAR (Doğrulanmış RSS) ===
        ('https://www.edsurge.com/articles_rss', 'EdSurge', 'Ana'),
        ('https://www.the74million.org/feed/', 'The 74 Million', 'Ana'),
        ('https://www.eschoolnews.com/feed/', 'eSchool News', 'Ana'),
        ('https://edtechmagazine.com/k12/rss.xml', 'EdTech Magazine', 'Ana'),
        
        # === EDTECH BLOGLAR ===
        ('https://www.techlearning.com/rss.xml', 'Tech & Learning', 'EdTech'),
        ('https://classtechtips.com/feed/', 'Class Tech Tips', 'EdTech'),
        ('https://www.freetech4teachers.com/feeds/posts/default', 'Free Tech 4 Teachers', 'EdTech'),
        ('https://ditchthattextbook.com/feed/', 'Ditch That Textbook', 'EdTech'),
        
        # === AI & TEKNOLOJİ ===
        ('https://www.technologyreview.com/feed/', 'MIT Tech Review', 'AI'),
        ('https://openai.com/blog/rss/', 'OpenAI', 'AI'),
        
        # === ÖĞRENME BİLİMİ ===
        ('https://www.gettingsmart.com/feed/', 'Getting Smart', 'Araştırma'),
        ('https://www.insidehighered.com/rss.xml', 'Inside Higher Ed', 'Araştırma'),
        
        # === KÜRESEL ===
        ('https://www.weforum.org/agenda/feed', 'World Economic Forum', 'Global'),
        
        # === ÖĞRETİM ===
        ('https://www.facultyfocus.com/feed/', 'Faculty Focus', 'Öğretim'),
        ('https://www.elearningindustry.com/feed', 'eLearning Industry', 'Öğretim'),
    ]
    
    # AI/EdTech anahtar kelimeleri
    ai_keywords = [
        # Yapay Zeka
        'ai', 'artificial intelligence', 'machine learning', 'deep learning',
        'chatgpt', 'gpt', 'claude', 'gemini', 'copilot',
        'generative ai', 'genai', 'llm', 'large language model',
        # EdTech
        'edtech', 'education technology', 'learning platform',
        'adaptive learning', 'personalized learning', 'intelligent tutoring',
        'online learning', 'digital learning', 'hybrid learning',
        # Platformlar
        'khan academy', 'khanmigo', 'duolingo', 'coursera',
        'google classroom', 'canvas', 'kahoot', 'quizlet',
        # Eğitim Uygulamaları
        'ai tutor', 'ai teacher', 'ai grading', 'ai assessment',
        'automated feedback', 'learning analytics',
        # Trendler
        'future of education', 'digital transformation',
        'ai literacy', 'computational thinking',
        # Türkçe
        'yapay zeka', 'eğitim teknolojisi'
    ]
    
    # Yüksek öncelikli
    high_priority_keywords = [
        'chatgpt', 'ai tutor', 'ai teacher', 'khanmigo', 'generative ai',
        'ai classroom', 'ai education', 'ai literacy', 'personalized learning ai'
    ]
    
    for rss_url, source, category in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:4]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300] if entry.get('summary') else ''
                link = entry.get('link', '')
                
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
                        'is_ai_related': True,
                        'is_high_priority': is_high_priority,
                        'needs_translation': True
                    })
        except Exception as e:
            print(f"RSS hatası ({source}): {e}")
            continue
    
    # Önce yüksek öncelikli
    news = sorted(news, key=lambda x: (x.get('is_high_priority', False)), reverse=True)
    
    return news[:12]

# ══════════════════════════════════════════════════════════════════════════════
# 🌍 GLOBAL EĞİTİM HABERLERİ - ÜLKE BAZLI
# ══════════════════════════════════════════════════════════════════════════════

def get_global_education_news() -> Dict[str, List[Dict]]:
    """
    Dünya genelinde eğitim, AI ve matematik alanında öncü ülkelerden haberler
    Her ülke için özel kaynaklar ve anahtar kelimeler
    """
    
    # Ülke bazlı haber kaynakları
    country_sources = {
        # 🇨🇳 ÇİN - AI ve EdTech Devrimi
        'china': {
            'flag': '🇨🇳',
            'name': 'Çin',
            'focus': 'AI Eğitim Devrimi',
            'sources': [
                ('https://news.cgtn.com/rss/education.xml', 'CGTN Education'),
                ('https://www.globaltimes.cn/rss/outbrain.xml', 'Global Times'),
                ('https://www.sixthtone.com/rss/news', 'Sixth Tone'),
            ],
            'keywords': ['china education', 'chinese school', 'gaokao', 'deepseek', 
                        'chinese ai', 'beijing education', 'shanghai school',
                        'smart classroom china', 'ai pilot school', 'chinese student',
                        'ministry of education china', 'tsinghua', 'peking university'],
            'priority_keywords': ['deepseek', 'chinese ai education', 'gaokao reform',
                                 'ai classroom china', 'smart education china']
        },
        
        # 🇯🇵 JAPONYA - Robotik ve STEM
        'japan': {
            'flag': '🇯🇵',
            'name': 'Japonya',
            'focus': 'Robotik & STEM İnovasyonu',
            'sources': [
                ('https://www.japantimes.co.jp/feed/', 'Japan Times'),
                ('https://japantoday.com/feed', 'Japan Today'),
                ('https://english.kyodonews.net/rss/all.xml', 'Kyodo News'),
            ],
            'keywords': ['japan education', 'japanese school', 'juku', 'robotics education',
                        'stem japan', 'tokyo university', 'japanese student',
                        'programming education japan', 'ai japan', 'digital textbook japan'],
            'priority_keywords': ['japan ai education', 'robotics school japan', 
                                 'japanese stem', 'mext education']
        },
        
        # 🇰🇷 GÜNEY KORE - AI Müfredat & EdTech
        'korea': {
            'flag': '🇰🇷',
            'name': 'Güney Kore',
            'focus': 'AI Müfredat & EdTech',
            'sources': [
                ('https://koreajoongangdaily.joins.com/section/rss/education', 'Korea JoongAng'),
                ('https://en.yna.co.kr/RSS/news.xml', 'Yonhap News'),
                ('https://www.koreaherald.com/rss/023.xml', 'Korea Herald'),
            ],
            'keywords': ['korea education', 'korean school', 'suneung', 'csat korea',
                        'korean ai', 'seoul education', 'hagwon', 'korean student',
                        'digital textbook korea', 'ai tutor korea', 'edtech korea'],
            'priority_keywords': ['korea ai curriculum', 'korean ai education',
                                 'keris education', 'korean digital textbook']
        },
        
        # 🇫🇮 FİNLANDİYA - Eğitim Reformu
        'finland': {
            'flag': '🇫🇮',
            'name': 'Finlandiya',
            'focus': 'Eğitim Reformu & Öğretmen Eğitimi',
            'sources': [
                ('https://www.helsinkitimes.fi/feed.rss', 'Helsinki Times'),
                ('https://yle.fi/rss/uutiset.rss', 'YLE News'),
            ],
            'keywords': ['finland education', 'finnish school', 'pisa finland',
                        'teacher training finland', 'helsinki university',
                        'finnish student', 'no homework finland', 'play-based learning'],
            'priority_keywords': ['finnish education reform', 'pisa results finland',
                                 'teacher education finland']
        },
        
        # 🇸🇬 SİNGAPUR - Smart Nation & Kişiselleştirilmiş Öğrenme
        'singapore': {
            'flag': '🇸🇬',
            'name': 'Singapur',
            'focus': 'Smart Nation & Kişiselleştirilmiş Öğrenme',
            'sources': [
                ('https://www.straitstimes.com/rss/singapore', 'Straits Times'),
                ('https://www.channelnewsasia.com/rss/latest_news.xml', 'CNA'),
            ],
            'keywords': ['singapore education', 'singapore school', 'moe singapore',
                        'smart nation', 'singapore ai', 'nus', 'ntu',
                        'adaptive learning singapore', 'psle', 'o level singapore'],
            'priority_keywords': ['singapore ai education', 'smart nation education',
                                 'singapore digital learning', 'nie singapore']
        },
        
        # 🇷🇺 RUSYA - Matematik & Bilim Olimpiyatları  
        'russia': {
            'flag': '🇷🇺',
            'name': 'Rusya',
            'focus': 'Matematik Olimpiyatları & Bilim Eğitimi',
            'sources': [
                ('https://tass.com/rss/v2.xml', 'TASS'),
                ('https://sputnikglobe.com/export/rss2/archive/index.xml', 'Sputnik'),
            ],
            'keywords': ['russia education', 'russian school', 'math olympiad russia',
                        'russian mathematics', 'moscow university', 'msu',
                        'unified state exam', 'ege russia', 'russian science'],
            'priority_keywords': ['russian math olympiad', 'imo russia',
                                 'russian mathematics education']
        },
        
        # 🇮🇱 İSRAİL - Startup & Teknoloji Eğitimi
        'israel': {
            'flag': '🇮🇱',
            'name': 'İsrail',
            'focus': 'Startup Ekosistemi & Teknoloji Eğitimi',
            'sources': [
                ('https://www.timesofisrael.com/feed/', 'Times of Israel'),
                ('https://www.jpost.com/rss/rssfeedseducation.aspx', 'Jerusalem Post'),
            ],
            'keywords': ['israel education', 'israeli school', 'technion',
                        'hebrew university', 'startup nation education',
                        'israeli tech', 'coding education israel', 'cyber education'],
            'priority_keywords': ['israel tech education', 'israeli startup education',
                                 'cybersecurity education israel']
        },
        
        # 🇮🇳 HİNDİSTAN - EdTech Unicorn'ları
        'india': {
            'flag': '🇮🇳',
            'name': 'Hindistan',
            'focus': 'EdTech Unicorn & Dijital Dönüşüm',
            'sources': [
                ('https://indianexpress.com/section/education/feed/', 'Indian Express'),
                ('https://timesofindia.indiatimes.com/rssfeeds/913168846.cms', 'Times of India'),
            ],
            'keywords': ['india education', 'indian school', 'iit', 'neet',
                        'jee exam', 'byju', 'unacademy', 'vedantu',
                        'indian edtech', 'digital india education', 'nep 2020'],
            'priority_keywords': ['india edtech', 'indian ai education',
                                 'nep education', 'digital classroom india']
        },
        
        # 🇪🇪 ESTONYA - Dijital Vatandaşlık & Kodlama
        'estonia': {
            'flag': '🇪🇪',
            'name': 'Estonya',
            'focus': 'Dijital Vatandaşlık & Kodlama Eğitimi',
            'sources': [
                ('https://news.err.ee/rss', 'ERR News'),
            ],
            'keywords': ['estonia education', 'estonian school', 'e-estonia',
                        'digital citizenship', 'progettiger', 'coding education estonia',
                        'tartu university', 'tallinn tech'],
            'priority_keywords': ['estonia digital education', 'e-estonia education',
                                 'progettiger coding']
        },
    }
    
    global_news = {}
    
    # Genel haber kaynakları (ülke bazlı filtreleme için)
    general_sources = [
        ('https://www.weforum.org/agenda/feed', 'World Economic Forum'),
        ('https://www.brookings.edu/feed/', 'Brookings'),
        ('https://www.rand.org/pubs/rss.xml', 'RAND'),
        ('https://internationalednews.com/feed/', 'International Ed News'),
    ]
    
    for country_code, config in country_sources.items():
        country_news = []
        
        # Ülke spesifik kaynakları tara
        for rss_url, source_name in config['sources']:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:8]:
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')[:400] if entry.get('summary') else ''
                    link = entry.get('link', '')
                    
                    # Eğitim ile ilgili mi kontrol et
                    text = (title + ' ' + summary).lower()
                    
                    # Ülke anahtar kelimelerini kontrol et
                    is_relevant = any(kw in text for kw in config['keywords'])
                    is_priority = any(kw in text for kw in config['priority_keywords'])
                    
                    # Genel eğitim kelimeleri
                    education_keywords = ['education', 'school', 'student', 'teacher',
                                         'university', 'learning', 'curriculum', 'exam',
                                         'ai', 'digital', 'stem', 'math', 'science']
                    is_education = any(kw in text for kw in education_keywords)
                    
                    if is_relevant or (is_education and config['name'].lower() in text):
                        country_news.append({
                            'title': title[:150],
                            'summary': summary[:200],
                            'source': source_name,
                            'link': link,
                            'country': config['name'],
                            'flag': config['flag'],
                            'focus': config['focus'],
                            'is_priority': is_priority,
                            'needs_translation': True
                        })
            except Exception as e:
                print(f"Global RSS hatası ({source_name}): {e}")
                continue
        
        # Genel kaynaklardan da bu ülkeye ait haberleri çek
        for rss_url, source_name in general_sources:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:5]:
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')[:400] if entry.get('summary') else ''
                    link = entry.get('link', '')
                    
                    text = (title + ' ' + summary).lower()
                    
                    # Bu ülkeyle ilgili mi?
                    country_mentioned = any(kw in text for kw in config['keywords'][:5])
                    
                    if country_mentioned:
                        country_news.append({
                            'title': title[:150],
                            'summary': summary[:200],
                            'source': source_name,
                            'link': link,
                            'country': config['name'],
                            'flag': config['flag'],
                            'focus': config['focus'],
                            'is_priority': False,
                            'needs_translation': True
                        })
            except:
                continue
        
        # Öncelikli haberleri öne al ve en fazla 3 haber tut
        country_news = sorted(country_news, key=lambda x: x.get('is_priority', False), reverse=True)
        global_news[country_code] = country_news[:3]
    
    return global_news

# ══════════════════════════════════════════════════════════════════════════════
# 📄 BİLİMSEL MAKALELER - arXiv & Akademik Kaynaklar
# ══════════════════════════════════════════════════════════════════════════════

def get_arxiv_papers() -> List[Dict]:
    """
    arXiv'den AI, Makine Öğrenmesi ve Eğitim Teknolojisi makaleleri
    """
    papers = []
    
    # arXiv kategorileri ve RSS URL'leri
    arxiv_categories = [
        ('http://export.arxiv.org/rss/cs.AI', 'cs.AI', 'Yapay Zeka'),
        ('http://export.arxiv.org/rss/cs.CL', 'cs.CL', 'Doğal Dil İşleme'),
        ('http://export.arxiv.org/rss/cs.LG', 'cs.LG', 'Makine Öğrenmesi'),
        ('http://export.arxiv.org/rss/cs.CY', 'cs.CY', 'Bilgisayar ve Toplum'),
        ('http://export.arxiv.org/rss/stat.ML', 'stat.ML', 'İstatistiksel ML'),
    ]
    
    # Eğitim ile ilgili anahtar kelimeler
    education_keywords = [
        'education', 'learning', 'student', 'teacher', 'classroom',
        'tutoring', 'assessment', 'curriculum', 'pedagogy', 'school',
        'adaptive learning', 'intelligent tutoring', 'educational',
        'e-learning', 'mooc', 'personalized learning'
    ]
    
    for rss_url, category, category_name in arxiv_categories:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:10]:
                title = entry.get('title', '').replace('\n', ' ')
                summary = entry.get('summary', '')[:500] if entry.get('summary') else ''
                link = entry.get('link', '')
                authors = ', '.join([a.get('name', '') for a in entry.get('authors', [])[:3]])[:100]
                
                # Eğitim ile ilgili mi kontrol et
                text = (title + ' ' + summary).lower()
                is_education_related = any(kw in text for kw in education_keywords)
                
                papers.append({
                    'title': title[:200],
                    'summary': summary[:300],
                    'authors': authors,
                    'link': link,
                    'category': category_name,
                    'arxiv_cat': category,
                    'is_education_related': is_education_related,
                    'source': 'arXiv',
                    'needs_translation': True
                })
        except Exception as e:
            print(f"arXiv hatası ({category}): {e}")
            continue
    
    # Eğitim ile ilgili olanları öne al
    papers = sorted(papers, key=lambda x: x.get('is_education_related', False), reverse=True)
    
    return papers[:10]

def get_research_papers() -> List[Dict]:
    """
    Akademik araştırma makaleleri - çeşitli kaynaklardan
    """
    papers = []
    
    # Akademik kaynaklar
    sources = [
        # Nature Education
        ('http://feeds.nature.com/srep/rss/current', 'Nature Scientific Reports'),
        # Science
        ('https://www.science.org/rss/news_current.xml', 'Science News'),
        # PLOS ONE Education
        ('https://journals.plos.org/plosone/feed/atom', 'PLOS ONE'),
        # Frontiers in Education
        ('https://www.frontiersin.org/journals/education/rss', 'Frontiers in Education'),
    ]
    
    education_keywords = [
        'education', 'learning', 'student', 'teacher', 'school',
        'cognitive', 'pedagogy', 'instruction', 'assessment',
        'mathematics', 'stem', 'science education', 'ai', 'technology'
    ]
    
    for rss_url, source_name in sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:8]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:400] if entry.get('summary') else ''
                link = entry.get('link', '')
                
                text = (title + ' ' + summary).lower()
                is_relevant = any(kw in text for kw in education_keywords)
                
                if is_relevant:
                    papers.append({
                        'title': title[:200],
                        'summary': summary[:300],
                        'link': link,
                        'source': source_name,
                        'needs_translation': True
                    })
        except Exception as e:
            print(f"Research RSS hatası ({source_name}): {e}")
            continue
    
    return papers[:6]
# ══════════════════════════════════════════════════════════════════════════════

def get_student_trending_topics() -> List[Dict]:
    """
    Öğrencilerin gündemindeki konular
    Sık sorulan sorular ve güncel konular
    """
    trending = []
    
    # Ekşi Sözlük'ten eğitim başlıkları çekmeye çalış
    try:
        url = "https://eksisozluk.com/basliklar/gundem"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Eğitim ile ilgili anahtar kelimeler
            education_keywords = [
                'lgs', 'yks', 'tyt', 'ayt', 'ösym', 'sınav', 'okul', 'ders',
                'öğretmen', 'öğrenci', 'üniversite', 'lise', 'matematik',
                'fizik', 'kimya', 'biyoloji', 'türkçe', 'tarih', 'coğrafya',
                'müfredat', 'meb', 'eğitim', 'kpss', 'ales', 'yds', 'dgs',
                'sınıf', 'not', 'karne', 'tatil', 'burs', 'yurt', 'kredi'
            ]
            
            # Başlıkları bul - farklı selector'lar dene
            topic_links = soup.select('ul.topic-list a') or soup.select('a[href*="/"]')
            
            for link in topic_links[:50]:
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                # Sadece metin içeren ve eğitimle ilgili olanları al
                if title and len(title) > 5 and len(title) < 100:
                    # # işareti veya garip karakterler içermiyorsa
                    if '#' not in title and 'tüm kanallar' not in title.lower():
                        if any(kw in title.lower() for kw in education_keywords):
                            # Entry sayısını bul
                            small = link.find('small')
                            count = small.get_text(strip=True) if small else ''
                            
                            trending.append({
                                'topic': title[:80],
                                'source': 'Ekşi Sözlük',
                                'entry_count': count,
                                'category': 'Gündem'
                            })
                            
                            if len(trending) >= 6:
                                break
    except Exception as e:
        print(f"Trending topics hatası: {e}")
    
    # Eğer yeterli veri gelmezse, güncel ve sık sorulan konuları ekle
    if len(trending) < 5:
        # Dinamik tarih hesapla
        from datetime import datetime
        today = datetime.now()
        current_month = today.strftime('%B')
        current_year = today.year
        
        # Mevsime göre güncel konular
        month = today.month
        
        # Dönem bazlı konular
        if month in [9, 10, 11]:  # Güz dönemi
            seasonal_topics = [
                {'topic': f'{current_year}-{current_year+1} müfredat değişiklikleri', 'category': 'Müfredat'},
                {'topic': '1. dönem sınav tarihleri', 'category': 'Sınav'},
                {'topic': 'Yeni eğitim öğretim yılı değişiklikleri', 'category': 'Güncel'},
            ]
        elif month in [12, 1]:  # Kış - yarıyıl
            seasonal_topics = [
                {'topic': 'Yarıyıl tatili ne zaman başlıyor?', 'category': 'Tatil'},
                {'topic': '1. dönem karne notları', 'category': 'Not'},
                {'topic': 'Yarıyıl tatilinde nasıl çalışmalı?', 'category': 'Çalışma'},
            ]
        elif month in [2, 3, 4, 5]:  # Bahar - sınav hazırlık
            seasonal_topics = [
                {'topic': 'LGS son tekrar stratejileri', 'category': 'LGS'},
                {'topic': 'YKS motivasyon nasıl korunur?', 'category': 'YKS'},
                {'topic': 'Deneme sınavı değerlendirme', 'category': 'Deneme'},
            ]
        else:  # Yaz
            seasonal_topics = [
                {'topic': 'YKS tercih robotu nasıl kullanılır?', 'category': 'Tercih'},
                {'topic': 'Üniversite tercih stratejileri', 'category': 'Tercih'},
                {'topic': 'Yaz tatilinde verimli çalışma', 'category': 'Çalışma'},
            ]
        
        # Sabit popüler konular
        common_topics = [
            {'topic': '2026 LGS ne zaman yapılacak?', 'category': 'Sınav Takvimi'},
            {'topic': '2026 YKS başvuru tarihleri', 'category': 'Sınav Takvimi'},
            {'topic': 'Beceri temelli sorular nasıl çözülür?', 'category': 'Soru Çözümü'},
            {'topic': 'TYT Matematik konu listesi ve ağırlıkları', 'category': 'Konu'},
            {'topic': 'LGS paragraf soruları taktikleri', 'category': 'Taktik'},
            {'topic': 'Pomodoro tekniği ile verimli çalışma', 'category': 'Çalışma'},
            {'topic': 'Deneme sınavı analizi nasıl yapılır?', 'category': 'Analiz'},
            {'topic': 'Sınav kaygısı ile başa çıkma', 'category': 'Motivasyon'},
        ]
        
        # Mevsimsel + sabit konuları birleştir
        all_topics = seasonal_topics + common_topics
        
        # Mevcut trending'e ekle
        for topic in all_topics:
            if len(trending) < 8:
                # Tekrar kontrolü
                if not any(t['topic'] == topic['topic'] for t in trending):
                    topic['source'] = 'Sık Sorulan'
                    trending.append(topic)
    
    return trending[:8]

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
    Gemini ile kapsamlı günlük analiz ve özet oluştur
    Tüm haberleri yorumlayarak öğretmen ve öğrencilere değerli içgörüler sunar
    """
    if not GEMINI_KEY or not genai:
        return ""
    
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        
        # Haberleri kategorize et
        news_text = ""
        
        # Türkiye haberleri
        news_text += "=== TÜRKİYE EĞİTİM GÜNDEMİ ===\n"
        if all_news.get('meb_news'):
            for n in all_news['meb_news'][:3]:
                news_text += f"- {n['title']}\n"
        if all_news.get('education_news'):
            for n in all_news['education_news'][:4]:
                news_text += f"- {n['title']}\n"
        
        # AI ve EdTech haberleri
        news_text += "\n=== YAPAY ZEKA & EĞİTİM TEKNOLOJİSİ ===\n"
        if all_news.get('ai_news'):
            for n in all_news['ai_news'][:5]:
                news_text += f"- {n['title']} ({n.get('source', '')})\n"
        
        # Matematik haberleri
        news_text += "\n=== MATEMATİK GELİŞMELERİ ===\n"
        if all_news.get('math_news'):
            for n in all_news['math_news'][:3]:
                news_text += f"- {n['title']}\n"
        
        # Global haberler - ülke bazlı
        news_text += "\n=== DÜNYADAN EĞİTİM HABERLERİ ===\n"
        if all_news.get('global_news'):
            country_names = {
                'china': 'Çin', 'japan': 'Japonya', 'korea': 'Güney Kore',
                'finland': 'Finlandiya', 'singapore': 'Singapur', 'russia': 'Rusya',
                'israel': 'İsrail', 'india': 'Hindistan', 'estonia': 'Estonya'
            }
            for country_code, news_list in all_news['global_news'].items():
                country_name = country_names.get(country_code, country_code)
                for n in news_list[:2]:
                    news_text += f"- [{country_name}] {n['title']}\n"
        
        # Bilimsel makaleler
        news_text += "\n=== BİLİMSEL MAKALELER ===\n"
        if all_news.get('arxiv_papers'):
            for p in all_news['arxiv_papers'][:4]:
                edu_tag = "[EĞİTİM]" if p.get('is_education_related') else "[AI/ML]"
                news_text += f"- {edu_tag} {p['title'][:100]}\n"
        
        prompt = f"""Sen deneyimli bir eğitim analisti ve danışmanısın. Aşağıdaki güncel eğitim haberlerini analiz ederek öğretmenler ve öğrenciler için kapsamlı bir günlük brifing hazırla.

{news_text}

GÖREV: Yukarıdaki haberleri analiz ederek aşağıdaki formatta bir rapor yaz:

📊 GÜNÜN ANALİZİ

🇹🇷 TÜRKİYE'DE BUGÜN:
• [Türkiye'deki en önemli 2-3 gelişmeyi analiz et]
• [Bu gelişmelerin öğretmen ve öğrencilere etkisini açıkla]
• [Varsa sınav veya müfredat ile ilgili önemli notları belirt]

🤖 YAPAY ZEKA & TEKNOLOJİ TRENDLERİ:
• [AI ve EdTech haberlerinden önemli gelişmeleri yorumla]
• [Bu teknolojilerin eğitime nasıl entegre edilebileceğini açıkla]
• [Öğretmenlerin dikkat etmesi gereken noktaları belirt]

🌍 DÜNYADAN DERSLER:
• [Farklı ülkelerden gelen haberleri karşılaştır]
• [Türkiye için çıkarılabilecek dersleri belirt]
• [Global trendlerin Türk eğitim sistemine olası etkilerini yorumla]

🔬 BİLİM & ARAŞTIRMA:
• [Akademik makalelerden öne çıkan bulguları özetle]
• [Bu araştırmaların pratik uygulamalarını açıkla]

💡 ÖĞRETMENLERE TAVSİYELER:
• [Günün haberlerinden yola çıkarak 2-3 pratik öneri ver]

📚 ÖĞRENCİLERE NOT:
• [Öğrencilerin bilmesi gereken 1-2 önemli nokta]

KURALLAR:
1. Her madde 1-2 cümle olsun, özlü ama bilgilendirici
2. Haberleri sadece özetleme, YORUMLA ve BAĞLAM ekle
3. Türkçe yaz, akıcı ve profesyonel bir dil kullan
4. Spekülasyon yapma, haberlere dayalı analiz yap
5. Emoji kullan ama aşırıya kaçma
6. Toplam 300-400 kelime civarında tut

Analiz:"""

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
            title = news['title'][:80]
            link = news.get('link', '')
            
            if link:
                report.append(f"{prefix} {title}")
                report.append(f"   🔗 {link}")
            else:
                report.append(f"{prefix} {title}")
    
    # Sonra genel eğitim haberleri
    if education_news:
        report.append("\n📰 GÜNDEM:")
        for news in education_news[:5]:
            prefix = "🔴" if news.get('is_exam_related') else "📌" if news.get('is_important') else "•"
            title = news['title'][:80]
            link = news.get('link', '')
            source = news['source']
            
            if link:
                report.append(f"{prefix} {title}")
                report.append(f"   📍 {source} | 🔗 {link}")
            else:
                report.append(f"{prefix} {title}")
                report.append(f"   📍 {source}")
    
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
                
                link = news.get('link', '')
                report.append(f"\n🚀 {title_tr}")
                if link:
                    report.append(f"   📍 {news['source']} [{news.get('category', '')}]")
                    report.append(f"   🔗 {link}")
                else:
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
                        
                        link = news.get('link', '')
                        report.append(f"• {title_tr[:100]}")
                        if link:
                            report.append(f"  📍 {news['source']} | 🔗 {link}")
                        else:
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
        for news in math_news[:5]:
            # İlk 4 haberi çevir
            if news.get('needs_translation') and translate_count < 4:
                title_tr = translate_to_turkish(news['title'], is_headline=True)
                translate_count += 1
                import time
                time.sleep(0.3)
            else:
                title_tr = news['title']
            
            link = news.get('link', '')
            report.append(f"\n🔬 {title_tr}")
            if link:
                report.append(f"   📍 {news['source']} ({news.get('region', 'Dünya')})")
                report.append(f"   🔗 {link}")
            else:
                report.append(f"   📍 {news['source']} ({news.get('region', 'Dünya')})")
    else:
        report.append("• Henüz yeni haber yok")
    
    report.append("")
    
    # 5. 🌍 GLOBAL EĞİTİM HABERLERİ
    print("🌍 Global eğitim haberleri çekiliyor...")
    global_news = get_global_education_news()
    
    report.append("━" * 50)
    report.append("🌍 DÜNYADAN EĞİTİM HABERLERİ")
    report.append("━" * 50)
    
    # Çeviri sayacı
    translate_count = 0
    max_translations = 10  # Global haberler için maksimum çeviri
    
    # Ülkeleri grupla
    country_groups = {
        'ai_leaders': ['china', 'korea', 'japan'],  # AI'da öncü
        'education_leaders': ['finland', 'singapore', 'estonia'],  # Eğitimde öncü
        'other': ['russia', 'israel', 'india']  # Matematik, Startup, EdTech
    }
    
    group_titles = {
        'ai_leaders': '🤖 AI & TEKNOLOJİ ÖNCÜLERİ',
        'education_leaders': '📚 EĞİTİM ÖNCÜLERİ',
        'other': '🔬 BİLİM & İNOVASYON'
    }
    
    for group_key, countries in country_groups.items():
        group_has_news = False
        group_report = []
        
        for country_code in countries:
            if country_code in global_news and global_news[country_code]:
                if not group_has_news:
                    group_report.append(f"\n{group_titles[group_key]}:")
                    group_has_news = True
                
                for news in global_news[country_code][:2]:
                    # Çeviri
                    if news.get('needs_translation') and translate_count < max_translations:
                        title_tr = translate_to_turkish(news['title'], is_headline=True)
                        translate_count += 1
                        import time
                        time.sleep(0.3)
                    else:
                        title_tr = news['title']
                    
                    flag = news.get('flag', '🌐')
                    country = news.get('country', '')
                    link = news.get('link', '')
                    
                    group_report.append(f"\n{flag} {title_tr[:90]}")
                    if link:
                        group_report.append(f"   📍 {news['source']} ({country})")
                        group_report.append(f"   🔗 {link}")
                    else:
                        group_report.append(f"   📍 {news['source']} ({country})")
        
        if group_has_news:
            report.extend(group_report)
    
    # Eğer hiç global haber yoksa
    if not any(global_news.get(c) for c in global_news):
        report.append("\n• Şu an yeni global haber yok")
    
    report.append("")
    
    # 6. 📄 BİLİMSEL MAKALELER
    print("📄 Bilimsel makaleler çekiliyor...")
    arxiv_papers = get_arxiv_papers()
    research_papers = get_research_papers()
    
    report.append("━" * 50)
    report.append("📄 BİLİMSEL MAKALELER & ARAŞTIRMALAR")
    report.append("━" * 50)
    
    # arXiv makaleleri
    translate_count = 0
    if arxiv_papers:
        # Eğitim ile ilgili olanları öne al
        edu_papers = [p for p in arxiv_papers if p.get('is_education_related')]
        other_papers = [p for p in arxiv_papers if not p.get('is_education_related')]
        
        if edu_papers:
            report.append("\n🎓 EĞİTİM & AI (arXiv):")
            for paper in edu_papers[:3]:
                if paper.get('needs_translation') and translate_count < 4:
                    title_tr = translate_to_turkish(paper['title'], is_headline=True)
                    translate_count += 1
                    import time
                    time.sleep(0.3)
                else:
                    title_tr = paper['title']
                
                report.append(f"\n📑 {title_tr[:100]}")
                report.append(f"   📂 {paper.get('category', 'AI')} | arXiv")
                if paper.get('link'):
                    report.append(f"   🔗 {paper['link']}")
        
        if other_papers:
            report.append("\n🧠 YAPAY ZEKA & ML (arXiv):")
            for paper in other_papers[:2]:
                if paper.get('needs_translation') and translate_count < 6:
                    title_tr = translate_to_turkish(paper['title'], is_headline=True)
                    translate_count += 1
                    import time
                    time.sleep(0.3)
                else:
                    title_tr = paper['title']
                
                report.append(f"\n📑 {title_tr[:100]}")
                report.append(f"   📂 {paper.get('category', 'ML')} | arXiv")
                if paper.get('link'):
                    report.append(f"   🔗 {paper['link']}")
    
    # Diğer akademik makaleler
    if research_papers:
        report.append("\n📚 AKADEMİK ARAŞTIRMALAR:")
        for paper in research_papers[:2]:
            if paper.get('needs_translation') and translate_count < 8:
                title_tr = translate_to_turkish(paper['title'], is_headline=True)
                translate_count += 1
                import time
                time.sleep(0.3)
            else:
                title_tr = paper['title']
            
            report.append(f"\n📖 {title_tr[:100]}")
            report.append(f"   📍 {paper['source']}")
            if paper.get('link'):
                report.append(f"   🔗 {paper['link']}")
    
    if not arxiv_papers and not research_papers:
        report.append("\n• Henüz yeni makale yok")
    
    report.append("")
    
    # 7. ÖĞRENCİ GÜNDEMİ
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
    
    # 8. GÜNÜN MOTİVASYONU
    print("💪 Motivasyon mesajı hazırlanıyor...")
    motivation = get_daily_motivation()
    
    report.append("━" * 50)
    report.append("💪 GÜNÜN MOTİVASYONU")
    report.append("━" * 50)
    report.append("")
    report.append(motivation['message'])
    report.append("")
    
    # 9. GÜNÜN ÖZETİ (AI)
    print("📝 Günün özeti oluşturuluyor...")
    all_news = {
        'meb_news': meb_news,
        'education_news': education_news,
        'ai_news': ai_news,
        'math_news': math_news,
        'global_news': global_news,
        'arxiv_papers': arxiv_papers
    }
    summary = generate_daily_summary(all_news)
    
    if summary:
        report.append("━" * 50)
        report.append("📊 GÜNÜN ANALİZİ & DEĞERLENDİRME")
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
