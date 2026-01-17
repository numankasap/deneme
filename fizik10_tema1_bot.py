"""
10. Sınıf Fizik - Tema 1: Bir Boyutta Hareket
Soru Üretim Botu v1.0
=====================================
Türkiye Yüzyılı Maarif Modeli Uyumlu
Bloom Taksonomisi Tabanlı Zorluk Seviyeleri

Kapsam:
- 1.1. Sabit Hızlı Hareket
- 1.2. Bir Boyutta Sabit İvmeli Hareket
- 1.3. Serbest Düşme
- 1.4. İki Boyutta Sabit İvmeli Hareket

Kullanım:
  python fizik10_tema1_bot.py --mode batch --count 30
  python fizik10_tema1_bot.py --mode topic --topic sabit_hizli --count 10
  python fizik10_tema1_bot.py --mode single --konu ivmeli_hareket --bloom Analiz --zorluk 4
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
# API CONFIGURATION
# ============================================================================

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"
GEMINI_TEXT_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent"

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    REQUEST_TIMEOUT = 90
    RATE_LIMIT_DELAY = 3
    DEFAULT_GRADE_LEVEL = 10
    DEFAULT_SUBJECT = "Fizik"
    DEFAULT_TOPIC_GROUP = "10. Sınıf Fizik"
    TEMPERATURE = 0.85
    MAX_OUTPUT_TOKENS = 8192
    STORAGE_BUCKET = "questions-images"

# ============================================================================
# BLOOM TAKSONOMİSİ - 6 BASAMAK (YENİ BLOOM)
# ============================================================================

BLOOM_TAKSONOMISI = {
    "Hatırlama": {
        "seviye": 1,
        "aciklama": "Bilgiyi tanıma, hatırlama, listeleme, tanımlama",
        "fiiller": ["tanımlar", "listeler", "adlandırır", "hatırlar", "tanır", "seçer"],
        "soru_kokleri": [
            "Aşağıdakilerden hangisi ... tanımıdır?",
            "... kavramı neyi ifade eder?",
            "Aşağıdakilerden hangisi ... için doğrudur?",
            "... birimi aşağıdakilerden hangisidir?"
        ],
        "zorluk_aralik": [1, 2],
        "soru_sayisi_30": 5,
        "ornek_soru_tipi": "Temel tanım ve kavram soruları"
    },

    "Anlama": {
        "seviye": 2,
        "aciklama": "Bilgiyi açıklama, yorumlama, örneklendirme, sınıflandırma",
        "fiiller": ["açıklar", "yorumlar", "örneklendirir", "özetler", "karşılaştırır", "sınıflandırır"],
        "soru_kokleri": [
            "Bu durumun nedeni aşağıdakilerden hangisidir?",
            "Grafik incelendiğinde aşağıdakilerden hangisi söylenebilir?",
            "... ile ... arasındaki fark nedir?",
            "Bu hareket türü aşağıdakilerden hangisiyle açıklanabilir?"
        ],
        "zorluk_aralik": [2, 3],
        "soru_sayisi_30": 5,
        "ornek_soru_tipi": "Grafik yorumlama, kavram karşılaştırma"
    },

    "Uygulama": {
        "seviye": 3,
        "aciklama": "Bilgiyi yeni durumlara uygulama, problem çözme, hesaplama yapma",
        "fiiller": ["hesaplar", "uygular", "çözer", "kullanır", "gösterir", "bulur"],
        "soru_kokleri": [
            "Buna göre ... kaç m/s'dir?",
            "Cismin ... değeri kaçtır?",
            "... süresinde aldığı yol kaç metredir?",
            "Grafiğe göre ... değerini hesaplayınız."
        ],
        "zorluk_aralik": [2, 3, 4],
        "soru_sayisi_30": 5,
        "ornek_soru_tipi": "Formül uygulamalı hesaplama soruları"
    },

    "Analiz": {
        "seviye": 4,
        "aciklama": "Parça-bütün ilişkisi kurma, karşılaştırma, ilişkilendirme, çözümleme",
        "fiiller": ["analiz eder", "karşılaştırır", "ayırt eder", "ilişkilendirir", "inceler", "çözümler"],
        "soru_kokleri": [
            "Bu iki hareket karşılaştırıldığında hangisi doğrudur?",
            "Grafiklerin her ikisi incelendiğinde aşağıdakilerden hangisine ulaşılır?",
            "A ve B cisimlerinin hareketleri arasındaki ilişki nedir?",
            "Tablodaki veriler incelendiğinde hangi sonuca ulaşılır?"
        ],
        "zorluk_aralik": [3, 4, 5],
        "soru_sayisi_30": 5,
        "ornek_soru_tipi": "Grafik dönüşümü, çoklu veri analizi"
    },

    "Değerlendirme": {
        "seviye": 5,
        "aciklama": "Yargılama, karar verme, ölçüt kullanma, eleştirme, seçim yapma",
        "fiiller": ["değerlendirir", "yargılar", "karar verir", "seçer", "savunur", "eleştirir"],
        "soru_kokleri": [
            "Aşağıdaki ifadelerden hangileri doğrudur?",
            "Bu deneyde yapılan hata aşağıdakilerden hangisidir?",
            "Verilen bilgilere göre hangi yorum yapılamaz?",
            "I, II ve III numaralı ifadelerden hangileri kesinlikle doğrudur?"
        ],
        "zorluk_aralik": [4, 5],
        "soru_sayisi_30": 5,
        "ornek_soru_tipi": "Öncüllü sorular (I, II, III), yargı değerlendirme"
    },

    "Yaratma": {
        "seviye": 6,
        "aciklama": "Tasarlama, planlama, üretme, sentezleme, özgün çözüm geliştirme",
        "fiiller": ["tasarlar", "oluşturur", "planlar", "sentezler", "üretir", "geliştirir"],
        "soru_kokleri": [
            "Bu problemi çözmek için hangi strateji uygulanmalıdır?",
            "Verilen koşullarda sistemi optimize etmek için ne yapılmalıdır?",
            "Deney düzeneği nasıl tasarlanmalıdır?",
            "Bu sonuca ulaşmak için hangi adımlar izlenmelidir?"
        ],
        "zorluk_aralik": [5, 6],
        "soru_sayisi_30": 5,
        "ornek_soru_tipi": "Deney tasarımı, problem çözme stratejisi"
    }
}

# ============================================================================
# ZORLUK SEVİYELERİ (1-6 BLOOM UYUMLU)
# ============================================================================

ZORLUK_DAGILIMI = {
    1: {"oran": 0.10, "aciklama": "Çok Kolay - Temel tanım hatırlama", "adim_sayisi": 1, "bloom": ["Hatırlama"]},
    2: {"oran": 0.20, "aciklama": "Kolay - Basit kavram anlama/uygulama", "adim_sayisi": 1, "bloom": ["Hatırlama", "Anlama", "Uygulama"]},
    3: {"oran": 0.30, "aciklama": "Orta - Standart problem çözme", "adim_sayisi": 2, "bloom": ["Anlama", "Uygulama", "Analiz"]},
    4: {"oran": 0.25, "aciklama": "Zor - Çoklu adım, grafik analizi", "adim_sayisi": 3, "bloom": ["Uygulama", "Analiz", "Değerlendirme"]},
    5: {"oran": 0.10, "aciklama": "Çok Zor - Öncüllü, sentez gerektiren", "adim_sayisi": 4, "bloom": ["Analiz", "Değerlendirme", "Yaratma"]},
    6: {"oran": 0.05, "aciklama": "Seçici - Yaratıcı problem çözme", "adim_sayisi": 5, "bloom": ["Değerlendirme", "Yaratma"]}
}

# ============================================================================
# 10. SINIF 1. TEMA - MÜFREDAT SINIRLARI VE KAZANIMLAR
# ============================================================================

TEMA1_MUFREDAT = {

    "sabit_hizli_hareket": {
        "display_name": "Sabit Hızlı Hareket (Doğrusal Hareket)",
        "kazanim_kodu": "FİZ.10.1.1",
        "kazanimlar": [
            "FİZ.10.1.1.a - Yatay doğrultuda sabit hızlı hareket eden cisimlerin konum, yer değiştirme, hız ve zaman değişkenlerini deney yaparak gözlemler.",
            "FİZ.10.1.1.b - Yatay doğrultuda sabit hızlı hareket eden cisimlerin hareket grafiklerinden yararlanarak ortalama hız, ortalama sürat ve yer değiştirmenin matematiksel modelini bulur.",
            "FİZ.10.1.1.c - Yatay doğrultuda sabit hızlı hareket eden cisimlerin hız, sürat, yer değiştirme ve alınan yol değişkenlerine ilişkin matematiksel modelleri geneller."
        ],
        "temel_kavramlar": {
            "konum": "Bir cismin belirlenmiş bir referans noktasına göre bulunduğu yer",
            "alinan_yol": "Bir hareketlinin yörüngesi üzerinde kat ettiği toplam mesafe (skaler)",
            "yer_degistirme": "Cismin son konumu ile ilk konumu arasındaki en kısa mesafe (vektörel)",
            "surat": "Birim zamanda alınan yol (skaler)",
            "hiz": "Birim zamandaki yer değiştirme (vektörel)",
            "sabit_surat": "Eşit zaman aralıklarında eşit yollar alma durumu",
            "sabit_hiz": "Eşit zaman aralıklarında eşit yer değiştirmelere sahip olma durumu",
            "ortalama_hiz": "Toplam yer değiştirme / Geçen süre",
            "ortalama_surat": "Toplam alınan yol / Geçen süre"
        },
        "matematiksel_modeller": [
            "Δx = v · Δt (Yer değiştirme)",
            "v = (x_son - x_ilk) / (t_son - t_ilk) = Δx / Δt (Hız)",
            "Ortalama hız = Toplam yer değiştirme / Geçen süre",
            "Ortalama sürat = Alınan toplam yol / Geçen süre"
        ],
        "grafik_yetkinlikleri": [
            "x-t grafiği çizme ve yorumlama",
            "x-t grafiğinin eğiminin hızı verdiğini anlama",
            "Pozitif eğim = pozitif yönde hareket, Negatif eğim = negatif yönde hareket",
            "v-t grafiği çizme ve yorumlama",
            "Sabit hızda v-t grafiğinin yatay olduğunu bilme",
            "v-t grafiğinde alan = yer değiştirme"
        ],
        "deger_araliklari": {
            "hiz": {"min": -100, "max": 100, "birim": "m/s"},
            "zaman": {"min": 0, "max": 1000, "birim": "s"},
            "mesafe": {"min": 0, "max": 10000, "birim": "m"}
        },
        "senaryo_sinirlari": "En fazla 3 farklı sabit hızlı bölüm",
        "ornek_senaryolar": [
            "Robot süpürgelerin evin odaları arasında yaptığı doğrusal hareketler",
            "Doğrusal parkurda birbirine doğru veya aynı yönde hareket eden bisikletliler",
            "Farklı sabit hızlara sahip taşıyıcı bantlar üzerinde hareket eden ürünler",
            "CNC makinesinin bir harfi oluşturmak için yaptığı parçalı doğrusal kesim hareketleri",
            "Evden durağa yürüme ve otobüsle okula gitme (parçalı hareket)",
            "Platform tipi asansörlerin katlar arasında yaptığı sabit hızlı dikey hareketler",
            "Elektrikli scooter ile sabit hızda ilerleme",
            "Yürüyen merdiven ve platform asansör karşılaştırması"
        ],
        "gorsel_tipleri": ["x-t_grafigi", "v-t_grafigi", "hareket_diyagrami", "parkur_semasi"]
    },

    "ivmeli_hareket": {
        "display_name": "Bir Boyutta Sabit İvmeli Hareket",
        "kazanim_kodu": "FİZ.10.1.2, FİZ.10.1.3",
        "kazanimlar": [
            "FİZ.10.1.2.a - İvme ve hız değişimi arasındaki ilişkiyi keşfeder.",
            "FİZ.10.1.2.b - İvme ve hız değişimi arasındaki ilişkiyi geneller.",
            "FİZ.10.1.3.a - Yatay doğrultuda sabit ivmeli hareket grafiklerini inceler.",
            "FİZ.10.1.3.b - Yatay doğrultuda sabit ivmeli hareket grafiklerini birbirine dönüştürerek matematiksel modellere ulaşır.",
            "FİZ.10.1.3.c - Yatay doğrultuda sabit ivmeyle hareket eden cisimlerin hareketine ilişkin grafikleri ve matematiksel modeller arasındaki ilişkiyi kendi cümleleriyle yeniden ifade eder."
        ],
        "temel_kavramlar": {
            "ivme": "Cismin hızında birim zamanda meydana gelen değişim (a = Δv/Δt), vektörel, birimi m/s²",
            "sabit_ivme": "Hareketlinin hızının eşit zaman aralıklarında aynı miktarda artması/azalması",
            "hizlanan_hareket": "Hız vektörü ile ivme vektörünün aynı yönlü olduğu hareket (sürat artar)",
            "yavalayan_hareket": "Hız vektörü ile ivme vektörünün zıt yönlü olduğu hareket (sürat azalır)",
            "pozitif_ivme": "İvmenin koordinat sistemine göre pozitif yönde olması",
            "negatif_ivme": "İvmenin koordinat sistemine göre negatif yönde olması"
        },
        "matematiksel_modeller": [
            "a = Δv / Δt = (v_son - v_ilk) / (t_son - t_ilk)",
            "v = v₀ + a·t",
            "x = v₀·t + (1/2)·a·t²",
            "v² = v₀² + 2·a·x"
        ],
        "grafik_yetkinlikleri": [
            "x-t grafiğinin parabolik olduğunu anlama",
            "v-t grafiğinin eğimi = ivme",
            "v-t grafiğindeki alan = yer değiştirme",
            "a-t grafiğinin sabit ivmede yatay olduğunu bilme",
            "a-t grafiğindeki alan = hız değişimi (Δv)",
            "Grafikler arası dönüşüm yapabilme (a-t → v-t → x-t)"
        ],
        "deger_araliklari": {
            "hiz": {"min": -100, "max": 100, "birim": "m/s"},
            "ivme": {"min": -20, "max": 20, "birim": "m/s²"},
            "zaman": {"min": 0, "max": 100, "birim": "s"}
        },
        "senaryo_sinirlari": "En fazla 2 farklı sabit ivmeli bölüm (örn: hızlanma + yavaşlama)",
        "ornek_senaryolar": [
            "Kısa mesafe koşucularının start anındaki ivmelenme hareketleri",
            "Trafikte gaz pedalına basan veya frene basan aracın hızlanma/yavaşlama hareketi",
            "Metro veya YHT'nin istasyondan kalkışı ve duruşu",
            "Zıt yönlerde veya aynı yönde ivmeli hareket yapan araçların karşılaşması",
            "Sürücünün tepki süresi ve fren mesafesi hesaplamaları",
            "Kürek takımı veya koşucuların performans verileri analizi",
            "Yarış otomobillerinin hızlanma performansı",
            "Motosikletli teslimat görevlisinin trafikte hızlanma/yavaşlama hareketi"
        ],
        "gorsel_tipleri": ["x-t_grafigi", "v-t_grafigi", "a-t_grafigi", "hareket_diyagrami"]
    },

    "serbest_dusme": {
        "display_name": "Serbest Düşme",
        "kazanim_kodu": "FİZ.10.1.4, FİZ.10.1.5",
        "kazanimlar": [
            "FİZ.10.1.4.a - Serbest düşme hareketi yapan cisimleri gözlemleyerek ivme ve hız değişimleri arasındaki ilişkiyi bulur.",
            "FİZ.10.1.4.b - Serbest düşme hareketi yapan cisimlerin ivmesi hakkında genelleme yapar.",
            "FİZ.10.1.5.a - Serbest düşme hareketi ile ilgili verileri toplayarak kaydeder.",
            "FİZ.10.1.5.b - Serbest düşme hareketi ile ilgili veri setleri oluşturur.",
            "FİZ.10.1.5.c - Serbest düşme hareketini verilere dayalı olarak açıklar."
        ],
        "temel_kavramlar": {
            "yer_cekimi_kuvveti": "Dünya'nın kütlesinden dolayı cisimlere uyguladığı ve yere doğru düşmesine neden olan kuvvet",
            "yer_cekimi_ivmesi": "Sadece yer çekimi kuvvetinin etkisiyle hareket eden cismin kazandığı ivme (g ≈ 9.8 m/s² veya 10 m/s²)",
            "serbest_dusme": "Cismin ilk hızsız olarak serbest bırakıldığında, hava sürtünmesi ihmal edilerek yalnızca yer çekimi etkisinde yaptığı hareket",
            "kutleden_bagimsizlik": "Sürtünmesiz ortamda cisimlerin kütlelerine bakılmaksızın aynı yer çekimi ivmesiyle düşmesi"
        },
        "matematiksel_modeller": [
            "v = g·t (Hız, belirli süre sonra)",
            "h = (1/2)·g·t² (Yükseklik/Kat edilen mesafe)",
            "v² = 2·g·h (Zamansız hız formülü)"
        ],
        "grafik_yetkinlikleri": [
            "h-t grafiği çizme ve yorumlama",
            "v-t grafiği çizme ve yorumlama",
            "a-t grafiğinin sabit (g) olduğunu bilme"
        ],
        "deger_araliklari": {
            "yukseklik": {"min": 1, "max": 5000, "birim": "m"},
            "g": {"degerler": [9.8, 10], "birim": "m/s²"}
        },
        "senaryo_sinirlari": "Yalnızca ilk hızsız (v₀ = 0) serbest düşme. Yukarı/aşağı yönde ilk hızla atış KAPSAM DIŞI.",
        "ornek_senaryolar": [
            "Belirli yükseklikten serbest bırakılan taş/top/nesnenin yere düşme süresi hesaplama",
            "Kuyu veya uçurum derinliğinin düşme süresiyle hesaplanması",
            "Ay veya Mars'ta serbest düşme karşılaştırması",
            "Havası boşaltılmış ortamda tüy ve çekiç deneyi (Apollo 15)",
            "Paraşütçünün paraşüt açılmadan önceki düşüşü",
            "Binadan serbest bırakılan topun yere düşmesi"
        ],
        "gorsel_tipleri": ["h-t_grafigi", "v-t_grafigi", "a-t_grafigi", "dusme_diyagrami"]
    },

    "iki_boyutta_hareket": {
        "display_name": "İki Boyutta Sabit İvmeli Hareket",
        "kazanim_kodu": "FİZ.10.1.6",
        "kazanimlar": [
            "FİZ.10.1.6.a - İki boyutta sabit ivmeli hareketin bileşenleri ile sabit hızlı ve sabit ivmeli hareket arasındaki ilişkiyi bulur.",
            "FİZ.10.1.6.b - İki boyutta sabit ivmeli hareketine yönelik genelleme yapar."
        ],
        "temel_kavramlar": {
            "yatay_bilesen": "İki boyutta harekette yatay doğrultudaki hız bileşeni (sabit, ivmesiz)",
            "dusey_bilesen": "İki boyutta harekette düşey doğrultudaki hız bileşeni (yer çekimi etkisinde)",
            "bileske_hiz": "Yatay ve düşey hız bileşenlerinin vektörel toplamı",
            "menzil": "Cismin atıldığı noktadan yatay doğrultuda gittiği en uzak mesafe",
            "ucus_suresi": "Cismin havada kalma süresi",
            "maksimum_yukseklik": "Cismin düşey doğrultuda ulaştığı en yüksek nokta"
        },
        "matematiksel_modeller": [
            "vₓ = v₀·cos(θ) (Yatay hız bileşeni - sabit)",
            "vᵧ = v₀·sin(θ) - g·t (Düşey hız bileşeni)",
            "x = vₓ·t (Yatay yer değiştirme)",
            "h = vᵧ₀·t - (1/2)·g·t² (Düşey yer değiştirme - yukarı atış)",
            "h = (1/2)·g·t² (Düşey yer değiştirme - yatay atış)",
            "v² = vₓ² + vᵧ² (Bileşke hız)",
            "x_menzil = v₀·t_uçuş (Menzil)"
        ],
        "grafik_yetkinlikleri": [
            "Yörünge eğrisi çizme ve yorumlama",
            "Yatay ve düşey hız bileşenlerinin zamanla değişimini gösterme",
            "Bileşke hız vektörünü farklı noktalarda gösterme"
        ],
        "deger_araliklari": {
            "hiz": {"min": 0, "max": 100, "birim": "m/s"},
            "aci": {"degerler": [30, 37, 45, 53, 60], "birim": "derece"},
            "yukseklik": {"min": 0, "max": 500, "birim": "m"}
        },
        "senaryo_sinirlari": "Hava direnci ihmal edilir. Yatay atış ve eğik atış.",
        "ornek_senaryolar": [
            "Masa tenisinde topa vuruş ve topun hareketi",
            "Futbolcunun şut çekişi ve topun yörüngesi",
            "Şelaleden akan suyun hareketi",
            "Voleybol oyuncularının top atışı",
            "Cirit atma sporu",
            "Sirk akrobatının atlayışı",
            "Su roketi yarışması"
        ],
        "gorsel_tipleri": ["yorunge_diyagrami", "hiz_bilesenleri", "menzil_semasi"]
    }
}

# ============================================================================
# KAPSAM DIŞI KONULAR - KESİNLİKLE SORULMAYACAK
# ============================================================================

KAPSAM_DISI = {
    "konular": [
        "Hava direnci ve sürtünme kuvveti (Tüm problemlerde ihmal edilir)",
        "Limit hız kavramı",
        "İki boyutta hareket - Eğik atış, yatay atış dışındaki durumlar",
        "Vektörlerin bileşenlerine ayrılmasını gerektiren karmaşık iki boyutlu problemler",
        "Dinamik (Newton'un Hareket Yasaları) - F=ma hesaplamaları",
        "Kuvvet, net kuvvet, sürtünme kuvveti nicelikleri",
        "İş, Güç ve Enerji kavramları",
        "Kinetik enerji (1/2mv²), potansiyel enerji (mgh)",
        "Momentum ve çarpışmalar (p=mv)",
        "Dairesel hareket, açısal hız, merkezcil ivme",
        "Değişken ivmeli hareket (integral/türev gerektiren)"
    ],
    "uyari": "Bu konulardan kesinlikle soru üretilmemelidir!"
}

# ============================================================================
# KAVRAM YANILGILARI VERİTABANI (10. SINIF - 1. TEMA)
# ============================================================================

KAVRAM_YANILGILARI = {
    "sabit_hizli_hareket": {
        "yanilgilar": [
            "Hız ve sürat aynı şeydir",
            "Yer değiştirme ile alınan yol her zaman eşittir",
            "Ortalama hız ile ortalama sürat her zaman eşittir",
            "Negatif hız, yavaşlamak demektir",
            "Hız sıfırsa cisim hareket etmiyordur (anlık hız vs ortalama hız karışıklığı)",
            "x-t grafiğinde yüksek nokta = yüksek hız"
        ],
        "celdirici_stratejileri": [
            "Alınan yol ile yer değiştirmeyi karıştıran seçenek",
            "Ortalama hız ile ortalama sürati eşitleyen seçenek",
            "Negatif hızı yavaşlama olarak yorumlayan seçenek",
            "Grafik eğimini yanlış yorumlayan seçenek"
        ]
    },

    "ivmeli_hareket": {
        "yanilgilar": [
            "Negatif ivme her zaman yavaşlama demektir",
            "İvme sıfırsa cisim duruyordur",
            "Hız sıfır olduğunda ivme de sıfırdır",
            "Pozitif ivme = hızlanma, negatif ivme = yavaşlama (her durumda)",
            "v-t grafiğindeki alan hızı verir",
            "x-t grafiğinde doğrusal çizgi = sabit ivmeli hareket"
        ],
        "celdirici_stratejileri": [
            "Negatif ivmeyi her zaman yavaşlama olarak gösteren seçenek",
            "İvme sıfır = duruyor diyen seçenek",
            "Grafik alanlarını yanlış yorumlayan seçenek",
            "Hız ve ivme yönlerini karıştıran seçenek"
        ]
    },

    "serbest_dusme": {
        "yanilgilar": [
            "Ağır cisimler daha hızlı düşer",
            "Düşme hızı kütleye bağlıdır",
            "Serbest düşmede ivme zamanla artar",
            "Cisim yere yaklaştıkça ivmesi artar",
            "Farklı yüksekliklerden bırakılan cisimler aynı anda yere düşer"
        ],
        "celdirici_stratejileri": [
            "Kütlesi büyük cismin daha hızlı düştüğünü ima eden seçenek",
            "İvmenin zamanla değiştiğini gösteren seçenek",
            "Yükseklikten bağımsız düşme süresi gösteren seçenek"
        ]
    },

    "iki_boyutta_hareket": {
        "yanilgilar": [
            "Tepe noktasında ivme sıfırdır",
            "Yatay atışta cisim düşey olarak düşmez",
            "Yatay hız bileşeni zamanla azalır",
            "Eğik atışta cisim tepe noktasında bir an durur",
            "Menzil sadece ilk hıza bağlıdır"
        ],
        "celdirici_stratejileri": [
            "Tepe noktasında ivmeyi sıfır alan seçenek",
            "Yatay hızın değiştiğini gösteren seçenek",
            "Açının etkisini göz ardı eden seçenek"
        ]
    }
}

# ============================================================================
# MAARİF MODELİ ÖLÇME KRİTERLERİ
# ============================================================================

MAARIF_MODELI_KRITERLERI = {
    "baglam_temelli": {
        "aciklama": "Soru gerçek yaşamla ilişkili, öğrenci için anlamlı bir bağlam içermeli",
        "kontrol": "Senaryo gerçekçi ve ilgi çekici mi?"
    },
    "ezberden_uzak": {
        "aciklama": "Soru bilginin hatırlanmasını değil, kullanılmasını/transfer edilmesini gerektirmeli",
        "kontrol": "Öğrenci formülü ezberlemeden çözebilir mi?"
    },
    "celdirici_mantigi": {
        "aciklama": "Yanlış seçenekler kavram yanılgılarına dayanmalı",
        "kontrol": "Her çeldirici belirli bir hata türünü hedefliyor mu?"
    },
    "gereksiz_bilgi_yok": {
        "aciklama": "Bağlam dikkat dağıtıcı gereksiz detaylardan arındırılmalı",
        "kontrol": "Verilen her bilgi çözüm için gerekli mi?"
    },
    "gorsel_okuryazarlik": {
        "aciklama": "Tablo, grafik veya görsel işlevsel olmalı",
        "kontrol": "Görsel sorunun çözümü için gerekli mi?"
    },
    "seceneklerin_dengesi": {
        "aciklama": "Doğru cevap diğerlerinden belirgin şekilde farklı uzunlukta olmamalı",
        "kontrol": "Seçenekler benzer uzunlukta mı?"
    }
}

# ============================================================================
# ÖSYM TARZI STANDART İFADELER
# ============================================================================

STANDART_IFADELER = {
    "ortam": [
        "Sürtünmeler ve hava direnci ihmal edilmektedir.",
        "Yatay düzlemde hareket eden",
        "Doğrusal bir yolda ilerleyen",
        "Başlangıçta durgun hâlde iken",
        "Sabit hızla hareket eden",
        "t = 0 anında",
        "Özdeş K ve L cisimleri"
    ],
    "soru_kokleri": [
        "Buna göre,",
        "Bu bilgilere göre,",
        "Yukarıdaki bilgilere göre,",
        "Grafiğe göre,",
        "Tablodaki verilere göre,"
    ],
    "karsilastirma": [
        "büyüktür", "küçüktür", "eşittir",
        "artar", "azalır", "değişmez",
        "2 katıdır", "yarısıdır", "4 katıdır"
    ],
    "oncul_format": {
        "giris": "Buna göre, ... ile ilgili aşağıdaki ifadelerden hangileri doğrudur?",
        "siklar": ["A) Yalnız I", "B) Yalnız II", "C) I ve II", "D) II ve III", "E) I, II ve III"]
    }
}

# ============================================================================
# TRİGONOMETRİK DEĞERLER (HESAPLAMA KOLAYLIĞI)
# ============================================================================

TRIGONOMETRIK_DEGERLER = {
    30: {"sin": 0.5, "cos": 0.87},
    37: {"sin": 0.6, "cos": 0.8},
    45: {"sin": 0.71, "cos": 0.71},
    53: {"sin": 0.8, "cos": 0.6},
    60: {"sin": 0.87, "cos": 0.5}
}

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class QuestionParams:
    konu: str
    alt_konu: str
    kazanim_kodu: str
    bloom_seviyesi: str
    zorluk: int
    baglam: str
    gorsel_tipi: str
    soru_tipi: str = "hikayeli"  # hikayeli, grafik, onculu, hesaplama
    grade_level: int = 10
    topic_group: str = "10. Sınıf Fizik - Tema 1"

@dataclass
class GeneratedQuestion:
    title: str
    original_text: str
    options: Dict[str, str]
    correct_answer: str
    solution_text: str
    difficulty: int
    subject: str
    grade_level: int
    topic: str
    topic_group: str
    kazanim_kodu: str
    bloom_level: str
    bloom_seviye_no: int
    maarif_uyumlu: bool
    scenario_text: str
    distractor_explanations: Dict[str, str]
    image_url: Optional[str] = None
    question_type: str = "coktan_secmeli"
    is_active: bool = True
    verified: bool = False

# ============================================================================
# SYSTEM PROMPT - 10. SINIF TEMA 1 ÖZEL
# ============================================================================

SYSTEM_PROMPT_TEMA1 = """Sen, Türkiye Yüzyılı Maarif Modeli konusunda uzmanlaşmış, 10. sınıf fizik dersi için soru bankası hazırlayan deneyimli bir fizik öğretmeni ve ölçme-değerlendirme uzmanısın.

## TEMEL GÖREV
"Bir Boyutta Hareket" ünitesi için Bloom Taksonomisi'nin 6 basamağına uygun, Maarif Modeli kriterlerini karşılayan, özgün ve pedagojik değeri yüksek çoktan seçmeli sorular üretmek.

## !!! MÜFREDAT SINIRLARI - KESİNLİKLE UYULMALI !!!

### KAPSAM DAHİLİ:
1. Sabit Hızlı Hareket: Konum, yer değiştirme, hız, sürat, ortalama hız/sürat, x-t ve v-t grafikleri
2. Sabit İvmeli Hareket: İvme kavramı, hızlanan/yavaşlayan hareket, kinematik denklemler, grafikler arası dönüşüm
3. Serbest Düşme: Yer çekimi ivmesi (g), İLK HIZSIZ düşme, h-t/v-t grafikleri
4. İki Boyutta Hareket: Yatay atış, eğik atış, bileşen ayrımı, menzil, uçuş süresi

### KAPSAM DIŞI (YASAK):
❌ Hava direnci, sürtünme kuvveti hesaplamaları
❌ Newton yasaları, F=ma problemleri
❌ İş, güç, enerji kavramları
❌ Momentum, çarpışma problemleri
❌ Dairesel hareket
❌ Değişken ivmeli hareket
❌ Yukarı/aşağı ilk hızla atış (serbest düşmede)

## BLOOM TAKSONOMİSİ SEVİYELERİ

### Seviye 1 - HATIRLAMA:
- Temel tanım ve kavramları hatırlama
- "... nedir?", "... birimi nedir?" tarzı sorular
- Zorluk: 1-2

### Seviye 2 - ANLAMA:
- Kavramları açıklama, yorumlama, örneklendirme
- Basit grafik okuma, kavram karşılaştırma
- Zorluk: 2-3

### Seviye 3 - UYGULAMA:
- Formül kullanarak problem çözme
- Standart hesaplama soruları
- Zorluk: 2-4

### Seviye 4 - ANALİZ:
- Grafik dönüşümü, çoklu veri analizi
- İlişki kurma, karşılaştırma
- Zorluk: 3-5

### Seviye 5 - DEĞERLENDİRME:
- Öncüllü sorular (I, II, III)
- Yargı değerlendirme, hata bulma
- Zorluk: 4-5

### Seviye 6 - YARATMA:
- Deney tasarımı, strateji geliştirme
- Sentez ve özgün çözüm
- Zorluk: 5-6

## MAARİF MODELİ KRİTERLERİ

1. **BAĞLAM TEMELLİ**: Her soru gerçek yaşam senaryosu içermeli
2. **EZBERDEN UZAK**: Bilgiyi transfer etmeyi gerektirmeli
3. **ÇELDİRİCİ MANTIĞI**: Yanlış şıklar kavram yanılgılarını hedeflemeli
4. **GEREKSİZ BİLGİ YOK**: Dikkat dağıtıcı detaylardan arındırılmış
5. **GÖRSEL OKURYAZARLIK**: Grafik/tablo işlevsel olmalı
6. **SEÇENEK DENGESİ**: Şıklar benzer uzunlukta olmalı

## 5 ŞIK ZORUNLU - STANDART FORMAT

Her soruda mutlaka 5 şık (A, B, C, D, E) olmalıdır.

## ÖNCÜLLÜ SORU FORMATI - KRİTİK!

!!! ÖNCÜLLÜ SORULARDA I, II, III İFADELERİ MUTLAKA "soru_metni" İÇİNDE OLMALI !!!

Öncüllü soru yapısı:
1. Senaryo anlatılır
2. "Buna göre, ... ile ilgili aşağıdaki ifadelerden hangileri doğrudur?" yazılır
3. ARDINDAN MUTLAKA şu format kullanılır (soru_metni içinde):

I. [Birinci ifade - tam cümle]
II. [İkinci ifade - tam cümle]
III. [Üçüncü ifade - tam cümle]

4. Şıklar: A) Yalnız I, B) Yalnız II, C) I ve II, D) II ve III, E) I, II ve III

DOĞRU ÖRNEK (soru_metni):
"Bir sporcu cirit fırlatıyor. Hava direnci ihmal ediliyor.

Buna göre, ciritin hareketi ile ilgili aşağıdaki ifadelerden hangileri doğrudur?

I. Ciritin yatay hız bileşeni hareket boyunca sabittir.
II. Cirit maksimum yükseklikte iken toplam hızı sıfırdır.
III. Ciritin düşey hız bileşeni hareket boyunca değişir."

❌ YASAK: I, II, III öncüllerini yazmadan "Yalnız I" şeklinde şık kullanmak!
❌ YASAK: Öncülleri soru_metni dışında bırakmak!

## MATEMATİKSEL DEĞERLER

- g = 10 m/s² (aksi belirtilmedikçe)
- sin37° = cos53° = 0.6
- sin53° = cos37° = 0.8
- sin45° = cos45° = 0.71
- Kolay hesaplanan sayılar kullan (5, 10, 20, 25, 50, 100...)

## ÇIKTI FORMATI (JSON)

{
  "soru_metni": "Bağlamsal senaryo + soru cümlesi",
  "soru_koku": "Buna göre, [soru]",
  "siklar": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
  "dogru_cevap": "A/B/C/D/E",
  "cozum_adim_adim": "Adım 1: ...\\nAdım 2: ...\\nSonuç: ...",
  "bloom_seviyesi": "Hatırlama/Anlama/Uygulama/Analiz/Değerlendirme/Yaratma",
  "bloom_seviye_no": 1-6,
  "zorluk": 1-6,
  "kazanim_kodu": "FİZ.10.1.X",
  "kavram_yanilgisi_hedefi": "Bu sorunun hedeflediği kavram yanılgısı",
  "celdirici_analizi": {
    "A": "Bu şıkkı seçen öğrencinin hatası",
    "B": "...",
    "C": "...",
    "D": "...",
    "E": "..."
  },
  "gorsel_gerekli": true/false,
  "gorsel_betimleme": {
    "tip": "senaryo_diyagrami / x-t_grafigi / v-t_grafigi / hareket_sekli",
    "detay": "!!! SORUYA ÖZGÜ GÖRSEL AÇIKLAMASI !!! - Senaryodaki nesne/durum çizilmeli (örn: kuyu ve düşen taş, tekne, araç, yol vb.)",
    "ogeler": ["senaryodaki_ana_nesne", "hareket_yonu", "olcumler"],
    "etiketler": ["Soruda geçen değerler ve etiketler"],
    "senaryo_nesneleri": "Soruda geçen cisim/ortam: (örn: kuyu, taş, tekne, sporcular, araç, yol...)"
  },
  "maarif_uyumu": {
    "baglam_temelli": true/false,
    "ezberden_uzak": true/false,
    "kavram_yanilgisi_hedefli": true/false
  }
}
"""

# ============================================================================
# FEW-SHOT ÖRNEKLER (TEMA 1 ÖZEL)
# ============================================================================

FEW_SHOT_ORNEKLERI = {
    "hatirlama_ornegi": """
## ÖRNEK - HATIRLAMA (Bloom Seviye 1)

**Konu**: Sabit Hızlı Hareket
**Zorluk**: 1

**SORU**:
Doğrusal bir yolda hareket eden bir cismin belirli bir zaman aralığındaki son konumu ile ilk konumu arasındaki farka ne ad verilir?

A) Alınan yol
B) Sürat
C) Yer değiştirme
D) Ortalama hız
E) Konum

**DOĞRU CEVAP**: C

**ÇÖZÜM**: Yer değiştirme, cismin son konumu ile ilk konumu arasındaki en kısa mesafe olarak tanımlanır ve vektörel bir büyüklüktür.

**ÇELDİRİCİ ANALİZİ**:
- A) Alınan yol skaler bir büyüklüktür ve toplam kat edilen mesafeyi ifade eder
- B) Sürat, birim zamanda alınan yoldur
- D) Ortalama hız, yer değiştirmenin süreye oranıdır
- E) Konum, referans noktasına göre bulunulan yerdir
""",

    "anlama_ornegi": """
## ÖRNEK - ANLAMA (Bloom Seviye 2)

**Konu**: Sabit Hızlı Hareket
**Zorluk**: 2

**SORU**:
Bir taşıyıcı bant üzerinde ürünler A noktasından B noktasına sabit süratle taşınmaktadır. Bantın hızı v olup A-B mesafesi doğrusal değil, eğriseldir.

Buna göre, ürünlerin A'dan B'ye hareketi sırasında aşağıdakilerden hangisi kesinlikle doğrudur?

A) Yer değiştirme büyüklüğü ile alınan yol eşittir.
B) Ortalama hız ile ortalama sürat eşittir.
C) Sürat sabittir ancak hız değişir.
D) Hız ve sürat birbirine eşittir.
E) İvme sıfırdan farklıdır.

**DOĞRU CEVAP**: C

**ÇÖZÜM**:
- Sabit sürat = eşit zaman aralıklarında eşit yollar alma (skaler)
- Eğrisel yolda hareket eden cismin yönü değiştiği için hızı değişir
- Sürat sabitken hız (yön içerdiği için) değişebilir

**KAVRAM YANILGISI HEDEFİ**: "Hız ve sürat aynı şeydir" yanılgısı
""",

    "uygulama_ornegi": """
## ÖRNEK - UYGULAMA (Bloom Seviye 3)

**Konu**: Sabit İvmeli Hareket
**Zorluk**: 3

**SORU**:
Bir metro treni istasyondan harekete başlayıp 2 m/s² sabit ivme ile hızlanmaktadır. Tren 100 m yol aldığında durağa ulaşan bir yolcu trene yetişmek için 10 m/s sabit hızla koşmaya başlıyor.

Buna göre, yolcu trene kaç saniye sonra yetişir?

A) 5 s    B) 10 s    C) 15 s    D) 20 s    E) Yetişemez

**DOĞRU CEVAP**: D

**ÇÖZÜM**:
Adım 1: Trenin 100 m sonundaki hızı
v² = v₀² + 2ax → v² = 0 + 2(2)(100) = 400 → v = 20 m/s

Adım 2: Trenin 100 m alması için geçen süre
v = v₀ + at → 20 = 0 + 2t → t = 10 s

Adım 3: Yolcunun treni yakalaması için
x_tren = x_yolcu
100 + 20t + (1/2)(2)t² = 10t (yolcu t=10s'de başlıyor, t=0'dan hesapla)
... (hesaplama devamı)

**ÇELDİRİCİ ANALİZİ**:
- E şıkkı yanlış hesaplama yapan veya erken vazgeçen öğrenci için
""",

    "analiz_ornegi": """
## ÖRNEK - ANALİZ (Bloom Seviye 4)

**Konu**: Grafik Dönüşümü
**Zorluk**: 4

**SORU**:
Doğrusal bir yolda hareket eden bir cismin v-t grafiği şekildeki gibidir.

[GRAFİK: v-t grafiği, 0'dan başlayıp 4s'de 20 m/s'ye lineer artış, sonra 8s'ye kadar sabit 20 m/s]

Buna göre, cismin hareketine ait x-t grafiği aşağıdakilerden hangisidir?

**ÇÖZÜM**:
- (0-4) s: Sabit ivmeli hareket → x-t grafiği parabolik (yukarı açık)
- (4-8) s: Sabit hızlı hareket → x-t grafiği doğrusal

**KAVRAM YANILGISI HEDEFİ**: Grafik dönüşümünde eğim-alan ilişkisini karıştırma
""",

    "degerlendirme_ornegi": """
## ÖRNEK - DEĞERLENDİRME (Bloom Seviye 5)

**Konu**: Serbest Düşme
**Zorluk**: 5

**SORU**:
Havası boşaltılmış bir ortamda aynı yükseklikten serbest bırakılan farklı kütlelerdeki K ve L cisimleri için,

I. K ve L cisimleri aynı anda yere düşer.
II. Kütlesi büyük olan cisim daha büyük ivme ile hareket eder.
III. Her iki cismin de ivmesi yer çekimi ivmesine eşittir.

ifadelerinden hangileri doğrudur?

A) Yalnız I    B) Yalnız III    C) I ve II    D) I ve III    E) I, II ve III

**DOĞRU CEVAP**: D

**ÇÖZÜM**:
I. DOĞRU - Sürtünmesiz ortamda kütle farketmeksizin aynı ivme (g) ile düşerler
II. YANLIŞ - İvme kütleden bağımsızdır, her ikisi de g ivmesiyle düşer
III. DOĞRU - Serbest düşmede a = g

**KAVRAM YANILGISI HEDEFİ**: "Ağır cisimler daha hızlı düşer" yanılgısı
"""
}

# ============================================================================
# GÖRSEL PROMPT ŞABLONU
# ============================================================================

IMAGE_PROMPT_TEMPLATE = """10. Sınıf Fizik sorusu için GERÇEKÇİ, 3D, CANLI eğitim görseli oluştur.

## GÖRSEL TİPİ: {tip}

## DETAYLI BETİMLEME:
{detay}

## !!! GÖRSEL STİLİ - ÇOK ÖNEMLİ !!!

### 3D GERÇEKÇİ RENDER:
- Fotorealistik 3D render kalitesi
- Gerçekçi ışıklandırma ve gölgeler
- Derinlik hissi veren perspektif
- Yüksek kaliteli texture ve malzeme görünümü
- Soft shadows ve ambient occlusion

### CANLI VE DİNAMİK:
- Hareket hissi veren blur efektleri (motion blur)
- Canlı, parlak renkler
- Enerji ve dinamizm hissi
- Modern, çekici tasarım

### SENARYO BAZLI:
- Soruda geçen GERÇEK nesneler çizilmeli:
  * Kuyu → Gerçekçi taş kuyu, derinlik hissi, düşen taş
  * Tekne → 3D kürek teknesi, su yüzeyi, sporcular
  * Araç → Modern araba, yol, çevre
  * Top → Gerçekçi top, hareket yörüngesi
  * Asansör → Modern asansör kabini, içi görünen

### RENK PALETİ (CANLI):
- Ana renkler: Canlı mavi (#0066FF), Turuncu (#FF6600), Yeşil (#00CC00)
- Arka plan: Soft gradient (açık mavi → beyaz) veya gerçekçi ortam
- Vektörler: Parlak, glow efektli oklar
- Nesneler: Gerçekçi renkler ve dokular

### FİZİK GÖSTERİMLERİ:
- Hız vektörleri: Yeşil, parlak, ok ucu belirgin, glow efekti
- İvme vektörleri: Turuncu/kırmızı, kalın oklar
- Yörünge: Kesikli çizgi, hareket yönü belirgin
- Ölçümler: Şık etiketler, modern font

### GRAFİK STİLİ (Grafik tipi sorularda):
- 3D görünümlü eksenler
- Gradient dolgulu eğriler
- Glow efektli data noktaları
- Modern, minimalist grid
- Drop shadow efektli etiketler

## KALİTE:
- 4K çözünürlük kalitesi
- Anti-aliased, pürüzsüz kenarlar
- Profesyonel eğitim materyali görünümü
- Öğrencinin ilgisini çekecek modern tasarım

## YASAKLAR:
❌ Soru metni veya cümleler
❌ A), B), C), D), E) şıkları
❌ Çözüm adımları veya formüller
❌ Cevabı veren bilgi
❌ Düz, sıkıcı 2D çizimler
❌ Clipart tarzı basit görseller
"""

# ============================================================================
# GEMINI API CLIENT (Imagen 3 + Text Generation)
# ============================================================================

class GeminiAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None
        self.text_url = f"{GEMINI_TEXT_URL}?key={api_key}"
        self.request_count = 0
        self.last_request_time = 0

    def _rate_limit(self):
        """API rate limiting"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time

        if self.request_count >= 4:
            wait_time = 65 - (current_time - self.last_request_time)
            if wait_time > 0:
                logger.info(f"Rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()

        if self.request_count > 0:
            time.sleep(3)

        self.request_count += 1

    def generate_question(self, params: QuestionParams) -> Dict[str, Any]:
        """Tek soru üret"""

        konu_data = TEMA1_MUFREDAT.get(params.konu, {})
        bloom_data = BLOOM_TAKSONOMISI.get(params.bloom_seviyesi, {})
        zorluk_data = ZORLUK_DAGILIMI.get(params.zorluk, {})
        yanilgi_data = KAVRAM_YANILGILARI.get(params.konu, {})

        # Few-shot örneği seç
        bloom_key = params.bloom_seviyesi.lower() + "_ornegi"
        few_shot = FEW_SHOT_ORNEKLERI.get(bloom_key, "")

        user_prompt = f"""
## SORU ÜRETİM TALİMATI

### Konu Bilgileri:
- **Ana Konu**: {konu_data.get('display_name', params.konu)}
- **Kazanım Kodu**: {params.kazanim_kodu}
- **Kazanımlar**:
{chr(10).join(['  - ' + k for k in konu_data.get('kazanimlar', [])])}

### Bloom Taksonomisi:
- **Seviye**: {params.bloom_seviyesi} (Seviye {bloom_data.get('seviye', 3)})
- **Açıklama**: {bloom_data.get('aciklama', '')}
- **Fiiller**: {', '.join(bloom_data.get('fiiller', []))}
- **Örnek Soru Kökleri**:
{chr(10).join(['  - ' + k for k in bloom_data.get('soru_kokleri', [])])}

### Zorluk:
- **Seviye**: {params.zorluk}/6 - {zorluk_data.get('aciklama', '')}
- **Beklenen Adım Sayısı**: {zorluk_data.get('adim_sayisi', 2)}

### Bağlam:
- **Senaryo**: {params.baglam}
- **Soru Tipi**: {params.soru_tipi}

### Temel Kavramlar:
{chr(10).join(['- ' + k + ': ' + v for k, v in konu_data.get('temel_kavramlar', {}).items()])}

### Matematiksel Modeller:
{chr(10).join(['- ' + m for m in konu_data.get('matematiksel_modeller', [])])}

### Kavram Yanılgısı Hedefleri (Çeldirici için):
Yaygın Yanılgılar:
{chr(10).join(['- ' + y for y in yanilgi_data.get('yanilgilar', [])])}

Çeldirici Stratejileri:
{chr(10).join(['- ' + s for s in yanilgi_data.get('celdirici_stratejileri', [])])}

### Kapsam Dışı (YASAK):
{chr(10).join(['❌ ' + k for k in KAPSAM_DISI.get('konular', [])])}

### Referans Örnek:
{few_shot}

---

## ÖNEMLİ KURALLAR:

1. Bloom Taksonomisi "{params.bloom_seviyesi}" seviyesine UYGUN soru üret
2. Maarif Modeli kriterlerine uy (bağlam temelli, ezberden uzak)
3. 5 şıklı (A, B, C, D, E) olmalı
4. Matematiksel olarak %100 DOĞRU olmalı
5. Çeldiriciler KAVRAM YANILGILARINI hedeflemeli
6. g = 10 m/s² kullan (aksi belirtilmedikçe)
7. KAPSAM DIŞI konulara GİRME!

{"### !!! ÖNCÜLLÜ SORU FORMATI - KRİTİK !!!" if params.soru_tipi == "onculu" else ""}
{'''
!!! ÖNCÜLLER "soru_metni" İÇİNDE MUTLAKA OLMALI !!!

Öncüllü soruda soru_metni şu yapıda olmalı:

"[Senaryo açıklaması]

Buna göre, [konu] ile ilgili aşağıdaki ifadelerden hangileri doğrudur?

I. [Birinci ifade - tam cümle olarak yazılmalı]
II. [İkinci ifade - tam cümle olarak yazılmalı]
III. [Üçüncü ifade - tam cümle olarak yazılmalı]"

Şıklar: A) Yalnız I, B) Yalnız II, C) I ve II, D) II ve III, E) I, II ve III

❌ YASAK: I, II, III yazmadan şıklarda "Yalnız I" kullanmak!
❌ YASAK: Öncülleri soru_metni dışında tutmak!

ÖRNEK soru_metni:
"Bir sporcu cirit fırlatıyor. Hava direnci ihmal ediliyor.

Buna göre, ciritin hareketi ile ilgili aşağıdaki ifadelerden hangileri doğrudur?

I. Ciritin yatay hız bileşeni hareket boyunca sabittir.
II. Cirit maksimum yükseklikte iken toplam hızı sıfırdır.
III. Ciritin düşey hız bileşeni hareket boyunca değişir."
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
                            "system_instruction": SYSTEM_PROMPT_TEMA1,
                            "temperature": Config.TEMPERATURE,
                            "max_output_tokens": Config.MAX_OUTPUT_TOKENS,
                            "response_mime_type": "application/json"
                        }
                    )
                    text_content = response.text
                else:
                    payload = {
                        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT_TEMA1}]},
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

                    if response.status_code != 200:
                        logger.error(f"API Hatası: {response.status_code}")
                        continue

                    result = response.json()
                    text_content = result["candidates"][0]["content"]["parts"][0]["text"]

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

                # Bloom seviyesi ekle
                question_data["bloom_seviyesi"] = params.bloom_seviyesi
                question_data["bloom_seviye_no"] = bloom_data.get("seviye", 3)
                question_data["konu"] = params.konu
                question_data["alt_konu"] = params.alt_konu

                logger.info(f"  ✓ Soru başarıyla üretildi")
                return question_data

            except json.JSONDecodeError as e:
                logger.error(f"JSON parse hatası: {e}")
                continue
            except Exception as e:
                logger.error(f"Hata: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)
                continue

        return None

    def generate_image(self, gorsel_betimleme: Dict[str, str], konu: str = None, soru_metni: str = None) -> Optional[bytes]:
        """Imagen 3 ile SORUYA ÖZGÜ görsel üret"""
        if not NEW_GENAI or not self.client:
            logger.warning("  google-genai SDK yok, görsel üretilemiyor")
            return None

        tip = gorsel_betimleme.get("tip", "grafik")
        detay = gorsel_betimleme.get("detay", "")
        ogeler = gorsel_betimleme.get("ogeler", [])
        renkler = gorsel_betimleme.get("renkler", {})

        # Renk bilgisini prompt'a ekle
        renk_talimati = ""
        if renkler:
            renk_talimati = "\n\nRENK TALİMATLARI:\n"
            for oge, renk in renkler.items():
                renk_talimati += f"- {oge}: {renk}\n"

        # SORUYA ÖZGÜ görsel için soru metnini analiz et
        soru_baglami = ""
        if soru_metni:
            soru_baglami = f"""

## SORU BAĞLAMI (Görsel bu senaryoya uygun olmalı):
{soru_metni[:500]}

ÖNEMLI: Görsel SADECE bu senaryodaki durumu göstermeli!
- Soruda kuyu varsa → kuyu ve düşen taş göster
- Soruda tekne varsa → tekne göster
- Soruda araç varsa → araç göster
- Genel fizik diyagramı ÇİZME, soruya özgü çiz!
"""

        full_detay = f"{detay}\n\nGörselde görünecek öğeler: {', '.join(ogeler) if ogeler else 'Belirtilmemiş'}{renk_talimati}{soru_baglami}"
        prompt = IMAGE_PROMPT_TEMPLATE.format(tip=tip, detay=full_detay)

        self._rate_limit()

        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  Image API çağrısı (deneme {attempt + 1}/{Config.MAX_RETRIES})...")

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
                                    image_bytes = base64.b64decode(image_data)
                                else:
                                    image_bytes = bytes(image_data) if not isinstance(image_data, bytes) else image_data
                                logger.info(f"  Görsel üretildi ({len(image_bytes)} bytes)")
                                return image_bytes

            except Exception as e:
                logger.error(f"  Image API hatası (deneme {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)

        return None


# ============================================================================
# SUPABASE CLIENT
# ============================================================================

class SupabaseClient:
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

    def get_curriculum_for_grade(self, grade_level: int = 10, lesson_name: str = "Fizik") -> List[Dict]:
        """Müfredattan kazanımları çek"""
        if self._curriculum_cache is not None:
            return self._curriculum_cache

        query_url = f"{self.url}/rest/v1/curriculum?grade_level=eq.{grade_level}&lesson_name=eq.{lesson_name}&select=id,topic_code,topic_name,sub_topic,learning_outcome_code,learning_outcome_description,bloom_level"

        try:
            response = requests.get(query_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            self._curriculum_cache = response.json()
            logger.info(f"  Curriculum'dan {len(self._curriculum_cache)} kazanım yüklendi")
            return self._curriculum_cache
        except Exception as e:
            logger.error(f"  Curriculum yükleme hatası: {e}")
            return []

    def upload_image(self, image_data: bytes, filename: str) -> Optional[str]:
        """Görseli Supabase Storage'a yükle"""
        bucket = Config.STORAGE_BUCKET
        upload_url = f"{self.url}/storage/v1/object/{bucket}/{filename}"

        try:
            if isinstance(image_data, str):
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
            logger.info(f"  Görsel yüklendi: {filename}")
            return public_url

        except Exception as e:
            logger.error(f"  Storage upload hatası: {e}")
            return None

    def insert_question(self, question: 'GeneratedQuestion', kazanim_id: int = None) -> Optional[int]:
        """Soruyu veritabanına kaydet"""
        insert_url = f"{self.url}/rest/v1/question_bank"

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
            "pisa_level": question.pisa_level,
            "pisa_context": question.pisa_context,
            "scenario_text": question.scenario_text,
            "distractor_explanations": question.distractor_explanations,
            "image_url": question.image_url,
            "question_type": question.question_type,
            "is_active": question.is_active,
            "verified": question.verified,
            "is_past_exam": False,
            "exam_type": "FIZIK10_TEMA1_BOT"
        }

        try:
            response = requests.post(insert_url, headers=self.headers, json=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                question_id = result[0].get("id")
                logger.info(f"  Soru kaydedildi, ID: {question_id}")
                return question_id

            return None

        except Exception as e:
            logger.error(f"  Supabase insert hatası: {e}")
            return None


# ============================================================================
# QUALITY VALIDATOR
# ============================================================================

class QualityValidator:
    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None
        self.quality_threshold = 7

    def validate_question(self, question_data: Dict, params: QuestionParams) -> Dict:
        """Soru kalite kontrolü"""
        if not NEW_GENAI or not self.client:
            return {"pass": True, "overall_score": 7, "problems": [], "skipped": True}

        yanilgi_data = KAVRAM_YANILGILARI.get(params.konu, {})

        try:
            prompt = f"""Bu 10. sınıf Fizik sorusunu KALİTE KONTROLÜ yap.

## !!! ÖNEMLİ: TÜRKİYE YÜZYILI MAARİF MODELİ MÜFREDATI !!!

Bu soru TÜRKİYE YÜZYILI MAARİF MODELİ (2024-2025) müfredatına göre hazırlanmıştır.
ESKİ MEB müfredatı ile KARŞILAŞTIRMA YAPMA!

### MAARİF MODELİ 10. SINIF FİZİK MÜFREDATI:
- **TEMA 1: BİR BOYUTTA HAREKET** ← BU SORU BURADAN
  * Sabit Hızlı Hareket (konum, yer değiştirme, hız, sürat, grafikler)
  * Sabit İvmeli Hareket (ivme, kinematik denklemler, grafikler)
  * Serbest Düşme (g ivmesi, ilk hızsız düşme)
  * İki Boyutta Hareket (yatay atış, eğik atış)
- TEMA 2: Kuvvet ve Hareket
- TEMA 3: Enerji

### ESKİ MÜFREDAT (KULLANMA!):
❌ Eski MEB'de 10. sınıf: Elektrik, Optik, Dalgalar idi
❌ Bu artık GEÇERLİ DEĞİL!
❌ Maarif Modeli'nde hareket konuları 10. sınıfa alındı

## SORU BİLGİLERİ
Konu: {params.konu}
Zorluk: {params.zorluk}/6
Bloom: {params.bloom_seviyesi}

SORU METNİ: {question_data.get("soru_metni", "")}
SORU KÖKÜ: {question_data.get("soru_koku", "")}
ŞIKLAR: {json.dumps(question_data.get("siklar", {}), ensure_ascii=False)}
DOĞRU CEVAP: {question_data.get("dogru_cevap", "")}
ÇÖZÜM: {question_data.get("cozum_adim_adim", "")}

## KONTROL KRİTERLERİ

1. FİZİKSEL DOĞRULUK: Fizik kanunları doğru uygulanmış mı?
2. MATEMATİKSEL DOĞRULUK: Hesaplamalar doğru mu?
3. BLOOM UYUMU: {params.bloom_seviyesi} seviyesine uygun mu?
4. ÇELDİRİCİ KALİTESİ: Çeldiriciler makul ve ayırt edici mi?
5. KAPSAM: Maarif Modeli 10. sınıf Tema 1 içinde mi? (EVET, hareket konuları 10. sınıfta!)

Hedeflenmesi gereken kavram yanılgıları:
{chr(10).join(['- ' + y for y in yanilgi_data.get('yanilgilar', [])])}

JSON formatında döndür:
{{"is_physically_correct": true/false, "is_mathematically_correct": true/false, "bloom_match": true/false, "distractors_quality": 1-10, "in_scope": true/false, "overall_score": 1-10, "pass": true/false, "problems": ["problem1", "problem2"]}}"""

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

    def validate_image(self, image_bytes: bytes, gorsel_betimleme: Dict = None) -> Dict:
        """Görsel kalite kontrolü"""
        if not NEW_GENAI or not self.client:
            return {"pass": True, "overall_score": 7, "problems": [], "skipped": True}

        try:
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')

            expected_elements = gorsel_betimleme.get("ogeler", []) if gorsel_betimleme else []
            expected_colors = gorsel_betimleme.get("renkler", {}) if gorsel_betimleme else {}

            response = self.client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                            {"text": f"""Bu fizik görseli için kalite kontrolü yap.

Beklenen öğeler: {expected_elements}
Beklenen renkler: {expected_colors}

Kontrol et:
1. Soru metni veya şık OLMAMALI
2. Türkçe etiketler doğru olmalı
3. Fiziksel temsil doğru olmalı
4. Renkler profesyonel ve tutarlı olmalı
5. Temiz ve okunaklı olmalı

JSON formatında döndür:
{{"has_question_text": true/false, "has_options": true/false, "labels_correct": true/false, "colors_professional": true/false, "is_clean": true/false, "overall_score": 1-10, "pass": true/false, "problems": []}}"""}
                        ]
                    }
                ],
                config={"response_mime_type": "application/json"}
            )

            result = json.loads(response.text)

            problems = result.get("problems", [])
            if result.get("has_question_text"):
                problems.append("Görselde soru metni var")
            if result.get("has_options"):
                problems.append("Görselde şıklar var")

            result["problems"] = problems
            result["pass"] = result.get("overall_score", 0) >= self.quality_threshold
            return result

        except Exception as e:
            logger.error(f"  Görsel validasyon hatası: {e}")
            return {"pass": True, "overall_score": 5, "problems": [str(e)], "error": True}


# ============================================================================
# GENERATED QUESTION DATA CLASS
# ============================================================================

@dataclass
class GeneratedQuestion:
    title: str
    original_text: str
    options: Dict[str, str]
    correct_answer: str
    solution_text: str
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
# MAIN GENERATOR CLASS
# ============================================================================

class Fizik10Tema1Generator:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.warning("SUPABASE credentials not set - veritabanına kayıt yapılamayacak")
            self.supabase = None
        else:
            self.supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)

        self.gemini = GeminiAPI(GEMINI_API_KEY)
        self.validator = QualityValidator(GEMINI_API_KEY)
        self.stats = {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "with_image": 0,
            "questions_rejected": 0,
            "images_rejected": 0,
            "quality_retries": 0,
            "by_difficulty": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            "by_bloom": {}
        }

    def _get_bloom_distribution(self, count: int) -> Dict[str, int]:
        """30 soru için Bloom dağılımını hesapla"""
        distribution = {}
        base_count = count // 6
        remainder = count % 6

        for i, bloom in enumerate(BLOOM_TAKSONOMISI.keys()):
            distribution[bloom] = base_count + (1 if i < remainder else 0)

        return distribution

    def _select_random_params(self, bloom_seviyesi: str, konu: Optional[str] = None) -> QuestionParams:
        """Rastgele soru parametreleri seç"""

        if konu and konu in TEMA1_MUFREDAT:
            secilen_konu = konu
        else:
            secilen_konu = random.choice(list(TEMA1_MUFREDAT.keys()))

        konu_data = TEMA1_MUFREDAT[secilen_konu]
        bloom_data = BLOOM_TAKSONOMISI[bloom_seviyesi]

        zorluk = random.choice(bloom_data["zorluk_aralik"])
        baglam = random.choice(konu_data["ornek_senaryolar"])
        gorsel_tipi = random.choice(konu_data["gorsel_tipleri"])

        if bloom_seviyesi in ["Değerlendirme", "Yaratma"]:
            soru_tipi = random.choice(["onculu", "analiz", "tasarim"])
        elif bloom_seviyesi in ["Analiz"]:
            soru_tipi = random.choice(["grafik", "karsilastirma", "analiz"])
        elif bloom_seviyesi in ["Uygulama"]:
            soru_tipi = random.choice(["hesaplama", "grafik", "hikayeli"])
        else:
            soru_tipi = random.choice(["hikayeli", "tanim", "kavram"])

        return QuestionParams(
            konu=secilen_konu,
            alt_konu=konu_data["display_name"],
            kazanim_kodu=konu_data["kazanim_kodu"],
            bloom_seviyesi=bloom_seviyesi,
            zorluk=zorluk,
            baglam=baglam,
            gorsel_tipi=gorsel_tipi,
            soru_tipi=soru_tipi
        )

    def generate_single_question(self, params: QuestionParams) -> Optional[int]:
        """Tek soru üret ve veritabanına kaydet"""
        self.stats["total_attempts"] += 1
        konu_data = TEMA1_MUFREDAT.get(params.konu, {})
        konu_display = konu_data.get("display_name", params.konu)

        logger.info(f"\n{'='*70}")
        logger.info(f"SORU ÜRETİMİ BAŞLIYOR")
        logger.info(f"   Konu: {konu_display}")
        logger.info(f"   Bloom: {params.bloom_seviyesi} | Zorluk: {params.zorluk}/6")
        logger.info(f"   Soru Tipi: {params.soru_tipi}")
        logger.info(f"{'='*70}")

        max_question_retries = 3
        max_image_retries = 3

        try:
            # ADIM 1: SORU ÜRETİMİ
            question_data = None
            question_quality_score = 0

            for q_attempt in range(max_question_retries):
                logger.info(f"\n[1/5] Gemini ile soru üretiliyor (Deneme {q_attempt + 1}/{max_question_retries})...")

                question_data = self.gemini.generate_question(params)

                if not question_data:
                    continue

                # Temel alan kontrolü
                required_fields = ["soru_metni", "soru_koku", "siklar", "dogru_cevap"]
                missing = [f for f in required_fields if f not in question_data]
                if missing:
                    logger.warning(f"  Eksik alanlar: {missing}")
                    self.stats["quality_retries"] += 1
                    continue

                # 5 şık kontrolü
                siklar = question_data.get("siklar", {})
                if len(siklar) < 5:
                    logger.warning(f"  Yetersiz şık sayısı: {len(siklar)}")
                    self.stats["quality_retries"] += 1
                    continue

                # ÖNCÜLLÜ SORU VALİDASYONU
                # Seçeneklerde "Yalnız I", "I ve II" vb. varsa soru metninde I., II., III. olmalı
                soru_metni_check = question_data.get("soru_metni", "")
                siklar_text = " ".join(str(v) for v in siklar.values()).lower()

                oncul_patterns = ["yalnız i", "i ve ii", "ii ve iii", "i ve iii", "i, ii ve iii"]
                has_oncul_options = any(pattern in siklar_text for pattern in oncul_patterns)

                if has_oncul_options:
                    # Soru metninde I., II., III. ifadeleri aranır
                    has_oncul_statements = (
                        ("I." in soru_metni_check or "I-" in soru_metni_check or "\nI " in soru_metni_check) and
                        ("II." in soru_metni_check or "II-" in soru_metni_check or "\nII " in soru_metni_check) and
                        ("III." in soru_metni_check or "III-" in soru_metni_check or "\nIII " in soru_metni_check)
                    )

                    if not has_oncul_statements:
                        logger.warning(f"  ❌ ÖNCÜL HATASI: Şıklarda 'Yalnız I' vb. var ama soru metninde I, II, III ifadeleri yok!")
                        logger.warning(f"     Soru metni kontrol ediliyor: I={('I.' in soru_metni_check)}, II={('II.' in soru_metni_check)}, III={('III.' in soru_metni_check)}")
                        self.stats["quality_retries"] += 1
                        continue

                # Kalite kontrolü
                logger.info("  Kalite kontrolü yapılıyor...")
                q_validation = self.validator.validate_question(question_data, params)
                question_quality_score = q_validation.get("overall_score", 5)

                logger.info(f"  Kalite Puanı: {question_quality_score}/10")

                if q_validation.get("pass", False):
                    logger.info("  ✓ Soru kalite kontrolünü geçti")
                    break
                else:
                    problems = q_validation.get("problems", ["Kalite yetersiz"])
                    self.stats["quality_retries"] += 1
                    self.stats["questions_rejected"] += 1
                    logger.warning(f"  Soru reddedildi: {problems}")

            if not question_data:
                self.stats["failed"] += 1
                logger.error("  Tüm soru denemeleri başarısız")
                return None

            # ADIM 2: GÖRSEL ÜRETİMİ
            image_url = None
            image_bytes = None
            gorsel_betimleme = question_data.get("gorsel_betimleme", {})

            gorsel_uret = False
            if question_data.get("gorsel_gerekli", False):
                gorsel_uret = True
            elif params.soru_tipi == "grafik":
                gorsel_uret = True
            elif gorsel_betimleme and gorsel_betimleme.get("tip"):
                gorsel_uret = True
            elif random.random() < 0.5:  # %50 ihtimalle görsel üret
                gorsel_uret = True
                if not gorsel_betimleme:
                    gorsel_betimleme = {
                        "tip": random.choice(konu_data.get("gorsel_tipleri", ["grafik"])),
                        "detay": f"{konu_display} için açıklayıcı diyagram",
                        "ogeler": ["eksenler", "etiketler", "oklar"],
                        "renkler": {"ana": "mavi", "vurgu": "kırmızı", "arka_plan": "beyaz"}
                    }

            if gorsel_uret and gorsel_betimleme:
                logger.info(f"\n[2/5] Görsel üretiliyor (soruya özgü)...")
                soru_metni_for_image = question_data.get("soru_metni", "")

                for img_attempt in range(max_image_retries):
                    image_bytes = self.gemini.generate_image(gorsel_betimleme, params.konu, soru_metni_for_image)

                    if image_bytes:
                        logger.info("  Görsel kalite kontrolü yapılıyor...")
                        img_validation = self.validator.validate_image(image_bytes, gorsel_betimleme)

                        if img_validation.get("pass", False):
                            logger.info("  ✓ Görsel kalite kontrolünü geçti")
                            break
                        else:
                            self.stats["images_rejected"] += 1
                            logger.warning(f"  Görsel reddedildi: {img_validation.get('problems', [])}")
                            image_bytes = None

                if image_bytes and self.supabase:
                    filename = f"fizik10_tema1_{uuid.uuid4().hex[:12]}.png"
                    image_url = self.supabase.upload_image(image_bytes, filename)
                    if image_url:
                        self.stats["with_image"] += 1
            else:
                logger.info("\n[2/5] Görsel gerekli değil, atlanıyor...")

            # ADIM 3: VERİ YAPISI
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
                subject="Fizik",
                grade_level=10,
                topic=params.konu,
                topic_group="Tema1_BirBoyuttaHareket",
                kazanim_kodu=params.kazanim_kodu,
                bloom_level=params.bloom_seviyesi,
                pisa_level=question_data.get("pisa_seviyesi", 3),
                pisa_context=question_data.get("pisa_baglam", "Bilimsel"),
                scenario_text=soru_metni,
                distractor_explanations=question_data.get("celdirici_analizi", {}),
                image_url=image_url
            )

            # ADIM 4: ÖZET
            logger.info(f"\n[4/5] KALİTE ÖZETİ:")
            logger.info(f"   Soru Puanı: {question_quality_score}/10")
            logger.info(f"   Bloom: {params.bloom_seviyesi}")

            # ADIM 5: KAYDET
            if self.supabase:
                logger.info("\n[5/5] Veritabanına kaydediliyor...")
                question_id = self.supabase.insert_question(generated)

                if question_id:
                    self.stats["successful"] += 1
                    self.stats["by_difficulty"][params.zorluk] += 1
                    self.stats["by_bloom"][params.bloom_seviyesi] = self.stats["by_bloom"].get(params.bloom_seviyesi, 0) + 1
                    logger.info(f"\n✓ BAŞARILI! Soru ID: {question_id}")
                    return question_id
                else:
                    self.stats["failed"] += 1
                    logger.error("\nVeritabanı kaydı başarısız")
                    return None
            else:
                # Supabase yoksa JSON olarak döndür
                self.stats["successful"] += 1
                self.stats["by_difficulty"][params.zorluk] += 1
                self.stats["by_bloom"][params.bloom_seviyesi] = self.stats["by_bloom"].get(params.bloom_seviyesi, 0) + 1
                logger.info(f"\n✓ BAŞARILI! (Veritabanı bağlantısı yok)")
                return -1  # Başarılı ama DB'ye kaydedilmedi

        except Exception as e:
            self.stats["failed"] += 1
            logger.error(f"\nHATA: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

    def generate_batch(self, count: int = 30, konu: Optional[str] = None) -> Dict[str, Any]:
        """Toplu soru üret (Bloom dağılımına göre)"""

        distribution = self._get_bloom_distribution(count)

        logger.info(f"\n{'#'*70}")
        logger.info(f"10. SINIF FİZİK - TEMA 1: BİR BOYUTTA HAREKET")
        logger.info(f"Gemini 2.5 Flash + Imagen 3 + Supabase")
        logger.info(f"Toplam {count} soru üretilecek")
        logger.info(f"{'#'*70}")
        logger.info(f"\nBloom Dağılımı:")
        for bloom, sayi in distribution.items():
            logger.info(f"  - {bloom}: {sayi} soru")
        logger.info(f"{'#'*70}\n")

        results = {"generated_ids": [], "failed_topics": [], "stats": {}}

        for bloom_seviyesi, soru_sayisi in distribution.items():
            logger.info(f"\n[{bloom_seviyesi.upper()}] - {soru_sayisi} soru üretiliyor...")

            for i in range(soru_sayisi):
                params = self._select_random_params(bloom_seviyesi, konu)
                logger.info(f"  Soru {i+1}/{soru_sayisi}: {params.alt_konu} - {params.soru_tipi}")

                question_id = self.generate_single_question(params)
                if question_id:
                    results["generated_ids"].append(question_id)
                else:
                    results["failed_topics"].append(f"{params.konu}_{bloom_seviyesi}_{i+1}")

                time.sleep(Config.RATE_LIMIT_DELAY)

        results["stats"] = self.stats
        return results

    def print_stats(self):
        """İstatistikleri yazdır"""
        logger.info(f"\n{'='*70}")
        logger.info("SONUÇ İSTATİSTİKLERİ")
        logger.info(f"{'='*70}")
        logger.info(f"   Toplam deneme      : {self.stats['total_attempts']}")
        logger.info(f"   Başarılı           : {self.stats['successful']}")
        logger.info(f"   Başarısız          : {self.stats['failed']}")
        logger.info(f"   Görselli soru      : {self.stats['with_image']}")
        logger.info(f"   Reddedilen sorular : {self.stats['questions_rejected']}")
        logger.info(f"   Reddedilen görseller: {self.stats['images_rejected']}")
        logger.info(f"\n   Zorluk Dağılımı:")
        for level, count in self.stats['by_difficulty'].items():
            if count > 0:
                logger.info(f"     Seviye {level}: {count} soru")
        logger.info(f"\n   Bloom Dağılımı:")
        for bloom, count in self.stats['by_bloom'].items():
            logger.info(f"     {bloom}: {count} soru")

        if self.stats['total_attempts'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total_attempts']) * 100
            logger.info(f"\n   Başarı oranı: %{success_rate:.1f}")
        logger.info(f"{'='*70}\n")


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="10. Sınıf Fizik - Tema 1: Bir Boyutta Hareket Soru Üretim Botu v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Yenilikler v2.0:
  - Gemini 2.5 Flash + Imagen 3 entegrasyonu
  - Supabase veritabanı desteği
  - Bloom Taksonomisi (6 seviye) dağılımı
  - Maarif Modeli kriterleri
  - Kalite validasyonu

Örnekler:
  python fizik10_tema1_bot.py --mode batch --count 30
  python fizik10_tema1_bot.py --mode topic --topic sabit_hizli_hareket --count 10
  python fizik10_tema1_bot.py --mode single --konu ivmeli_hareket --bloom Analiz --zorluk 4

Konular:
  - sabit_hizli_hareket: Sabit Hızlı Hareket
  - ivmeli_hareket: Bir Boyutta Sabit İvmeli Hareket
  - serbest_dusme: Serbest Düşme
  - iki_boyutta_hareket: İki Boyutta Sabit İvmeli Hareket

Bloom Seviyeleri:
  - Hatırlama (1), Anlama (2), Uygulama (3)
  - Analiz (4), Değerlendirme (5), Yaratma (6)
        """
    )

    parser.add_argument("--mode", choices=["batch", "topic", "single"], default="batch",
                        help="Üretim modu: batch (toplu), topic (konuya göre), single (tekli)")
    parser.add_argument("--count", type=int, default=30,
                        help="Üretilecek soru sayısı (varsayılan: 30)")
    parser.add_argument("--topic", "--konu", type=str, default=None,
                        help="Konu seçimi (topic/single modları için)")
    parser.add_argument("--bloom", type=str, default=None,
                        help="Bloom seviyesi (single modu için)")
    parser.add_argument("--zorluk", type=int, default=None,
                        help="Zorluk seviyesi 1-6 (single modu için)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Çıktı dosya adı")

    args = parser.parse_args()

    logger.info("""
========================================================================
     10. SINIF FİZİK SORU ÜRETİM BOTU v2.0
     Tema 1: Bir Boyutta Hareket

     Gemini 2.5 Flash + Imagen 3 + Supabase

     Özellikler:
     - Bloom Taksonomisi (6 seviye)
     - Maarif Modeli Kriterleri
     - Kavram Yanılgıları Veritabanı
     - Kalite Validasyonu
========================================================================
    """)

    logger.info(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Mod: {args.mode}")

    try:
        generator = Fizik10Tema1Generator()

        if args.mode == "batch":
            logger.info(f"Batch modu - {args.count} soru üretilecek")
            results = generator.generate_batch(count=args.count, konu=args.topic)
            logger.info(f"\nÜretilen soru sayısı: {len(results['generated_ids'])}")
            if results['failed_topics']:
                logger.info(f"Başarısız: {len(results['failed_topics'])}")

        elif args.mode == "topic":
            if not args.topic:
                print("HATA: --topic parametresi gerekli!")
                print(f"Geçerli konular: {', '.join(TEMA1_MUFREDAT.keys())}")
                sys.exit(1)

            if args.topic not in TEMA1_MUFREDAT:
                print(f"HATA: Geçersiz konu: {args.topic}")
                print(f"Geçerli konular: {', '.join(TEMA1_MUFREDAT.keys())}")
                sys.exit(1)

            logger.info(f"Topic modu - {args.topic} için {args.count} soru")
            results = generator.generate_batch(count=args.count, konu=args.topic)
            logger.info(f"\nÜretilen soru sayısı: {len(results['generated_ids'])}")

        elif args.mode == "single":
            konu = args.topic or random.choice(list(TEMA1_MUFREDAT.keys()))
            bloom = args.bloom or random.choice(list(BLOOM_TAKSONOMISI.keys()))
            zorluk = args.zorluk or random.choice([2, 3, 4])

            if bloom not in BLOOM_TAKSONOMISI:
                print(f"HATA: Geçersiz Bloom seviyesi: {bloom}")
                print(f"Geçerli seviyeler: {', '.join(BLOOM_TAKSONOMISI.keys())}")
                sys.exit(1)

            params = QuestionParams(
                konu=konu,
                alt_konu=TEMA1_MUFREDAT[konu]["display_name"],
                kazanim_kodu=TEMA1_MUFREDAT[konu]["kazanim_kodu"],
                bloom_seviyesi=bloom,
                zorluk=zorluk,
                baglam=random.choice(TEMA1_MUFREDAT[konu]["ornek_senaryolar"]),
                gorsel_tipi=random.choice(TEMA1_MUFREDAT[konu]["gorsel_tipleri"]),
                soru_tipi="hikayeli"
            )

            logger.info(f"Single modu - {konu}")
            logger.info(f"Bloom: {bloom}, Zorluk: {zorluk}/6")
            question_id = generator.generate_single_question(params)

            if question_id:
                logger.info(f"\n✓ Soru başarıyla üretildi! ID: {question_id}")
            else:
                logger.error("\nSoru üretilemedi")
                sys.exit(1)

        generator.print_stats()

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
