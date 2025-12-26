"""
🎯 CURRICULUM BECERİ TEMELLİ SORU ÜRETİCİ BOT V3
═══════════════════════════════════════════════════════════════════════════════

TYT, AYT ve LGS sınav formatlarında, günlük yaşam becerilerini ölçen,
güncel müfredatı AŞMAYAN, Bloom taksonomisine uygun sorular üretir.

📚 ÖZELLİKLER:
✅ TYT/AYT/LGS Gerçek Sınav Formatı
✅ 3-12. Sınıf Tüm Kazanımlardan Dengeli Üretim
✅ Bloom Taksonomisi Tam Entegrasyon
✅ Güncel Müfredat Uyumu (Kapsam Aşmama)
✅ Günlük Yaşam Becerileri Temelli Senaryolar
✅ Chain of Thought (CoT) Kalite Sistemi
✅ DeepSeek Doğrulama
✅ Sınıf Bazlı Kota Sistemi (Dengeli Dağılım)

@version 3.0.0
@author MATAİ PRO
"""

import os
import json
import random
import time
import hashlib
import re
from datetime import datetime
from collections import defaultdict
from openai import OpenAI

from google import genai
from google.genai import types
from supabase import create_client

# ═══════════════════════════════════════════════════════════════════════════════
# YAPILANDIRMA
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

# Ayarlar
SORU_PER_KAZANIM = int(os.environ.get('SORU_PER_KAZANIM', '2'))
MAX_ISLEM_PER_RUN = int(os.environ.get('MAX_ISLEM_PER_RUN', '50'))
DEEPSEEK_DOGRULAMA = bool(DEEPSEEK_API_KEY)
COT_AKTIF = True
BEKLEME = 1.5
MAX_DENEME = 5  # 4'ten 5'e artırıldı
MIN_DEEPSEEK_PUAN = 55  # 65'ten 55'e düşürüldü
API_TIMEOUT = 30

PROGRESS_TABLE = 'curriculum_pisa_progress'  # Artık kullanılmıyor, question_bank tabanlı

# ═══════════════════════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

deepseek = None
if DEEPSEEK_API_KEY:
    deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
    print("✅ DeepSeek doğrulama AKTİF")
else:
    print("⚠️ DeepSeek API key yok, doğrulama DEVRE DIŞI")

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════════════════════
# SINAV FORMATLARI - TYT/AYT/LGS
# ═══════════════════════════════════════════════════════════════════════════════

SINAV_FORMATLARI = {
    'LGS': {
        'siniflar': [5, 6, 7, 8],
        'seceneksayisi': 4,  # A, B, C, D
        'senaryo_uzunluk': (60, 100),  # kelime
        'adim_sayisi': (2, 4),
        'zorluk_dagilimi': {'kolay': 0.30, 'orta': 0.50, 'zor': 0.20},
        'ozellikler': [
            'Günlük yaşam senaryoları',
            'Görsel/tablo destekli sorular',
            'Beceri temelli yaklaşım',
            'MEB müfredatına tam uyum',
            'Kısa ve net ifadeler'
        ]
    },
    'TYT': {
        'siniflar': [9, 10],
        'seceneksayisi': 5,  # A, B, C, D, E
        'senaryo_uzunluk': (80, 130),
        'adim_sayisi': (3, 5),
        'zorluk_dagilimi': {'kolay': 0.25, 'orta': 0.50, 'zor': 0.25},
        'ozellikler': [
            'Temel matematik becerileri',
            'Güncel yaşam problemleri',
            'Orta düzey analiz',
            'Lise 9-10 müfredatı'
        ]
    },
    'AYT': {
        'siniflar': [11, 12],
        'seceneksayisi': 5,  # A, B, C, D, E
        'senaryo_uzunluk': (100, 160),
        'adim_sayisi': (4, 6),
        'zorluk_dagilimi': {'kolay': 0.15, 'orta': 0.50, 'zor': 0.35},
        'ozellikler': [
            'İleri düzey analiz ve sentez',
            'Çok adımlı problem çözme',
            'Soyut kavramların uygulaması',
            'Lise 11-12 müfredatı'
        ]
    },
    'ILKOKUL': {
        'siniflar': [3, 4],
        'seceneksayisi': 4,  # A, B, C, D
        'senaryo_uzunluk': (40, 70),
        'adim_sayisi': (1, 2),
        'zorluk_dagilimi': {'kolay': 0.50, 'orta': 0.40, 'zor': 0.10},
        'ozellikler': [
            'Basit ve anlaşılır dil',
            'Somut örnekler',
            'Günlük yaşam durumları',
            'Görsel destekli açıklamalar',
            'Tek veya iki adımlı çözümler'
        ]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# BLOOM TAKSONOMİSİ - TAM ENTEGRASYON
# ═══════════════════════════════════════════════════════════════════════════════

BLOOM_TAKSONOMISI = {
    'hatırlama': {
        'seviye': 1,
        'eylemler': ['tanımla', 'listele', 'hatırla', 'tanı', 'bul', 'seç'],
        'soru_kipleri': ['Aşağıdakilerden hangisi...?', 'Hangisi doğrudur?'],
        'aciklama': 'Bilgiyi olduğu gibi hatırlama',
        'siniflar': [3, 4, 5],  # Ağırlıklı kullanım
        'puan_katsayi': 1.0
    },
    'anlama': {
        'seviye': 2,
        'eylemler': ['açıkla', 'yorumla', 'özetle', 'karşılaştır', 'sınıflandır'],
        'soru_kipleri': ['Bu durumda ne olur?', 'Ne anlama gelir?'],
        'aciklama': 'Anlamı kavrama ve yorumlama',
        'siniflar': [4, 5, 6, 7],
        'puan_katsayi': 1.2
    },
    'uygulama': {
        'seviye': 3,
        'eylemler': ['uygula', 'çöz', 'hesapla', 'kullan', 'göster'],
        'soru_kipleri': ['Buna göre kaç...?', 'Sonuç ne olur?'],
        'aciklama': 'Bilgiyi yeni durumlarda kullanma',
        'siniflar': [5, 6, 7, 8, 9],
        'puan_katsayi': 1.4
    },
    'analiz': {
        'seviye': 4,
        'eylemler': ['analiz et', 'ayırt et', 'incele', 'ilişkilendir', 'karşılaştır'],
        'soru_kipleri': ['Aradaki fark nedir?', 'Hangi sonuca ulaşılır?'],
        'aciklama': 'Bilgiyi parçalara ayırma ve ilişkileri anlama',
        'siniflar': [7, 8, 9, 10, 11],
        'puan_katsayi': 1.6
    },
    'değerlendirme': {
        'seviye': 5,
        'eylemler': ['değerlendir', 'eleştir', 'karar ver', 'seç', 'savun'],
        'soru_kipleri': ['Hangisi en uygun?', 'En doğru yaklaşım hangisi?'],
        'aciklama': 'Kriterlere göre yargıda bulunma',
        'siniflar': [9, 10, 11, 12],
        'puan_katsayi': 1.8
    },
    'yaratma': {
        'seviye': 6,
        'eylemler': ['tasarla', 'oluştur', 'planla', 'üret', 'geliştir'],
        'soru_kipleri': ['Nasıl bir çözüm üretilir?', 'Hangi strateji izlenir?'],
        'aciklama': 'Yeni ve özgün ürün/fikir oluşturma',
        'siniflar': [10, 11, 12],
        'puan_katsayi': 2.0
    }
}

# Sınıf -> Bloom Eşleştirmesi (Gerçekçi seviyeler)
SINIF_BLOOM_ESLESTIRME = {
    3: ['hatırlama', 'anlama'],
    4: ['hatırlama', 'anlama'],
    5: ['anlama', 'uygulama'],
    6: ['anlama', 'uygulama'],
    7: ['uygulama', 'analiz'],
    8: ['uygulama', 'analiz'],
    9: ['uygulama', 'analiz'],
    10: ['uygulama', 'analiz'],
    11: ['uygulama', 'analiz'],  # Değerlendirme/yaratma kaldırıldı
    12: ['uygulama', 'analiz']   # Değerlendirme/yaratma kaldırıldı
}

# ═══════════════════════════════════════════════════════════════════════════════
# GÜNLÜK YAŞAM BECERİLERİ BAĞLAMLARI
# ═══════════════════════════════════════════════════════════════════════════════

YASAM_BECERILERI_BAGLAMLARI = {
    'finansal_okuryazarlik': {
        'ad': 'Finansal Okuryazarlık',
        'temalar': [
            {'tema': 'alısveris_butce', 'aciklama': 'Harçlık yönetimi, indirim hesaplama, bütçe planı'},
            {'tema': 'tasarruf_birikim', 'aciklama': 'Birikim planı, faiz hesabı, hedef tasarruf'},
            {'tema': 'fiyat_karsilastirma', 'aciklama': 'Birim fiyat karşılaştırma, kampanya analizi'},
            {'tema': 'harcama_takibi', 'aciklama': 'Aylık gider takibi, kategori analizi'}
        ],
        'siniflar': [5, 6, 7, 8, 9, 10, 11, 12]
    },
    'saglik_beslenme': {
        'ad': 'Sağlık ve Beslenme',
        'temalar': [
            {'tema': 'kalori_hesaplama', 'aciklama': 'Günlük kalori ihtiyacı, besin değerleri'},
            {'tema': 'ilac_dozaj', 'aciklama': 'İlaç dozajı, saatlik alım planı'},
            {'tema': 'spor_performans', 'aciklama': 'Egzersiz süresi, kalori yakımı, nabız'},
            {'tema': 'uyku_duzeni', 'aciklama': 'Uyku süresi hesaplama, uyku kalitesi'}
        ],
        'siniflar': [4, 5, 6, 7, 8, 9, 10, 11, 12]
    },
    'zaman_yonetimi': {
        'ad': 'Zaman Yönetimi',
        'temalar': [
            {'tema': 'ders_programi', 'aciklama': 'Ders çalışma planı, zaman dağılımı'},
            {'tema': 'seyahat_planlama', 'aciklama': 'Varış saati hesaplama, aktarma planı'},
            {'tema': 'proje_zamanlama', 'aciklama': 'Görev süresi tahmini, deadline hesabı'},
            {'tema': 'gunluk_rutin', 'aciklama': 'Günlük aktivite planlaması'}
        ],
        'siniflar': [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    },
    'cevre_surdurulebilirlik': {
        'ad': 'Çevre ve Sürdürülebilirlik',
        'temalar': [
            {'tema': 'enerji_tasarrufu', 'aciklama': 'Elektrik/su tüketimi, tasarruf hesabı'},
            {'tema': 'geri_donusum', 'aciklama': 'Geri dönüşüm oranları, atık hesabı'},
            {'tema': 'karbon_ayakizi', 'aciklama': 'Ulaşım tercihi, karbon salınımı'},
            {'tema': 'dogal_kaynak', 'aciklama': 'Su/enerji kullanımı, kaynak yönetimi'}
        ],
        'siniflar': [5, 6, 7, 8, 9, 10, 11, 12]
    },
    'dijital_okuryazarlik': {
        'ad': 'Dijital Okuryazarlık',
        'temalar': [
            {'tema': 'veri_boyutu', 'aciklama': 'Dosya boyutu, indirme süresi, depolama'},
            {'tema': 'internet_kullanimi', 'aciklama': 'Kota hesabı, veri tüketimi'},
            {'tema': 'sosyal_medya', 'aciklama': 'İstatistik analizi, etkileşim oranı'},
            {'tema': 'online_guvenlik', 'aciklama': 'Şifre güvenliği, güvenlik puanı'}
        ],
        'siniflar': [6, 7, 8, 9, 10, 11, 12]
    },
    'ev_yonetimi': {
        'ad': 'Ev Yönetimi',
        'temalar': [
            {'tema': 'yemek_hazirlama', 'aciklama': 'Tarif oranları, porsiyon hesabı'},
            {'tema': 'ev_duzenleme', 'aciklama': 'Oda boyama, mobilya yerleşimi'},
            {'tema': 'fatura_hesaplama', 'aciklama': 'Elektrik/su faturası, tüketim analizi'},
            {'tema': 'market_alisverisi', 'aciklama': 'Liste oluşturma, maliyet tahmini'}
        ],
        'siniflar': [3, 4, 5, 6, 7, 8, 9, 10]
    },
    'bilimsel_dusunme': {
        'ad': 'Bilimsel Düşünme',
        'temalar': [
            {'tema': 'deney_olcum', 'aciklama': 'Ölçüm analizi, veri yorumlama'},
            {'tema': 'hava_durumu', 'aciklama': 'Sıcaklık değişimi, tahmin doğruluğu'},
            {'tema': 'doga_gozlemi', 'aciklama': 'Popülasyon takibi, büyüme oranı'},
            {'tema': 'istatistik_analiz', 'aciklama': 'Veri toplama, grafik yorumlama'}
        ],
        'siniflar': [6, 7, 8, 9, 10, 11, 12]
    },
    'mesleki_beceriler': {
        'ad': 'Mesleki Beceriler',
        'temalar': [
            {'tema': 'insaat_olcum', 'aciklama': 'Alan hesabı, malzeme miktarı'},
            {'tema': 'ticaret_hesap', 'aciklama': 'Kar/zarar, maliyet analizi'},
            {'tema': 'tarim_planlama', 'aciklama': 'Ekim alanı, verim hesabı'},
            {'tema': 'uretim_planlama', 'aciklama': 'Malzeme kesimi, fire hesabı'}
        ],
        'siniflar': [8, 9, 10, 11, 12]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# TÜRK İSİMLERİ
# ═══════════════════════════════════════════════════════════════════════════════

TURK_ISIMLERI = {
    'kiz': ['Elif', 'Zeynep', 'Defne', 'Ecrin', 'Azra', 'Nehir', 'Asya', 'Mira', 'Ela', 'Duru', 
            'Lina', 'Ada', 'Eylül', 'Ceren', 'İpek', 'Sude', 'Yağmur', 'Melis', 'Beren', 'Nil'],
    'erkek': ['Yusuf', 'Eymen', 'Ömer', 'Emir', 'Mustafa', 'Ahmet', 'Kerem', 'Miran', 'Çınar', 'Aras',
              'Kuzey', 'Efe', 'Baran', 'Rüzgar', 'Atlas', 'Arda', 'Doruk', 'Eren', 'Burak', 'Kaan']
}

kullanilan_isimler = set()

def rastgele_isim_sec():
    global kullanilan_isimler
    cinsiyet = random.choice(['kiz', 'erkek'])
    isimler = TURK_ISIMLERI[cinsiyet]
    if len(kullanilan_isimler) >= len(isimler) * 0.7:
        kullanilan_isimler.clear()
    kullanilabilir = [i for i in isimler if i not in kullanilan_isimler]
    if not kullanilabilir:
        kullanilabilir = isimler
    secilen = random.choice(kullanilabilir)
    kullanilan_isimler.add(secilen)
    return secilen

# ═══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════════════

kullanilan_hashler = set()

def hash_olustur(soru):
    icerik = f"{soru.get('soru_metni', '')}|{soru.get('dogru_cevap', '')}"
    return hashlib.md5(icerik.encode()).hexdigest()

def benzersiz_mi(soru):
    return hash_olustur(soru) not in kullanilan_hashler

def hash_kaydet(soru):
    kullanilan_hashler.add(hash_olustur(soru))

def sinav_formati_belirle(sinif):
    """Sınıfa göre sınav formatını belirle"""
    for format_adi, format_bilgi in SINAV_FORMATLARI.items():
        if sinif in format_bilgi['siniflar']:
            return format_adi, format_bilgi
    return 'LGS', SINAV_FORMATLARI['LGS']

def zorluk_sec(format_bilgi):
    """Zorluk dağılımına göre rastgele zorluk seç"""
    r = random.random()
    dagilim = format_bilgi['zorluk_dagilimi']
    if r < dagilim['kolay']:
        return 'kolay'
    elif r < dagilim['kolay'] + dagilim['orta']:
        return 'orta'
    return 'zor'

def bloom_seviye_sec(sinif):
    """Sınıfa uygun Bloom seviyesi seç"""
    uygun_seviyeler = SINIF_BLOOM_ESLESTIRME.get(sinif, ['uygulama'])
    return random.choice(uygun_seviyeler)

def uygun_baglam_sec(sinif, topic_name=''):
    """Sınıfa ve KONUYA uygun yaşam becerisi bağlamı seç"""
    topic_lower = topic_name.lower() if topic_name else ''
    
    # Geometri konuları için özel bağlamlar
    geometri_kelimeleri = ['üçgen', 'dörtgen', 'çokgen', 'daire', 'çember', 'alan', 'çevre', 
                           'hacim', 'prizma', 'silindir', 'koni', 'küre', 'açı', 'geometri',
                           'dönüşüm', 'öteleme', 'yansıma', 'benzerlik', 'eşlik', 'koordinat']
    
    is_geometri = any(k in topic_lower for k in geometri_kelimeleri)
    
    if is_geometri:
        # Geometri için uygun bağlamlar
        geometri_baglamlari = [
            {'kategori': 'ev_yonetimi', 'kategori_ad': 'Ev Yönetimi', 
             'tema': 'ev_duzenleme', 'aciklama': 'Oda boyama, mobilya yerleşimi, bahçe düzenleme'},
            {'kategori': 'mesleki_beceriler', 'kategori_ad': 'Mesleki Beceriler',
             'tema': 'insaat_olcum', 'aciklama': 'Alan hesabı, malzeme miktarı, ölçüm'},
            {'kategori': 'mesleki_beceriler', 'kategori_ad': 'Mesleki Beceriler',
             'tema': 'tarim_planlama', 'aciklama': 'Ekim alanı, tarla ölçümü'},
            {'kategori': 'bilimsel_dusunme', 'kategori_ad': 'Bilimsel Düşünme',
             'tema': 'deney_olcum', 'aciklama': 'Ölçüm analizi, alan/hacim hesabı'},
            {'kategori': 'cevre_surdurulebilirlik', 'kategori_ad': 'Çevre ve Sürdürülebilirlik',
             'tema': 'dogal_kaynak', 'aciklama': 'Park alanı, yeşil alan hesabı'}
        ]
        return random.choice(geometri_baglamlari)
    
    # Sayılar/Cebir konuları için uygun bağlamlar
    sayi_kelimeleri = ['sayı', 'kesir', 'ondalık', 'oran', 'yüzde', 'üslü', 'karekök',
                       'denklem', 'eşitsizlik', 'cebir', 'özdeşlik', 'çarpan', 'bölünebilme']
    
    is_sayi = any(k in topic_lower for k in sayi_kelimeleri)
    
    if is_sayi:
        sayi_baglamlari = [
            {'kategori': 'finansal_okuryazarlik', 'kategori_ad': 'Finansal Okuryazarlık',
             'tema': 'alısveris_butce', 'aciklama': 'İndirim hesaplama, bütçe planı'},
            {'kategori': 'finansal_okuryazarlik', 'kategori_ad': 'Finansal Okuryazarlık',
             'tema': 'tasarruf_birikim', 'aciklama': 'Birikim planı, faiz hesabı'},
            {'kategori': 'finansal_okuryazarlik', 'kategori_ad': 'Finansal Okuryazarlık',
             'tema': 'fiyat_karsilastirma', 'aciklama': 'Birim fiyat karşılaştırma'},
            {'kategori': 'saglik_beslenme', 'kategori_ad': 'Sağlık ve Beslenme',
             'tema': 'kalori_hesaplama', 'aciklama': 'Günlük kalori ihtiyacı, besin değerleri'},
            {'kategori': 'zaman_yonetimi', 'kategori_ad': 'Zaman Yönetimi',
             'tema': 'ders_programi', 'aciklama': 'Ders çalışma planı, zaman dağılımı'}
        ]
        return random.choice(sayi_baglamlari)
    
    # Olasılık/İstatistik konuları için
    istatistik_kelimeleri = ['olasılık', 'istatistik', 'veri', 'grafik', 'ortalama', 
                             'medyan', 'mod', 'permütasyon', 'kombinasyon']
    
    is_istatistik = any(k in topic_lower for k in istatistik_kelimeleri)
    
    if is_istatistik:
        istatistik_baglamlari = [
            {'kategori': 'bilimsel_dusunme', 'kategori_ad': 'Bilimsel Düşünme',
             'tema': 'istatistik_analiz', 'aciklama': 'Veri toplama, grafik yorumlama'},
            {'kategori': 'bilimsel_dusunme', 'kategori_ad': 'Bilimsel Düşünme',
             'tema': 'hava_durumu', 'aciklama': 'Sıcaklık değişimi, tahmin doğruluğu'},
            {'kategori': 'dijital_okuryazarlik', 'kategori_ad': 'Dijital Okuryazarlık',
             'tema': 'sosyal_medya', 'aciklama': 'İstatistik analizi, etkileşim oranı'},
            {'kategori': 'saglik_beslenme', 'kategori_ad': 'Sağlık ve Beslenme',
             'tema': 'spor_performans', 'aciklama': 'Performans takibi, istatistik'}
        ]
        return random.choice(istatistik_baglamlari)
    
    # Türev/İntegral/Limit için
    analiz_kelimeleri = ['türev', 'integral', 'limit', 'fonksiyon', 'logaritma', 'üstel']
    
    is_analiz = any(k in topic_lower for k in analiz_kelimeleri)
    
    if is_analiz:
        analiz_baglamlari = [
            {'kategori': 'bilimsel_dusunme', 'kategori_ad': 'Bilimsel Düşünme',
             'tema': 'doga_gozlemi', 'aciklama': 'Popülasyon değişimi, büyüme oranı'},
            {'kategori': 'bilimsel_dusunme', 'kategori_ad': 'Bilimsel Düşünme',
             'tema': 'hava_durumu', 'aciklama': 'Sıcaklık değişim hızı'},
            {'kategori': 'mesleki_beceriler', 'kategori_ad': 'Mesleki Beceriler',
             'tema': 'uretim_planlama', 'aciklama': 'Maliyet optimizasyonu, verimlilik'},
            {'kategori': 'cevre_surdurulebilirlik', 'kategori_ad': 'Çevre ve Sürdürülebilirlik',
             'tema': 'enerji_tasarrufu', 'aciklama': 'Enerji tüketim değişimi'}
        ]
        return random.choice(analiz_baglamlari)
    
    # Genel durum - sınıfa uygun bağlam
    uygun_baglamlar = []
    for baglam_key, baglam_bilgi in YASAM_BECERILERI_BAGLAMLARI.items():
        if sinif in baglam_bilgi['siniflar']:
            uygun_baglamlar.append((baglam_key, baglam_bilgi))
    
    if not uygun_baglamlar:
        uygun_baglamlar = list(YASAM_BECERILERI_BAGLAMLARI.items())
    
    baglam_key, baglam_bilgi = random.choice(uygun_baglamlar)
    tema = random.choice(baglam_bilgi['temalar'])
    
    return {
        'kategori': baglam_key,
        'kategori_ad': baglam_bilgi['ad'],
        'tema': tema['tema'],
        'aciklama': tema['aciklama']
    }

# ═══════════════════════════════════════════════════════════════════════════════
# CURRICULUM VERİ ÇEKİMİ - DENGELİ DAĞILIM
# ═══════════════════════════════════════════════════════════════════════════════

def curriculum_getir():
    """Curriculum tablosundan TÜM Matematik kazanımlarını çeker (3-12. sınıf)"""
    try:
        result = supabase.table('curriculum')\
            .select('*')\
            .eq('lesson_name', 'Matematik')\
            .gte('grade_level', 3)\
            .lte('grade_level', 12)\
            .execute()
        
        if result.data:
            # Sınıf bazlı dağılımı göster
            sinif_dagilimi = defaultdict(int)
            for item in result.data:
                sinif_dagilimi[item.get('grade_level', 0)] += 1
            
            print(f"✅ {len(result.data)} Matematik kazanımı bulundu (3-12. sınıf)")
            print(f"   📊 Sınıf Dağılımı:")
            for sinif in sorted(sinif_dagilimi.keys()):
                format_adi, _ = sinav_formati_belirle(sinif)
                print(f"      {sinif}. Sınıf ({format_adi}): {sinif_dagilimi[sinif]} kazanım")
            
            return result.data
        else:
            # Alternatif arama
            print("⚠️ 'Matematik' bulunamadı, alternatif arama yapılıyor...")
            result = supabase.table('curriculum')\
                .select('*')\
                .gte('grade_level', 3)\
                .lte('grade_level', 12)\
                .execute()
            
            if result.data:
                matematik_kayitlari = [
                    r for r in result.data 
                    if 'matematik' in str(r.get('lesson_name', '')).lower()
                    or 'math' in str(r.get('lesson_name', '')).lower()
                ]
                print(f"✅ {len(matematik_kayitlari)} Matematik kazanımı bulundu (alternatif)")
                return matematik_kayitlari
            
            print("⚠️ Curriculum tablosunda Matematik verisi bulunamadı")
            return []
            
    except Exception as e:
        print(f"❌ Curriculum çekme hatası: {str(e)}")
        return []

# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS TAKİP SİSTEMİ - QUESTION_BANK TABANLI
# ═══════════════════════════════════════════════════════════════════════════════

# Progress için ayrı tablo yerine question_bank'taki mevcut soruları sayıyoruz
PROGRESS_CACHE = {}

def progress_tablosu_kontrol():
    """Her zaman True döner - question_bank tablosunu kullanıyoruz"""
    return True

def question_bank_soru_sayisi_getir(curriculum_id):
    """Bir kazanım için question_bank'taki mevcut soru sayısını getir"""
    global PROGRESS_CACHE
    
    # Cache'de varsa döndür
    if curriculum_id in PROGRESS_CACHE:
        return PROGRESS_CACHE[curriculum_id]
    
    try:
        result = supabase.table('question_bank')\
            .select('id', count='exact')\
            .eq('kazanim_id', curriculum_id)\
            .eq('subject', 'Matematik')\
            .execute()
        
        count = result.count if result.count else 0
        PROGRESS_CACHE[curriculum_id] = count
        return count
    except:
        return 0

def progress_getir(curriculum_id):
    """Bir kazanım için mevcut progress'i getir (question_bank tabanlı)"""
    soru_sayisi = question_bank_soru_sayisi_getir(curriculum_id)
    
    # Tur hesapla: Her SORU_PER_KAZANIM soru = 1 tur
    tur = (soru_sayisi // SORU_PER_KAZANIM) + 1
    kalan = soru_sayisi % SORU_PER_KAZANIM
    
    return {
        'curriculum_id': curriculum_id,
        'current_tur': tur,
        'questions_in_current_tur': kalan,
        'total_questions': soru_sayisi
    }

def progress_guncelle(curriculum_id, tur, soru_sayisi):
    """Cache'i güncelle (artık ayrı tablo yok)"""
    global PROGRESS_CACHE
    # Cache'i güncelle - yeni soru eklendiyse
    if curriculum_id in PROGRESS_CACHE:
        PROGRESS_CACHE[curriculum_id] += 1
    else:
        PROGRESS_CACHE[curriculum_id] = soru_sayisi

def mevcut_turu_hesapla(curriculum_data):
    """Mevcut turu hesapla - işlenecek en düşük turu bul"""
    min_tur = float('inf')
    max_tur = 0
    
    for item in curriculum_data:
        progress = progress_getir(item['id'])
        tur = progress.get('current_tur', 1)
        soru = progress.get('questions_in_current_tur', 0)
        
        max_tur = max(max_tur, tur)
        
        # Bu kazanımda eksik soru varsa, bu tur işlenmeli
        if soru < SORU_PER_KAZANIM:
            min_tur = min(min_tur, tur)
    
    # Eğer hiç eksik yoksa (min_tur güncellenmedi), max_tur döndür
    # Bu durumda tüm kazanımlar bu turda tamamlanmış demektir
    if min_tur == float('inf'):
        return max_tur
    
    return min_tur

def tur_tamamlandi_mi(curriculum_data, tur):
    """Belirtilen turun tamamlanıp tamamlanmadığını kontrol et"""
    for item in curriculum_data:
        progress = progress_getir(item['id'])
        mevcut_tur = progress.get('current_tur', 1)
        soru = progress.get('questions_in_current_tur', 0)
        
        # Bu kazanım henüz bu tura ulaşmamış
        if mevcut_tur < tur:
            return False
        
        # Bu kazanım bu turda ama henüz tamamlanmamış
        # NOT: mevcut_tur == tur ve soru == 0 ise bu kazanım bir önceki turu
        # tamamlamış ve yeni tura geçmiş demektir, bu durumda tamamlanmamış
        if mevcut_tur == tur and soru < SORU_PER_KAZANIM:
            return False
    
    return True

def sonraki_kazanimlari_getir(curriculum_data, tur, limit):
    """
    DENGELİ DAĞILIM: Her sınıftan eşit sayıda kazanım seç
    Hem mevcut turdan hem de sonraki turlardan eksik kazanımları al
    """
    # Sınıflara göre grupla
    sinif_gruplari = defaultdict(list)
    
    for item in curriculum_data:
        sinif = item.get('grade_level', 8)
        progress = progress_getir(item['id'])
        
        mevcut_tur = progress.get('current_tur', 1)
        mevcut_soru = progress.get('questions_in_current_tur', 0)
        
        # Eksik soru varsa ekle (hangi turda olursa olsun)
        if mevcut_soru < SORU_PER_KAZANIM:
            # Öncelik: Düşük turlar önce
            oncelik = mevcut_tur * 1000 + mevcut_soru
            sinif_gruplari[sinif].append({
                'curriculum': item,
                'tur': mevcut_tur,
                'mevcut_soru': mevcut_soru,
                'oncelik': oncelik
            })
    
    # Her sınıftaki kazanımları önceliğe göre sırala
    for sinif in sinif_gruplari:
        sinif_gruplari[sinif].sort(key=lambda x: x['oncelik'])
    
    # Dengeli dağılım: Her sınıftan eşit sayıda al
    sonuc = []
    sinif_sayisi = len(sinif_gruplari)
    
    if sinif_sayisi == 0:
        return []
    
    per_sinif = max(1, limit // sinif_sayisi)
    
    # Önce her sınıftan eşit sayıda al (öncelik sırasına göre)
    for sinif in sorted(sinif_gruplari.keys()):
        items = sinif_gruplari[sinif]
        sonuc.extend(items[:per_sinif])
    
    # Limit'e kadar doldur
    if len(sonuc) < limit:
        tum_kalanlar = []
        for sinif, items in sinif_gruplari.items():
            tum_kalanlar.extend(items[per_sinif:])
        tum_kalanlar.sort(key=lambda x: x['oncelik'])
        sonuc.extend(tum_kalanlar[:limit - len(sonuc)])
    
    random.shuffle(sonuc)  # Final karıştırma
    return sonuc[:limit]

# ═══════════════════════════════════════════════════════════════════════════════
# COT (CHAIN OF THOUGHT) ÇÖZÜM SİSTEMİ
# ═══════════════════════════════════════════════════════════════════════════════

def cot_cozum_olustur(curriculum_row, params):
    """Önce matematiksel çözümü oluştur, sonra soruyu bundan türet"""
    try:
        sinif = curriculum_row.get('grade_level', 8)
        topic = curriculum_row.get('topic_name', '')
        sub_topic = curriculum_row.get('sub_topic', '')
        baglam = params.get('baglam', {})
        
        format_adi, format_bilgi = sinav_formati_belirle(sinif)
        min_adim, max_adim = format_bilgi['adim_sayisi']
        
        isim = rastgele_isim_sec()
        
        prompt = f'''Sen bir matematik öğretmenisin. {sinif}. sınıf "{topic}" konusunda bir problem TASARLA ve ÇÖZ.

## KONU
• Ana Konu: {topic}
• Alt Konu: {sub_topic if sub_topic else 'Genel'}
• Sınıf: {sinif}. Sınıf

## BAĞLAM
{baglam.get('kategori_ad', 'Günlük Yaşam')} - {baglam.get('tema', 'genel').replace('_', ' ')}
Açıklama: {baglam.get('aciklama', 'Günlük yaşam problemi')}

## KARAKTER
{isim} (Tek karakter kullan!)

## GÖREV
1. "{topic}" konusuyla DOĞRUDAN ilgili bir problem tasarla
2. Küçük, hesaplanabilir sayılar kullan (1-100 arası)
3. Adım adım çöz ({min_adim}-{max_adim} adım)
4. Sonucu açıkça belirt

## JSON FORMATI
```json
{{
  "problem": "[40-80 kelime problem tanımı - {isim} karakteri ile]",
  "verilen_degerler": {{"değişken1": değer1, "değişken2": değer2}},
  "istenen": "Ne bulunacak?",
  "cozum_adimlari": [
    "Adım 1: [Açıklama] → [İşlem] = [Sonuç]",
    "Adım 2: [Açıklama] → [İşlem] = [Sonuç]"
  ],
  "sonuc": [sayısal sonuç],
  "sonuc_aciklama": "[Sonucun anlamı]"
}}
```

⚠️ SADECE JSON döndür!'''

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.6,  # Daha düşük sıcaklık = daha tutarlı
                max_output_tokens=1500,
                response_mime_type="application/json"
            )
        )
        
        return json_temizle(response.text.strip())
        
    except Exception as e:
        print(f"      ⚠️ CoT hatası: {str(e)[:40]}")
        return None


def cozumden_soru_olustur(cozum, curriculum_row, params):
    """Hazır çözümden çoktan seçmeli soru oluştur"""
    try:
        sinif = curriculum_row.get('grade_level', 8)
        topic = curriculum_row.get('topic_name', '')
        
        format_adi, format_bilgi = sinav_formati_belirle(sinif)
        secenek_sayisi = format_bilgi['seceneksayisi']
        
        if secenek_sayisi == 4:
            secenek_harfleri = "A, B, C, D"
        else:
            secenek_harfleri = "A, B, C, D, E"
        
        sonuc = cozum.get('sonuc', 0)
        
        prompt = f'''Aşağıdaki çözülmüş problemi {secenek_sayisi} seçenekli çoktan seçmeli soruya dönüştür.

## HAZIR ÇÖZÜM
**Problem:** {cozum.get('problem', '')}
**Veriler:** {json.dumps(cozum.get('verilen_degerler', {}), ensure_ascii=False)}
**İstenen:** {cozum.get('istenen', '')}
**Çözüm:** {json.dumps(cozum.get('cozum_adimlari', []), ensure_ascii=False)}
**Sonuç:** {sonuc}
**Açıklama:** {cozum.get('sonuc_aciklama', '')}

## GÖREV
1. Problemi senaryo + soru olarak yeniden yaz
2. Doğru cevap: {sonuc}
3. Çeldiriciler: Yaygın hesaplama hatalarından türet
4. MUTLAKA {secenek_sayisi} seçenek olsun ({secenek_harfleri})

## JSON FORMATI
```json
{{
  "senaryo": "[Problem metni]",
  "soru_metni": "[Soru kökü - ne soruluyor?]",
  "secenekler": {{
    "A": "[değer]",
    "B": "[değer]",
    "C": "[değer]",
    "D": "[değer]"{"," if secenek_sayisi == 5 else ""}
    {"\"E\": \"[değer]\"" if secenek_sayisi == 5 else ""}
  }},
  "dogru_cevap": "[{secenek_harfleri}'den biri]",
  "cozum_adimlari": {json.dumps(cozum.get('cozum_adimlari', []), ensure_ascii=False)},
  "solution_detailed": "[Öğrenci dostu detaylı açıklama]",
  "celdirici_aciklamalar": {{
    "[Yanlış şık]": "[Neden yanlış]"
  }}
}}
```

⚠️ Doğru cevap MUTLAKA {sonuc} olmalı!
⚠️ SADECE JSON döndür!'''

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=2000,
                response_mime_type="application/json"
            )
        )
        
        soru = json_temizle(response.text.strip())
        
        if soru:
            # Meta bilgileri ekle
            soru['sinif'] = sinif
            soru['curriculum_id'] = curriculum_row.get('id')
            soru['topic_name'] = topic
            soru['sub_topic'] = curriculum_row.get('sub_topic', '')
            soru['bloom_seviye'] = params.get('bloom_seviye', 'uygulama')
            soru['baglam_kategori'] = params.get('baglam', {}).get('kategori', 'genel')
        
        return soru
        
    except Exception as e:
        print(f"      ⚠️ Soru oluşturma hatası: {str(e)[:40]}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# JSON TEMİZLEME
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """AI'dan gelen JSON'u temizle ve parse et"""
    if not text:
        return None
    
    if '```json' in text:
        try:
            text = text.split('```json')[1].split('```')[0]
        except:
            pass
    elif '```' in text:
        parts = text.split('```')
        for part in parts:
            if '{' in part and '}' in part:
                text = part
                break
    
    text = text.strip()
    if text.lower().startswith('json'):
        text = text[4:].strip()
    
    start = text.find('{')
    end = text.rfind('}')
    
    if start < 0 or end < 0 or end <= start:
        return None
    
    text = text[start:end+1]
    
    text = text.replace('\t', ' ')
    text = text.replace('\r\n', ' ')
    text = text.replace('\r', ' ')
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*\]', ']', text)
    
    try:
        return json.loads(text)
    except:
        pass
    
    try:
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return json.loads(text)
    except:
        pass
    
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# MÜFREDAT UYUMU KONTROLÜ
# ═══════════════════════════════════════════════════════════════════════════════

def mufredat_uyumu_prompt(curriculum_row):
    """Kazanıma göre müfredat sınırlarını belirle"""
    sinif = curriculum_row.get('grade_level', 8)
    topic = curriculum_row.get('topic_name', '')
    sub_topic = curriculum_row.get('sub_topic', '')
    
    # Excluded scope (kapsam dışı konular)
    excluded = curriculum_row.get('excluded_scope', '[]')
    try:
        excluded_list = json.loads(excluded) if excluded else []
    except:
        excluded_list = []
    
    # Included scope (dahil konular)
    included = curriculum_row.get('included_scope', '[]')
    try:
        included_list = json.loads(included) if included else []
    except:
        included_list = []
    
    uyari = f"""
## ⚠️ MÜFREDAT SINIRLARI - ÇOK ÖNEMLİ!

Bu soru {sinif}. SINIF müfredatına UYGUN olmalıdır.

### ✅ KULLANILACAK KAVRAMLAR ({topic} - {sub_topic}):
"""
    if included_list and included_list != ["Bu konuya dahil olan 1", "Bu konuya dahil olan 2"]:
        uyari += f"• {', '.join(included_list)}\n"
    else:
        uyari += f"• {topic} konusundaki temel kavramlar\n"
    
    uyari += """
### ❌ KULLANILMAYACAK KAVRAMLAR (Üst sınıf konuları):
"""
    if excluded_list and excluded_list != ["Bu konuya dahil olmayan 1", "Bu konuya dahil olmayan 2"]:
        for item in excluded_list:
            uyari += f"• {item}\n"
    else:
        # Sınıfa göre genel sınırlamalar
        if sinif <= 4:
            uyari += """• Negatif sayılar
• Kesir ve ondalık kesir işlemleri
• Denklemler
• Koordinat sistemi
"""
        elif sinif <= 6:
            uyari += """• Köklü sayılar
• Üslü sayılarda ileri işlemler
• 2. dereceden denklemler
• Trigonometri
"""
        elif sinif <= 8:
            uyari += """• Logaritma
• Türev ve integral
• Limit
• Kompleks sayılar
"""
        else:
            uyari += """• Sadece lise müfredatındaki kavramları kullan
• Üniversite düzeyindeki kavramlardan kaçın
"""
    
    uyari += f"""
### 🎯 UYARI:
- Soru MUTLAKA {sinif}. sınıf seviyesinde olmalı
- Üst sınıf kavramları KESINLIKLE kullanma
- Öğrencinin bilgi düzeyini aşan sorular KABUL EDİLMEZ
"""
    return uyari

# ═══════════════════════════════════════════════════════════════════════════════
# SORU ÜRETİM PROMPT'U - V3
# ═══════════════════════════════════════════════════════════════════════════════

def soru_uretim_prompt_olustur(curriculum_row, params):
    """Kapsamlı soru üretim prompt'u oluştur"""
    
    sinif = curriculum_row.get('grade_level', 8)
    topic = curriculum_row.get('topic_name', '')
    sub_topic = curriculum_row.get('sub_topic', '')
    learning_outcome = curriculum_row.get('learning_outcome_code', '')
    
    # Format bilgileri
    format_adi, format_bilgi = sinav_formati_belirle(sinif)
    secenek_sayisi = format_bilgi['seceneksayisi']
    min_kelime, max_kelime = format_bilgi['senaryo_uzunluk']
    min_adim, max_adim = format_bilgi['adim_sayisi']
    
    # Params
    bloom_seviye = params.get('bloom_seviye', 'uygulama')
    zorluk = params.get('zorluk', 'orta')
    baglam = params.get('baglam', {})
    
    bloom_bilgi = BLOOM_TAKSONOMISI.get(bloom_seviye, BLOOM_TAKSONOMISI['uygulama'])
    
    # Karakter seçimi
    isim1 = rastgele_isim_sec()
    
    # Key concepts
    try:
        key_concepts = json.loads(curriculum_row.get('key_concepts', '[]')) if curriculum_row.get('key_concepts') else []
    except:
        key_concepts = []
    
    # Real life contexts
    try:
        real_life = json.loads(curriculum_row.get('real_life_contexts', '[]')) if curriculum_row.get('real_life_contexts') else []
    except:
        real_life = []
    
    # Seçenek harfleri
    if secenek_sayisi == 4:
        secenek_harfleri = "A, B, C, D"
        secenek_json = '"A": "...", "B": "...", "C": "...", "D": "..."'
    else:
        secenek_harfleri = "A, B, C, D, E"
        secenek_json = '"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."'
    
    prompt = f'''Sen {format_adi} sınavı formatında uzman bir matematik soru yazarısın.

## 🎯 GÖREV
{sinif}. sınıf **{topic}** konusunda, günlük yaşam becerilerini ölçen bir soru üret.

## ⚠️ EN ÖNEMLİ KURAL - KONU UYUMU
Soru MUTLAKA **{topic}** konusuyla DOĞRUDAN ilgili olmalı!
- Senaryo {topic} konusunun MATEMATİKSEL kavramlarını içermeli
- Çözüm adımları {topic} konusundaki formül/yöntemleri kullanmalı
- Soru {sub_topic if sub_topic else topic} alt konusuna odaklanmalı

❌ YANLIŞ: Konuyla ilgisiz basit işlemler
✅ DOĞRU: Konunun matematiksel kavramlarını gerçek yaşama uygulama

## 📚 KAZANIM BİLGİSİ
• Sınıf: {sinif}. Sınıf
• Sınav Formatı: {format_adi}
• Konu: {topic}
• Alt Konu: {sub_topic if sub_topic else 'Genel'}
• Kazanım Kodu: {learning_outcome if learning_outcome else 'Belirtilmemiş'}
• Anahtar Kavramlar: {', '.join(key_concepts) if key_concepts else topic}
• Gerçek Yaşam Bağlamları: {', '.join(real_life) if real_life else 'Günlük yaşam'}

## 🧠 BLOOM SEVİYESİ (Referans)
Hedef: {bloom_seviye} ({bloom_bilgi['seviye']}/6)
Not: Soru konuya uygunsa Bloom seviyesi ikincil önceliktir.

## 📊 ZORLUK: {zorluk.upper()}
{"• Basit işlemler, tek adım" if zorluk == "kolay" else "• Orta karmaşıklık, 2-3 adım" if zorluk == "orta" else "• Çok adımlı, analiz gerektiren"}

## 🌍 YAŞAM BECERİSİ BAĞLAMI
Kategori: {baglam.get('kategori_ad', 'Günlük Yaşam')}
Tema: {baglam.get('tema', 'genel').replace('_', ' ')}
Açıklama: {baglam.get('aciklama', 'Günlük yaşam problemi')}

## 👤 KARAKTER
Ana Karakter: {isim1}
⚠️ Sadece TEK karakter kullan! İkinci kişi ekleme!

{mufredat_uyumu_prompt(curriculum_row)}

## 📝 SORU FORMAT KURALLARI - {format_adi}

1. **Senaryo**: {min_kelime}-{max_kelime} kelime
2. **Seçenek Sayısı**: {secenek_sayisi} ({secenek_harfleri})
3. **Çözüm Adımı**: {min_adim}-{max_adim} adım
4. **Dil**: Açık, anlaşılır, sınıf seviyesine uygun

## ⚠️ KRİTİK KURALLAR

1. ✅ Soru MUTLAKA "{topic}" konusunun kavramlarını kullanmalı
2. ✅ Çözüm adımları konuya özgü formül/yöntemleri içermeli
3. ❌ ÜST SINIF KAVRAMLARI KULLANMA
4. ✅ Tüm veriler senaryoda açıkça belirtilmeli
5. ✅ Gerçekçi, hesaplanabilir sayılar
6. ✅ Tek karakter üzerinden basit senaryo
7. ✅ {format_adi} gerçek soru formatına uygun

## 📋 JSON ÇIKTI FORMATI

```json
{{
  "senaryo": "[{min_kelime}-{max_kelime} kelime, {isim1} karakteri üzerinden]",
  "soru_metni": "[Net soru kökü]",
  "secenekler": {{
    {secenek_json}
  }},
  "dogru_cevap": "[{secenek_harfleri}'den biri]",
  "cozum_adimlari": [
    "Adım 1: [Açıklama] - [İşlem] = [Sonuç]",
    "Adım 2: ..."
  ],
  "solution_detailed": "[Öğrenci dostu, detaylı açıklama]",
  "celdirici_aciklamalar": {{
    "[Yanlış şık]": "[Kavram yanılgısı açıklaması]"
  }},
  "bloom_seviye": "{bloom_seviye}",
  "zorluk": "{zorluk}",
  "tahmini_sure": "[X dakika]"
}}
```

⚠️ SADECE JSON döndür. Başka metin yazma!'''

    return prompt

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU ÜRET
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret_v3(curriculum_row, params):
    """V3: Tek bir beceri temelli soru üret"""
    try:
        prompt = soru_uretim_prompt_olustur(curriculum_row, params)
        
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.75,
                max_output_tokens=2500,
                response_mime_type="application/json"
            )
        )
        
        soru = json_temizle(response.text.strip())
        
        if not soru:
            return None
        
        # Meta bilgileri ekle
        soru['sinif'] = curriculum_row.get('grade_level', 8)
        soru['curriculum_id'] = curriculum_row.get('id')
        soru['topic_name'] = curriculum_row.get('topic_name', '')
        soru['sub_topic'] = curriculum_row.get('sub_topic', '')
        soru['baglam_kategori'] = params.get('baglam', {}).get('kategori', 'genel')
        
        return soru
        
    except Exception as e:
        print(f"   ⚠️ Soru üretim hatası: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

DEEPSEEK_DOGRULAMA_PROMPT = """
# BECERİ TEMELLİ SORU DOĞRULAMA UZMANI

Sen TYT/AYT/LGS sınavlarında soru kalitesi değerlendiren uzman bir psikometristsin.

## DOĞRULAMA KRİTERLERİ

### 1. MATEMATİKSEL DOĞRULUK (25 puan)
- Çözüm adımları doğru mu?
- Hesaplamalar hatasız mı?
- Cevap doğru mu?

### 2. MÜFREDAT UYUMU (25 puan)
- Sınıf seviyesine uygun mu?
- Üst sınıf kavramları kullanılmış mı?
- Kazanıma uygun mu?

### 3. SENARYO KALİTESİ (25 puan)
- Günlük yaşam bağlamı var mı?
- Veriler tam mı?
- Gerçekçi mi?

### 4. BLOOM UYUMU (25 puan)
- Belirtilen Bloom seviyesine uygun mu?
- Soru kökü uygun eylem içeriyor mu?

## ÇIKTI FORMATI

```json
{
  "gecerli": true/false,
  "puan": 0-100,
  "detay_puanlar": {
    "matematiksel_dogruluk": 0-25,
    "mufredat_uyumu": 0-25,
    "senaryo_kalitesi": 0-25,
    "bloom_uyumu": 0-25
  },
  "sorunlar": ["Sorun 1", "Sorun 2"],
  "aciklama": "Kısa değerlendirme"
}
```

GEÇERSİZ eğer:
- Matematiksel hata varsa
- Müfredat dışı kavram varsa
- Toplam puan 65'in altındaysa

SADECE JSON döndür.
"""

def deepseek_dogrula(soru):
    """DeepSeek ile soru kalitesini doğrula"""
    if not deepseek or not DEEPSEEK_DOGRULAMA:
        return {'gecerli': True, 'puan': 75, 'aciklama': 'DeepSeek devre dışı'}
    
    try:
        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[
                {'role': 'system', 'content': DEEPSEEK_DOGRULAMA_PROMPT},
                {'role': 'user', 'content': f'Bu soruyu değerlendir:\n\n{json.dumps(soru, ensure_ascii=False, indent=2)}'}
            ],
            max_tokens=1000,
            timeout=API_TIMEOUT
        )
        
        result = json_temizle(response.choices[0].message.content)
        
        if result:
            return result
        return {'gecerli': False, 'puan': 0, 'aciklama': 'Parse hatası'}
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek hatası: {str(e)[:50]}")
        return {'gecerli': True, 'puan': 70, 'aciklama': f'DeepSeek hatası'}

# ═══════════════════════════════════════════════════════════════════════════════
# VERİ TAMLIĞI DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def senaryo_veri_tamligini_dogrula(soru):
    """Senaryonun kendi kendine yeterli olup olmadığını kontrol eder"""
    senaryo = soru.get('senaryo', '')
    
    if not senaryo or len(senaryo) < 30:
        return False, "Senaryo çok kısa"
    
    # Tehlikeli ifadeler kontrolü
    tehlikeli = ['tabloya göre', 'yukarıdaki', 'aşağıdaki grafik', 'şekle göre']
    for ifade in tehlikeli:
        if ifade in senaryo.lower() and '|' not in senaryo and '📊' not in senaryo:
            return False, f"'{ifade}' var ama veri yok"
    
    return True, "OK"

# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION_BANK KAYIT
# ═══════════════════════════════════════════════════════════════════════════════

def question_bank_kaydet(soru, curriculum_row, dogrulama_puan=None):
    """Soruyu question_bank tablosuna kaydet"""
    try:
        senaryo = soru.get('senaryo', '')
        soru_metni = soru.get('soru_metni', '')
        tam_metin = f"{senaryo}\n\n{soru_metni}" if senaryo else soru_metni
        
        # Seçenekleri JSON'a çevir
        secenekler = soru.get('secenekler', {})
        if isinstance(secenekler, dict):
            secenekler_str = json.dumps(secenekler, ensure_ascii=False)
        else:
            secenekler_str = str(secenekler)
        
        # Çözüm adımlarını birleştir
        cozum_adimlari = soru.get('cozum_adimlari', [])
        if isinstance(cozum_adimlari, list):
            cozum_str = '\n'.join(cozum_adimlari)
        else:
            cozum_str = str(cozum_adimlari)
        
        # Çeldirici açıklamaları
        celdirici = soru.get('celdirici_aciklamalar', {})
        if isinstance(celdirici, dict) and celdirici:
            celdirici_str = json.dumps(celdirici, ensure_ascii=False)
        else:
            celdirici_str = None
        
        # Difficulty: Bloom seviyesine göre 1-5
        bloom_seviye = soru.get('bloom_seviye', 'uygulama')
        bloom_bilgi = BLOOM_TAKSONOMISI.get(bloom_seviye, BLOOM_TAKSONOMISI['uygulama'])
        difficulty = min(5, max(1, bloom_bilgi['seviye']))
        
        # Sınav formatı
        sinif = curriculum_row.get('grade_level', 8)
        format_adi, _ = sinav_formati_belirle(sinif)
        
        kayit = {
            'original_text': tam_metin,
            'options': secenekler_str,
            'solution_text': cozum_str,
            'difficulty': difficulty,
            'subject': 'Matematik',
            'grade_level': sinif,
            'topic': f"{curriculum_row.get('topic_name', '')} -> {curriculum_row.get('sub_topic', '')}",
            'correct_answer': soru.get('dogru_cevap', ''),
            'kazanim_id': curriculum_row.get('id'),
            'question_type': 'coktan_secmeli',
            'solution_detailed': soru.get('solution_detailed', cozum_str),
            'is_active': True,
            'bloom_level': bloom_seviye,
            'scenario_text': senaryo,
            'distractor_explanations': celdirici_str,
            'topic_group': format_adi,  # LGS, TYT, AYT, ILKOKUL
            'life_skill_category': soru.get('baglam_kategori', 'genel'),
        }
        
        result = supabase.table('question_bank').insert(kayit).execute()
        
        if result.data:
            return result.data[0].get('id')
        return None
        
    except Exception as e:
        print(f"   ❌ Kayıt hatası: {str(e)[:80]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# ANA SORU ÜRETİM FONKSİYONU
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_pipeline(curriculum_row, params):
    """Tek bir soru üret (CoT yöntemiyle), doğrula ve kaydet"""
    for deneme in range(MAX_DENEME):
        try:
            # 1. CoT: Önce çözümü oluştur
            cozum = cot_cozum_olustur(curriculum_row, params)
            
            if not cozum:
                print(f"      ⚠️ CoT çözüm başarısız (Deneme {deneme+1})")
                continue
            
            # 2. Çözümden soru oluştur
            soru = cozumden_soru_olustur(cozum, curriculum_row, params)
            
            if not soru:
                print(f"      ⚠️ Soru oluşturma başarısız (Deneme {deneme+1})")
                continue
            
            # 3. Veri tamlığı kontrolü
            tamlik_ok, tamlik_mesaj = senaryo_veri_tamligini_dogrula(soru)
            if not tamlik_ok:
                print(f"      ⚠️ Veri eksik: {tamlik_mesaj} (Deneme {deneme+1})")
                continue
            
            # 4. Benzersizlik kontrolü
            if not benzersiz_mi(soru):
                print(f"      ⚠️ Tekrar soru (Deneme {deneme+1})")
                continue
            
            # 5. DeepSeek doğrulama
            dogrulama = deepseek_dogrula(soru)
            puan = dogrulama.get('puan', 0)
            
            if not dogrulama.get('gecerli', False) and puan < MIN_DEEPSEEK_PUAN:
                print(f"      ⚠️ Kalite yetersiz: {puan}/100 (Deneme {deneme+1})")
                if dogrulama.get('sorunlar'):
                    for sorun in dogrulama.get('sorunlar', [])[:2]:
                        print(f"         - {sorun[:50]}")
                continue
            
            # 6. Kaydet
            soru_id = question_bank_kaydet(soru, curriculum_row, puan)
            
            if soru_id:
                hash_kaydet(soru)
                return {
                    'success': True,
                    'id': soru_id,
                    'puan': puan
                }
            
        except Exception as e:
            print(f"      ⚠️ Hata: {str(e)[:40]} (Deneme {deneme+1})")
            continue
    
    return {'success': False}

# ═══════════════════════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════════════════════

def toplu_uret():
    """Tüm curriculum kazanımları için dengeli soru üret"""
    
    # Progress tablosu kontrolü
    if not progress_tablosu_kontrol():
        print("❌ Progress tablosu hazır değil!")
        return 0
    
    # Curriculum verilerini çek
    curriculum_data = curriculum_getir()
    
    if not curriculum_data:
        print("❌ Curriculum verisi bulunamadı!")
        return 0
    
    # Eksik kazanımları al (tüm turlardan)
    islenecekler = sonraki_kazanimlari_getir(curriculum_data, 0, MAX_ISLEM_PER_RUN)
    
    if not islenecekler:
        print("✅ Tüm kazanımlarda yeterli soru var!")
        print("   Yeni tur için soru sayısını artırabilirsiniz.")
        return 0
    
    # Sınıf dağılımını göster
    sinif_dagilimi = defaultdict(int)
    for item in islenecekler:
        sinif_dagilimi[item['curriculum'].get('grade_level', 0)] += 1
    
    # Mevcut tur bilgisi için istatistik
    tur_dagilimi = defaultdict(int)
    for item in islenecekler:
        tur_dagilimi[item['tur']] += 1
    
    print(f"\n{'='*70}")
    print(f"🎯 BECERİ TEMELLİ SORU ÜRETİM V3")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Toplam Matematik Kazanımı: {len(curriculum_data)}")
    print(f"   Bu Çalışmada İşlenecek: {len(islenecekler)} kazanım")
    print(f"   Kazanım Başına Soru: {SORU_PER_KAZANIM}")
    print(f"\n   📊 DENGELİ SINIF DAĞILIMI:")
    for sinif in sorted(sinif_dagilimi.keys()):
        format_adi, _ = sinav_formati_belirle(sinif)
        print(f"      {sinif}. Sınıf ({format_adi}): {sinif_dagilimi[sinif]} kazanım")
    print(f"\n   ✅ Özellikler:")
    print(f"      - TYT/AYT/LGS Sınav Formatları")
    print(f"      - Bloom Taksonomisi Entegrasyonu")
    print(f"      - Günlük Yaşam Becerileri")
    print(f"      - Müfredat Uyumu Kontrolü")
    print(f"   DeepSeek: {'✅ AKTİF' if DEEPSEEK_DOGRULAMA else '❌ DEVRE DIŞI'}")
    print(f"{'='*70}\n")
    
    basarili = 0
    dogrulanan = 0
    toplam_puan = 0
    sinif_basari = defaultdict(int)
    baslangic = time.time()
    
    for idx, item in enumerate(islenecekler):
        curriculum_row = item['curriculum']
        tur = item['tur']
        mevcut_soru = item['mevcut_soru']
        
        topic_name = curriculum_row.get('topic_name', 'Bilinmeyen')
        sub_topic = curriculum_row.get('sub_topic', '')
        grade_level = curriculum_row.get('grade_level', 8)
        curriculum_id = curriculum_row.get('id')
        
        format_adi, format_bilgi = sinav_formati_belirle(grade_level)
        
        print(f"\n[{idx+1}/{len(islenecekler)}] Kazanım ID: {curriculum_id}")
        print(f"   📚 {topic_name}" + (f" - {sub_topic}" if sub_topic else ""))
        print(f"   📊 {grade_level}. Sınıf | {format_adi}")
        print(f"   📝 Mevcut: {mevcut_soru}/{SORU_PER_KAZANIM} soru")
        
        # Bu kazanım için eksik soruları üret
        eksik_soru = SORU_PER_KAZANIM - mevcut_soru
        
        for soru_idx in range(eksik_soru):
            # Parametreleri belirle
            bloom_seviye = bloom_seviye_sec(grade_level)
            zorluk = zorluk_sec(format_bilgi)
            baglam = uygun_baglam_sec(grade_level, topic_name)  # Konuya göre bağlam
            
            params = {
                'bloom_seviye': bloom_seviye,
                'zorluk': zorluk,
                'baglam': baglam,
                'format': format_adi
            }
            
            print(f"\n   Soru {mevcut_soru + soru_idx + 1}/{SORU_PER_KAZANIM}:")
            print(f"      Bloom: {bloom_seviye} | Zorluk: {zorluk}")
            print(f"      Bağlam: {baglam['kategori_ad']} > {baglam['tema'].replace('_', ' ')}")
            
            try:
                sonuc = tek_soru_pipeline(curriculum_row, params)
                
                if sonuc['success']:
                    basarili += 1
                    sinif_basari[grade_level] += 1
                    puan = sonuc.get('puan')
                    if puan:
                        dogrulanan += 1
                        toplam_puan += puan
                    
                    # Progress güncelle
                    progress_guncelle(curriculum_id, tur, mevcut_soru + soru_idx + 1)
                    
                    print(f"      ✅ Başarılı! ID: {sonuc['id']}")
                    if puan:
                        print(f"      📊 Kalite: {puan}/100")
                else:
                    print(f"      ❌ Başarısız")
                    
            except Exception as e:
                print(f"      ❌ Hata: {str(e)[:50]}")
            
            time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    ort_puan = toplam_puan / dogrulanan if dogrulanan > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"📊 SONUÇ RAPORU")
    print(f"{'='*70}")
    print(f"   ✅ Toplam üretilen: {basarili} soru")
    print(f"   🔍 Doğrulanan: {dogrulanan}/{basarili}")
    print(f"   📈 Ortalama Kalite: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"\n   📊 SINIF BAZLI BAŞARI:")
    for sinif in sorted(sinif_basari.keys()):
        format_adi, _ = sinav_formati_belirle(sinif)
        print(f"      {sinif}. Sınıf ({format_adi}): {sinif_basari[sinif]} soru")
    print(f"{'='*70}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🎯 BECERİ TEMELLİ SORU ÜRETİCİ BOT V3")
    print("   📚 TYT/AYT/LGS Sınav Formatları")
    print("   📊 3-12. Sınıf Dengeli Dağılım")
    print("   🧠 Bloom Taksonomisi Entegrasyonu")
    print("   🌍 Günlük Yaşam Becerileri")
    print("   ✅ Müfredat Uyumu Kontrolü")
    print("="*70 + "\n")
    
    # Gemini testi
    print("🔍 Gemini API test ediliyor...")
    try:
        test_response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents='2+2=?'
        )
        print(f"✅ Gemini çalışıyor: {test_response.text.strip()}")
    except Exception as e:
        print(f"❌ Gemini HATASI: {e}")
        exit(1)
    
    # DeepSeek testi
    if deepseek:
        print("🔍 DeepSeek API test ediliyor...")
        try:
            test = deepseek.chat.completions.create(
                model='deepseek-chat',
                messages=[{'role': 'user', 'content': '3+5=?'}],
                max_tokens=10
            )
            print(f"✅ DeepSeek çalışıyor: {test.choices[0].message.content.strip()}")
        except Exception as e:
            print(f"⚠️ DeepSeek hatası: {e}")
            global DEEPSEEK_DOGRULAMA
            DEEPSEEK_DOGRULAMA = False
    
    print()
    
    # Soru üret
    basarili = toplu_uret()
    
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} beceri temelli soru question_bank'a kaydedildi.")

if __name__ == "__main__":
    main()
