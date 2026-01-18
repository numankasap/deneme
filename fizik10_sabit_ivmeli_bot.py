"""
10. Sınıf Fizik - Sabit İvmeli Hareket Özel Soru Bankası Botu
=============================================================
Türkiye Yüzyılı Maarif Modeli Uyumlu
Konu: 1.2. BİR BOYUTTA SABİT İVMELİ HAREKET

Modlar:
  --mod kazanim    : Kazanım temelli sorular
  --mod baglam     : Bağlamlı/senaryolu beceri soruları
  --mod karisik    : Her ikisinden karışık (varsayılan)

Kullanım:
  python fizik10_sabit_ivmeli_bot.py --mod kazanim --count 10
  python fizik10_sabit_ivmeli_bot.py --mod baglam --count 10
  python fizik10_sabit_ivmeli_bot.py --count 20  # karışık mod
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
    print("google-genai paketi bulunamadı. pip install google-genai yapın.")

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ENVIRONMENT & CONFIG
# ============================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-2.0-flash-exp-image-generation"

class Config:
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    REQUEST_TIMEOUT = 90
    RATE_LIMIT_DELAY = 3
    TEMPERATURE = 0.85
    MAX_OUTPUT_TOKENS = 8192
    STORAGE_BUCKET = "questions-images"

# ============================================================================
# SABİT İVMELİ HAREKET - MÜFREDAT VE KAZANIMLAR
# ============================================================================

KONU_BILGISI = {
    "kod": "FİZ.10.1.2-1.3",
    "baslik": "Bir Boyutta Sabit İvmeli Hareket",
    "unite": "Kuvvet ve Hareket",
    "tema": "Tema 1: Bir Boyutta Hareket",
    "sinif": 10,

    "kazanimlar": {
        "FIZ.10.1.2.a": {
            "kod": "FİZ.10.1.2.a",
            "aciklama": "İvme ve hız değişimi arasındaki ilişkiyi keşfeder.",
            "anahtar_kavramlar": ["ivme", "hız değişimi", "zaman aralığı"],
            "bloom_seviyeleri": ["Hatırlama", "Anlama"],
            "soru_turleri": ["tanim", "kavram", "grafik_okuma"]
        },
        "FIZ.10.1.2.b": {
            "kod": "FİZ.10.1.2.b",
            "aciklama": "İvme ve hız değişimi arasındaki ilişkiyi geneller.",
            "anahtar_kavramlar": ["ivme formülü", "birim zamandaki hız değişimi"],
            "bloom_seviyeleri": ["Anlama", "Uygulama"],
            "soru_turleri": ["hesaplama", "grafik_yorumlama"]
        },
        "FIZ.10.1.3.a": {
            "kod": "FİZ.10.1.3.a",
            "aciklama": "Yatay doğrultuda sabit ivmeli hareket grafiklerini inceler.",
            "anahtar_kavramlar": ["x-t grafiği", "v-t grafiği", "a-t grafiği", "parabolik eğri"],
            "bloom_seviyeleri": ["Anlama", "Analiz"],
            "soru_turleri": ["grafik_okuma", "grafik_cizme", "grafik_yorumlama"]
        },
        "FIZ.10.1.3.b": {
            "kod": "FİZ.10.1.3.b",
            "aciklama": "Yatay doğrultuda sabit ivmeli hareket grafiklerini birbirine dönüştürerek matematiksel modellere ulaşır.",
            "anahtar_kavramlar": ["grafik dönüşümü", "eğim", "alan hesabı", "matematiksel model"],
            "bloom_seviyeleri": ["Uygulama", "Analiz"],
            "soru_turleri": ["grafik_donusumu", "hesaplama", "analiz"]
        },
        "FIZ.10.1.3.c": {
            "kod": "FİZ.10.1.3.c",
            "aciklama": "Yatay doğrultuda sabit ivmeyle hareket eden cisimlerin hareketine ilişkin grafikleri ve matematiksel modeller arasındaki ilişkiyi kendi cümleleriyle yeniden ifade eder.",
            "anahtar_kavramlar": ["sentez", "yorumlama", "ifade etme"],
            "bloom_seviyeleri": ["Analiz", "Değerlendirme", "Yaratma"],
            "soru_turleri": ["yorum", "karsilastirma", "onculu"]
        }
    }
}

# ============================================================================
# TEMEL KAVRAMLAR VE MATEMATİKSEL MODELLER
# ============================================================================

TEMEL_KAVRAMLAR = {
    "ivme": {
        "tanim": "Cismin hızında birim zamanda meydana gelen değişim",
        "sembol": "a",
        "birim": "m/s²",
        "formul": "a = Δv/Δt = (v_son - v_ilk)/(t_son - t_ilk)",
        "ozellikler": ["Vektörel büyüklük", "Yönü hız değişimi yönünde"]
    },
    "sabit_ivme": {
        "tanim": "Hızın eşit zaman aralıklarında aynı miktarda artması veya azalması",
        "ornek": "Her 1 s'de hız 5 m/s artıyorsa ivme 5 m/s²"
    },
    "hizlanan_hareket": {
        "tanim": "Hız vektörü ile ivme vektörünün aynı yönlü olduğu hareket",
        "ozellik": "Sürat artar, ivme pozitif (hareket yönüne göre)"
    },
    "yavalayan_hareket": {
        "tanim": "Hız vektörü ile ivme vektörünün zıt yönlü olduğu hareket",
        "ozellik": "Sürat azalır, ivme negatif (hareket yönüne göre)"
    },
    "pozitif_ivme": {
        "tanim": "İvmenin koordinat sistemine göre pozitif yönde olması",
        "not": "Pozitif ivme her zaman hızlanma demek DEĞİLDİR!"
    },
    "negatif_ivme": {
        "tanim": "İvmenin koordinat sistemine göre negatif yönde olması",
        "not": "Negatif ivme her zaman yavaşlama demek DEĞİLDİR!"
    }
}

MATEMATIKSEL_MODELLER = {
    "ivme_formulu": {
        "model": "a = Δv/Δt = (v - v₀)/(t - t₀)",
        "aciklama": "İvme, hız değişiminin zaman değişimine oranıdır"
    },
    "hiz_formulu": {
        "model": "v = v₀ + a·t",
        "aciklama": "Son hız = İlk hız + İvme × Zaman"
    },
    "konum_formulu_1": {
        "model": "x = v₀·t + (1/2)·a·t²",
        "aciklama": "Yer değiştirme (ilk hız ve ivme biliniyorsa)"
    },
    "konum_formulu_2": {
        "model": "x = ((v + v₀)/2)·t",
        "aciklama": "Yer değiştirme (ortalama hız ile)"
    },
    "zamansiz_formul": {
        "model": "v² = v₀² + 2·a·x",
        "aciklama": "Zaman bilinmeden hız-konum ilişkisi"
    }
}

GRAFIK_BILGILERI = {
    "x_t_grafigi": {
        "sabit_ivmeli": "Parabolik eğri",
        "hizlanan": "Yukarı açık parabol (pozitif yönde)",
        "yavalayan": "Aşağı açık parabol veya eğimi azalan",
        "egim": "Anlık hızı verir",
        "not": "Doğrusal DEĞİL, eğri çizgi!"
    },
    "v_t_grafigi": {
        "sabit_ivmeli": "Doğrusal (düz çizgi)",
        "hizlanan": "Pozitif eğimli doğru",
        "yavalayan": "Negatif eğimli doğru",
        "egim": "İvmeyi verir (a = Δv/Δt)",
        "alan": "Yer değiştirmeyi verir"
    },
    "a_t_grafigi": {
        "sabit_ivmeli": "Yatay doğru (sabit değer)",
        "alan": "Hız değişimini verir (Δv)"
    }
}

# ============================================================================
# KAVRAM YANILGILARI
# ============================================================================

KAVRAM_YANILGILARI = {
    "yanilgilar": [
        "Negatif ivme her zaman yavaşlama demektir",
        "Pozitif ivme her zaman hızlanma demektir",
        "İvme sıfırsa cisim duruyordur",
        "Hız sıfır olduğunda ivme de sıfırdır",
        "v-t grafiğindeki alan hızı verir (YANLIŞ: yer değiştirme verir)",
        "x-t grafiğinde doğrusal çizgi = sabit ivmeli hareket (YANLIŞ: sabit hızlı)",
        "Tepe noktasında ivme sıfırdır (YANLIŞ: hız sıfır, ivme g)",
        "Hız ve ivme her zaman aynı yöndedir"
    ],
    "celdirici_stratejileri": [
        "Negatif ivmeyi her zaman yavaşlama olarak gösteren seçenek",
        "İvme sıfır = cisim durur diyen seçenek",
        "Grafik eğimi ile alanı karıştıran seçenek",
        "Hız sıfırken ivmeyi de sıfır alan seçenek",
        "x-t grafiğini v-t grafiği gibi yorumlayan seçenek",
        "Hız ve ivme yönlerini her zaman aynı kabul eden seçenek"
    ]
}

# ============================================================================
# ZENGİN SENARYO VERİTABANI - SABİT İVMELİ HAREKET ÖZEL
# ============================================================================

SENARYO_VERITABANI = {
    # === ULAŞIM VE ARAÇLAR ===
    "ulasim_araclar": [
        # Kara taşıtları
        "Otomobilin trafik ışığında duruştan kalkışı ve hızlanması",
        "Sürücünün frene basarak aracı durdurması",
        "Otobüsün duraktan kalkışı ve bir sonraki durakta durması",
        "Metro vagonunun istasyondan hızlanarak çıkışı",
        "YHT'nin Eskişehir istasyonundan kalkış ivmesi",
        "Tramvayın duraklara yaklaşırken frenleme süreci",
        "Elektrikli aracın (TOGG) 0-100 km/h hızlanma performansı",
        "Taksi şoförünün trafikte gaz-fren kullanım döngüsü",
        "Motosikletli teslimat görevlisinin kasis öncesi yavaşlaması",
        "Kamyonun rampa çıkışında hız kaybı",
        "Otobüsün otobanda şerit değiştirirken hızlanması",
        "Araç sürüş sınavında kalkış-durma manevrası",
        # Raylı sistemler
        "Marmaray'ın tüp geçitte hızlanma-yavaşlama profili",
        "Teleferik kabininin istasyondan çıkışta ivmelenmesi",
        "Füniküler hattında vagonun yokuş çıkışı",
        # Havacılık
        "Uçağın kalkış pistinde hızlanması",
        "Uçağın iniş pistinde frenleme süreci",
        "Helikopterin dikey kalkışta ivmelenmesi",
    ],

    # === SPOR VE PERFORMANS ===
    "spor_performans": [
        # Atletizm
        "100 metre koşucusunun start bloklarından çıkış ivmesi",
        "Maratonçunun bitiş çizgisine doğru sprint atması",
        "400 metre koşucusunun viraj çıkışında hızlanması",
        "Atlama sporcusunun sıçrama öncesi koşu ivmesi",
        # Su sporları
        "Yüzücünün duvarda dönüş sonrası itme ivmesi",
        "Kürek takımının start anındaki ivmelenme performansı",
        "Kano sporcusunun bitiş sprintinde hızlanması",
        "Su kayakçısının tekne tarafından çekilirken ivmesi",
        # Kış sporları
        "Kayakçının slalom parkurunda viraj arası hızlanması",
        "Buz patencisinin spin öncesi ivmelenmesi",
        "Bobsled takımının start ivmesi",
        "Atlama kulesi sporcusunun düşüş ivmesi",
        # Motor sporları
        "Formula 1 aracının pit stop çıkışı hızlanması",
        "Ralli aracının toprak zeminde frenleme mesafesi",
        "Drag yarışçısının 400 metrede hızlanma profili",
        "MotoGP yarışçısının viraj çıkışında gaz açması",
        # Diğer sporlar
        "Bisikletçinin yokuş aşağı ivmelenmesi",
        "Golf topunun vuruş anında ivmesi",
        "Tenis topunun servis atışında raketten çıkış ivmesi",
        "Okçunun ok bırakma anındaki ok ivmesi",
    ],

    # === TEKNOLOJİ VE MÜHENDİSLİK ===
    "teknoloji_muhendislik": [
        # Asansör sistemleri
        "Asansörün zemin kattan çıkış ivmesi",
        "Asansörün üst katta durmak için frenleme süreci",
        "Yük asansörünün ağır yükle kalkış performansı",
        "Panoramik asansörün konfor ivme limitleri",
        # Endüstriyel
        "Vinç kancasının yükü kaldırırken hızlanması",
        "Forklift operatörünün raf önünde hassas durması",
        "Konveyör bandının vardiya başında hızlanması",
        "Robot kolunun montaj noktasına yaklaşırken yavaşlaması",
        "CNC tezgahında kesici ucun hızlanma profili",
        "3D yazıcı kafasının eksen boyunca ivmelenmesi",
        # Ulaşım mühendisliği
        "Trafik ışığı yeşil dalga sisteminde araç akışı optimizasyonu",
        "Otoyol giriş rampasında hızlanma şeridi tasarımı",
        "Metro istasyonu yaklaşım frenleme mesafesi hesabı",
        "Havalimanı pisti uzunluğu ve kalkış ivmesi ilişkisi",
        # Sensör teknolojileri
        "İvme sensörünün telefonda ekran yönelimi algılaması",
        "Araç hava yastığı tetikleme ivme eşiği",
        "Fitness bilekliğinde adım sayarken ivme ölçümü",
        "Oyun kumandasında hareket algılama",
    ],

    # === GÜNLÜK YAŞAM ===
    "gunluk_yasam": [
        # Ev ve çevre
        "Garaj kapısının motorla açılırken hızlanıp durmadan önce yavaşlaması",
        "Elektrikli süpürgenin açılış anında motor ivmesi",
        "Çamaşır makinesi tamburunun sıkma programında hızlanması",
        "Bulaşık makinesi döner kolunun başlangıç ivmesi",
        # Alışveriş ve ticaret
        "Market arabasını itmeye başlarken hızlanma",
        "AVM'de yürüyen merdivenin başlangıç-bitiş ivmeleri",
        "Kargo paketinin taşıma bandında hızlanması",
        "Alışveriş merkezinde otopark bariyerinin açılışı",
        # Eğlence
        "Lunaparkta hız treni vagonunun rampa sonrası ivmesi",
        "Dönme dolabın başlangıç ivmesi",
        "Go-kart pistinde viraj öncesi frenleme",
        "Bowling topunun atış anındaki ivmesi",
    ],

    # === BİLİM VE DOĞA ===
    "bilim_doga": [
        # Laboratuvar deneyleri
        "Eğik düzlemde arabanın sabit ivme ile kayması",
        "Dinamik araba düzeneğinde ağırlık etkisiyle ivmelenme",
        "Hava yastıklı rayda farklı eğimlerde ivme ölçümü",
        "Atwood makinesinde farklı kütlelerle ivme değişimi",
        "Fotokapı sensörleriyle ivme ölçüm deneyi",
        "Akıllı telefon ivmeölçeri ile deney yapma",
        # Doğa olayları
        "Çığ başlangıcında kar kütlesinin ivmelenmesi",
        "Volkanik lav akışının eğimli yamaçta hızlanması",
        "Nehir suyunun baraj kapaklarından salınırken ivmesi",
        "Toprak kaymasının başlangıç ivmesi",
        # Hayvanlar
        "Çitanın avını kovalarken maksimum ivme kapasitesi",
        "Şahinin pike yaparak ivmelenmesi",
        "Kanguru sıçramasında bacak itme ivmesi",
        "At yarışında start ivmesi",
    ],

    # === ÇOKLU BAĞLAM - ANALİZ SEVİYESİ ===
    "coklu_baglam_analiz": [
        "Farklı markaların elektrikli araçlarının 0-100 hızlanma karşılaştırması",
        "Metro, tramvay ve otobüsün aynı güzergahta ivme profillerinin analizi",
        "Üç farklı asansör sisteminin konfor ivme değerlerinin karşılaştırması",
        "100m, 200m, 400m koşucularının ivme stratejisi farkları",
        "Kuru, ıslak ve buzlu zeminde aracın frenleme ivmesi değişimi",
        "Boş ve yüklü kamyonun aynı rampa çıkışında ivme farkı",
        "Benzinli, dizel ve elektrikli araçların hızlanma performans grafiklerinin karşılaştırması",
        "Kürek, kano ve dragon boat sporlarında takım ivme profillerinin analizi",
    ],

    # === ÇOKLU BAĞLAM - DEĞERLENDİRME SEVİYESİ ===
    "coklu_baglam_degerlendirme": [
        "Trafik kazası rekonstrüksiyonunda fren izlerinden ivme hesabı ve tutarlılık kontrolü",
        "Asansör güvenlik testinde ivme limitlerinin aşılıp aşılmadığının değerlendirilmesi",
        "Sporcunun antrenman verilerinde ivme profilinin performansa etkisinin değerlendirilmesi",
        "Sürücü tepki süresi ve fren mesafesi verilerinin güvenlik değerlendirmesi",
        "Üretim hattında konveyör ivme ayarının ürün kalitesine etkisinin analizi",
        "Farklı ivme değerlerine sahip asansörlerde yolcu konforu değerlendirmesi",
        "Ambulans ve helikopterin acil durum ulaşımında ivme-hız avantaj analizi",
    ],

    # === ÇOKLU BAĞLAM - YARATMA SEVİYESİ ===
    "coklu_baglam_yaratma": [
        "Yeni metro hattı için istasyona yaklaşma fren profilinin tasarlanması",
        "Engelli bireyler için asansör konfor ivme limitlerinin optimize edilmesi",
        "Otonom araç için trafik akışını bozmayan fren profili tasarımı",
        "Elektrikli otobüs filosu için enerji verimliliği-ivme dengesi optimizasyonu",
        "Spor salonları için güvenli ivme limitli fitness ekipmanı tasarımı",
        "Yaşlı ve çocuklar için güvenli lunapark treni ivme profili tasarımı",
        "Deprem tahliyesi için bina asansörlerinin acil mod ivme profili",
    ],
}

# ============================================================================
# BLOOM TAKSONOMİSİ
# ============================================================================

BLOOM_TAKSONOMISI = {
    "Hatırlama": {
        "seviye": 1,
        "fiiller": ["tanımlar", "listeler", "adlandırır", "hatırlar"],
        "soru_kokleri": [
            "İvmenin tanımı nedir?",
            "İvmenin birimi aşağıdakilerden hangisidir?",
            "Sabit ivmeli hareket nedir?"
        ],
        "zorluk": [1, 2]
    },
    "Anlama": {
        "seviye": 2,
        "fiiller": ["açıklar", "yorumlar", "örneklendirir", "karşılaştırır"],
        "soru_kokleri": [
            "Grafiğe göre cismin hareketi nasıldır?",
            "İvme ile hız değişimi arasındaki ilişki nedir?",
            "Hızlanan ve yavaşlayan hareket arasındaki fark nedir?"
        ],
        "zorluk": [2, 3]
    },
    "Uygulama": {
        "seviye": 3,
        "fiiller": ["hesaplar", "uygular", "çözer", "bulur"],
        "soru_kokleri": [
            "Cismin ivmesi kaç m/s² dir?",
            "t saniye sonundaki hızı kaç m/s olur?",
            "Cismin aldığı yol kaç metredir?"
        ],
        "zorluk": [2, 3, 4]
    },
    "Analiz": {
        "seviye": 4,
        "fiiller": ["analiz eder", "karşılaştırır", "ilişkilendirir", "inceler"],
        "soru_kokleri": [
            "Grafiklerin her ikisi incelendiğinde hangi sonuca ulaşılır?",
            "A ve B araçlarının hareketleri karşılaştırıldığında...",
            "Tablodaki veriler incelendiğinde..."
        ],
        "zorluk": [3, 4, 5]
    },
    "Değerlendirme": {
        "seviye": 5,
        "fiiller": ["değerlendirir", "yargılar", "karar verir", "eleştirir"],
        "soru_kokleri": [
            "Aşağıdaki ifadelerden hangileri doğrudur?",
            "Bu durumda yapılan hata nedir?",
            "Hangi yorum yapılamaz?"
        ],
        "zorluk": [4, 5]
    },
    "Yaratma": {
        "seviye": 6,
        "fiiller": ["tasarlar", "planlar", "üretir", "geliştirir"],
        "soru_kokleri": [
            "Bu problemi çözmek için hangi strateji uygulanmalıdır?",
            "Sistemi optimize etmek için ne yapılmalıdır?",
            "Deney düzeneği nasıl tasarlanmalıdır?"
        ],
        "zorluk": [5, 6]
    }
}

# ============================================================================
# SORU TİPLERİ
# ============================================================================

SORU_TIPLERI = {
    "kazanim_temelli": {
        "tanim": "Doğrudan kazanım ifadesini ölçen soru",
        "hesaplama": "v=v₀+at, x=v₀t+½at² gibi formül uygulaması",
        "grafik_okuma": "Verilen grafikten değer okuma",
        "grafik_cizme": "Verilen verilerden grafik oluşturma",
        "grafik_donusumu": "x-t'den v-t'ye veya v-t'den a-t'ye dönüşüm",
        "kavram": "Temel kavram bilgisi (ivme, hızlanma, yavaşlama)"
    },
    "baglam_temelli": {
        "tanim": "Gerçek yaşam senaryosu içeren beceri sorusu",
        "senaryo_hesaplama": "Senaryo içinde matematiksel problem",
        "senaryo_grafik": "Senaryo verilerinden grafik analizi",
        "senaryo_yorumlama": "Senaryo sonuçlarını yorumlama",
        "karsilastirma": "İki veya daha fazla durumun karşılaştırılması",
        "karar_verme": "Veri analizi ile karar verme"
    }
}

# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SYSTEM_PROMPT_KAZANIM = """Sen, Türkiye Yüzyılı Maarif Modeli'ne göre 10. sınıf fizik dersi için KAZANIM TEMELLİ soru hazırlayan uzman bir öğretmensin.

## KONU: BİR BOYUTTA SABİT İVMELİ HAREKET

### KAZANIMLAR:
- FİZ.10.1.2.a: İvme ve hız değişimi arasındaki ilişkiyi keşfeder.
- FİZ.10.1.2.b: İvme ve hız değişimi arasındaki ilişkiyi geneller.
- FİZ.10.1.3.a: Sabit ivmeli hareket grafiklerini inceler.
- FİZ.10.1.3.b: Grafikleri birbirine dönüştürerek matematiksel modellere ulaşır.
- FİZ.10.1.3.c: Grafikler ve matematiksel modeller arasındaki ilişkiyi ifade eder.

### MATEMATİKSEL MODELLER:
- a = Δv/Δt = (v - v₀)/(t - t₀)
- v = v₀ + a·t
- x = v₀·t + (1/2)·a·t²
- v² = v₀² + 2·a·x

### GRAFİK BİLGİLERİ:
- x-t grafiği: Parabolik eğri (sabit ivmede), eğim = anlık hız
- v-t grafiği: Doğrusal çizgi, eğim = ivme, alan = yer değiştirme
- a-t grafiği: Yatay çizgi (sabit ivmede), alan = hız değişimi

### SORU ÖZELLİKLERİ:
- Kazanım kodunu açıkça hedefle
- Matematiksel doğruluk %100 olmalı
- g = 10 m/s² kullan
- Kolay hesaplanan değerler kullan (5, 10, 20, 25, 50, 100)
- Her soruda 5 şık (A, B, C, D, E) olmalı

### ÖNCÜLLÜ SORU FORMATI:
Öncüllü sorularda I, II, III ifadeleri MUTLAKA soru_metni içinde olmalı:

"[Senaryo]
Buna göre, cismin hareketi ile ilgili aşağıdaki ifadelerden hangileri doğrudur?

I. [Birinci ifade]
II. [İkinci ifade]
III. [Üçüncü ifade]"

## JSON ÇIKTI FORMATI:
{
  "soru_metni": "...",
  "soru_koku": "Buna göre, ...",
  "siklar": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
  "dogru_cevap": "A/B/C/D/E",
  "cozum_adim_adim": "Adım 1: ...\\nAdım 2: ...\\nSonuç: ...",
  "kazanim_kodu": "FİZ.10.1.X.x",
  "bloom_seviyesi": "...",
  "zorluk": 1-6,
  "soru_tipi": "hesaplama/grafik_okuma/grafik_donusumu/kavram",
  "celdirici_analizi": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
  "gorsel_gerekli": true/false,
  "gorsel_betimleme": {"tip": "...", "detay": "..."}
}
"""

SYSTEM_PROMPT_BAGLAM = """Sen, Türkiye Yüzyılı Maarif Modeli'ne göre 10. sınıf fizik dersi için BAĞLAM TEMELLİ (senaryolu) beceri soruları hazırlayan uzman bir öğretmensin.

## KONU: BİR BOYUTTA SABİT İVMELİ HAREKET

### MAARİF MODELİ KRİTERLERİ:
1. **BAĞLAM TEMELLİ**: Her soru GERÇEK YAŞAM senaryosu içermeli
2. **EZBERDEN UZAK**: Bilgiyi transfer etmeyi gerektirmeli
3. **ÇELDİRİCİ MANTIĞI**: Yanlış şıklar kavram yanılgılarını hedeflemeli
4. **GEREKSİZ BİLGİ YOK**: Dikkat dağıtıcı detaylardan arındırılmış

### SENARYO KATEGORİLERİ:
1. **Ulaşım**: Metro, YHT, otomobil, uçak kalkış/iniş
2. **Spor**: Koşucu start ivmesi, kürek takımı, yüzücü
3. **Teknoloji**: Asansör, ivme sensörleri, otonom araçlar
4. **Günlük Yaşam**: Lunapark, alışveriş merkezi, ev aletleri
5. **Bilim**: Laboratuvar deneyleri, doğa olayları

### ÜST DÜZEY BLOOM İÇİN ÇOKLU BAĞLAM:
- **Analiz**: İki sistemin karşılaştırması (örn: farklı araçların ivme profilleri)
- **Değerlendirme**: Güvenlik değerlendirmesi, hata analizi
- **Yaratma**: Sistem tasarımı, optimizasyon

### MATEMATİKSEL MODELLER:
- a = Δv/Δt
- v = v₀ + a·t
- x = v₀·t + (1/2)·a·t²
- v² = v₀² + 2·a·x

### GRAFİK TİPLERİ:
- x-t grafiği (parabolik)
- v-t grafiği (doğrusal)
- a-t grafiği (yatay çizgi)

### KAVRAM YANILGILARI (ÇELDİRİCİLER İÇİN):
- Negatif ivme = yavaşlama (YANLIŞ olabilir)
- İvme sıfır = cisim durur (YANLIŞ)
- v-t grafiği alanı = hız (YANLIŞ: yer değiştirme)

### ÖNCÜLLÜ SORU FORMATI:
"[Senaryo açıklaması]

Buna göre, ... ile ilgili aşağıdaki ifadelerden hangileri doğrudur?

I. [Birinci ifade]
II. [İkinci ifade]
III. [Üçüncü ifade]"

Şıklar: A) Yalnız I, B) Yalnız II, C) I ve II, D) II ve III, E) I, II ve III

## JSON ÇIKTI FORMATI:
{
  "soru_metni": "SENARYO + SORU",
  "soru_koku": "Buna göre, ...",
  "siklar": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
  "dogru_cevap": "A/B/C/D/E",
  "cozum_adim_adim": "...",
  "bloom_seviyesi": "...",
  "zorluk": 1-6,
  "senaryo_kategorisi": "ulasim/spor/teknoloji/gunluk_yasam/bilim",
  "kazanim_kodu": "FİZ.10.1.X.x",
  "celdirici_analizi": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
  "gorsel_gerekli": true/false,
  "gorsel_betimleme": {"tip": "...", "detay": "...", "senaryo_nesneleri": "..."}
}
"""

# ============================================================================
# IMAGE PROMPT TEMPLATES
# ============================================================================

IMAGE_PROMPT_2D_GRAPH = """10. Sınıf Fizik - Sabit İvmeli Hareket için TEKNİK 2D GRAFİK çiz.

## GÖRSEL TİPİ: {tip}
## DETAY: {detay}

### GRAFİK STİLİ:
- Temiz koordinat sistemi, beyaz arka plan
- Siyah eksenler, ok uçlu
- Pembe/Magenta (#E91E63) veya Mavi (#2196F3) eğri
- Grid çizgileri (açık gri)

### GRAFİK TİPLERİ:
- x-t: Parabolik eğri (sabit ivmeli hareket)
- v-t: Doğrusal eğik çizgi
- a-t: Yatay düz çizgi

### EKSEN ETİKETLERİ:
- X ekseni: t (s)
- Y ekseni: x (m) veya v (m/s) veya a (m/s²)

YASAKLAR: 3D efekt, gölge, fotoğraf, soru metni
"""

IMAGE_PROMPT_3D_SCENARIO = """10. Sınıf Fizik - Sabit İvmeli Hareket için GERÇEKÇİ 3D GÖRSEL oluştur.

## GÖRSEL TİPİ: {tip}
## DETAY VE SENARYO: {detay}

### KRİTİK KURAL - SENARYO UYUMU:
- SORU BAĞLAMI'ndaki senaryoya TAM UYGUN görsel oluştur!
- Soruda "dinamik arabası" varsa → Laboratuvar ortamı, küçük tekerlekli deney arabası
- Soruda "otomobil/araba" varsa → Gerçekçi bir otomobil (spor araba, sedan, SUV - çeşitlilik!)
- Soruda "tren/metro" varsa → O zaman tren göster
- Soruda "asansör" varsa → Asansör kabini
- Soruda "top/cisim" varsa → Eğik düzlemde top veya küp
- Soruda "koşucu/atlet" varsa → Koşu pisti, atlet
- Soruda "roket/uzay" varsa → Roket fırlatma sahnesi
- Soruda "bisiklet" varsa → Bisikletçi
- Soruda "uçak" varsa → Pist üzerinde uçak
- Soruda "tekne/kayık" varsa → Su üzerinde tekne

### ARAÇ ÇEŞİTLİLİĞİ (her seferinde FARKLI):
- Otomobiller: Kırmızı spor araba, mavi sedan, yeşil SUV, sarı taksi, beyaz ambulans
- Laboratuvar: Mavi/kırmızı/yeşil dinamik arabası, ahşap eğik düzlem
- Trenler: Yüksek hızlı tren, metro, yük treni (SADECE soruda geçerse!)

### 3D GERÇEKÇİ STİL:
- Fotorealistik render kalitesi
- Gerçekçi ışıklandırma ve gölgeler
- Motion blur ile hareket hissi

### FİZİK GÖSTERİMLERİ:
- Hız vektörü: Yeşil ok, glow efekti
- İvme vektörü: Turuncu/kırmızı ok
- Grafik paneli: Şeffaf overlay olarak v-t veya x-t grafiği

YASAKLAR: Soru metni, şıklar, formüller, matematik sembolleri
"""

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class QuestionParams:
    mod: str  # "kazanim" veya "baglam"
    kazanim_kodu: str
    bloom_seviyesi: str
    zorluk: int
    soru_tipi: str
    senaryo: str = ""
    senaryo_kategorisi: str = ""

@dataclass
class GeneratedQuestion:
    title: str
    original_text: str
    options: Dict[str, str]
    correct_answer: str
    solution_text: str
    difficulty: int
    subject: str = "Fizik"
    grade_level: int = 10
    topic: str = "sabit_ivmeli_hareket"
    topic_group: str = "Bir Boyutta Sabit İvmeli Hareket"
    kazanim_kodu: str = ""
    bloom_level: str = ""
    scenario_text: str = ""
    distractor_explanations: Dict[str, str] = field(default_factory=dict)
    image_url: Optional[str] = None
    question_mode: str = ""  # kazanim/baglam

# ============================================================================
# GEMINI API CLIENT
# ============================================================================

class GeminiAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None
        self.last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < Config.RATE_LIMIT_DELAY:
            time.sleep(Config.RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def generate_question(self, params: QuestionParams) -> Optional[Dict]:
        """Soru üret"""

        # Mod'a göre system prompt seç
        if params.mod == "kazanim":
            system_prompt = SYSTEM_PROMPT_KAZANIM
        else:
            system_prompt = SYSTEM_PROMPT_BAGLAM

        # User prompt oluştur
        kazanim_info = KONU_BILGISI["kazanimlar"].get(params.kazanim_kodu, {})
        bloom_info = BLOOM_TAKSONOMISI.get(params.bloom_seviyesi, {})

        user_prompt = f"""
## SORU ÜRETİM TALİMATI

### MOD: {params.mod.upper()} TEMELLİ SORU

### Hedef Kazanım:
- Kod: {params.kazanim_kodu}
- Açıklama: {kazanim_info.get('aciklama', '')}

### Bloom Seviyesi: {params.bloom_seviyesi} (Seviye {bloom_info.get('seviye', 3)})
### Zorluk: {params.zorluk}/6
### Soru Tipi: {params.soru_tipi}

{"### Senaryo: " + params.senaryo if params.senaryo else ""}

### Matematiksel Modeller:
- a = Δv/Δt = (v - v₀)/(t - t₀)
- v = v₀ + a·t
- x = v₀·t + (1/2)·a·t²
- v² = v₀² + 2·a·x

### Grafik Bilgileri:
- v-t grafiğinin eğimi = ivme
- v-t grafiğinin altındaki alan = yer değiştirme
- x-t grafiği parabolik (sabit ivmede)

### Kavram Yanılgıları (Çeldiriciler için):
{chr(10).join(['- ' + y for y in KAVRAM_YANILGILARI['yanilgilar'][:4]])}

### Kurallar:
1. {params.mod.upper()} TEMELLİ soru üret
2. g = 10 m/s² kullan
3. 5 şık (A, B, C, D, E) olmalı
4. Matematiksel olarak %100 DOĞRU olmalı
5. Çeldiriciler kavram yanılgılarını hedeflemeli

{"### ÖNCÜLLÜ SORU FORMATI:" if params.soru_tipi == "onculu" else ""}
{'''
Öncüllü sorularda I, II, III MUTLAKA soru_metni içinde olmalı:

"[Senaryo]

Buna göre, ... ile ilgili aşağıdaki ifadelerden hangileri doğrudur?

I. [Birinci ifade]
II. [İkinci ifade]
III. [Üçüncü ifade]"
''' if params.soru_tipi == "onculu" else ""}
"""

        self._rate_limit()

        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  Gemini API çağrısı (deneme {attempt + 1}/{Config.MAX_RETRIES})...")

                if NEW_GENAI and self.client:
                    response = self.client.models.generate_content(
                        model=GEMINI_TEXT_MODEL,
                        contents=user_prompt,
                        config={
                            "system_instruction": system_prompt,
                            "temperature": Config.TEMPERATURE,
                            "max_output_tokens": Config.MAX_OUTPUT_TOKENS,
                            "response_mime_type": "application/json"
                        }
                    )
                    text_content = response.text
                else:
                    logger.error("google-genai SDK gerekli")
                    return None

                # JSON parse
                try:
                    question_data = json.loads(text_content)
                except json.JSONDecodeError:
                    clean_text = text_content.strip()
                    if clean_text.startswith("```json"):
                        clean_text = clean_text[7:]
                    if clean_text.endswith("```"):
                        clean_text = clean_text[:-3]
                    question_data = json.loads(clean_text.strip())

                # List kontrolü
                if isinstance(question_data, list):
                    if len(question_data) > 0:
                        question_data = question_data[0]
                    else:
                        continue

                if not isinstance(question_data, dict):
                    continue

                # Ek bilgiler ekle
                question_data["mod"] = params.mod
                question_data["kazanim_kodu"] = params.kazanim_kodu
                question_data["bloom_seviyesi"] = params.bloom_seviyesi

                logger.info(f"  ✓ Soru başarıyla üretildi")
                return question_data

            except Exception as e:
                logger.error(f"Hata: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)
                continue

        return None

    def generate_image(self, gorsel_betimleme: Dict, soru_metni: str = "") -> Optional[bytes]:
        """Görsel üret"""
        if not NEW_GENAI or not self.client:
            return None

        tip = gorsel_betimleme.get("tip", "grafik")
        detay = gorsel_betimleme.get("detay", "")

        # Soru bağlamı ekle
        if soru_metni:
            detay += f"\n\nSORU BAĞLAMI:\n{soru_metni[:400]}"

        # Grafik mi, senaryo görseli mi?
        if "grafik" in tip.lower() or "_t_" in tip.lower():
            prompt = IMAGE_PROMPT_2D_GRAPH.format(tip=tip, detay=detay)
            logger.info(f"  Görsel tipi: 2D GRAFİK ({tip})")
        else:
            prompt = IMAGE_PROMPT_3D_SCENARIO.format(tip=tip, detay=detay)
            logger.info(f"  Görsel tipi: 3D SENARYO ({tip})")

        self._rate_limit()

        for attempt in range(Config.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=GEMINI_IMAGE_MODEL,
                    contents=prompt,
                    config={"response_modalities": ["IMAGE", "TEXT"]}
                )

                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            inline = part.inline_data
                            if hasattr(inline, 'data') and inline.data:
                                image_data = inline.data
                                if isinstance(image_data, str):
                                    return base64.b64decode(image_data)
                                return bytes(image_data) if not isinstance(image_data, bytes) else image_data

            except Exception as e:
                logger.error(f"  Image API hatası: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)

        return None

# ============================================================================
# SUPABASE CLIENT
# ============================================================================

class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Görsel yükle"""
        try:
            upload_url = f"{self.url}/storage/v1/object/{Config.STORAGE_BUCKET}/{filename}"
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

            if response.status_code in [200, 201]:
                return f"{self.url}/storage/v1/object/public/{Config.STORAGE_BUCKET}/{filename}"
        except Exception as e:
            logger.error(f"Görsel yükleme hatası: {e}")

        return None

    def insert_question(self, question: GeneratedQuestion, kazanim_id: int = None) -> Optional[int]:
        """Soruyu veritabanına kaydet"""
        try:
            # Options formatı - orijinal bot ile uyumlu
            options_json = {
                "A": question.options.get("A", ""),
                "B": question.options.get("B", ""),
                "C": question.options.get("C", ""),
                "D": question.options.get("D", ""),
                "E": question.options.get("E", "")
            }

            data = {
                "title": question.title[:200] if question.title else "10. Sınıf Fizik Sorusu",
                "original_text": question.original_text,
                "options": options_json,
                "correct_answer": question.correct_answer,
                "solution_text": question.solution_text,
                "difficulty": question.difficulty,
                "subject": question.subject,
                "grade_level": question.grade_level,
                "topic": question.topic,
                "topic_group": question.topic_group,
                "kazanim_id": kazanim_id,
                "bloom_level": question.bloom_level,
                "pisa_level": None,
                "pisa_context": None,
                "scenario_text": question.scenario_text,
                "distractor_explanations": question.distractor_explanations,
                "image_url": question.image_url,
                "question_type": question.question_mode,
                "is_active": True,
                "verified": False,
                "is_past_exam": False,
                "exam_type": "FIZIK10_SABIT_IVMELI_BOT"
            }

            response = requests.post(
                f"{self.url}/rest/v1/question_bank",
                headers=self.headers,
                json=data,
                timeout=30
            )

            if response.status_code == 201:
                result = response.json()
                if result and len(result) > 0:
                    return result[0].get("id")
                else:
                    logger.warning(f"  DB: Boş yanıt döndü")
                    return None
            else:
                logger.error(f"  DB Hatası: {response.status_code} - {response.text[:200]}")

        except Exception as e:
            logger.error(f"Veritabanı hatası: {e}")

        return None

# ============================================================================
# SORU ÜRETİCİ
# ============================================================================

class SabitIvmeliHareketGenerator:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY gerekli!")

        self.gemini = GeminiAPI(GEMINI_API_KEY)
        self.supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

        # Command line flags
        self.gorsel_enabled = False
        self.kazanim_filtre = None

        self.stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "kazanim": 0,
            "baglam": 0,
            "with_image": 0
        }

    def _get_senaryo(self, bloom_seviyesi: str) -> Tuple[str, str]:
        """Bloom seviyesine uygun senaryo seç"""

        if bloom_seviyesi in ["Analiz", "Değerlendirme", "Yaratma"]:
            # Üst düzey için çoklu bağlam
            if random.random() < 0.6:
                if bloom_seviyesi == "Analiz":
                    kategori = "coklu_baglam_analiz"
                elif bloom_seviyesi == "Değerlendirme":
                    kategori = "coklu_baglam_degerlendirme"
                else:
                    kategori = "coklu_baglam_yaratma"
                return random.choice(SENARYO_VERITABANI[kategori]), kategori

        # Normal kategorilerden seç
        kategoriler = ["ulasim_araclar", "spor_performans", "teknoloji_muhendislik", "gunluk_yasam", "bilim_doga"]
        kategori = random.choice(kategoriler)
        return random.choice(SENARYO_VERITABANI[kategori]), kategori

    def _get_soru_tipi(self, mod: str, bloom_seviyesi: str) -> str:
        """Mod ve Bloom'a göre soru tipi seç"""

        if mod == "kazanim":
            if bloom_seviyesi in ["Hatırlama", "Anlama"]:
                return random.choice(["kavram", "grafik_okuma", "tanim"])
            elif bloom_seviyesi == "Uygulama":
                return random.choice(["hesaplama", "grafik_okuma"])
            elif bloom_seviyesi == "Analiz":
                return random.choice(["grafik_donusumu", "analiz"])
            else:
                return random.choice(["onculu", "analiz", "grafik_donusumu"])
        else:  # baglam
            if bloom_seviyesi in ["Hatırlama", "Anlama"]:
                return random.choice(["senaryo_kavram", "senaryo_grafik"])
            elif bloom_seviyesi == "Uygulama":
                return random.choice(["senaryo_hesaplama", "senaryo_grafik"])
            elif bloom_seviyesi == "Analiz":
                return random.choice(["karsilastirma", "senaryo_analiz"])
            else:
                return random.choice(["onculu", "karar_verme", "tasarim"])

    def generate_single(self, mod: str, bloom_seviyesi: str = None) -> Optional[int]:
        """Tek soru üret"""
        self.stats["total"] += 1

        # Bloom seviyesi seç
        if not bloom_seviyesi:
            bloom_seviyesi = random.choice(list(BLOOM_TAKSONOMISI.keys()))

        bloom_info = BLOOM_TAKSONOMISI[bloom_seviyesi]
        zorluk = random.choice(bloom_info["zorluk"])

        # Kazanım seç (filtre varsa kullan)
        if self.kazanim_filtre and self.kazanim_filtre in KONU_BILGISI["kazanimlar"]:
            kazanim_kodu = self.kazanim_filtre
        else:
            kazanim_kodu = random.choice(list(KONU_BILGISI["kazanimlar"].keys()))

        # Senaryo seç (bağlam modu için)
        senaryo, senaryo_kat = "", ""
        if mod == "baglam":
            senaryo, senaryo_kat = self._get_senaryo(bloom_seviyesi)

        # Soru tipi seç
        soru_tipi = self._get_soru_tipi(mod, bloom_seviyesi)

        params = QuestionParams(
            mod=mod,
            kazanim_kodu=kazanim_kodu,
            bloom_seviyesi=bloom_seviyesi,
            zorluk=zorluk,
            soru_tipi=soru_tipi,
            senaryo=senaryo,
            senaryo_kategorisi=senaryo_kat
        )

        logger.info(f"\n{'='*60}")
        logger.info(f"SORU ÜRETİMİ - Mod: {mod.upper()}")
        logger.info(f"  Bloom: {bloom_seviyesi} | Zorluk: {zorluk}/6")
        logger.info(f"  Kazanım: {kazanim_kodu}")
        logger.info(f"  Soru Tipi: {soru_tipi}")
        if senaryo:
            logger.info(f"  Senaryo: {senaryo[:50]}...")
        logger.info(f"{'='*60}")

        # Soru üret
        question_data = self.gemini.generate_question(params)

        if not question_data:
            self.stats["failed"] += 1
            logger.error("  Soru üretilemedi")
            return None

        # Temel alan kontrolü
        required = ["soru_metni", "siklar", "dogru_cevap"]
        if not all(f in question_data for f in required):
            self.stats["failed"] += 1
            logger.error("  Eksik alanlar")
            return None

        # 5 şık kontrolü
        if len(question_data.get("siklar", {})) < 5:
            self.stats["failed"] += 1
            logger.error("  Yetersiz şık sayısı")
            return None

        # Öncüllü soru validasyonu
        if soru_tipi == "onculu":
            soru_metni = question_data.get("soru_metni", "")
            siklar_text = " ".join(str(v) for v in question_data.get("siklar", {}).values()).lower()

            if "yalnız i" in siklar_text or "i ve ii" in siklar_text:
                if not ("I." in soru_metni and "II." in soru_metni):
                    logger.warning("  Öncül formatı hatalı, yeniden deneniyor...")
                    # Tekrar dene
                    question_data = self.gemini.generate_question(params)
                    if not question_data:
                        self.stats["failed"] += 1
                        return None

        # Görsel üret
        image_url = None
        gorsel = question_data.get("gorsel_betimleme", {})
        # --gorsel flag'i veya soru görsel gerektiriyorsa üret
        should_generate_image = self.gorsel_enabled or question_data.get("gorsel_gerekli")
        if should_generate_image and gorsel:
            logger.info("  Görsel üretiliyor...")
            image_bytes = self.gemini.generate_image(gorsel, question_data.get("soru_metni", ""))

            if image_bytes and self.supabase:
                filename = f"sabit_ivmeli_{uuid.uuid4().hex[:12]}.png"
                image_url = self.supabase.upload_image(image_bytes, filename)
                if image_url:
                    self.stats["with_image"] += 1
                    logger.info(f"  ✓ Görsel yüklendi")

        # Veritabanına kaydet
        soru_metni = question_data.get("soru_metni", "")
        soru_koku = question_data.get("soru_koku", "")
        full_text = f"{soru_metni}\n\n{soru_koku}" if soru_koku else soru_metni

        generated = GeneratedQuestion(
            title=soru_metni[:100],
            original_text=full_text,
            options=question_data.get("siklar", {}),
            correct_answer=question_data.get("dogru_cevap", "A"),
            solution_text=question_data.get("cozum_adim_adim", ""),
            difficulty=zorluk,
            kazanim_kodu=kazanim_kodu,
            bloom_level=bloom_seviyesi,
            scenario_text=senaryo,
            distractor_explanations=question_data.get("celdirici_analizi", {}),
            image_url=image_url,
            question_mode=mod
        )

        if self.supabase:
            question_id = self.supabase.insert_question(generated)
            if question_id:
                self.stats["successful"] += 1
                self.stats[mod] += 1
                logger.info(f"\n✓ BAŞARILI! ID: {question_id}")
                return question_id
        else:
            self.stats["successful"] += 1
            self.stats[mod] += 1
            logger.info(f"\n✓ BAŞARILI! (DB bağlantısı yok)")
            return -1

        self.stats["failed"] += 1
        return None

    def generate_batch(self, count: int = 20, mod: str = "karisik"):
        """Toplu soru üret"""
        logger.info(f"\n{'#'*70}")
        logger.info(f"SABİT İVMELİ HAREKET - SORU BANKASI BOTU")
        logger.info(f"Mod: {mod.upper()} | Toplam: {count} soru")
        logger.info(f"{'#'*70}\n")

        results = {"ids": [], "stats": {}}

        # Bloom dağılımı
        bloom_list = list(BLOOM_TAKSONOMISI.keys())
        per_bloom = count // 6
        remainder = count % 6

        distribution = {}
        for i, bloom in enumerate(bloom_list):
            distribution[bloom] = per_bloom + (1 if i < remainder else 0)

        logger.info("Bloom Dağılımı:")
        for bloom, sayi in distribution.items():
            logger.info(f"  {bloom}: {sayi}")

        for bloom_seviyesi, soru_sayisi in distribution.items():
            logger.info(f"\n[{bloom_seviyesi.upper()}] - {soru_sayisi} soru üretiliyor...")

            for i in range(soru_sayisi):
                # Mod seçimi
                if mod == "karisik":
                    current_mod = random.choice(["kazanim", "baglam"])
                else:
                    current_mod = mod

                logger.info(f"  Soru {i+1}/{soru_sayisi} ({current_mod})")

                question_id = self.generate_single(current_mod, bloom_seviyesi)
                if question_id:
                    results["ids"].append(question_id)

                time.sleep(1)  # Rate limit

        results["stats"] = self.stats
        return results

    def print_stats(self):
        """İstatistikleri yazdır"""
        logger.info(f"\n{'='*60}")
        logger.info("ÖZET İSTATİSTİKLER")
        logger.info(f"{'='*60}")
        logger.info(f"Toplam Deneme: {self.stats['total']}")
        logger.info(f"Başarılı: {self.stats['successful']}")
        logger.info(f"Başarısız: {self.stats['failed']}")
        logger.info(f"Kazanım Temelli: {self.stats['kazanim']}")
        logger.info(f"Bağlam Temelli: {self.stats['baglam']}")
        logger.info(f"Görselli: {self.stats['with_image']}")
        logger.info(f"Başarı Oranı: {(self.stats['successful']/max(1, self.stats['total'])*100):.1f}%")
        logger.info(f"{'='*60}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sabit İvmeli Hareket Soru Bankası Botu")
    parser.add_argument("--mod", choices=["kazanim", "baglam", "karisik"], default="karisik",
                       help="Soru modu: kazanim, baglam veya karisik (varsayılan)")
    parser.add_argument("--count", "--adet", type=int, default=20, dest="count",
                       help="Üretilecek soru sayısı")
    parser.add_argument("--bloom", type=str, help="Belirli Bloom seviyesi")
    parser.add_argument("--gorsel", action="store_true",
                       help="Görsel üretimini aktifleştir")
    parser.add_argument("--kazanim", type=str,
                       help="Belirli kazanım filtresi (ör: FIZ.10.1.2.a)")

    args = parser.parse_args()

    try:
        generator = SabitIvmeliHareketGenerator()

        # Görsel üretimi global flag
        generator.gorsel_enabled = args.gorsel

        # Kazanım filtresi
        generator.kazanim_filtre = args.kazanim

        if args.bloom:
            # Tek Bloom seviyesi
            if args.bloom not in BLOOM_TAKSONOMISI:
                print(f"Geçersiz Bloom: {args.bloom}")
                print(f"Geçerli: {', '.join(BLOOM_TAKSONOMISI.keys())}")
                sys.exit(1)

            for i in range(args.count):
                generator.generate_single(args.mod, args.bloom)
        else:
            # Toplu üretim
            generator.generate_batch(count=args.count, mod=args.mod)

        generator.print_stats()

    except Exception as e:
        logger.error(f"Hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
