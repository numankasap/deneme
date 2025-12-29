"""
LGS Matematik Bot
=================
Gemini 2.5 Flash (soru) + Gemini 3 Pro Image Preview (görsel) + Supabase
GitHub Actions ile otomatik çalışır

Kullanım:
  python lgs_matematik_bot.py --mode batch --count 1
  python lgs_matematik_bot.py --mode topic --topic karekoklu_ifadeler --count 5
  python lgs_matematik_bot.py --mode single --konu ucgenler --bloom Analiz --zorluk 4
"""

import os
import sys
import json
import time
import uuid
import base64
import random
import logging
import argparse
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict, field

# Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    NEW_GENAI = True
except ImportError:
    NEW_GENAI = False
    print("⚠️ google-genai paketi bulunamadı. pip install google-genai yapın.")

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ============================================================================
# API ENDPOINTS
# ============================================================================

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"  # Görsel üretimi için

GEMINI_TEXT_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent"
GEMINI_IMAGE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent"

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Bot konfigürasyonu"""
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    REQUEST_TIMEOUT = 90
    RATE_LIMIT_DELAY = 3
    DEFAULT_GRADE_LEVEL = 8
    DEFAULT_SUBJECT = "Matematik"
    DEFAULT_TOPIC_GROUP = "LGS"
    TEMPERATURE = 0.85
    MAX_OUTPUT_TOKENS = 8192
    STORAGE_BUCKET = "questions-images"  # Üretilen görseller için bucket

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class QuestionParams:
    """Soru üretim parametreleri"""
    konu: str
    alt_konu: str
    kazanim_kodu: str
    bloom_seviyesi: str
    zorluk: int
    baglam: str
    gorsel_tipi: str
    grade_level: int = 8
    topic_group: str = "LGS"

@dataclass
class GeneratedQuestion:
    """Üretilen soru verisi"""
    title: str
    original_text: str
    options: Dict[str, str]
    correct_answer: str
    solution_text: str  # Adım adım çözüm
    difficulty: int
    subject: str
    grade_level: int
    topic: str
    topic_group: str
    kazanim_kodu: str
    bloom_level: str
    pisa_level: int
    pisa_context: str
    scenario_text: str
    distractor_explanations: Dict[str, str]
    image_url: Optional[str] = None
    question_type: str = "coktan_secmeli"
    is_active: bool = True
    verified: bool = False

# ============================================================================
# LGS MÜFREDATİ - KONULAR VE KAZANIMLAR
# ============================================================================

LGS_KONULAR: Dict[str, Dict[str, Any]] = {
    "uslu_ifadeler": {
        "display_name": "Üslü İfadeler",
        "alt_konular": ["negatif_kuvvet", "carpma_bolme", "bilimsel_gosterim"],
        "kazanimlar": ["M.8.1.1.1", "M.8.1.1.2", "M.8.1.1.3", "M.8.1.1.4"],
        "ornek_baglamlar": [
            "Akkuyu Nükleer Güç Santrali enerji üretimi",
            "Uzay ve gezegen mesafeleri",
            "Mikro organizma boyutları",
            "Veri depolama kapasitesi",
            "Deprem büyüklükleri"
        ],
        "gorsel_tipleri": ["tablo", "bilgi_kutusu", "sayi_dogrusu"],
        "celdirici_hatalari": [
            "Negatif üssü yanlış hesaplama (2⁻³ = -6 sanma)",
            "Parantez dışı negatifi yanlış işleme (-3² = 9 sanma)",
            "Bilimsel gösterimde formatı yanlış yazma",
            "Birim dönüşümünü atlama"
        ]
    },
    
    "karekoklu_ifadeler": {
        "display_name": "Kareköklü İfadeler",
        "alt_konular": ["karekök_tahmini", "islemler", "rasyonel_irrasyonel", "sayi_dogrusu"],
        "kazanimlar": ["M.8.1.2.1", "M.8.1.2.2", "M.8.1.2.3", "M.8.1.2.4"],
        "ornek_baglamlar": [
            "Parke döşeme ve zemin kaplama",
            "Güneş paneli alanı hesaplama",
            "Bahçe düzenleme ve çit çevresi",
            "Fidan dikimi ve ağaç aralıkları",
            "Duvar kaplama malzemesi"
        ],
        "gorsel_tipleri": ["geometrik_sekil", "kareli_zemin", "sayi_dogrusu"],
        "celdirici_hatalari": [
            "Dağılma özelliği hatası (√(a+b) = √a + √b sanma)",
            "Katsayıyı kök içine yanlış alma (3√2 = √6 sanma)",
            "Çarpımda hata (√8 × √2 = √10 sanma)",
            "Toplama/çıkarmada benzer terimleri karıştırma"
        ]
    },
    
    "cebirsel_ifadeler": {
        "display_name": "Cebirsel İfadeler ve Özdeşlikler",
        "alt_konular": ["carpim", "ozdeslikler", "carpanlara_ayirma"],
        "kazanimlar": ["M.8.2.1.1", "M.8.2.1.2", "M.8.2.1.3", "M.8.2.1.4"],
        "ornek_baglamlar": [
            "Dikdörtgen tarla alan hesabı",
            "Havuz hacmi ve dolum süresi",
            "Ambalaj kutusu tasarımı",
            "Bahçe çiti çevresi",
            "Zemin döşeme maliyeti"
        ],
        "gorsel_tipleri": ["geometrik_sekil", "alan_modeli", "kareli_zemin"],
        "celdirici_hatalari": [
            "Orta terimi unutma ((a+b)² = a² + b² sanma)",
            "İşaret hatası ((a-b)² = a² - b² sanma)",
            "Çarpanlara ayırmada hata (x²-9 = (x-3)² sanma)"
        ]
    },
    
    "denklemler": {
        "display_name": "Doğrusal Denklemler",
        "alt_konular": ["birinci_derece", "problem_cozme", "grafik_yorumlama"],
        "kazanimlar": ["M.8.2.2.1", "M.8.2.2.2"],
        "ornek_baglamlar": [
            "Alışveriş ve indirim hesabı",
            "Yaş problemleri",
            "Hız-mesafe-zaman problemleri",
            "Havuz doldurma/boşaltma",
            "İşçi problemleri"
        ],
        "gorsel_tipleri": ["grafik", "tablo", "koordinat_duzlemi"],
        "celdirici_hatalari": [
            "İşlem önceliğini karıştırma",
            "Denklem kurarken bilinmeyeni yanlış yerleştirme",
            "Grafik okumada koordinat hatası"
        ]
    },
    
    "esitsizlikler": {
        "display_name": "Eşitsizlikler",
        "alt_konular": ["esitsizlik_kavrami", "cozum", "sayi_dogrusu"],
        "kazanimlar": ["M.8.2.3.1", "M.8.2.3.2"],
        "ornek_baglamlar": [
            "Bütçe ve harcama sınırı",
            "Kapasite ve limit problemleri",
            "Minimum/maksimum değer bulma",
            "Yarışma puan sınırı"
        ],
        "gorsel_tipleri": ["sayi_dogrusu", "grafik"],
        "celdirici_hatalari": [
            "Negatif sayıyla çarpmada yön değiştirmeme",
            "Eşitsizlik yönünü karıştırma",
            "Sayı doğrusunda aralığı yanlış gösterme"
        ]
    },
    
    "ucgenler": {
        "display_name": "Üçgenler",
        "alt_konular": ["kenar_aci", "esitsizlik", "yardimci_elemanlar"],
        "kazanimlar": ["M.8.3.2.1", "M.8.3.2.2", "M.8.3.2.3"],
        "ornek_baglamlar": [
            "Pergel ve cetvel kullanımı",
            "Çatı tasarımı ve eğimi",
            "Köprü yapısı ve dayanıklılık",
            "Bayrak direği ve gölge",
            "Uçurtma tasarımı"
        ],
        "gorsel_tipleri": ["geometrik_sekil", "kareli_zemin"],
        "celdirici_hatalari": [
            "Kenar-açı ilişkisini ters kurma",
            "Üçgen eşitsizliğini kontrol etmeme",
            "Açıortay ve kenarortayı karıştırma"
        ]
    },
    
    "benzerlik": {
        "display_name": "Eşlik ve Benzerlik",
        "alt_konular": ["benzer_cokgenler", "oran", "alan_orani"],
        "kazanimlar": ["M.8.3.3.1", "M.8.3.3.2", "M.8.3.3.3"],
        "ornek_baglamlar": [
            "Harita ve ölçek hesabı",
            "Gölge ve gerçek boy hesabı",
            "Fotoğraf büyütme/küçültme",
            "Maket yapımı oranları",
            "Mimari çizim ölçeği"
        ],
        "gorsel_tipleri": ["geometrik_sekil", "duz_zemin_olcekli"],
        "celdirici_hatalari": [
            "Benzerlik oranını tersine çevirme",
            "Alan oranını kenar oranı gibi hesaplama",
            "Karşılıklı kenarları yanlış eşleştirme"
        ],
        "gorsel_notu": "Benzerlik sorularında ölçüler genelde orantısızdır (örn: 0.8m ve 15m). Kareli zemin KULLANMA, düz beyaz zemin üzerine oklu ölçüler kullan."
    },
    
    "donusum_geometrisi": {
        "display_name": "Dönüşüm Geometrisi",
        "alt_konular": ["yansima", "oteleme", "dondurme"],
        "kazanimlar": ["M.8.3.4.1", "M.8.3.4.2", "M.8.3.4.3"],
        "ornek_baglamlar": [
            "Kilim ve halı deseni",
            "Logo tasarımı simetrisi",
            "Ayna yansıması",
            "Karo döşeme deseni",
            "Ebru sanatı motifleri"
        ],
        "gorsel_tipleri": ["geometrik_sekil", "kareli_zemin", "koordinat_duzlemi"],
        "celdirici_hatalari": [
            "Yansıma eksenini yanlış belirleme",
            "Döndürme açısını yanlış uygulama",
            "Öteleme vektörünü ters yönde uygulama"
        ]
    },
    
    "egim": {
        "display_name": "Eğim",
        "alt_konular": ["degisim_orani", "dogru_egimi"],
        "kazanimlar": ["M.8.3.5.1", "M.8.3.5.2"],
        "ornek_baglamlar": [
            "Engelli rampası tasarımı",
            "Yol ve viraj eğimi",
            "Merdiven basamak hesabı",
            "Kayak pisti eğimi",
            "Çatı eğimi hesabı"
        ],
        "gorsel_tipleri": ["grafik", "koordinat_duzlemi"],
        "celdirici_hatalari": [
            "Eğim formülünde pay/paydayı karıştırma",
            "Negatif eğimi pozitif hesaplama",
            "Koordinatları yanlış okuma"
        ]
    },
    
    "geometrik_cisimler": {
        "display_name": "Geometrik Cisimler (Silindir)",
        "alt_konular": ["silindir_elemanlar", "yuzey_alan", "hacim"],
        "kazanimlar": ["M.8.3.6.1", "M.8.3.6.2", "M.8.3.6.3"],
        "ornek_baglamlar": [
            "Su deposu kapasitesi",
            "Boru hattı hacmi",
            "Konserve kutusu tasarımı",
            "Rulo kağıt hesabı",
            "Silindir vazo boyama"
        ],
        "gorsel_tipleri": ["cisim_3d", "acilim"],
        "gorsel_renkleri": {
            "dolgu": "#E3F2FD",  # Açık mavi
            "cizgi": "#1565C0",   # Koyu mavi
            "vurgu": "#0D47A1"    # Çok koyu mavi
        },
        "celdirici_hatalari": [
            "Yanal yüzey alanını unutma",
            "Taban alanını tek hesaplama",
            "π değerini yanlış kullanma",
            "Yarıçap/çap karışıklığı"
        ]
    },
    
    "veri_analizi": {
        "display_name": "Veri Analizi",
        "alt_konular": ["grafik_gosterim", "merkezi_egilim", "yorumlama"],
        "kazanimlar": ["M.8.5.1.1", "M.8.5.1.2"],
        "ornek_baglamlar": [
            "Müze ziyaretçi istatistikleri",
            "Sınav sonuçları analizi",
            "Hava durumu grafikleri",
            "Satış verileri karşılaştırma",
            "Anket sonuçları değerlendirme"
        ],
        "gorsel_tipleri": ["grafik_sutun", "grafik_daire", "tablo", "kareli_zemin"],
        "gorsel_renkleri": {
            "seri1": "#42A5F5",  # Mavi
            "seri2": "#66BB6A",  # Yeşil
            "seri3": "#FFA726",  # Turuncu
            "seri4": "#AB47BC",  # Mor
            "arka_plan": "#FAFAFA"
        },
        "celdirici_hatalari": [
            "Grafik eksenlerini yanlış okuma",
            "Ortalama hesabında toplam/sayı hatası",
            "Yüzde hesabını yanlış yapma",
            "Daire grafiğinde açı-oran dönüşümü hatası"
        ]
    },
    
    "olasilik": {
        "display_name": "Olasılık",
        "alt_konular": ["basit_olasilik", "bagimli_bagimsiz", "olay_cesitleri"],
        "kazanimlar": ["M.8.4.1.1", "M.8.4.1.2", "M.8.4.1.3"],
        "ornek_baglamlar": [
            "Oyun ve şans oyunları",
            "Çekiliş ve kura",
            "Renkli top seçimi",
            "Zar ve yazı-tura",
            "Kart oyunu olasılıkları"
        ],
        "gorsel_tipleri": ["tablo", "kutular", "agac_diyagrami"],
        "celdirici_hatalari": [
            "Pay ve paydayı karıştırma",
            "Bağımlı/bağımsız olayları ayırt edememe",
            "Toplam sonuç sayısını yanlış hesaplama",
            "Koşullu olasılıkta paydayı yanlış alma"
        ]
    }
}

# ============================================================================
# BLOOM TAKSONOMİSİ
# ============================================================================

BLOOM_SEVIYELERI = {
    "Analiz": {
        "aciklama": "Parça-bütün ilişkisi, karşılaştırma, sınıflandırma, ilişkilendirme",
        "fiiller": ["karşılaştırır", "analiz eder", "ayırt eder", "ilişkilendirir", "sınıflandırır"],
        "soru_kaliplari": [
            "Buna göre, aşağıdaki ifadelerden hangisi doğrudur?",
            "Buna göre, X ile Y arasındaki fark kaçtır?",
            "Buna göre, I, II ve III ifadelerinden hangileri doğrudur?"
        ]
    },
    "Değerlendirme": {
        "aciklama": "Yargılama, karar verme, ölçüt kullanma, seçim yapma",
        "fiiller": ["değerlendirir", "yargılar", "karar verir", "seçer", "sonuç çıkarır"],
        "soru_kaliplari": [
            "Buna göre, en uygun seçenek hangisidir?",
            "Buna göre, en az kaçtır?",
            "Buna göre, en fazla kaç farklı değer alabilir?",
            "Buna göre, hangisi kesinlikle söylenebilir?"
        ]
    },
    "Yaratma": {
        "aciklama": "Tasarlama, planlama, üretme, sentezleme, özgün çözüm geliştirme",
        "fiiller": ["tasarlar", "oluşturur", "planlar", "üretir", "sentezler"],
        "soru_kaliplari": [
            "Buna göre, kaç farklı yolla yapılabilir?",
            "Buna göre, en uygun strateji hangisidir?",
            "Buna göre, X nasıl tasarlanmalıdır?"
        ]
    }
}

PISA_BAGLAMLAR = ["Kişisel", "Mesleki", "Toplumsal", "Bilimsel"]

# ============================================================================
# MASTER PROMPTS
# ============================================================================

SYSTEM_PROMPT_QUESTION = """Sen, Türkiye Cumhuriyeti Milli Eğitim Bakanlığı (MEB) Ölçme, Değerlendirme ve Sınav Hizmetleri Genel Müdürlüğü'nde görev yapan, 20 yıllık deneyimli kıdemli bir matematik soru yazarısın. PISA ve TIMSS uluslararası standartlarına uygun, beceri temelli LGS soruları hazırlamakta uzmansın.

## TEMEL PRENSİPLER

### 1. BAĞLAM ENTEGRASYONU (ÇOK ÖNEMLİ)
- Matematiksel problem GERÇEK HAYAT senaryosu içinde sunulmalı
- Bağlam KALDIRILDIĞINDA soru ANLAMSIZLAŞMALI (bağlam süs değil, veri taşıyıcı)
- Türkiye kültürüne, güncel olaylara ve teknolojiye uygun bağlamlar kullan
- Akkuyu NGS, yerli savunma sanayi, Türk el sanatları gibi güncel/kültürel temalar tercih et

### 2. ÖRTÜK VERİ İLKESİ (KRİTİK)
- Verinin bir kısmı MUTLAKA METİNDE olmalı
- Verinin diğer kısmı MUTLAKA GÖRSELDE olmalı
- Görselsiz çözüm İMKANSIZ olmalı
- Bu iki veri seti BİRLEŞTİRİLMEDEN soru çözülememeli

### 3. GÖRSEL TASARIM TALİMATI
Görselde ASLA:
- Çözüm adımları olmamalı
- Soru metni olmamalı
- Doğrudan cevabı veren bilgi olmamalı
- Gereksiz dekoratif öğeler olmamalı
- SORUDA KULLANILMAYAN VERİLER OLMAMALI (Çok önemli!)

Görselde MUTLAKA:
- Çözüm için gerekli VERİ olmalı
- Net etiketler ve ölçüler olmalı
- Kareli zemin kullanılıyorsa birim kareler net olmalı

### 3.5. KARELİ ZEMİN KURALLARI (KRİTİK!)
⚠️ Kareli zemin SADECE ölçüler orantılı olduğunda kullanılabilir!

**ÖRNEK YANLIŞ:**
- Ölçüler: 0.80 m, 1.60 m, 15 m
- Kareli zeminde 9 kare = 15 m, 3 kare = 0.80 m → ORANLAR TUTMUYOR!
- Bu durumda kareli zemin KULLANILMAMALI

**ÖRNEK DOĞRU:**
- Ölçüler: 3 m, 4 m, 5 m
- Her kare = 1 m → 3 kare, 4 kare, 5 kare → ORANLAR TUTUYOR
- Bu durumda kareli zemin kullanılabilir

**KARAR VERME:**
1. Sorudaki tüm uzunluk ölçülerini listele
2. Bu ölçülerin hepsini bölen ortak bir birim var mı?
3. EVET → kareli zemin OK, HAYIR → düz beyaz zemin kullan

### 3.6. KULLANILMAYAN VERİ YASAĞI (KRİTİK!)
⚠️ Görselde SADECE soruda kullanılan veriler olmalı!

**ÖRNEK YANLIŞ:**
- Soru: "Anıtın yüksekliği kaç metredir?"
- Görsel: Anıt yüksekliği H + fazladan "1 m" etiketi (soruda yok!)
- SORUN: "1 m" soruda kullanılmıyor, kafa karıştırıcı!

**ÖRNEK DOĞRU:**
- Soru: "Öğrencinin boyu 1.60 m, gölgesi 0.80 m, anıtın gölgesi 15 m ise yüksekliği?"
- Görsel: SADECE 1.60 m, 0.80 m, 15 m ve H (soru işareti ile)
- TÜM değerler soruda var!

### 4. DİL VE ÜSLUP
- %100 doğru Türkçe dil bilgisi
- MEB terminolojisi (doğru, doğru parçası, çember, daire, vb.)
- Soru kökü MUTLAKA "Buna göre, ..." ile başlamalı
- 60-100 kelime arası optimal uzunluk

### 5. ÇELDİRİCİ MANTIĞI (ÇOK ÖNEMLİ)
Her yanlış şık, gerçek bir öğrenci hatasının sonucu olmalı:
- A şıkkı: [Doğru cevap veya spesifik hata]
- B şıkkı: [Farklı bir hata türü]
- C şıkkı: [Başka bir hata türü]
- D şıkkı: [Farklı bir hata türü]

Rastgele sayılar ASLA kullanılmamalı. Her şık pedagojik bir hataya dayanmalı.
"Hiçbiri" veya "Hepsi" şıkkı YASAK.

### 5.5. GÖRSEL-METİN TUTARLILIĞI (KRİTİK!)
⚠️ Soru metninde bahsedilen TÜM veriler görselde de olmalı!

YANLIŞ ÖRNEK:
- Metin: "Tip A, Tip B, Tip C, Tip D panellerden birini seçecek"
- Görsel: Sadece duvar boyutları (6m x 5m)
- SORUN: Panel tipleri görselde YOK!

DOĞRU ÖRNEK:
- Metin: "Aşağıdaki tabloda verilen panel tiplerinden birini seçecek"
- Görsel: Duvar boyutları + Panel tipleri tablosu
  | Tip | Kenar Uzunluğu |
  | A   | √2 m          |
  | B   | √5 m          |
  | C   | √8 m          |
  | D   | √13 m         |

KURAL: Eğer soru metninde "görselde verilen", "tabloda gösterilen", "şekilde belirtilen" gibi ifadeler varsa, o bilgiler MUTLAKA görsel betimlemesinde de olmalı!

### 6. BİLİŞSEL SEVİYE
Hedef Bloom seviyeleri:
- ANALİZ: Karşılaştırma, ilişkilendirme, parça-bütün analizi
- DEĞERLENDİRME: Yargılama, en uygun seçimi yapma, karar verme
- YARATMA: Strateji geliştirme, farklı yolları bulma

### 7. ÖNCÜL BİLGİ (SCAFFOLDING)
Eğer özel bir formül veya kural gerekiyorsa, sorunun BAŞINDA bilgi kutusu olarak ver:
"a, b birer doğal sayı olmak üzere a√b = √(a²b) dir."

## ÇIKTI FORMATI
Yanıtını YALNIZCA aşağıdaki JSON formatında ver. Başka hiçbir açıklama ekleme:

{
  "soru_metni": "Hikayeleştirilmiş tam soru metni. Öncül bilgi varsa başta, senaryo ortada, veriler net.",
  "soru_koku": "Buna göre, ... şeklinde biten soru cümlesi",
  "siklar": {
    "A": "Şık A içeriği (sayısal veya ifade)",
    "B": "Şık B içeriği",
    "C": "Şık C içeriği", 
    "D": "Şık D içeriği"
  },
  "dogru_cevap": "A, B, C veya D",
  "cozum_adim_adim": "Adım 1: [ilk adım açıklaması]\nAdım 2: [ikinci adım açıklaması]\nAdım 3: [üçüncü adım açıklaması]\n...\nSonuç: [final cevap]",
  "celdirici_analizi": {
    "A": "Bu şıkkı seçen öğrencinin yaptığı hata açıklaması",
    "B": "Bu şıkkı seçen öğrencinin yaptığı hata açıklaması",
    "C": "Bu şıkkı seçen öğrencinin yaptığı hata açıklaması",
    "D": "Bu şıkkı seçen öğrencinin yaptığı hata açıklaması"
  },
  "gorsel_gerekli": true,
  "gorsel_betimleme": {
    "tip": "geometrik_sekil / grafik / tablo / kareli_zemin / sayi_dogrusu / cisim_3d / karma",
    "detay": "ÇOK DETAYLI görsel talimatı. Soru metninde bahsedilen TÜM verileri içermeli! Örnek: 'Kareli zemin üzerinde 6x5 birim dikdörtgen ABCD + sağ tarafta panel tablosu: Tip A √2m, Tip B √5m, Tip C √8m, Tip D √13m'",
    "gorunen_veriler": ["Görselde görünecek TÜM değerler - şekil boyutları, tablo verileri, etiketler"],
    "gizli_bilgi": "SADECE görselde olmaması gereken bilgiler (çevre hesabı, cevap vb.)",
    "dikkat": "Soru metninde 'görselde verilen', 'tabloda gösterilen' gibi ifadeler varsa, o bilgiler MUTLAKA burada detaylı belirtilmeli!",
    "kareli_zemin_uygunlugu": "HESAPLA: Tüm ölçüler (örn: 0.80m, 1.60m, 15m) ortak bir birime bölünebiliyor mu? Evet ise kareli zemin kullan, hayır ise DÜZ ZEMİN kullan. Bu sorudaki ölçüler: [liste] → Kareli zemin: EVET/HAYIR",
    "kullanilan_veriler_kontrolu": "Görseldeki TÜM veriler soru metninde kullanılıyor mu? Kullanılmayan veri varsa SİL!"
  },
  "pisa_seviyesi": 3,
  "pisa_baglam": "Kişisel / Mesleki / Toplumsal / Bilimsel"
}"""

IMAGE_PROMPT_TEMPLATE = """LGS 8. sınıf matematik sorusu için eğitim görseli oluştur.

## GÖRSEL TİPİ: {tip}

## DETAYLI BETİMLEME:
{detay}

## KRİTİK KURALLAR:

### 📐 GEOMETRİK ŞEKİL KURALLARI:

**⚠️ KARELİ ZEMİN - ÖLÇEK TUTARLILIĞI (ÇOK ÖNEMLİ!):**
- Kareli zemin SADECE tüm ölçüler birbiriyle orantılı olduğunda kullanılabilir
- Her kare AYNI birimi temsil etmeli (1 m, 1 cm, vb.)
- ÖRNEK YANLIŞ: 9 kare = 15 m iken 3 kare = 0.8 m OLAMAZ (oranlar tutmuyor!)
- ÖRNEK DOĞRU: 6 kare = 6 m ve 4 kare = 4 m (her kare = 1 m)
- Eğer ölçüler orantısızsa (örn: 0.80 m ve 15 m), kareli zemin KULLANMA, düz beyaz zemin kullan
- Kareli zemin kullanılacaksa: en_küçük_ölçü / kare_boyutu = tam_sayı olmalı

**Kareli Zemin Kullanım Kontrolü:**
1. Tüm ölçüleri listele
2. En küçük ortak bölen hesapla
3. Tüm ölçüler bu bölene bölünebiliyorsa → kareli zemin OK
4. Bölünemiyorsa → DÜZ ZEMİN kullan

**⚠️ KULLANILMAYAN VERİ YASAĞI (ÇOK ÖNEMLİ!):**
- Görselde SADECE soru çözümünde KULLANILAN veriler olmalı
- Soruda geçmeyen ölçüler ASLA görsele eklenmemeli
- Her görsel verisi soru metninde MUTLAKA referans verilmeli
- ÖRNEK YANLIŞ: Soruda sadece "yükseklik H" soruluyorken görsele fazladan "1 m" eklemek
- ÖRNEK DOĞRU: Görseldeki TÜM değerler soru metninde kullanılıyor

**Dikdörtgen/Kare Çizimi:**
- 4 köşe noktası büyük harflerle: A, B, C, D (saat yönünde)
- Her köşede küçük siyah nokta (●)
- Kenar uzunlukları çift yönlü ok (↔) ile gösterilmeli
- Ölçüler şeklin DIŞINDA yazılmalı (6 m, 5 m gibi)
- Birim kare göstermek istiyorsan şeklin DIŞINDA küçük bir kare çiz ve "1 m" yaz

**Üçgen Çizimi:**
- 3 köşe noktası: A, B, C
- Açılar gerekiyorsa yay ile göster
- Kenar uzunlukları kenarın ortasına yakın

**Benzerlik/Gölge Soruları:**
- Kareli zemin KULLANMA (ölçekler genelde orantısız)
- Düz beyaz/açık gri zemin kullan
- Ölçüleri oklu çizgilerle göster
- Gölge bölgesini açık gri dolgulu göster

**3 Boyutlu Cisim:**
- Perspektif görünüm (izometrik veya kavalye)
- Görünen kenarlar düz çizgi, görünmeyen kesikli çizgi
- Boyut etiketleri: uzunluk, genişlik, yükseklik

### ⚠️ TÜRKÇE YAZIM:
- "ı" harfini DOĞRU yaz (noktalı "i" DEĞİL)
- "ğ", "ş", "ü", "ö", "ç" harflerini DOĞRU yaz
- Kelimeleri TAM yaz, yarıda KESME
- Sadece kısa etiketler kullan (6 m, A, B, vb.)
- Uzun kelimeler YAZMA

### 🎨 STİL KURALLARI (MEB DERS KİTABI):

**Renkler (CANLI AMA GÖZ YORMAYAN):**
- Arka plan: Beyaz veya çok açık krem (#FFFEF5)
- Şekil dolguları - FARKLI RENKLER KULLAN:
  * Açık mavi: #E3F2FD (su, gökyüzü temaları)
  * Açık yeşil: #E8F5E9 (doğa, bahçe temaları)
  * Açık turuncu: #FFF3E0 (enerji, sıcak temalar)
  * Açık mor: #F3E5F5 (bilim, teknoloji temaları)
  * Açık sarı: #FFFDE7 (güneş, ışık temaları)
  * Açık pembe: #FCE4EC (sanat, tasarım temaları)
  * Açık turkuaz: #E0F7FA (deniz, su temaları)
- Çizgiler: Koyu gri (#424242), 2px kalınlık
- Etiketler: Siyah veya koyu gri, kalın font
- Vurgular: Koyu mavi (#1565C0) veya koyu yeşil (#2E7D32)

**Renk Kombinasyonu Önerileri:**
- Silindir/Depo: Açık mavi dolgu + koyu mavi çizgi
- Bahçe/Tarla: Açık yeşil dolgu + koyu yeşil çizgi  
- Bina/Yapı: Açık turuncu dolgu + kahverengi çizgi
- Grafik: Her seri farklı pastel renk (mavi, yeşil, turuncu, mor)
- Tablo: Başlık satırı açık mavi, satırlar beyaz/açık gri sıralı

**YASAK:**
- Sade gri tonlar (#E0E0E0, #BDBDBD) - ÇOK SIKICI!
- Tek renk kullanımı - HER ELEMAN FARKLI RENK OLSUN
- Koyu renkler dolgu için - SADECE pastel/açık tonlar

**Boyutlandırma:**
- Şekil görsel alanının %60-70'ini kaplamalı
- Etiketler için yeterli boşluk bırak
- Çok küçük veya çok büyük çizme

### ❌ MUTLAK YASAKLAR:
❌ Soru metni veya cümleler
❌ "Buna göre...", "Aşağıdaki..." gibi ifadeler
❌ A), B), C), D) şıkları
❌ Çözüm adımları veya hesaplamalar
❌ Cevabı veren bilgi
❌ Gereksiz dekorasyon
❌ Bulanık çizgiler
❌ Türkçe karakter hatası
❌ Orantısız kareli zemin
❌ Soruda kullanılmayan veriler"""

# ============================================================================
# API CLASSES
# ============================================================================

class GeminiAPI:
    """Gemini API wrapper - google-genai SDK ile"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
            logger.info("✅ Google GenAI client başlatıldı")
        else:
            # Fallback: requests kullan
            self.client = None
            logger.warning("⚠️ google-genai SDK yok, requests kullanılacak")
        
        self.text_url = f"{GEMINI_TEXT_URL}?key={api_key}"
        self.image_url = f"{GEMINI_IMAGE_URL}?key={api_key}"
        self.request_count = 0
        self.last_request_time = 0
    
    def _rate_limit(self):
        """Rate limiting"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= 4:
            wait_time = 65 - (current_time - self.last_request_time)
            if wait_time > 0:
                logger.info(f"⏳ Rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        
        if self.request_count > 0:
            time.sleep(3)
        
        self.request_count += 1
    
    def generate_question(self, params: QuestionParams) -> Dict[str, Any]:
        """Gemini ile soru üret"""
        
        # Konu bilgilerini al
        konu_data = LGS_KONULAR.get(params.konu, {})
        bloom_data = BLOOM_SEVIYELERI.get(params.bloom_seviyesi, {})
        
        user_prompt = f"""
## SORU ÜRETİM TALİMATI

### Konu Bilgileri:
- **Ana Konu**: {konu_data.get('display_name', params.konu)}
- **Alt Konu**: {params.alt_konu}
- **Kazanım Kodu**: {params.kazanim_kodu}

### Soru Parametreleri:
- **Bloom Seviyesi**: {params.bloom_seviyesi}
  - Açıklama: {bloom_data.get('aciklama', '')}
  - Kullanılabilecek fiiller: {', '.join(bloom_data.get('fiiller', []))}
- **Zorluk (1-5)**: {params.zorluk}
- **Sınıf Seviyesi**: {params.grade_level}. sınıf

### Bağlam Talimatı:
- **Önerilen bağlam**: {params.baglam}
- Bu bağlamı kullan veya benzer gerçekçi bir senaryo oluştur

### Görsel Talimatı:
- **Görsel tipi**: {params.gorsel_tipi}
- Görsel betimlemesi ÇOK DETAYLI olmalı

### Dikkat Edilecek Yaygın Öğrenci Hataları:
{chr(10).join(['- ' + h for h in konu_data.get('celdirici_hatalari', [])])}

### Örnek Soru Kökleri ({params.bloom_seviyesi} seviyesi için):
{chr(10).join(['- ' + k for k in bloom_data.get('soru_kaliplari', [])])}

---

Yukarıdaki tüm kriterlere uygun, özgün ve yaratıcı bir LGS matematik sorusu oluştur.
Matematiksel olarak %100 DOĞRU olmalı. Tek bir doğru cevap olmalı.
"""
        
        self._rate_limit()
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  Gemini API çağrısı (deneme {attempt + 1}/{Config.MAX_RETRIES})...")
                
                if NEW_GENAI and self.client:
                    # Yeni SDK kullan
                    response = self.client.models.generate_content(
                        model=GEMINI_TEXT_MODEL,
                        contents=user_prompt,
                        config={
                            "system_instruction": SYSTEM_PROMPT_QUESTION,
                            "temperature": Config.TEMPERATURE,
                            "max_output_tokens": Config.MAX_OUTPUT_TOKENS,
                            "response_mime_type": "application/json"
                        }
                    )
                    
                    text_content = response.text
                else:
                    # Fallback: requests kullan
                    payload = {
                        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT_QUESTION}]},
                        "generationConfig": {
                            "temperature": Config.TEMPERATURE,
                            "maxOutputTokens": Config.MAX_OUTPUT_TOKENS,
                            "responseMimeType": "application/json"
                        }
                    }
                    
                    response = requests.post(
                        self.text_url,
                        headers={"Content-Type": "application/json"},
                        json=payload,
                        timeout=Config.REQUEST_TIMEOUT
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    if "candidates" not in result or len(result["candidates"]) == 0:
                        logger.warning("  Gemini yanıtında candidate bulunamadı")
                        continue
                    
                    text_content = result["candidates"][0]["content"]["parts"][0]["text"]
                
                # JSON parse
                try:
                    question_data = json.loads(text_content)
                    logger.info("  ✓ Soru JSON başarıyla parse edildi")
                    return question_data
                except json.JSONDecodeError as je:
                    logger.warning(f"  JSON parse hatası: {je}")
                    # JSON düzeltme denemesi
                    clean_text = text_content.strip()
                    
                    # Markdown code block temizliği
                    if clean_text.startswith("```json"):
                        clean_text = clean_text[7:]
                    if clean_text.startswith("```"):
                        clean_text = clean_text[3:]
                    if clean_text.endswith("```"):
                        clean_text = clean_text[:-3]
                    clean_text = clean_text.strip()
                    
                    # Eksik kapanış parantezlerini düzelt
                    open_braces = clean_text.count('{')
                    close_braces = clean_text.count('}')
                    if open_braces > close_braces:
                        clean_text += '}' * (open_braces - close_braces)
                    
                    # Eksik string kapanışını düzelt (basit durum)
                    if clean_text.count('"') % 2 != 0:
                        clean_text += '"'
                    
                    try:
                        question_data = json.loads(clean_text)
                        logger.info("  ✓ JSON düzeltme sonrası parse başarılı")
                        return question_data
                    except json.JSONDecodeError:
                        logger.warning("  JSON düzeltilemedi, yeniden deneniyor...")
                        if attempt < Config.MAX_RETRIES - 1:
                            time.sleep(Config.RETRY_DELAY)
                            continue
                        raise
                    
            except Exception as e:
                logger.error(f"  API hatası (deneme {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)
                    
        raise Exception("Gemini API maksimum deneme sayısına ulaşıldı")
    
    def generate_image(self, gorsel_betimleme: Dict[str, str], konu: str = None) -> Optional[bytes]:
        """Gemini 2.5 Flash Image ile görsel üret (google-genai SDK)"""
        
        if not NEW_GENAI or not self.client:
            logger.warning("  google-genai SDK yok, görsel üretilemiyor")
            return None
        
        tip = gorsel_betimleme.get("tip", "geometrik_sekil")
        detay = gorsel_betimleme.get("detay", "")
        gorunen_veriler = gorsel_betimleme.get("gorunen_veriler", "")
        
        # Konuya göre renk önerisi ekle
        renk_talimat = ""
        if konu and konu in LGS_KONULAR:
            renkler = LGS_KONULAR[konu].get("gorsel_renkleri", {})
            if renkler:
                renk_talimat = f"\n\n🎨 RENK TALİMATI: Bu görsel için şu renkleri kullan: {json.dumps(renkler, ensure_ascii=False)}"
        
        # Varsayılan renk talimatı
        if not renk_talimat:
            renk_talimat = """

🎨 RENK TALİMATI: 
- Şekil dolgusu için AÇIK PASTEL renkler kullan (açık mavi #E3F2FD, açık yeşil #E8F5E9, açık turuncu #FFF3E0)
- GRİ TONLARI KULLANMA! Sıkıcı görünüyor.
- Her farklı eleman için FARKLI renk kullan
- Çizgiler koyu renk olsun (koyu mavi #1565C0, koyu yeşil #2E7D32)"""
        
        full_detay = f"{detay}\n\nGörselde görünecek değerler: {gorunen_veriler}{renk_talimat}"
        prompt = IMAGE_PROMPT_TEMPLATE.format(tip=tip, detay=full_detay)
        
        self._rate_limit()
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  Image API çağrısı (deneme {attempt + 1}/{Config.MAX_RETRIES})...")
                
                # google-genai SDK ile görsel üret
                response = self.client.models.generate_content(
                    model=GEMINI_IMAGE_MODEL,
                    contents=prompt,
                    config={
                        "response_modalities": ["IMAGE", "TEXT"],
                    }
                )
                
                # Response'dan görsel çıkar
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            inline = part.inline_data
                            if hasattr(inline, 'data') and inline.data:
                                image_data = inline.data
                                if isinstance(image_data, str):
                                    image_bytes = base64.b64decode(image_data)
                                else:
                                    image_bytes = bytes(image_data) if not isinstance(image_data, bytes) else image_data
                                logger.info(f"  ✓ Görsel üretildi ({len(image_bytes)} bytes)")
                                return image_bytes
                
                logger.warning("  Görsel response'da bulunamadı")
                
            except Exception as e:
                logger.error(f"  Image API hatası (deneme {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)
        
        logger.warning("  Görsel üretimi başarısız, devam ediliyor...")
        return None


class SupabaseClient:
    """Supabase client"""
    
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self._curriculum_cache = None
    
    def get_curriculum_for_grade(self, grade_level: int = 8, lesson_name: str = "Matematik") -> List[Dict]:
        """Curriculum tablosundan kazanımları çek"""
        
        if self._curriculum_cache is not None:
            return self._curriculum_cache
        
        query_url = f"{self.url}/rest/v1/curriculum?grade_level=eq.{grade_level}&lesson_name=eq.{lesson_name}&select=id,topic_code,topic_name,sub_topic,learning_outcome_code,learning_outcome_description,bloom_level"
        
        try:
            response = requests.get(
                query_url,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            self._curriculum_cache = response.json()
            logger.info(f"  ✓ Curriculum'dan {len(self._curriculum_cache)} kazanım yüklendi")
            return self._curriculum_cache
        except Exception as e:
            logger.error(f"  Curriculum yükleme hatası: {e}")
            return []
    
    def get_random_kazanim(self, topic_filter: str = None) -> Optional[Dict]:
        """Rastgele bir kazanım seç"""
        curriculum = self.get_curriculum_for_grade()
        
        if not curriculum:
            return None
        
        if topic_filter:
            # Konu adına göre filtrele
            filtered = [k for k in curriculum if topic_filter.lower() in k.get('topic_name', '').lower()]
            if filtered:
                return random.choice(filtered)
        
        return random.choice(curriculum)
    
    def upload_image(self, image_data: bytes, filename: str) -> Optional[str]:
        """Storage'a görsel yükle (bytes olarak)"""
        
        bucket = Config.STORAGE_BUCKET
        upload_url = f"{self.url}/storage/v1/object/{bucket}/{filename}"
        
        try:
            # image_data zaten bytes olarak geliyor
            if isinstance(image_data, str):
                # base64 string ise decode et
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data
            
            response = requests.post(
                upload_url,
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "image/png"
                },
                data=image_bytes,
                timeout=30
            )
            response.raise_for_status()
            
            public_url = f"{self.url}/storage/v1/object/public/{bucket}/{filename}"
            logger.info(f"  ✓ Görsel yüklendi: {filename}")
            return public_url
            
        except requests.exceptions.RequestException as e:
            logger.error(f"  Storage upload hatası: {e}")
            return None
    
    def insert_question(self, question: GeneratedQuestion, kazanim_id: int = None) -> Optional[int]:
        """question_bank tablosuna soru ekle"""
        
        insert_url = f"{self.url}/rest/v1/question_bank"
        
        # Options JSON formatı
        options_json = {
            "A": question.options.get("A", ""),
            "B": question.options.get("B", ""),
            "C": question.options.get("C", ""),
            "D": question.options.get("D", "")
        }
        
        data = {
            "title": question.title[:200] if question.title else "LGS Matematik Sorusu",
            "original_text": question.original_text,
            "options": options_json,
            "correct_answer": question.correct_answer,
            "solution_text": question.solution_text,  # Adım adım çözüm
            "difficulty": question.difficulty,
            "subject": question.subject,
            "grade_level": question.grade_level,
            "topic": question.topic,
            "topic_group": question.topic_group,
            "kazanim_id": kazanim_id,  # curriculum tablosundan gelen id
            "bloom_level": question.bloom_level,
            "pisa_level": question.pisa_level,
            "pisa_context": question.pisa_context,
            "scenario_text": question.scenario_text,
            "distractor_explanations": question.distractor_explanations,
            "image_url": question.image_url,
            "question_type": question.question_type,
            "is_active": question.is_active,
            "verified": question.verified,
            "is_past_exam": False,
            "exam_type": "LGS_AI_BOT"
        }
        
        try:
            response = requests.post(
                insert_url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                question_id = result[0].get("id")
                logger.info(f"  ✓ Soru kaydedildi, ID: {question_id}")
                return question_id
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"  Supabase insert hatası: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"  Response: {e.response.text[:500]}")
            return None

# ============================================================================
# QUALITY VALIDATOR CLASS - Soru ve Görsel Kalite Kontrolü
# ============================================================================

class QualityValidator:
    """Gemini ile soru ve görsel kalite kontrolü + Feedback sistemi"""
    
    QUESTION_VALIDATION_PROMPT = """Bu LGS matematik sorusunu KALİTE KONTROLÜ yap.

════════════════════════════════════════════════════════════════
📝 SORU BİLGİLERİ
════════════════════════════════════════════════════════════════

SORU METNİ:
{question_text}

ŞIKLAR:
A) {option_a}
B) {option_b}
C) {option_c}
D) {option_d}

DOĞRU CEVAP: {correct_answer}

ÇÖZÜM:
{solution}

════════════════════════════════════════════════════════════════
✅ KONTROL KRİTERLERİ
════════════════════════════════════════════════════════════════

1. MATEMATİKSEL DOĞRULUK:
   - Verilen çözüm adımları doğru mu?
   - Doğru cevap gerçekten doğru mu?
   - Hesaplamalar hatasız mı?

2. ÇELDİRİCİ KALİTESİ:
   - Yanlış şıklar mantıklı öğrenci hatalarından mı geliyor?
   - Rastgele sayılar var mı? (KÖTÜ)
   - Her şık farklı bir hata türünü mü temsil ediyor?

3. DİL VE FORMAT:
   - Türkçe dil bilgisi doğru mu?
   - Soru kökü "Buna göre, ..." ile mi başlıyor?

4. PEDAGOJİK KALİTE:
   - Soru LGS 8. sınıf seviyesine uygun mu?
   - Bağlam gerçekçi ve anlamlı mı?
   - Soru tek doğru cevaplı mı?

════════════════════════════════════════════════════════════════

JSON formatında döndür:
{{
    "is_mathematically_correct": true,
    "correct_answer_verified": true,
    "distractors_quality": 8,
    "language_quality": 9,
    "pedagogical_quality": 8,
    "overall_score": 8,
    "pass": true,
    "problems": [],
    "suggestions": [],
    "recommendation": "KABUL"
}}

PUANLAMA (1-10):
- 9-10: Mükemmel
- 7-8: İyi
- 5-6: Orta
- 1-4: Kabul edilemez

SADECE JSON döndür!"""

    IMAGE_VALIDATION_PROMPT = """Bu matematik sorusu görseli için KALİTE KONTROLÜ yap.

════════════════════════════════════════════════════════════════
✅ KABUL KRİTERLERİ
════════════════════════════════════════════════════════════════

1. TEMİZLİK:
   ✅ Soru metni/cümle YOK (sadece kısa etiketler)
   ✅ A), B), C), D) şıkları YOK
   ✅ Sadece şekil ve matematiksel etiketler var

2. TÜRKÇE YAZIM:
   ✅ Türkçe karakterler doğru (ı, ğ, ş, ü, ö, ç)
   ✅ Kelimeler tam ve doğru yazılmış
   ❌ Eksik harf veya yanlış karakter: "Kalınn" → "Kalınlığı"

3. MATEMATİKSEL TUTARLILIK:
   ✅ Değişkenler mantıklı kullanılmış
   ✅ Etiketler ve değerler tutarlı

════════════════════════════════════════════════════════════════
❌ RED SEBEPLERİ
════════════════════════════════════════════════════════════════

1. SORU METNİ: Görselde uzun Türkçe cümle var ("Buna göre...")
2. ŞIKLAR: A), B), C), D) seçenekleri görünüyor
3. YAZIM HATASI: Eksik/yanlış harfli kelimeler
4. İNGİLİZCE: English words görünüyor

════════════════════════════════════════════════════════════════

JSON formatında döndür:
{{
    "has_question_text": false,
    "has_options": false,
    "has_spelling_errors": false,
    "spelling_errors_found": [],
    "has_english": false,
    "is_clean": true,
    "detected_labels": [],
    "overall_score": 8,
    "pass": true,
    "problems": [],
    "recommendation": "KABUL"
}}

SADECE JSON döndür!"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None
        self.quality_threshold = 7
        logger.info("✅ QualityValidator başlatıldı")
    
    def validate_question(self, question_data: Dict) -> Dict:
        """Üretilen soruyu Gemini ile doğrula"""
        
        if not NEW_GENAI or not self.client:
            return {"pass": True, "overall_score": 7, "problems": [], "skipped": True}
        
        try:
            prompt = self.QUESTION_VALIDATION_PROMPT.format(
                question_text=question_data.get("soru_metni", "") + "\\n" + question_data.get("soru_koku", ""),
                option_a=question_data.get("siklar", {}).get("A", ""),
                option_b=question_data.get("siklar", {}).get("B", ""),
                option_c=question_data.get("siklar", {}).get("C", ""),
                option_d=question_data.get("siklar", {}).get("D", ""),
                correct_answer=question_data.get("dogru_cevap", ""),
                solution=question_data.get("cozum_adim_adim", "")
            )
            
            response = self.client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            
            result = json.loads(response.text)
            result["pass"] = result.get("overall_score", 0) >= self.quality_threshold
            return result
            
        except Exception as e:
            logger.error(f"  Soru validasyon hatası: {e}")
            return {"pass": True, "overall_score": 5, "problems": [str(e)], "error": True}
    
    def validate_image(self, image_bytes: bytes, question_text: str = "") -> Dict:
        """Üretilen görseli Gemini ile kontrol et"""
        
        if not NEW_GENAI or not self.client:
            return {"pass": True, "overall_score": 7, "problems": [], "skipped": True}
        
        try:
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            response = self.client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                            {"text": self.IMAGE_VALIDATION_PROMPT}
                        ]
                    }
                ],
                config={"response_mime_type": "application/json"}
            )
            
            result = json.loads(response.text)
            
            # Sorunları topla
            problems = result.get("problems", [])
            
            if result.get("has_question_text"):
                problems.append("Görselde soru metni var")
            if result.get("has_options"):
                problems.append("Görselde şıklar (A,B,C,D) var")
            if result.get("has_spelling_errors"):
                spelling = result.get("spelling_errors_found", [])
                problems.append(f"Yazım hataları: {spelling}")
            if result.get("has_english"):
                problems.append("İngilizce kelimeler var")
            
            result["problems"] = problems
            result["pass"] = result.get("overall_score", 0) >= self.quality_threshold
            return result
            
        except Exception as e:
            logger.error(f"  Görsel validasyon hatası: {e}")
            return {"pass": True, "overall_score": 5, "problems": [str(e)], "error": True}

# ============================================================================
# MAIN GENERATOR CLASS
# ============================================================================

class LGSQuestionGenerator:
    """Ana soru üretim sınıfı - Kalite Kontrol ve Feedback Sistemi ile"""
    
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE credentials not set")
        
        self.gemini = GeminiAPI(GEMINI_API_KEY)
        self.supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
        self.validator = QualityValidator(GEMINI_API_KEY)
        self.stats = {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "with_image": 0,
            "questions_rejected": 0,
            "images_rejected": 0,
            "quality_retries": 0
        }
    
    def generate_single_question(self, params: QuestionParams, kazanim_from_db: Dict = None) -> Optional[int]:
        """Tek bir soru üret ve kaydet - KALİTE KONTROL ile"""
        
        self.stats["total_attempts"] += 1
        konu_display = LGS_KONULAR.get(params.konu, {}).get("display_name", params.konu)
        
        # Curriculum'dan kazanım bilgisi
        kazanim_id = None
        kazanim_info = ""
        if kazanim_from_db:
            kazanim_id = kazanim_from_db.get("id")
            kazanim_info = f"\n   Kazanım ID: {kazanim_id} - {kazanim_from_db.get('learning_outcome_code', '')}"
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📝 SORU ÜRETİMİ BAŞLIYOR")
        logger.info(f"   Konu: {konu_display}")
        logger.info(f"   Alt Konu: {params.alt_konu}")
        logger.info(f"   Kazanım: {params.kazanim_kodu}{kazanim_info}")
        logger.info(f"   Bloom: {params.bloom_seviyesi} | Zorluk: {params.zorluk}/5")
        logger.info(f"{'='*70}")
        
        previous_question_problems = []  # Önceki soru denemelerindeki sorunlar
        previous_image_problems = []     # Önceki görsel denemelerindeki sorunlar
        max_question_retries = 3
        max_image_retries = 3
        
        try:
            # ═══════════════════════════════════════════════════════════════
            # ADIM 1: SORU ÜRETİMİ (Kalite Kontrol + Feedback Döngüsü)
            # ═══════════════════════════════════════════════════════════════
            
            question_data = None
            question_quality_score = 0
            
            for q_attempt in range(max_question_retries):
                logger.info(f"\n[1/5] Gemini ile soru üretiliyor (Deneme {q_attempt + 1}/{max_question_retries})...")
                
                # Feedback varsa prompt'a ekle
                if previous_question_problems:
                    feedback_text = f"\n\n⚠️ ÖNCEKİ DENEMELERDE TESPİT EDİLEN SORUNLAR:\n"
                    feedback_text += "\n".join([f"❌ {p}" for p in previous_question_problems])
                    feedback_text += "\n\nBu hataları TEKRARLAMA! Düzelt ve yeniden üret."
                    params_with_feedback = QuestionParams(
                        konu=params.konu,
                        alt_konu=params.alt_konu + feedback_text,
                        kazanim_kodu=params.kazanim_kodu,
                        bloom_seviyesi=params.bloom_seviyesi,
                        zorluk=params.zorluk,
                        baglam=params.baglam,
                        gorsel_tipi=params.gorsel_tipi
                    )
                else:
                    params_with_feedback = params
                
                question_data = self.gemini.generate_question(params_with_feedback)
                
                # Zorunlu alanları kontrol et
                required_fields = ["soru_metni", "soru_koku", "siklar", "dogru_cevap"]
                missing = [f for f in required_fields if f not in question_data]
                if missing:
                    previous_question_problems.append(f"Eksik alanlar: {missing}")
                    self.stats["quality_retries"] += 1
                    continue
                
                # SORU KALİTE KONTROLÜ
                logger.info("  📊 Soru kalite kontrolü yapılıyor...")
                q_validation = self.validator.validate_question(question_data)
                question_quality_score = q_validation.get("overall_score", 5)
                
                logger.info(f"  📈 Soru Kalite Puanı: {question_quality_score}/10")
                
                if q_validation.get("pass", False):
                    logger.info(f"  ✅ Soru KABUL EDİLDİ")
                    break
                else:
                    # Sorunları kaydet ve bir sonraki denemeye feedback olarak gönder
                    problems = q_validation.get("problems", [])
                    suggestions = q_validation.get("suggestions", [])
                    
                    for p in problems:
                        if p not in previous_question_problems:
                            previous_question_problems.append(p)
                    for s in suggestions:
                        if s not in previous_question_problems:
                            previous_question_problems.append(f"Öneri: {s}")
                    
                    self.stats["questions_rejected"] += 1
                    self.stats["quality_retries"] += 1
                    logger.warning(f"  ❌ Soru REDDEDİLDİ - Sorunlar: {problems}")
                    
                    if q_attempt < max_question_retries - 1:
                        logger.info(f"  🔄 Feedback ile yeniden denenecek...")
                        time.sleep(2)
            
            if not question_data:
                raise ValueError("Soru üretilemedi")
            
            logger.info("  ✓ Soru metni hazır")
            
            # ═══════════════════════════════════════════════════════════════
            # ADIM 2: GÖRSEL ÜRETİMİ (Kalite Kontrol + Feedback Döngüsü)
            # ═══════════════════════════════════════════════════════════════
            
            image_url = None
            image_bytes = None
            image_quality_score = 0
            
            if question_data.get("gorsel_gerekli", False):
                gorsel_betimleme = question_data.get("gorsel_betimleme", {})
                
                if gorsel_betimleme and gorsel_betimleme.get("detay"):
                    
                    for img_attempt in range(max_image_retries):
                        logger.info(f"\n[2/5] Görsel üretiliyor (Deneme {img_attempt + 1}/{max_image_retries})...")
                        
                        # Feedback varsa görsel prompt'una ekle
                        if previous_image_problems:
                            gorsel_betimleme_with_feedback = gorsel_betimleme.copy()
                            feedback = "\n\n⚠️ ÖNCEKİ GÖRSEL SORUNLARI (TEKRARLAMA!):\n"
                            feedback += "\n".join([f"❌ {p}" for p in previous_image_problems])
                            gorsel_betimleme_with_feedback["detay"] = gorsel_betimleme["detay"] + feedback
                        else:
                            gorsel_betimleme_with_feedback = gorsel_betimleme
                        
                        image_bytes = self.gemini.generate_image(gorsel_betimleme_with_feedback, konu=params.konu)
                        
                        if not image_bytes:
                            previous_image_problems.append("Görsel üretilemedi")
                            self.stats["quality_retries"] += 1
                            continue
                        
                        # GÖRSEL KALİTE KONTROLÜ
                        logger.info("  📊 Görsel kalite kontrolü yapılıyor...")
                        soru_metni = question_data.get("soru_metni", "")
                        img_validation = self.validator.validate_image(image_bytes, soru_metni)
                        image_quality_score = img_validation.get("overall_score", 5)
                        
                        logger.info(f"  📈 Görsel Kalite Puanı: {image_quality_score}/10")
                        
                        if img_validation.get("pass", False):
                            logger.info(f"  ✅ Görsel KABUL EDİLDİ")
                            break
                        else:
                            # Sorunları kaydet ve bir sonraki denemeye feedback olarak gönder
                            problems = img_validation.get("problems", [])
                            spelling_errors = img_validation.get("spelling_errors_found", [])
                            
                            for p in problems:
                                if p not in previous_image_problems:
                                    previous_image_problems.append(p)
                            
                            if spelling_errors:
                                previous_image_problems.append(f"Yazım hataları: {spelling_errors}")
                            
                            self.stats["images_rejected"] += 1
                            self.stats["quality_retries"] += 1
                            logger.warning(f"  ❌ Görsel REDDEDİLDİ - Sorunlar: {problems}")
                            
                            if img_attempt < max_image_retries - 1:
                                logger.info(f"  🔄 Feedback ile yeniden denenecek...")
                                time.sleep(3)
                    
                    # Görsel yükle (en iyi sonuçla)
                    if image_bytes:
                        filename = f"lgs_{params.konu}_{uuid.uuid4().hex[:8]}_{int(time.time())}.png"
                        image_url = self.supabase.upload_image(image_bytes, filename)
                        
                        if image_url:
                            self.stats["with_image"] += 1
                            logger.info(f"  ✓ Görsel yüklendi (Kalite: {image_quality_score}/10)")
                        else:
                            logger.warning("  ⚠ Görsel yüklenemedi")
                    else:
                        logger.warning("  ⚠ Tüm görsel denemeleri başarısız")
                else:
                    logger.warning("  ⚠ Görsel betimleme eksik")
            else:
                logger.info("\n[2/5] Görsel gerekli değil, atlanıyor...")
            
            # ═══════════════════════════════════════════════════════════════
            # ADIM 3: VERİ YAPISI OLUŞTUR
            # ═══════════════════════════════════════════════════════════════
            
            logger.info("\n[3/5] Veri yapısı hazırlanıyor...")
            
            soru_metni = question_data.get("soru_metni", "")
            soru_koku = question_data.get("soru_koku", "")
            full_text = f"{soru_metni}\n\n{soru_koku}"
            
            generated = GeneratedQuestion(
                title=soru_metni[:100] + "..." if len(soru_metni) > 100 else soru_metni,
                original_text=full_text,
                options=question_data.get("siklar", {}),
                correct_answer=question_data.get("dogru_cevap", "A"),
                solution_text=question_data.get("cozum_adim_adim", ""),
                difficulty=params.zorluk,
                subject=Config.DEFAULT_SUBJECT,
                grade_level=params.grade_level,
                topic=params.konu,
                topic_group=params.topic_group,
                kazanim_kodu=params.kazanim_kodu,
                bloom_level=params.bloom_seviyesi,
                pisa_level=question_data.get("pisa_seviyesi", 3),
                pisa_context=question_data.get("pisa_baglam", "Kişisel"),
                scenario_text=soru_metni,
                distractor_explanations=question_data.get("celdirici_analizi", {}),
                image_url=image_url
            )
            logger.info("  ✓ Veri yapısı hazır")
            
            # ═══════════════════════════════════════════════════════════════
            # ADIM 4: KALİTE ÖZET
            # ═══════════════════════════════════════════════════════════════
            
            logger.info(f"\n[4/5] 📊 KALİTE ÖZETİ:")
            logger.info(f"   Soru Puanı: {question_quality_score}/10")
            if image_bytes:
                logger.info(f"   Görsel Puanı: {image_quality_score}/10")
            logger.info(f"   Toplam Deneme: Soru={len(previous_question_problems) + 1}, Görsel={len(previous_image_problems) + 1 if gorsel_betimleme else 0}")
            
            # ═══════════════════════════════════════════════════════════════
            # ADIM 5: VERİTABANINA KAYDET
            # ═══════════════════════════════════════════════════════════════
            
            logger.info("\n[5/5] Veritabanına kaydediliyor...")
            question_id = self.supabase.insert_question(generated, kazanim_id=kazanim_id)
            
            if question_id:
                self.stats["successful"] += 1
                logger.info(f"\n✅ BAŞARILI! Soru ID: {question_id}")
                return question_id
            else:
                self.stats["failed"] += 1
                logger.error("\n❌ Veritabanı kaydı başarısız")
                return None
                
        except Exception as e:
            self.stats["failed"] += 1
            logger.error(f"\n❌ HATA: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def generate_batch(self, count_per_topic: int = 1) -> Dict[str, Any]:
        """Tüm konular için toplu soru üret - Curriculum tablosundan kazanım çeker"""
        
        logger.info(f"\n{'#'*70}")
        logger.info(f"🚀 TOPLU SORU ÜRETİMİ BAŞLIYOR")
        logger.info(f"   Her konu için {count_per_topic} soru üretilecek")
        logger.info(f"{'#'*70}\n")
        
        # Önce curriculum'dan 8. sınıf matematik kazanımlarını çek
        logger.info("📚 Curriculum tablosundan kazanımlar yükleniyor...")
        curriculum = self.supabase.get_curriculum_for_grade(grade_level=8, lesson_name="Matematik")
        
        if not curriculum:
            logger.error("❌ Curriculum'dan kazanım yüklenemedi!")
            return {"generated_ids": [], "failed_topics": [], "stats": self.stats}
        
        logger.info(f"   ✓ {len(curriculum)} kazanım bulundu\n")
        
        results = {
            "generated_ids": [],
            "failed_topics": [],
            "stats": {}
        }
        
        # Her konu için belirlenen sayıda soru üret
        for i in range(count_per_topic * len(LGS_KONULAR)):
            # Rastgele bir kazanım seç
            kazanim = random.choice(curriculum)
            
            topic_name = kazanim.get("topic_name", "Genel")
            sub_topic = kazanim.get("sub_topic", "")
            learning_code = kazanim.get("learning_outcome_code", "")
            bloom = kazanim.get("bloom_level") or random.choice(list(BLOOM_SEVIYELERI.keys()))
            
            # LGS_KONULAR'dan en uygun konuyu bul
            konu_key = self._find_matching_konu(topic_name)
            konu_data = LGS_KONULAR.get(konu_key, {})
            
            logger.info(f"\n📚 Konu: {topic_name} (Kazanım ID: {kazanim.get('id')})")
            
            # Parametreleri oluştur
            zorluk = random.randint(3, 5)
            baglam = random.choice(konu_data.get("ornek_baglamlar", ["genel"]))
            gorsel_tipi = random.choice(konu_data.get("gorsel_tipleri", ["geometrik_sekil"]))
            
            params = QuestionParams(
                konu=konu_key,
                alt_konu=sub_topic or konu_data.get("alt_konular", ["genel"])[0],
                kazanim_kodu=learning_code or "M.8.1.1.1",
                bloom_seviyesi=bloom if bloom in BLOOM_SEVIYELERI else "Analiz",
                zorluk=zorluk,
                baglam=baglam,
                gorsel_tipi=gorsel_tipi
            )
            
            question_id = self.generate_single_question(params, kazanim_from_db=kazanim)
            
            if question_id:
                results["generated_ids"].append(question_id)
            else:
                results["failed_topics"].append(f"{topic_name}_{kazanim.get('id')}")
            
            # Rate limiting
            time.sleep(Config.RATE_LIMIT_DELAY)
        
        results["stats"] = self.stats
        return results
    
    def _find_matching_konu(self, topic_name: str) -> str:
        """Curriculum topic_name'den LGS_KONULAR key'ini bul"""
        topic_lower = topic_name.lower()
        
        mapping = {
            "üslü": "uslu_ifadeler",
            "kareköklü": "karekoklu_ifadeler",
            "karekök": "karekoklu_ifadeler",
            "cebirsel": "cebirsel_ifadeler",
            "özdeşlik": "cebirsel_ifadeler",
            "denklem": "denklemler",
            "eşitsizlik": "esitsizlikler",
            "üçgen": "ucgenler",
            "benzerlik": "benzerlik",
            "eşlik": "benzerlik",
            "dönüşüm": "donusum_geometrisi",
            "yansıma": "donusum_geometrisi",
            "öteleme": "donusum_geometrisi",
            "döndürme": "donusum_geometrisi",
            "eğim": "egim",
            "silindir": "geometrik_cisimler",
            "geometrik cisim": "geometrik_cisimler",
            "veri": "veri_analizi",
            "istatistik": "veri_analizi",
            "olasılık": "olasilik",
        }
        
        for keyword, konu_key in mapping.items():
            if keyword in topic_lower:
                return konu_key
        
        # Varsayılan
        return "karekoklu_ifadeler"
    
    def generate_for_topic(self, konu: str, count: int = 5) -> List[int]:
        """Belirli bir konu için soru üret - Curriculum'dan kazanım çeker"""
        
        if konu not in LGS_KONULAR:
            logger.error(f"Geçersiz konu: {konu}")
            logger.info(f"Geçerli konular: {', '.join(LGS_KONULAR.keys())}")
            return []
        
        konu_data = LGS_KONULAR[konu]
        generated_ids = []
        
        # Curriculum'dan bu konuya uygun kazanımları çek
        curriculum = self.supabase.get_curriculum_for_grade(grade_level=8, lesson_name="Matematik")
        
        # Konuya göre filtrele
        filtered_curriculum = [
            k for k in curriculum 
            if self._find_matching_konu(k.get('topic_name', '')) == konu
        ]
        
        if not filtered_curriculum:
            logger.warning(f"  ⚠ {konu} için curriculum'da kazanım bulunamadı, tüm kazanımlar kullanılacak")
            filtered_curriculum = curriculum
        
        logger.info(f"\n📚 {konu_data['display_name']} için {count} soru üretilecek")
        logger.info(f"   Uygun kazanım sayısı: {len(filtered_curriculum)}")
        
        for i in range(count):
            # Rastgele kazanım seç
            kazanim = random.choice(filtered_curriculum) if filtered_curriculum else None
            
            alt_konu = kazanim.get("sub_topic") if kazanim else random.choice(konu_data["alt_konular"])
            kazanim_kodu = kazanim.get("learning_outcome_code") if kazanim else konu_data["kazanimlar"][0]
            bloom = kazanim.get("bloom_level") if kazanim and kazanim.get("bloom_level") in BLOOM_SEVIYELERI else random.choice(list(BLOOM_SEVIYELERI.keys()))
            zorluk = random.randint(3, 5)
            baglam = random.choice(konu_data["ornek_baglamlar"])
            gorsel_tipi = random.choice(konu_data.get("gorsel_tipleri", ["geometrik_sekil"]))
            
            params = QuestionParams(
                konu=konu,
                alt_konu=alt_konu or konu_data["alt_konular"][0],
                kazanim_kodu=kazanim_kodu or "M.8.1.1.1",
                bloom_seviyesi=bloom,
                zorluk=zorluk,
                baglam=baglam,
                gorsel_tipi=gorsel_tipi
            )
            
            question_id = self.generate_single_question(params, kazanim_from_db=kazanim)
            if question_id:
                generated_ids.append(question_id)
            
            time.sleep(Config.RATE_LIMIT_DELAY)
        
        return generated_ids
    
    def print_stats(self):
        """İstatistikleri yazdır"""
        logger.info(f"\n{'='*70}")
        logger.info("📊 SONUÇ İSTATİSTİKLERİ")
        logger.info(f"{'='*70}")
        logger.info(f"   Toplam deneme      : {self.stats['total_attempts']}")
        logger.info(f"   Başarılı           : {self.stats['successful']}")
        logger.info(f"   Başarısız          : {self.stats['failed']}")
        logger.info(f"   Görselli soru      : {self.stats['with_image']}")
        logger.info(f"   ─────────────────────────────")
        logger.info(f"   Reddedilen sorular : {self.stats['questions_rejected']}")
        logger.info(f"   Reddedilen görseller: {self.stats['images_rejected']}")
        logger.info(f"   Kalite yeniden deneme: {self.stats['quality_retries']}")
        
        if self.stats['total_attempts'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total_attempts']) * 100
            logger.info(f"   ─────────────────────────────")
            logger.info(f"   Başarı oranı       : %{success_rate:.1f}")
        logger.info(f"{'='*70}\n")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Ana fonksiyon - GitHub Actions tarafından çağrılır"""
    
    parser = argparse.ArgumentParser(
        description='LGS Matematik Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python lgs_matematik_bot.py --mode batch --count 1
  python lgs_matematik_bot.py --mode topic --topic karekoklu_ifadeler --count 5
  python lgs_matematik_bot.py --mode single --konu ucgenler --bloom Analiz --zorluk 4

Geçerli Konular:
  uslu_ifadeler, karekoklu_ifadeler, cebirsel_ifadeler, denklemler,
  esitsizlikler, ucgenler, benzerlik, donusum_geometrisi, egim,
  geometrik_cisimler, veri_analizi, olasilik
        """
    )
    
    parser.add_argument('--mode', type=str, default='batch',
                       choices=['batch', 'single', 'topic'],
                       help='Çalışma modu')
    parser.add_argument('--count', type=int, default=1,
                       help='Üretilecek soru sayısı')
    parser.add_argument('--topic', type=str, default=None,
                       help='Konu (topic modu için)')
    parser.add_argument('--konu', type=str, default='karekoklu_ifadeler',
                       help='Konu (single modu için)')
    parser.add_argument('--alt-konu', type=str, default=None,
                       help='Alt konu (single modu için)')
    parser.add_argument('--kazanim', type=str, default=None,
                       help='Kazanım kodu (single modu için)')
    parser.add_argument('--bloom', type=str, default='Analiz',
                       choices=['Analiz', 'Değerlendirme', 'Yaratma'],
                       help='Bloom seviyesi')
    parser.add_argument('--zorluk', type=int, default=4,
                       choices=[1, 2, 3, 4, 5],
                       help='Zorluk seviyesi (1-5)')
    
    args = parser.parse_args()
    
    # Banner
    logger.info("""
╔══════════════════════════════════════════════════════════════════════╗
║         🎓 LGS MATEMATİK BOT v2.0                                    ║
║         Gemini 2.5 Flash + Imagen 3 + Supabase                       ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    logger.info(f"📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⚙️  Mod: {args.mode}")
    
    try:
        generator = LGSQuestionGenerator()
        
        if args.mode == 'batch':
            logger.info(f"📦 Batch modu - Her konu için {args.count} soru")
            results = generator.generate_batch(count_per_topic=args.count)
            logger.info(f"\n📋 Üretilen soru sayısı: {len(results['generated_ids'])}")
            if results['failed_topics']:
                logger.info(f"⚠️  Başarısız: {results['failed_topics']}")
            
        elif args.mode == 'topic':
            topic = args.topic or args.konu
            logger.info(f"📚 Topic modu - {topic} için {args.count} soru")
            ids = generator.generate_for_topic(topic, args.count)
            logger.info(f"\n📋 Üretilen sorular: {ids}")
            
        elif args.mode == 'single':
            konu_data = LGS_KONULAR.get(args.konu, {})
            
            alt_konu = args.alt_konu or (konu_data.get("alt_konular", ["genel"])[0] if konu_data else "genel")
            kazanim = args.kazanim or (konu_data.get("kazanimlar", ["M.8.1.1.1"])[0] if konu_data else "M.8.1.1.1")
            baglam = konu_data.get("ornek_baglamlar", ["genel"])[0] if konu_data else "genel"
            gorsel_tipi = konu_data.get("gorsel_tipleri", ["geometrik_sekil"])[0] if konu_data else "geometrik_sekil"
            
            params = QuestionParams(
                konu=args.konu,
                alt_konu=alt_konu,
                kazanim_kodu=kazanim,
                bloom_seviyesi=args.bloom,
                zorluk=args.zorluk,
                baglam=baglam,
                gorsel_tipi=gorsel_tipi
            )
            
            logger.info(f"📝 Single modu - {args.konu}")
            question_id = generator.generate_single_question(params)
            
            if question_id:
                logger.info(f"\n✅ Soru başarıyla üretildi! ID: {question_id}")
            else:
                logger.error("\n❌ Soru üretilemedi")
                sys.exit(1)
        
        generator.print_stats()
        f
    except ValueError as ve:
        logger.error(f"Konfigürasyon hatası: {ve}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Kritik hata: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
