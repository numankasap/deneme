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

## ÖNCÜLLÜ SORU FORMATI

Öncüllü sorularda:
1. Önce senaryo anlatılır
2. "Buna göre, ... ile ilgili aşağıdaki ifadelerden hangileri doğrudur?" yazılır
3. I, II, III öncülleri ayrı satırlarda yazılır
4. Şıklar: A) Yalnız I, B) Yalnız II, C) I ve II, D) II ve III, E) I, II ve III

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
    "tip": "x-t_grafigi / v-t_grafigi / hareket_diyagrami",
    "detay": "Çizilecek görselin detaylı açıklaması",
    "ogeler": ["eksenler", "eğri", "noktalar"],
    "etiketler": ["x(m)", "t(s)", "A noktası"]
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

IMAGE_PROMPT_TEMPLATE = """10. Sınıf Fizik sorusu için PROFESYONEL eğitim görseli oluştur.

## GÖRSEL TİPİ: {tip}

## DETAYLI BETİMLEME:
{detay}

## RENK ŞEMASI
- Arka plan: Beyaz (#FFFFFF)
- Ana çizgiler: Koyu gri (#333333)
- Grid çizgileri: Açık gri (#CCCCCC)
- Cisimler: Mavi tonları (#2196F3)
- Hız vektörleri: Yeşil (#4CAF50)
- İvme vektörleri: Mor (#9C27B0)
- Kuvvet vektörleri: Kırmızı (#E53935)

## GRAFİK STANDARTLARI
- Eksen etiketleri: Değişken adı ve birimi [m], [s], [m/s]
- Grid çizgileri: Açık gri, ince
- Veri çizgisi: Mavi, kalın
- Eksenler: Siyah, kalın (2-3px)

## YASAKLAR
❌ Soru metni veya cümleler
❌ A), B), C), D), E) şıkları
❌ Çözüm adımları
❌ Cevabı veren bilgi
"""

# ============================================================================
# ANA BOT SINIFI
# ============================================================================

class Fizik10Tema1Bot:
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

    def _get_bloom_distribution(self, count: int) -> Dict[str, int]:
        """30 soru için Bloom dağılımını hesapla"""
        distribution = {}
        base_count = count // 6  # Her seviyeye eşit dağılım
        remainder = count % 6

        for i, bloom in enumerate(BLOOM_TAKSONOMISI.keys()):
            distribution[bloom] = base_count + (1 if i < remainder else 0)

        return distribution

    def _select_random_params(self, bloom_seviyesi: str, konu: Optional[str] = None) -> QuestionParams:
        """Rastgele soru parametreleri seç"""

        # Konu seçimi
        if konu and konu in TEMA1_MUFREDAT:
            secilen_konu = konu
        else:
            secilen_konu = random.choice(list(TEMA1_MUFREDAT.keys()))

        konu_data = TEMA1_MUFREDAT[secilen_konu]
        bloom_data = BLOOM_TAKSONOMISI[bloom_seviyesi]

        # Zorluk seviyesi seçimi (Bloom'a uygun)
        zorluk = random.choice(bloom_data["zorluk_aralik"])

        # Bağlam seçimi
        baglam = random.choice(konu_data["ornek_senaryolar"])

        # Görsel tipi seçimi
        gorsel_tipi = random.choice(konu_data["gorsel_tipleri"])

        # Soru tipi seçimi (Bloom seviyesine göre)
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

{"### ÖNCÜLLÜ SORU FORMATI" if params.soru_tipi == "onculu" else ""}
{'''
Öncüllü soruda:
1. Önce senaryo anlat
2. "Buna göre, ... ile ilgili aşağıdaki ifadelerden hangileri doğrudur?" yaz
3. I, II, III öncüllerini AYRI SATIRLARDA yaz
4. Şıklar: A) Yalnız I, B) Yalnız II, C) I ve II, D) II ve III, E) I, II ve III
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
                question_data = json.loads(text_content)

                # Bloom seviyesi ekle
                question_data["bloom_seviyesi"] = params.bloom_seviyesi
                question_data["bloom_seviye_no"] = bloom_data.get("seviye", 3)
                question_data["konu"] = params.konu
                question_data["alt_konu"] = params.alt_konu

                logger.info(f"  ✓ Soru başarıyla üretildi: {params.bloom_seviyesi} - Zorluk {params.zorluk}")
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

    def generate_batch(self, count: int = 30, konu: Optional[str] = None) -> List[Dict[str, Any]]:
        """Toplu soru üret (Bloom dağılımına göre)"""

        distribution = self._get_bloom_distribution(count)
        questions = []

        logger.info(f"\n{'='*60}")
        logger.info(f"10. SINIF FİZİK - TEMA 1: BİR BOYUTTA HAREKET")
        logger.info(f"Toplam {count} soru üretilecek")
        logger.info(f"{'='*60}")
        logger.info(f"\nBloom Dağılımı:")
        for bloom, sayi in distribution.items():
            logger.info(f"  - {bloom}: {sayi} soru")
        logger.info(f"{'='*60}\n")

        for bloom_seviyesi, soru_sayisi in distribution.items():
            logger.info(f"\n[{bloom_seviyesi.upper()}] - {soru_sayisi} soru üretiliyor...")

            for i in range(soru_sayisi):
                params = self._select_random_params(bloom_seviyesi, konu)
                logger.info(f"  Soru {i+1}/{soru_sayisi}: {params.alt_konu} - {params.soru_tipi}")

                question = self.generate_question(params)
                if question:
                    questions.append(question)
                else:
                    logger.warning(f"  ⚠ Soru üretilemedi, atlanıyor...")

        logger.info(f"\n{'='*60}")
        logger.info(f"TOPLAM: {len(questions)}/{count} soru başarıyla üretildi")
        logger.info(f"{'='*60}")

        return questions

    def save_questions(self, questions: List[Dict], filename: str = None):
        """Soruları JSON dosyasına kaydet"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fizik10_tema1_sorular_{timestamp}.json"

        output = {
            "metadata": {
                "sinif": 10,
                "ders": "Fizik",
                "tema": "Tema 1: Bir Boyutta Hareket",
                "toplam_soru": len(questions),
                "olusturma_tarihi": datetime.now().isoformat(),
                "bloom_dagilimi": {},
                "zorluk_dagilimi": {}
            },
            "sorular": questions
        }

        # Dağılımları hesapla
        for q in questions:
            bloom = q.get("bloom_seviyesi", "Bilinmiyor")
            zorluk = q.get("zorluk", 0)
            output["metadata"]["bloom_dagilimi"][bloom] = output["metadata"]["bloom_dagilimi"].get(bloom, 0) + 1
            output["metadata"]["zorluk_dagilimi"][str(zorluk)] = output["metadata"]["zorluk_dagilimi"].get(str(zorluk), 0) + 1

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"\n✓ Sorular kaydedildi: {filename}")
        return filename


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="10. Sınıf Fizik - Tema 1: Bir Boyutta Hareket Soru Üretim Botu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
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

    # API key kontrolü
    if not GEMINI_API_KEY:
        print("HATA: GEMINI_API_KEY environment variable tanımlı değil!")
        print("Lütfen: export GEMINI_API_KEY='your-api-key' komutunu çalıştırın.")
        sys.exit(1)

    # Bot oluştur
    bot = Fizik10Tema1Bot(GEMINI_API_KEY)

    if args.mode == "batch":
        # Toplu üretim
        questions = bot.generate_batch(count=args.count, konu=args.topic)
        bot.save_questions(questions, args.output)

    elif args.mode == "topic":
        # Konuya göre üretim
        if not args.topic:
            print("HATA: --topic parametresi gerekli!")
            print(f"Geçerli konular: {', '.join(TEMA1_MUFREDAT.keys())}")
            sys.exit(1)

        if args.topic not in TEMA1_MUFREDAT:
            print(f"HATA: Geçersiz konu: {args.topic}")
            print(f"Geçerli konular: {', '.join(TEMA1_MUFREDAT.keys())}")
            sys.exit(1)

        questions = bot.generate_batch(count=args.count, konu=args.topic)
        bot.save_questions(questions, args.output)

    elif args.mode == "single":
        # Tekli üretim
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

        question = bot.generate_question(params)
        if question:
            print("\n" + "="*60)
            print("ÜRETİLEN SORU:")
            print("="*60)
            print(json.dumps(question, ensure_ascii=False, indent=2))
        else:
            print("HATA: Soru üretilemedi!")


if __name__ == "__main__":
    main()
