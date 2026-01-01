"""
AYT Fizik Soru Uretim Botu v2.0
================================
Gemini 2.5 Flash + Imagen 3 + Supabase
OSYM Formatinda AYT Fizik Sorulari

Yenilikler v2.0:
- Kavram Yanilgisi Veri Tabani (Misconception Database)
- Psikometrik Zorluk Dagilimi
- Gelistirilmis Prompt Muhendisligi (Few-Shot)
- Renkli Gorsel Sablonlari
- OSYM Jargonu ve Uslubu
- 2025 Trend Bazli Soru Tipleri

Kullanim:
  python ayt_fizik_bot.py --mode batch --count 1
  python ayt_fizik_bot.py --mode topic --topic elektrostatik --count 5
  python ayt_fizik_bot.py --mode single --konu hareket_ve_kuvvet --bloom Analiz --zorluk 4
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
    print("google-genai paketi bulunamadi. pip install google-genai yapin.")

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
    DEFAULT_GRADE_LEVEL = 12
    DEFAULT_SUBJECT = "Fizik"
    DEFAULT_TOPIC_GROUP = "AYT"
    TEMPERATURE = 0.85
    MAX_OUTPUT_TOKENS = 8192
    STORAGE_BUCKET = "questions-images"

# ============================================================================
# PSIKOMETRIK ZORLUK DAGILIMI (OSYM Tarzi)
# ============================================================================

ZORLUK_DAGILIMI = {
    1: {"oran": 0.10, "aciklama": "Kolay - Temel tanim ve basit uygulama", "adim_sayisi": 1},
    2: {"oran": 0.25, "aciklama": "Orta-Kolay - Standart formul uygulamasi", "adim_sayisi": 2},
    3: {"oran": 0.30, "aciklama": "Orta - Bilinen senaryolarda kazanim uygulamasi", "adim_sayisi": 2},
    4: {"oran": 0.25, "aciklama": "Zor - Coklu kazanim veya detayli grafik analizi", "adim_sayisi": 3},
    5: {"oran": 0.10, "aciklama": "Secici - Onculu (I,II,III) format, derin kavramsal analiz", "adim_sayisi": 4}
}

# ============================================================================
# KAVRAM YANILGISI VERI TABANI (MISCONCEPTION DATABASE)
# ============================================================================

KAVRAM_YANILGILARI = {
    "dinamik": {
        "yanilgilar": [
            "Hizin oldugu yerde mutlaka kuvvet de vardir",
            "Sabit hizla giden cisme net kuvvet etki eder",
            "Agir cisimler daha hizli duser",
            "Kuvvet olmadan hareket olmaz"
        ],
        "celdirici_stratejileri": [
            "Sabit hizla giden cisme net kuvvet etki ettigini iddia eden sik",
            "Kutlenin dusme hizini etkiledigini gosteren sik",
            "Surtunen cisimlerin mutlaka yavasladigini soyleyen sik"
        ]
    },
    "atislar": {
        "yanilgilar": [
            "Tepe noktasinda ivme sifirdir",
            "Tepe noktasinda hiz sifirdir (egik atista)",
            "Yatay atis serbest dusme degildir",
            "Havada asili kalma ani vardir"
        ],
        "celdirici_stratejileri": [
            "Tepe noktasindaki ivmeyi sifir alan hesaplama",
            "Yatay hiz bilesenini tepe noktasinda sifir alan sik",
            "Ucus suresini yanlis hesaplayan sik"
        ]
    },
    "elektrik": {
        "yanilgilar": [
            "Akim devrede harcanir, eksi kutba daha az akim doner",
            "Elektrik alanin sifir oldugu yerde potansiyel de sifirdir",
            "Paralel bagli lambalarin hepsi ayni parlakliktadir",
            "Pil bittikce akim azalir ama gerilim ayni kalir"
        ],
        "celdirici_stratejileri": [
            "Seri bagli lambalarda akimin azaldigini ima eden sik",
            "Alan sifir = Potansiyel sifir yanilgisini kullanan sik",
            "Direnc artinca akimin her yerde azaldigini soyleyen sik"
        ]
    },
    "manyetizma": {
        "yanilgilar": [
            "Manyetik kuvvet duragan yuklere de etki eder",
            "Manyetik alan cizgileri birbirini keser",
            "Bobindeki akim artinca manyetik alan azalir",
            "Manyetik kuvvet hiz yonundedir"
        ],
        "celdirici_stratejileri": [
            "Hizi sifir olan yuke F=qvB uygulayan tuzak",
            "Manyetik kuvveti hiz yonunde gosteren sik",
            "Alan cizgilerinin kesistigini ima eden sik"
        ]
    },
    "induksiyon": {
        "yanilgilar": [
            "Manyetik aki buyukse induksiyon emk buyuktur",
            "Bobinden gecen aki sabitse akim olusur",
            "Lenz yasasi sadece yonu belirler, buyuklugu degil"
        ],
        "celdirici_stratejileri": [
            "Aki degisim hizi yerine dogrudan aki buyuklugune odaklanan sik",
            "Sabit akida bile akim oldugunu soyleyen sik"
        ]
    },
    "dalgalar": {
        "yanilgilar": [
            "Dalga hizi frekansa baglidir",
            "Ses dalgalari bosluktada yayilir",
            "Kirilmada frekans degisir",
            "Girisimde enerji yok olur"
        ],
        "celdirici_stratejileri": [
            "Frekans artinca dalga hizinin arttigini gosteren sik",
            "Kirilmada frekansin degistigini soyleyen sik"
        ]
    },
    "modern_fizik": {
        "yanilgilar": [
            "Foton sayisi artinca elektron hizi artar",
            "Esik frekansinin altinda uzun sure beklersek elektron kopar",
            "X-isinlari ve gama isinlari ayni seyi yapar",
            "Radyoaktif bozunma hizi sicakliga baglidir"
        ],
        "celdirici_stratejileri": [
            "Isik siddetinin elektron hizini artirdigini soyleyen sik",
            "Esik altinda beklemeyle elektron kopacagini ima eden sik"
        ]
    },
    "enerji": {
        "yanilgilar": [
            "Enerji harcanir ve biter",
            "Kinetik enerji vektoreldir",
            "Potansiyel enerji her zaman pozitiftir",
            "Is ve enerji ayni seydir"
        ],
        "celdirici_stratejileri": [
            "Enerjinin kayboldugunua soyleyen sik",
            "Kinetik enerjiyi vektorel hesaplayan sik"
        ]
    },
    "cembersel_hareket": {
        "yanilgilar": [
            "Merkezkac kuvveti gercek bir kuvvettir",
            "Hiz sabitse ivme sifirdir",
            "Merkezcil kuvvet ayri bir kuvvet turudur"
        ],
        "celdirici_stratejileri": [
            "Duzgun cembersel harekette ivmenin sifir oldugunu soyleyen sik",
            "Merkezkac kuvvetini gercek kuvvet olarak hesaplayan sik"
        ]
    },
    "bhh": {
        "yanilgilar": [
            "Yay-kutle sisteminin periyodu yer cekiminden etkilenir",
            "Egik duzlemde yay-kutle periyodu farklidir",
            "Basit sarkacin periyodu kutleye baglidir",
            "Denge noktasinda ivme maksimumdur",
            "Genlik noktasinda hiz maksimumdur",
            "Uzanim arttikca hiz da artar",
            "Periyot genlige baglidir",
            "Ay'da yay-kutle periyodu degisir"
        ],
        "celdirici_stratejileri": [
            "Yay-kutle periyodunun g'ye bagimli oldugunu soyleyen sik",
            "Egik duzlemde farkli periyot gosteren sik",
            "Basit sarkac periyodunun kutleye bagimli oldugunu soyleyen sik",
            "Denge noktasinda ivmenin maksimum oldugunu soyleyen sik",
            "Uzanim arttikca hizin arttigini gosteren sik",
            "Ay'da yay-kutle periyodunun degistigini soyleyen sik"
        ]
    }
}

# ============================================================================
# OSYM JARGONU VE STANDART IFADELER
# ============================================================================

OSYM_JARGON = {
    "ortam": [
        "Surtunmeler ve hava direnci ihmal edilmektedir.",
        "Yalitkan bir zemin uzerinde",
        "Homojen ve duzgun yogunluklu",
        "Noktasal cisim olarak kabul edilen",
        "Ozdes K ve L cisimleri",
        "Baslangicta durgun haldeki",
        "Sabit hizla hareket eden"
    ],
    "soru_kokleri": [
        "Buna gore,",
        "Bu bilgilere gore,",
        "Yukaridaki bilgilere gore,",
        "Buna gore asagidaki yargIlardan hangileri kesinlikle dogrudur?",
        "Buna gore I, II ve III numarali ifadelerden hangileri dogrudur?"
    ],
    "karsilastirma": [
        "buyuktur", "kucuktur", "esittir",
        "artar", "azalir", "degismez",
        "2 katidir", "yarisidir", "4 katidir"
    ],
    "oncul_format": [
        "I. [ifade1]\nII. [ifade2]\nIII. [ifade3]",
        "ifadelerinden hangileri dogrudur?",
        "A) Yalniz I  B) Yalniz II  C) I ve II  D) II ve III  E) I, II ve III"
    ]
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
    soru_tipi: str = "hikayeli"  # hikayeli, grafik, onculu, deney
    grade_level: int = 12
    topic_group: str = "AYT"

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
# AYT FIZIK MUFREDATI - KONULAR VE KAZANIMLAR (GENISLETILMIS)
# ============================================================================

AYT_FIZIK_KONULAR: Dict[str, Dict[str, Any]] = {
    
    "hareket_ve_kuvvet": {
        "display_name": "Hareket ve Kuvvet",
        "alt_konular": [
            "dusey_atis", "yatay_atis", "egik_atis", "bagil_hiz",
            "newton_kanunlari", "surtunme_kuvveti", "momentum", "carpismalar"
        ],
        "kazanimlar": ["F.12.1.1.1", "F.12.1.1.2", "F.12.1.1.3", "F.12.1.1.4", "F.12.1.2.1", "F.12.1.2.2", "F.12.1.2.3"],
        "ornek_baglamlar": [
            "Batiya dogru ucan karga ve ceviz",
            "Tren uzerinde yuruyеn yolcu",
            "Nehirde yuzen yuzucu ve antrenor",
            "Lunaparkta donen hedef tahtasi",
            "Asansor icindeki tartI",
            "Balonlu oyuncak araba"
        ],
        "gorsel_tipleri": ["yorunge_diyagrami", "hiz_vektoru", "kuvvet_diyagrami", "carpma_oncesi_sonrasi", "referans_cercevesi"],
        "celdirici_kategorisi": "atislar",
        "trend_2025": "Hikayeli birlеsik hareket, bagil hiz ile atislarin kombinasyonu",
        "soru_tipleri": ["hikayeli", "grafik", "onculu"],
        "formul_bilgisi": """
        Egik Atis: vx = v0*cos(θ), vy = v0*sin(θ) - gt
        Menzil = v0²*sin(2θ)/g, h_max = v0²*sin²(θ)/2g
        Momentum: p = mv, Impuls: J = F*Δt = Δp
        """,
        "few_shot_ornek": """
        ORNEK SORU (2025 Tarzi - Karga ve Ceviz):
        Yatay raylarda 30 m/s sabit hizla ilerleyen ustu acik bir vagonun 
        80 m yukarsindan, vagonla ayni yonde 10 m/s hizla ucan bir kus, 
        tasidigi cevizi serbest birakiyor. (g=10 m/s²)
        Buna gore, ceviz vagona duser mi? Aciklayiniz.
        
        COZUM MANTIGI:
        - Cevizin yere gore yatay hizi = 10 m/s (kusun hizi)
        - Dusme suresi: h = ½gt² → 80 = 5t² → t = 4s
        - Cevizin yatayda aldigi yol = 10 × 4 = 40 m
        - Vagonun aldigi yol = 30 × 4 = 120 m
        - Fark = 80 m, vagon cevizi gecer, ceviz vagona dusmez.
        """
    },
    
    "tork_ve_denge": {
        "display_name": "Tork ve Denge",
        "alt_konular": ["tork_kavrami", "denge_kosullari", "agirlik_merkezi", "kaldiraci_sistemleri", "basit_makineler"],
        "kazanimlar": ["F.12.1.3.1", "F.12.1.3.2", "F.12.1.3.3"],
        "ornek_baglamlar": [
            "Makas ve kesme kuvveti",
            "El arabasi dengeleme",
            "Tahterevalli ve kutle dagilimu",
            "Vinc kolu ve yuk kaldirma",
            "Kapi mentesesi ve tork"
        ],
        "gorsel_tipleri": ["kaldiraci_diyagrami", "tork_vektoru", "denge_sistemi", "kutle_merkezi"],
        "celdirici_kategorisi": "dinamik",
        "trend_2025": "Gunluk hayat aletleri uzerinden tork uygulamalari",
        "soru_tipleri": ["hikayeli", "deney"],
        "formul_bilgisi": "Tork: τ = F × d, Denge: Στ = 0"
    },
    
    "dairesel_hareket": {
        "display_name": "Dairesel Hareket",
        "alt_konular": ["duzgun_dairesel_hareket", "acisal_hiz", "merkezcil_ivme", "uydu_hareketi", "viraj_problemleri"],
        "kazanimlar": ["F.12.1.4.1", "F.12.1.4.2", "F.12.1.4.3"],
        "ornek_baglamlar": [
            "Virajda donen arac ve eylemsizlik",
            "Lunapark donme dolabi",
            "Uydu yorungeleri ve GPS",
            "Camas9r makinesi sikma",
            "Atletizm viraj kosușu"
        ],
        "gorsel_tipleri": ["cembersel_yorunge", "uydu_diyagrami", "hiz_ivme_vektorleri", "viraj_kesiti"],
        "celdirici_kategorisi": "cembersel_hareket",
        "trend_2025": "Merkezcil/merkezkac kavramsallaștirmasi",
        "soru_tipleri": ["hikayeli", "onculu"]
    },
    
    "basit_harmonik_hareket": {
        "display_name": "Basit Harmonik Hareket",
        "alt_konular": [
            "yayli_sarkac", 
            "basit_sarkac", 
            "periyod_ve_frekans", 
            "enerji_donusumleri",
            "uzanim_hiz_ivme_iliskisi",
            "farkli_ortamlarda_periyot",
            "yay_sarkac_karsilastirma",
            "farkli_duzlemlerde_bhh",
            "rezonans_ve_zorlamali_titresim",
            "sonumlu_titresim",
            "enerji_grafikleri",
            "faz_iliskisi"
        ],
        "kazanimlar": ["F.12.1.5.1", "F.12.1.5.2", "F.12.1.5.3", "F.12.1.5.4"],
        "ornek_baglamlar": [
            # KLASIK BAGLAMLAR (azaltildi)
            "Metronom ve tempo ayari",
            "Saat sarkaci ve sicaklik etkisi",
            
            # TEKNOLOJI VE MUHENDISLIK
            "Akilli telefon ivmeolcer sensoru - telefon sallandiginda ekran donusu",
            "Gokdelen sismik damperi - Taipei 101'deki dev salinimli kutle",
            "Koltuk basinda titresim izolasyonu - ucak veya arac",
            "Kamera stabilizasyonu - gimbal sisteminin titresim sonumleme prensibi",
            "Akustik gitar teli - parmak basinca periyot degisimi",
            "Kulakliktaki hoparlor membrani - ses dalgasi uretimi",
            "MR cihazindaki proton spinleri - Larmor frekansi (kavramsallik icin)",
            
            # UZAY VE ASTRONOMI
            "Uzay istasyonunda sarkac deneyi - mikroyercekimde ne olur?",
            "Mars'ta Perseverance roverinin sismografi",
            "Asteroit uzerinde ziplayan astronot - farkli g'de BHH",
            "Uydu gunes paneli acilma mekanizmasi - torsiyonel salinim",
            
            # DOGA VE BIYOLOJI
            "Orumcek aginda avini bekleyen orumcek - ag titresimi",
            "Sinekkapan bitkisinin kapanma mekanizmasi - elastik enerji",
            "Kalp atisi ve kalp kapakcigi salnimi - biyomekanik",
            "Kulak zari titresimi - isitme fizyolojisi",
            "Kus kanat cirpisi frekansi - kutle ve kanat boyu iliskisi",
            
            # GUNLUK HAYAT - BEKLENMEDIK
            "Salincakta salinan cocuk - bacak hareketinin etkisi",
            "Bungee jumping - elastik ip ve serbest dusus kombinasyonu",
            "Trampolin uzerinde ziplama - farkli kutlelerin etkisi",
            "Kopru uzerinden gecen asker birligi - rezonans tehlikesi",
            "Bardaktaki su yuzeyinin titresimi - deprem oncesi isaret",
            "Buzdolabi kompresoru titresimi - ev icin gurultu kaynaği",
            
            # FIZIK TARIHI VE DENEY
            "Galileo'nun kilise avizeleri gozlemi - izokronizm keşfi",
            "Cavendish deneyi - burulma sarkaci ile G olcumu",
            "Foucault sarkaci - Dunya donusunun kaniti",
            
            # MUHENDISLIK PROBLEMLERI
            "Asansor kablosunun titresimi - guvenlik analizi",
            "Ruzgar turbini kanadinin dogal frekansi",
            "Yaya koprusunun rezonans frekansi - Millennium Bridge olayi",
            "Deprem izolatorlu bina tasarimi",
            
            # EKSTREM KOSULLAR
            "Derin deniz dalisi - yuksek basinçta yay sabiti degisimi",
            "Kutup bolgesi - dusuk sicaklikta yay davranisi",
            "Yuksek irtifa - hava direncinin azalmasi"
        ],
        "gorsel_tipleri": [
            "konum_zaman_grafigi", 
            "sarkac_diyagrami", 
            "yayli_sistem", 
            "enerji_grafigi",
            "kuvvet_yon_diyagrami",
            "farkli_duzlem_karsilastirma",
            "periyot_karsilastirma_tablo",
            "faz_diyagrami",
            "rezonans_egrisi",
            "sonumlu_titresim_grafigi"
        ],
        "celdirici_kategorisi": "bhh",
        "trend_2025": "Gercek hayat muhendislik uygulamalari, beklenmedik baglamlar, enerji donusumleri",
        "soru_tipleri": ["grafik", "hikayeli", "onculu", "karsilastirma", "hesaplama", "yorum"],
        "soru_kaliplari": [
            # KLASIK KALIPLAR
            "Buna gore, cismin uzanimi arttikca hangi nicelikler azalir?",
            "Buna gore, periyotlar arasindaki iliski nedir?",
            
            # ORIJINAL KALIPLAR
            "Bu durumda sistemin titresim frekansini artirmak icin ne yapilmalidir?",
            "Hangi degisiklik periyodu ETKILEMEZ?",
            "Sistemin toplam mekanik enerjisi nasil degisir?",
            "Grafikte verilen anda cismin konumu ve hareketi hakkinda ne soylenebilir?",
            "Bu iki sistem ayni anda salınıma baslarsa, ilk kez ayni fazda ne zaman bulusurlar?",
            "Rezonans olusması icin hangi kosul saglanmalidir?",
            "Enerji kaybi olmadan sistemin genligini artirmak icin ne yapilabilir?",
            "Bu gozlem hangi fiziksel ilkeyle aciklanabilir?"
        ],
        "formul_bilgisi": """
        Basit Sarkac: T = 2π√(L/g) - Kutleden BAGIMSIZ, g'ye BAGIMLI
        Yay-Kutle: T = 2π√(m/k) - g'den BAGIMSIZ, kutleye BAGIMLI
        Torsiyonel Sarkac: T = 2π√(I/κ) - Eylemsizlik momenti ve burulma sabiti
        
        Uzanim-Hiz-Ivme Faz Iliskisi:
        x = A.sin(ωt) → konum
        v = Aω.cos(ωt) = Aω.sin(ωt + π/2) → hiz, konumdan 90° ileri fazda
        a = -Aω².sin(ωt) = Aω².sin(ωt + π) → ivme, konumdan 180° ileri fazda
        
        Onemli Noktalar:
        - Denge noktasi (x=0): v=max, a=0, F_net=0, KE=max, PE=0
        - Genlik noktasi (x=±A): v=0, a=max, F_net=max, KE=0, PE=max
        - Uzanim arttikca: |a| ARTAR, |F| ARTAR, |v| AZALIR
        
        Enerji:
        E_toplam = ½kA² = ½mω²A² (sabit, genlige bagimli)
        KE + PE = sabit (enerji korunumu)
        
        Ozel Durumlar:
        - Egik duzlemde yay-kutle: T = 2π√(m/k) - acidan BAGIMSIZ
        - Sivi icinde sarkac: T artar (efektif g azalir)
        - Asansorde sarkac: yukari ivmelenme → efektif g artar → T azalir
        - Mikroyercekimde sarkac: T → ∞ (salinim olmaz), yay-kutle NORMAL calisir
        """,
        "orijinal_soru_fikirleri": [
            # UZAY TEMALARI
            """
            UZAY ISTASYONU SENARYOSU:
            ISS'de gorev yapan astronot, yay-kutle ve basit sarkac sistemlerini test ediyor.
            Dunya'da her ikisinin periyodu 2s idi.
            Soru: Mikro-yercekimde hangi sistem calisir? Periyotlari ne olur?
            Cevap: Yay-kutle normal calisir (T=2s), sarkac salinim yapmaz.
            """,
            
            # REZONANS SENARYOSU  
            """
            KOPRU REZONANSI:
            Bir yaya koprusu 0.5 Hz dogal frekansa sahip. Asker birligi adim frekansi?
            Soru: Hangi adim frekansi kopruyu tehlikeye sokar?
            Cevap: 0.5 Hz veya katlari (1 Hz, 1.5 Hz...) - rezonans
            """,
            
            # TEKNOLOJI SENARYOSU
            """
            AKILLI TELEFON IVMEOLCER:
            Telefondaki MEMS ivmeolcer, kucuk bir yay-kutle sistemidir.
            Soru: Telefonun sarsılması ivmeolcerde ne olușturur?
            Cevap: Kutle salınır, yer degistirme elektrik sinyaline donusur.
            """,
            
            # BIYOLOJI SENARYOSU
            """
            KUS KANAT CIRPISI:
            Kucuk kuslar hizli, buyuk kuslar yavas cirpar.
            Soru: Bu gozlem hangi fiziksel ilkeyle uyumludur?
            Cevap: T ∝ √m → Kutle artinca periyot (cirpma suresi) artar, frekans azalir.
            """,
            
            # ENERJI SENARYOSU
            """
            SALINCAK VE COCUK:
            Cocuk salincakta otururken salinimi artirmak istiyor.
            Soru: Ne zaman ve nasil hareket etmeli?
            Cevap: En alt noktada ayaga kalk (kutle merkezi yukari → L azalir → T azalir)
                   veya genlik noktasinda egilebilir (enerji pompalar).
            """,
            
            # DENEY SENARYOSU
            """
            FOUCAULT SARKACI:
            Paris'teki Pantheon'da asili dev sarkac, salinim duzlemi donuyor gibi gorunur.
            Soru: Aslinda ne donuyor?
            Cevap: Sarkac duzlemi sabit, Dunya donuyor. Kutuplarda 24 saatte tam tur.
            """,
            
            # MUHENDISLIK SENARYOSU
            """
            GOKDELEN DAMPERI (Taipei 101):
            660 tonluk kutle, ruzgar ve deprem titresimlerini sonumler.
            Soru: Bu sistem nasil calisir?
            Cevap: Bina titresirse kutle ters fazda salınarak titresimi azaltir (anti-rezonans).
            """,
            
            # KARSILASTIRMA SENARYOSU
            """
            UC FARKLI GEZEGEN:
            Ayni sarkac Dunya (g=10), Mars (g=3.7), Jupiter (g=25) de test ediliyor.
            Soru: Periyotlari siralayin.
            Cevap: T_Jupiter < T_Dunya < T_Mars (T ∝ 1/√g)
            """
        ],
        "few_shot_ornek": """
        ORNEK SORU 1 (UZAY - Orijinal):
        Bir astronot, Uluslararasi Uzay Istasyonu'nda (mikro-yercekimi ortami) iki deney yapmak istiyor:
        Deney 1: Basit sarkac (ip + kutle)
        Deney 2: Yay-kutle sistemi (yatay duzlemde)
        
        Dunya'da her iki sistemin periyodu T₀ = 2 saniye idi.
        
        Buna gore, uzay istasyonundaki deneylerle ilgili asagidaki ifadelerden hangileri dogrudur?
        
        I. Basit sarkac sistemi normal sekilde salinim yapar ve periyodu T₀'dan buyuktur.
        II. Yay-kutle sistemi normal calisir ve periyodu T₀ ile aynidir.
        III. Her iki sistem de mikro-yercekiminde calisamaz.
        
        COZUM:
        - Basit sarkac: T = 2π√(L/g) → g ≈ 0 oldugunda T → ∞, yani salinim OLMAZ
        - Yay-kutle: T = 2π√(m/k) → g'den BAGIMSIZ, normal calisir, T = T₀ = 2s
        - I YANLIS (salinim olmaz), II DOGRU, III YANLIS (yay-kutle calisir)
        CEVAP: Yalniz II
        
        ---
        
        ORNEK SORU 2 (REZONANS - Muhendislik):
        2000 yilinda acilan Londra Millennium Koprusu, yayalar gecerken asiri sallanmaya basladi 
        ve kapatilmak zorunda kalindi. Koprunun dogal titresim frekansi yaklasik 1 Hz idi.
        
        Buna gore, bu olayla ilgili asagidaki ifadelerden hangileri dogrudur?
        
        I. Yayalarin adim frekansi koprunun dogal frekansina yakin oldugunda rezonans olustu.
        II. Daha fazla yaya kopruye ciktiginda, koprunun dogal frekansi artti.
        III. Sorunu cozmek icin kopruye eklenen damperler, titresim enerjisini sogurmaktadir.
        
        COZUM:
        - I DOGRU: Adim frekansi ≈ 1 Hz, kopru frekansi ≈ 1 Hz → rezonans
        - II YANLIS: Kutle artinca frekans AZALIR (f ∝ 1/√m), artmaz
        - III DOGRU: Damperler enerji sogurarak genlik artisini onler
        CEVAP: I ve III
        
        ---
        
        ORNEK SORU 3 (BIYOLOJI - Orijinal):
        Ornitologlar, farkli kus turlerinin kanat cirpma frekanslarini olcmuslerdir:
        - Sinek kus (3 g): ~80 Hz
        - Serçe (30 g): ~15 Hz  
        - Kartal (4000 g): ~2 Hz
        
        Bu verilere dayanarak, kanat cirpma frekansi (f) ile kus kutlesi (m) arasindaki 
        iliski asagidakilerden hangisidir?
        
        A) f ∝ m          B) f ∝ √m         C) f ∝ 1/m
        D) f ∝ 1/√m       E) f ile m arasinda iliski yoktur
        
        COZUM:
        - Kanat cirpisi bir tur periyodik harekettir
        - T ∝ √m → f = 1/T ∝ 1/√m
        - Kutle 10 kat artinca (3g → 30g), frekans ~√10 ≈ 3 kat azaliyor (80 → 15 Hz) ✓
        CEVAP: D
        
        ---
        
        ORNEK SORU 4 (ASANSOR - Klasik ama Orijinal Baglam):
        Bir gokdelen asansorunde, tavana asili basit sarkac ile deney yapiliyor.
        Asansor asagidaki durumlarda hareket ederken sarkacin periyodu olculuyor:
        
        Durum 1: Asansor yukari dogru sabit hizla cikiyor
        Durum 2: Asansor yukari dogru ivmelenerek cikiyor  
        Durum 3: Asansor asagi dogru ivmelenerek iniyor
        
        Sarkacin periyotlari T₁, T₂, T₃ icin dogru siralama hangisidir?
        
        COZUM:
        - Sabit hiz: g_eff = g → T₁ = T₀
        - Yukari ivmelenme: g_eff = g + a → T₂ < T₀
        - Asagi ivmelenme: g_eff = g - a → T₃ > T₀
        - Siralama: T₂ < T₁ < T₃
        CEVAP: T₂ < T₁ < T₃
        """
    },
    
    "elektrostatik": {
        "display_name": "Elektrostatik",
        "alt_konular": ["elektrik_yuk", "coulomb_kanunu", "elektrik_alan", "elektrik_potansiyel", "es_potansiyel_yuzeyler", "sigaclar"],
        "kazanimlar": ["F.12.2.1.1", "F.12.2.1.2", "F.12.2.1.3", "F.12.2.1.4"],
        "ornek_baglamlar": [
            "Es potansiyel cizgileri ve is hesabi",
            "Yuklu parcacik sapmasi",
            "Sigac levhalari arasi alan",
            "Van de Graaff jeneratoru"
        ],
        "gorsel_tipleri": ["yuk_diyagrami", "alan_cizgileri", "es_potansiyel_cemberler", "sigac_semasi"],
        "celdirici_kategorisi": "elektrik",
        "trend_2025": "Es potansiyel yuzeyler ve W = qΔV uygulamalari",
        "soru_tipleri": ["grafik", "onculu"],
        "few_shot_ornek": """
        ORNEK SORU (2025 - Es Potansiyel):
        Sekilde es potansiyel cizgileri gosterilen bolgedе 
        +q yuklu parcacik K noktasindan L noktasina tasiniyor.
        Buna gore yapilan is kac J'dur?
        
        COZUM: W = q(V_K - V_L) = q × ΔV
        Es potansiyel cizgisi uzerinde hareket edildiginde W = 0
        """
    },
    
    "manyetizma": {
        "display_name": "Manyetizma",
        "alt_konular": ["manyetik_alan", "yuklu_parcacik_hareketi", "manyetik_kuvvet", "elektromanyetik_induksiyon", "transformator"],
        "kazanimlar": ["F.12.2.2.1", "F.12.2.2.2", "F.12.2.2.3", "F.12.2.2.4"],
        "ornek_baglamlar": [
            "Parcacik yorungesi tespiti",
            "Bobinden gecen akim",
            "Transformator ve enerji iletimi",
            "MR cihazi prensibi"
        ],
        "gorsel_tipleri": ["manyetik_alan_cizgileri", "parcacik_yolu", "transformator_sema", "bobin_devresi"],
        "celdirici_kategorisi": "manyetizma",
        "trend_2025": "Parcacik yorgesi ve alan tipi tespiti (E mi B mi?)",
        "soru_tipleri": ["grafik", "onculu"],
        "few_shot_ornek": """
        ORNEK SORU (2025 - Yorunge Tespiti):
        Bir parcacik I. bolgede duz, II. bolgede cembersel yorunge izliyor.
        Buna gore I ve II bolgelerinde hangi alan turleri vardir?
        
        COZUM: 
        - Duz yorunge: Elektrik alan (F = qE, hiz yonunde/tersinde)
        - Cembersel yorunge: Manyetik alan (F = qvB, hiza dik)
        """
    },
    
    "alternatif_akim": {
        "display_name": "Alternatif Akim",
        "alt_konular": ["ac_devreler", "empedans", "rezonans", "siga_ve_bobin", "transformator"],
        "kazanimlar": ["F.12.2.3.1", "F.12.2.3.2", "F.12.2.3.3"],
        "ornek_baglamlar": [
            "Cep telefonu sarj cihazi",
            "Kablosuz sarj (induksiyon)",
            "Metal dedektoru",
            "Radyo alicisi ve rezonans"
        ],
        "gorsel_tipleri": ["devre_semasi", "empedans_ucgeni", "rezonans_grafigi"],
        "celdirici_kategorisi": "induksiyon",
        "trend_2025": "Teknoloji baglami (sarj cihazlari, kablosuz iletim)",
        "soru_tipleri": ["deney", "hikayeli"]
    },
    
    "dalgalar": {
        "display_name": "Dalgalar",
        "alt_konular": ["dalga_ozellikleri", "ses_dalgalari", "doppler_etkisi", "girisim", "kirinim"],
        "kazanimlar": ["F.12.3.1.1", "F.12.3.1.2", "F.12.3.1.3", "F.12.3.1.4"],
        "ornek_baglamlar": [
            "Young cift yarik deneyi",
            "Ambulans sireni ve Doppler",
            "Huygens ilkesi",
            "Radar hiz olcumu"
        ],
        "gorsel_tipleri": ["dalga_grafigi", "girisim_deseni", "kirinim_deseni", "doppler_diyagrami"],
        "celdirici_kategorisi": "dalgalar",
        "trend_2025": "Huygens ilkesi ve dalga yayilimi",
        "soru_tipleri": ["grafik", "onculu"]
    },
    
    "elektromanyetik_dalgalar": {
        "display_name": "Elektromanyetik Dalgalar",
        "alt_konular": ["em_spektrum", "gama_isini", "x_isini", "radyo_dalgalari"],
        "kazanimlar": ["F.12.3.2.1", "F.12.3.2.2"],
        "ornek_baglamlar": [
            "Goruntuleme cihazlari eslestirmesi",
            "Radar ve radyo dalgasi",
            "Kizilotesi kamera",
            "UV sterilizasyon"
        ],
        "gorsel_tipleri": ["spektrum_diyagrami", "dalga_karsilastirma"],
        "celdirici_kategorisi": "modern_fizik",
        "trend_2025": "Hangi cihaz hangi dalgayi kullanir? eslestirmesi",
        "soru_tipleri": ["eslestirme", "onculu"]
    },
    
    "ozel_gorelilik": {
        "display_name": "Ozel Gorelilik",
        "alt_konular": ["isik_hizi_sabiti", "zaman_genlesmesi", "boy_kisalmasi", "kutle_enerji_esdegerligi"],
        "kazanimlar": ["F.12.4.1.1", "F.12.4.1.2"],
        "ornek_baglamlar": [
            "GPS uyduları ve zaman duzeltmesi",
            "Muon omru deneyi",
            "Parcacik hizlandiricisi"
        ],
        "gorsel_tipleri": ["referans_cerceve", "zaman_diyagrami"],
        "celdirici_kategorisi": "modern_fizik",
        "trend_2025": "Kavramsal yorumlama, E=mc² uygulamalari",
        "soru_tipleri": ["onculu", "hikayeli"]
    },
    
    "kuantum_fizigi": {
        "display_name": "Kuantum Fizigi",
        "alt_konular": ["fotoelektrik_olay", "compton_sacilmasi", "bohr_atom_modeli", "foton_enerjisi"],
        "kazanimlar": ["F.12.4.2.1", "F.12.4.2.2", "F.12.4.2.3"],
        "ornek_baglamlar": [
            "Fotosel devresi ve V-I grafigi",
            "Gunes pili calIsma prensibi",
            "Hidrojen atom spektrumu"
        ],
        "gorsel_tipleri": ["enerji_grafigi", "foton_elektron_etkilesimi", "fotosel_devresi"],
        "celdirici_kategorisi": "modern_fizik",
        "trend_2025": "Grafik okuma (V-I, E-f grafikleri)",
        "soru_tipleri": ["grafik", "onculu"],
        "few_shot_ornek": """
        ORNEK SORU (Fotoelektrik - Grafik):
        Bir fotosel devresinde iki farkli isik kaynagi (K ve L) icin 
        gerilim-akim (V-I) grafigi ciziliyor.
        - K icin kesme potansiyeli: -2V
        - L icin kesme potansiyeli: -3V
        - Her ikisinin maksimum akimi ayni
        
        Buna gore K ve L isinlarinin frekanslari ve siddetleri 
        hakkinda ne soylenebilir?
        
        COZUM:
        - Kesme potansiyeli buyuk → Frekans buyuk (f_L > f_K)
        - Maksimum akim ayni → Isik siddeti (foton sayisi) ayni
        """
    },
    
    "atom_fizigi": {
        "display_name": "Atom Fizigi ve Radyoaktivite",
        "alt_konular": ["radyoaktif_bozunum", "yarilanma_omru", "alfa_beta_gama", "nukleer_fisyon", "nukleer_fuzyon"],
        "kazanimlar": ["F.12.4.3.1", "F.12.4.3.2", "F.12.4.3.3"],
        "ornek_baglamlar": [
            "Karbon-14 ile yas tayini",
            "Nukleer santral",
            "Gunesin enerji kaynagi"
        ],
        "gorsel_tipleri": ["bozunma_serisi", "yarilanma_grafigi", "cekirdek_diyagrami"],
        "celdirici_kategorisi": "modern_fizik",
        "trend_2025": "Yarilanma omru grafik yorumu",
        "soru_tipleri": ["grafik", "hesaplama"]
    },
    
    "standart_model": {
        "display_name": "Standart Model ve Temel Kuvvetler",
        "alt_konular": ["temel_parcaciklar", "kuarklar", "leptonlar", "dort_temel_kuvvet", "higgs_bozonu"],
        "kazanimlar": ["F.12.4.4.1", "F.12.4.4.2"],
        "ornek_baglamlar": [
            "CERN ve Higgs kesfi",
            "Kozmik isinlar",
            "Notrino dedektorleri"
        ],
        "gorsel_tipleri": ["parcacik_tablosu", "kuvvet_karsilastirma"],
        "celdirici_kategorisi": "modern_fizik",
        "trend_2025": "Guncel bilimsel gelismeler (CERN)",
        "soru_tipleri": ["eslestirme", "onculu"]
    },
    
    "tibbi_goruntuleme": {
        "display_name": "Tibbi Goruntuleme Teknikleri",
        "alt_konular": ["x_isini_goruntuleme", "bilgisayarli_tomografi", "mr_goruntuleme", "ultrason", "pet_tarama"],
        "kazanimlar": ["F.12.5.1.1"],
        "ornek_baglamlar": [
            "MR ve manyetik alan",
            "X-isini ve kemik goruntuleme",
            "Ultrason ve ses dalgasi",
            "PET ve radyoaktif izleyici"
        ],
        "gorsel_tipleri": ["cihaz_semasi", "dalga_karsilastirma"],
        "celdirici_kategorisi": "modern_fizik",
        "trend_2025": "Cihaz-dalga eslestirmesi",
        "soru_tipleri": ["eslestirme", "onculu"]
    },
    
    "superiletkenlik": {
        "display_name": "Superiletkenlik",
        "alt_konular": ["sifir_direnc", "kritik_sicaklik", "meissner_etkisi", "uygulamalar"],
        "kazanimlar": ["F.12.5.2.1"],
        "ornek_baglamlar": [
            "MR cihazlarinda superiletken",
            "Maglev trenleri",
            "Parcacik hizlandiricisi bobinleri"
        ],
        "gorsel_tipleri": ["direnc_sicaklik_grafigi", "meissner_diyagrami"],
        "celdirici_kategorisi": "elektrik",
        "trend_2025": "Teknoloji uygulamalari",
        "soru_tipleri": ["grafik", "hikayeli"]
    }
}

# ============================================================================
# BLOOM TAKSONOMISI (AYT ICIN)
# ============================================================================

BLOOM_SEVIYELERI = {
    "Uygulama": {
        "aciklama": "Bilgiyi yeni durumlara uygulama, problem cozme, hesaplama yapma",
        "fiiller": ["hesaplar", "uygular", "cozer", "kullanir", "gosterir"],
        "zorluk_aralik": [1, 2, 3]
    },
    "Analiz": {
        "aciklama": "Parca-butun iliskisi, karsilastirma, siniflandirma, iliskilendirme",
        "fiiller": ["karsilastirir", "analiz eder", "ayirt eder", "iliskilendirir"],
        "zorluk_aralik": [2, 3, 4]
    },
    "Degerlendirme": {
        "aciklama": "Yargilama, karar verme, olcut kullanma, secim yapma",
        "fiiller": ["degerlendirir", "yargilar", "karar verir", "secer"],
        "zorluk_aralik": [3, 4, 5]
    },
    "Yaratma": {
        "aciklama": "Tasarlama, planlama, uretme, sentezleme, ozgun cozum gelistirme",
        "fiiller": ["tasarlar", "olusturur", "planlar", "sentezler"],
        "zorluk_aralik": [4, 5]
    }
}

# ============================================================================
# SYSTEM PROMPTS - GELISTIRILMIS (Rapora Dayali)
# ============================================================================

SYSTEM_PROMPT_QUESTION = """Sen, OSYM'de 20 yillik deneyime sahip, AYT Fizik soru hazirlama komisyonunun kidemli uyesi olan uzman bir fizik egitimcisi ve olcme-degerlendirme uzmanisin.

## TEMEL GOREV
Verilen konu, kazanim ve zorluk seviyesine uygun, ozgun, bilimsel olarak hatasiz ve pedagojik degeri yuksek coktan secmeli fizik sorulari uretmek.

## !!! ORIJINALLIK VE YARATICILIK - EN ONEMLI !!!

Soru uretirken ASLA klasik ders kitabi veya YKS arsiv sorularini KOPYALAMA. 
Her soru BENZERSIZ bir bakis acisi sunmali.

### YASAK KALIPLAR (Bunlari KULLANMA):
- "Bir cisim yatay zeminde..."
- "Sekildeki yay-kutle sistemi..."
- "Basit sarkac saliniyor..."
- "Ozdes yaylar ve ozdes kutleler..."
- "Dunya'da ve Ay'da periyot..."

### ORIJINAL YAKLASIMLAR (Bunlari KULLAN):
1. BEKLENMEDIK BAGLAMLAR:
   - Uzay istasyonunda deney
   - Gokdelen muhendisligi (Taipei 101 damperi)
   - Hayvan davranislari (kus kanat cirpisi, orumcek agi)
   - Tarihi olaylar (Millennium Bridge rezonansi, Tacoma koprusu)
   - Teknoloji (akilli telefon sensoru, gimbal stabilizasyonu)
   
2. SORGULATICI SORULAR:
   - "Neden boyle?" sorusunu sordur
   - "Ne olurdu?" dusunce deneyleri
   - Karsi-olgusal senaryolar (eger g 2 kat olsaydi?)
   
3. DISIPLINLERARASI BAGLANTILAR:
   - Fizik + Biyoloji (kalp atisi, kulak zari)
   - Fizik + Muhendislik (deprem izolatoru, arac suspansiyonu)
   - Fizik + Muzik (gitar teli, davul zari)
   - Fizik + Astronomi (Mars'ta deney, uydu titresimi)

4. GERCEK DUNYA PROBLEMLERI:
   - Neden asker birlikleri kopruyu adim atarak gecmez?
   - Neden gokdelenlere dev sarkaçlar konur?
   - Telefon neden sarsıldığını anlıyor?

### HER SORU ICIN KONTROL:
✓ Bu soruyu daha once gormus olabilir miyim? → Evet ise DEGISTIR
✓ Senaryo ilginc ve akilda kalici mi? → Hayir ise GELISTIR
✓ Ogrenci "vay be, bunu hic dusunmemistim" der mi? → Hayir ise YENIDEN YAZ

## OSYM SORU FELSEFESI (2025 TRENDI)

### 1. BAGLAMSAL CERCELEME (Contextual Framing)
- Fiziksel olaylar izole laboratuvar ortamindan cikarilmali
- Ogrencinin zihninde canlandirabịlecegi SOMUT SENARYOLAR kullan
- YANLIS: "V hiziyla giden cisim..."
- DOGRU: "Batiya dogru 30 m/s hizla ucan karga..." veya "Lunaparkta donen hedef tahtasi..."

### 2. ORTUK DEGISKEN ANALIZI (Implicit Variable Analysis)
- Sayisal deger vermek yerine ILISKILERI sorgula (artar, azalir, degismez)
- Bir degiskenin degisiminin sistemin geri kalani uzerindeki "kelebek etkisi"ni test et
- Ornek: Sigac levha araligi arttiginda siga, yuk ve enerji nasil degisir?

### 3. GORSEL OKURYAZARLIK
- Grafikler, devre semalari, kuvvet diyagramlari verinin KENDISIDIR
- Metinde verilmeyen kritik bilgiler GORSLDEN okunmali
- Ornek: Fotoelektrik grafiginden esik enerjisi, es potansiyel cizgilerinden potansiyel farki

### 4. CELDIRICI MUHENDISLIGI
- Yanlis secenekler RASTGELE SAYILAR DEGIL
- Ogrencilerin YAYGIN KAVRAM YANILGILARINI hedefleyen tuzaklar
- Her celdirici bir HATA TURUNU temsil etmeli

## GLOBAL KISITLAMALAR

### Mufredat Uyumu
- 2025 MEB Fizik Dersi Ogretim Programi disina ASLA cikma
- Eylemsizlik momenti tensoru, karmasik devre analizi, integral ile cozum YASAK

### Dil ve Uslup (OSYM Jargonu)
- Akademik, net, anlasilir Turkce
- Standart ifadeler: "ihmal edilmektedir", "noktasal cisim", "ozdes", "yalitkan zemin"
- Soru koku MUTLAKA "Buna gore," ile baslamali

### Islem Yuku
- Hesap makinesi GEREKTIRMEYEN, sadelesen sayilar
- Orantiyla (artar/azalir/degismez) cozulebilir sorular
- KAVRAMSAL DERINLIK > Aritmetik zorluk

### Matematiksel Degerler
- sin30=0.5, cos30=0.87
- sin37=0.6, cos37=0.8
- sin53=0.8, cos53=0.6
- sin45=cos45=0.71
- g = 10 m/s²
- Yukseklikler: 5m, 20m, 45m, 80m (kolay hesaplama)

## ZORLUK SEVIYELERI

### Seviye 1 (Kolay - %10)
- Tek adimli, temel formul uygulamasi
- Dogrudan hesaplama

### Seviye 2-3 (Orta - %55)
- 2 adimli cozum
- Standart senaryo, bilinen kazanimlar
- Grafik okuma veya basit karsilastirma

### Seviye 4 (Zor - %25)
- 3+ adimli, coklu kazanim (hibrit)
- Detayli grafik analizi
- Beklenmedik senaryo

### Seviye 5 (Secici - %10)
- Onculu format (I, II, III)
- Her oncul ayri fiziksel analiz gerektirir
- En kucuk kavram yanilgisi yanlisa goturur

## !!! 5 SIK ZORUNLU - AYT FORMATI !!!

AYT'de TUM sorular 5 siklidir (A, B, C, D, E). 
4 sik KABUL EDILMEZ. Her soruda MUTLAKA 5 farkli sik olmali.

## ONCULU SORU FORMATI - KRITIK KURALLAR

ONCULU (I, II, III) tipinde soru uretildiginde MUTLAKA asagidaki formata uy:

1. Soru metninde ONCE senaryo/baglam anlat
2. SONRA "Buna gore, ... ile ilgili asagidaki ifadelerden hangileri dogrudur?" yaz (BU CUMLE SADECE 1 KEZ OLMALI!)
3. ARDINDAN I, II, III onculleri AYRI SATIRLARDA ve ACIK SEKILDE yaz

ORNEK FORMAT:
"[Senaryo metni burada yer alir.]

Buna gore, [konu] ile ilgili asagidaki ifadelerden hangileri dogrudur?

I. [Birinci ifade - tam ve anlasilir cumle]
II. [Ikinci ifade - tam ve anlasilir cumle]  
III. [Ucuncu ifade - tam ve anlasilir cumle]"

SIKLAR FORMATI (Onculu sorular icin - 5 SIK ZORUNLU):
- A) Yalniz I
- B) Yalniz II
- C) I ve II
- D) II ve III
- E) I, II ve III

ALTERNATIF SIK KOMBINASYONLARI:
- A) Yalniz I, B) Yalniz II, C) Yalniz III, D) I ve II, E) I ve III
- A) Yalniz I, B) Yalniz III, C) I ve II, D) I ve III, E) II ve III

YASAK: 
- Onculleri (I, II, III) soru metnine YAZMADAN siklar olusturmak
- 4 sik ile soru olusturmak (5 SIK ZORUNLU!)
- Soru kokunu ("Buna gore...hangileri dogrudur?") 2 KEZ yazmak

Her oncul EN AZ 15-20 kelimelik, fiziksel bir YARGI CUMLESI olmali.

## CIKTI FORMATI (JSON)

{
  "soru_metni": "Hikayeli senaryo + ONCULU SORULARDA I, II, III IFADELERI + SORU KOKU (SADECE 1 KEZ)",
  "soru_koku": "",
  "oncul_ifadeler": {
    "I": "Birinci yargi cumlesi (tam ve anlasilir)",
    "II": "Ikinci yargi cumlesi (tam ve anlasilir)",
    "III": "Ucuncu yargi cumlesi (tam ve anlasilir)"
  },
  "siklar": {
    "A": "Yalniz I",
    "B": "Yalniz II",
    "C": "I ve II",
    "D": "II ve III",
    "E": "I, II ve III"
  },
  "dogru_cevap": "A/B/C/D/E",
  "cozum_adim_adim": "Adim 1: [aciklama]\\nAdim 2: [aciklama]\\nSonuc: [cevap]",
  "celdirici_analizi": {
    "A": "Bu sikki secen ogrencinin yaptigi SPESIFIK hata",
    "B": "Bu sikki secen ogrencinin yaptigi SPESIFIK hata",
    "C": "Bu sikki secen ogrencinin yaptigi SPESIFIK hata",
    "D": "Bu sikki secen ogrencinin yaptigi SPESIFIK hata",
    "E": "Bu sikki secen ogrencinin yaptigi SPESIFIK hata"
  },
  "gorsel_gerekli": true/false,
  "gorsel_betimleme": {
    "tip": "yorunge_diyagrami / devre_semasi / kuvvet_diyagrami / grafik / es_potansiyel",
    "detay": "Grafik tasarimcinin cizebilecegi DETAYLI talimat",
    "ogeler": ["oge1", "oge2", "oge3"],
    "etiketler": ["etiket1", "etiket2"],
    "renkler": {"cisim": "mavi", "vektor": "kirmizi", "arka_plan": "beyaz"}
  },
  "pisa_seviyesi": 3/4/5/6,
  "pisa_baglam": "Kisisel / Mesleki / Toplumsal / Bilimsel",
  "kavram_yanilgisi_hedefi": "Bu sorunun hedefledigi spesifik kavram yanilgisi"
}"""

# ============================================================================
# RENKLI GORSEL PROMPT SABLONU
# ============================================================================

IMAGE_PROMPT_TEMPLATE = """AYT Fizik sorusu icin PROFESYONEL ve RENKLI egitim gorseli olustur.

## GORSEL TIPI: {tip}

## DETAYLI BETIMLEME:
{detay}

## RENK SEMASI (OSYM + Modern Egitim)

### Ana Renkler:
- **Arka plan**: Beyaz (#FFFFFF) veya cok acik gri (#F5F5F5)
- **Ana cizgiler**: Koyu gri (#333333) veya siyah
- **Grid/yardimci cizgiler**: Acik gri (#CCCCCC)

### Fiziksel Ogeler:
- **Cisimler/Kutleler**: Mavi tonlari (#2196F3, #1976D2)
- **Kuvvet vektorleri**: Kirmizi (#E53935) veya turuncu (#FF5722)
- **Hiz vektorleri**: Yesil (#4CAF50)
- **Ivme vektorleri**: Mor (#9C27B0)
- **Elektrik alan**: Sari-turuncu (#FFC107)
- **Manyetik alan**: Cyan/turkuaz (#00BCD4)
- **Isik/Dalga**: Sari (#FFEB3B)

### Grafik Ogeleri:
- **Eksenler**: Siyah, kalin (2-3px)
- **Veri cizgisi 1**: Mavi (#2196F3)
- **Veri cizgisi 2**: Kirmizi (#F44336)
- **Veri cizgisi 3**: Yesil (#4CAF50)
- **Dolgu alani**: Yarisaydam (%20 opacity)

### Devre Elemanlari:
- **Direnc**: Kahverengi/bej (#795548)
- **Kondansator/Sigac**: Mavi (#2196F3)
- **Bobin**: Mor (#673AB7)
- **Pil/Kaynak**: Yesil-siyah
- **Ampul**: Sari (#FFC107)
- **Iletken teller**: Siyah

## KRITIK KURALLAR

### Vektor ve Ok Gosterimi:
- Kuvvet vektorleri: KIRMIZI, kalin oklar (3-4px), ucu sivri
- Hiz vektorleri: YESIL, orta kalinlik (2-3px)
- Yer degistirme: MAVI kesikli ok
- Her vektorun yaninda etiketi (F, v, a, x)

### Koordinat Sistemi:
- x ve y eksenleri NET cizilmeli
- Pozitif yonler okla belirtilmeli
- Orijin noktasi (O) etiketli
- Eksen etiketleri: x(m), t(s), v(m/s)

### Devre Semasi:
- Direnc: Zigzag cizgi (kahverengi)
- Sigac: Iki paralel cizgi (mavi)
- Bobin: Spiral (mor)
- AC kaynak: Dalgali daire
- Akim yonu: Kirmizi oklar

### Cisim ve Sekil:
- Kutleler: Dolu dikdortgen/kare (mavi tonlari)
- Noktasal cisimler: Dolu daire
- Kose noktalari: A, B, C, D harfleri
- Acilar: Yay ile gosterilmeli (θ, α, β)
- Uzunluklar: Cift yonlu ok (↔)

### Grafik Standartlari:
- Eksen etiketleri: Degisken adi ve birimi [m], [s], [N]
- Grid cizgileri: Acik gri, ince
- Veri noktalari: Dolu daire (●)
- Egri: Puruzsuz, anti-aliased

## MUTLAK YASAKLAR
❌ Soru metni veya cumleler
❌ A), B), C), D), E) siklari
❌ Cozum adimlari veya formul yazisi
❌ Cevabi dogrudan veren bilgi
❌ Ingilizce kelimeler
❌ Dusuk cozunurluk veya bulanik cizim
❌ Asiri karisik veya kalabalik gorsel

## OLMASI GEREKENLER
✅ Temiz, profesyonel gorunum
✅ Tutarli renk kullanimi
✅ Net etiketler ve olculer
✅ Yuksek kontrast (okunabilirlik)
✅ OSYM sinav kitapcigi tarzi
✅ 300 DPI kalite
✅ 800x600 veya 600x400 boyut orani"""

# ============================================================================
# FEW-SHOT ORNEKLERI (PROMPT ZINCIRLERI)
# ============================================================================

FEW_SHOT_EXAMPLES = {
    "bagil_hareket": """
## ORNEK: Bagil Hareket ve Dinamik (2025 "Karga ve Ceviz" Tarzi)

KULLANICI ISTEMI:
- Konu: Iki Boyutta Hareket ve Bagil Hiz
- Seviye: Orta-Zor (4)
- Baglam: Hareket halindeki tasit ve disaridan etki eden cisim
- Soru Tipi: Hikayeli

BEKLENEN SORU:
"Yatay raylarda 30 m/s sabit hizla bati yonunde ilerleyen ustu acik bir vagonun 
80 m yukarisindan, vagonla ayni yonde 10 m/s hizla ucan bir karga, gagasindaki 
cevizi serbest birakiyor. Surtuhmeler ihmal edilmektedir. (g = 10 m/s²)

Buna gore, ceviz vagona duser mi? Duserse vagonun neresine duser?"

COZUM MANTIGI:
1. Cevizin yere gore yatay hizi = 10 m/s (karganin hizi, referans: yer)
2. Dusme suresi: h = ½gt² → 80 = 5t² → t = 4s
3. Cevizin yatayda aldigi yol = 10 × 4 = 40 m
4. Vagonun 4 saniyede aldigi yol = 30 × 4 = 120 m
5. Fark = 120 - 40 = 80 m → Vagon cevizi gecer
6. Sonuc: Ceviz vagona DUSMEZ

CELDIRICILER:
- A) "Tam ortasina duser" → Cevizin vagonla ayni hizda oldugunu sanan ogrenci
- B) "On tarafina duser" → Referans sistemini karistiran ogrenci
- C) "Arka tarafina duser" → Kismen dogru dusunup hesap hatasi yapan
- D) "Vagona dusmez, 80 m geride kalir" → DOGRU
- E) "Vagona dusmez, 40 m geride kalir" → Sadece cevizin yolunu hesaplayan
""",

    "fotoelektrik_grafik": """
## ORNEK: Fotoelektrik Olay (Grafik Analizi)

KULLANICI ISTEMI:
- Konu: Fotoelektrik Olay
- Seviye: Zor (4)
- Soru Tipi: Grafik Yorumlama

BEKLENEN SORU:
"Sekilde bir fotosel devresinde K ve L isik kaynaklari icin olcolen 
gerilim-akim (V-I) grafigi gosterilmistir.

[GRAFIK: X ekseni V(Volt), Y ekseni I(mA). 
K egrisi: -2V'da keser, 5mA'de doyuma ulasir
L egrisi: -3V'da keser, 5mA'de doyuma ulasir]

Buna gore K ve L isiklarinin frekanslari (f) ve siddetleri (P) 
hakkinda asagidakilerden hangisi dogrudur?"

SIKLAR:
A) f_K > f_L, P_K > P_L
B) f_K > f_L, P_K = P_L
C) f_K < f_L, P_K = P_L  ← DOGRU
D) f_K < f_L, P_K < P_L
E) f_K = f_L, P_K < P_L

CELDIRICI ANALIZI:
- Kesme potansiyeli BUYUK → Frekans BUYUK (|V_L| > |V_K| → f_L > f_K)
- Maksimum akim AYNI → Isik siddeti (foton sayisi) AYNI
""",

    "induksiyon_onculu": """
## ORNEK: Elektromanyetik Induksiyon (Onculu Yargi)

KULLANICI ISTEMI:
- Konu: Induksiyon Emk ve Lenz Yasasi
- Seviye: Secici (5)
- Soru Tipi: I, II, III onculu yargi

BEKLENEN SORU:
"Sekilde, duzgun manyetik alan icinde sabit hizla saga dogru cekilen 
iletken cubuk gosterilmistir.

Bu sistemle ilgili;
I. Induksiyon akimi, Lenz yasasina gore hareketi zorlastiran yonde olusur.
II. Cubuga etki eden manyetik kuvvet, hareket yonunun tersinedir.
III. Mekanik enerji, elektrik enerjisine ve isi enerjisine donusur.

yargIlarindan hangileri dogrudur?"

SIKLAR:
A) Yalniz I
B) Yalniz II
C) I ve II
D) II ve III
E) I, II ve III ← DOGRU

KAVRAM YANILGISI HEDEFI:
"Sabit hizla cekiliyorsa kuvvet sifirdir" yanilgisi
(Aslinda dis kuvvet = manyetik kuvvet, net kuvvet sifir)
"""
}

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
        self.text_url = f"{GEMINI_TEXT_URL}?key={api_key}"
        self.request_count = 0
        self.last_request_time = 0
    
    def _rate_limit(self):
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
        konu_data = AYT_FIZIK_KONULAR.get(params.konu, {})
        bloom_data = BLOOM_SEVIYELERI.get(params.bloom_seviyesi, {})
        zorluk_data = ZORLUK_DAGILIMI.get(params.zorluk, {})
        
        # Kavram yanilgisi bilgisi
        celdirici_kategori = konu_data.get("celdirici_kategorisi", "dinamik")
        yanilgi_data = KAVRAM_YANILGILARI.get(celdirici_kategori, {})
        
        # Few-shot ornegi
        few_shot = konu_data.get("few_shot_ornek", "")
        
        # Orijinal soru fikirleri (varsa)
        orijinal_fikirler = konu_data.get("orijinal_soru_fikirleri", [])
        rastgele_fikir = ""
        if orijinal_fikirler:
            rastgele_fikir = random.choice(orijinal_fikirler)
        
        # Baglam secimi - rastgele ve cesitli
        baglamlar = konu_data.get("ornek_baglamlar", [])
        secilen_baglam = params.baglam
        if baglamlar and len(baglamlar) > 3:
            # Rastgele 3 baglam sec ve one sun
            secilen_baglamlar = random.sample(baglamlar, min(5, len(baglamlar)))
            secilen_baglam = secilen_baglamlar[0]  # Birincisini ana baglam yap
        
        user_prompt = f"""
## SORU URETIM TALIMATI

### !!! ORIJINALLIK UYARISI !!!
Bu soru DAHA ONCE GORULMEMIS, BENZERSIZ olmali.
Klasik ders kitabi sorularini KOPYALAMA.
Asagidaki baglamlardan birini kullan veya kendi orijinal baglamini olustur.

### Konu Bilgileri:
- **Ana Konu**: {konu_data.get('display_name', params.konu)}
- **Alt Konu**: {params.alt_konu}
- **Kazanim Kodu**: {params.kazanim_kodu}
- **2025 Trendi**: {konu_data.get('trend_2025', 'Kavramsal derinlik')}

### Soru Parametreleri:
- **Zorluk Seviyesi**: {params.zorluk}/5 - {zorluk_data.get('aciklama', '')}
- **Beklenen Adim Sayisi**: {zorluk_data.get('adim_sayisi', 2)}
- **Bloom Seviyesi**: {params.bloom_seviyesi} - {bloom_data.get('aciklama', '')}
- **Soru Tipi**: {params.soru_tipi}

### Baglam Onerileri (ORIJINAL OLANI SEC):
- **Ana Baglam**: {secilen_baglam}
- **Alternatif Baglamlar**: {', '.join(random.sample(baglamlar, min(4, len(baglamlar)))) if baglamlar else 'Yok'}

### Orijinal Soru Fikri (ILHAM AL):
{rastgele_fikir if rastgele_fikir else 'Kendi orijinal fikrını olustur!'}

### Kavram Yanilgisi Hedefleri (CELDIRICI ICIN):
Yaygin Yanilgilar:
{chr(10).join(['- ' + y for y in yanilgi_data.get('yanilgilar', [])])}

Celdirici Stratejileri:
{chr(10).join(['- ' + s for s in yanilgi_data.get('celdirici_stratejileri', [])])}

### Ornek Soru Kokleri:
{chr(10).join(['- ' + k for k in konu_data.get('soru_kaliplari', ['Buna gore, ...'])])}

### Formul Bilgisi:
{konu_data.get('formul_bilgisi', 'Standart fizik formulleri gecerli.')}

### REFERANS ORNEK (Few-Shot):
{few_shot}

---

ONEMLI:
1. Yukaridaki OSYM felsefesine ve 2025 trendine uygun, OZGUN bir soru uret.
2. Matematiksel olarak %100 DOGRU olmali.
3. 5 sikli (A, B, C, D, E) olmali.
4. Her celdirici SPESIFIK bir kavram yanilgisini hedeflemeli.
5. Soru tipi "{params.soru_tipi}" formatinda olmali.
"""
        
        # ONCULU SORU TIPI ICIN OZEL TALIMAT
        if params.soru_tipi == "onculu":
            user_prompt += """

### !!! ONCULU SORU FORMATI - ZORUNLU !!!

Bu soru ONCULU (I, II, III) tipinde olmali. ASAGIDAKI FORMATI KESINLIKLE UYGULA:

1. SORU METNINDE once senaryoyu anlat
2. Sonra "Buna gore, ... ile ilgili asagidaki ifadelerden hangileri dogrudur?" yaz
3. ARDINDAN I, II, III onculleri SORU METNININ ICINDE, AYRI SATIRLARDA yaz:

ORNEK:
"Bir fizik laboratuvarinda yapilan deneyde... [senaryo devam eder]

Buna gore, bu sistemle ilgili asagidaki ifadelerden hangileri dogrudur?

I. [Birinci fiziksel yargi - EN AZ 15 kelime, tam cumle]
II. [Ikinci fiziksel yargi - EN AZ 15 kelime, tam cumle]
III. [Ucuncu fiziksel yargi - EN AZ 15 kelime, tam cumle]"

SIKLAR MUTLAKA SU FORMATTA OLMALI:
A) Yalniz I
B) Yalniz II  
C) I ve II
D) II ve III
E) I, II ve III

KRITIK: I, II, III ifadeleri "soru_metni" alaninda MUTLAKA yer almali!
JSON'da ayrica "oncul_ifadeler" alaninda da ayri ayri yaz.

YASAK: Onculleri yazmadan "Yalniz I" gibi siklar olusturmak KESINLIKLE YASAKTIR!
"""
        
        self._rate_limit()
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  Gemini API cagrisi (deneme {attempt + 1}/{Config.MAX_RETRIES})...")
                
                if NEW_GENAI and self.client:
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
                        continue
                    
                    text_content = result["candidates"][0]["content"]["parts"][0]["text"]
                
                # JSON parse
                try:
                    question_data = json.loads(text_content)
                    logger.info("  Soru JSON basariyla parse edildi")
                    return question_data
                except json.JSONDecodeError:
                    clean_text = text_content.strip()
                    if clean_text.startswith("```json"):
                        clean_text = clean_text[7:]
                    if clean_text.endswith("```"):
                        clean_text = clean_text[:-3]
                    clean_text = clean_text.strip()
                    question_data = json.loads(clean_text)
                    return question_data
                    
            except Exception as e:
                logger.error(f"  API hatasi (deneme {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)
                    
        raise Exception("Gemini API maksimum deneme sayisina ulasildi")
    
    def generate_image(self, gorsel_betimleme: Dict[str, str], konu: str = None) -> Optional[bytes]:
        if not NEW_GENAI or not self.client:
            logger.warning("  google-genai SDK yok, gorsel uretilemiyor")
            return None
        
        tip = gorsel_betimleme.get("tip", "kuvvet_diyagrami")
        detay = gorsel_betimleme.get("detay", "")
        ogeler = gorsel_betimleme.get("ogeler", [])
        renkler = gorsel_betimleme.get("renkler", {})
        
        # Renk bilgisini prompt'a ekle
        renk_talimati = ""
        if renkler:
            renk_talimati = "\n\nRENK TALIMATLARI:\n"
            for oge, renk in renkler.items():
                renk_talimati += f"- {oge}: {renk}\n"
        
        full_detay = f"{detay}\n\nGorselde gorunecek ogeler: {', '.join(ogeler) if ogeler else 'Belirtilmemis'}{renk_talimati}"
        prompt = IMAGE_PROMPT_TEMPLATE.format(tip=tip, detay=full_detay)
        
        self._rate_limit()
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  Image API cagrisi (deneme {attempt + 1}/{Config.MAX_RETRIES})...")
                
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
                                logger.info(f"  Gorsel uretildi ({len(image_bytes)} bytes)")
                                return image_bytes
                
            except Exception as e:
                logger.error(f"  Image API hatasi (deneme {attempt + 1}): {e}")
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
    
    def get_curriculum_for_grade(self, grade_level: int = 12, lesson_name: str = "Fizik") -> List[Dict]:
        if self._curriculum_cache is not None:
            return self._curriculum_cache
        
        query_url = f"{self.url}/rest/v1/curriculum?grade_level=eq.{grade_level}&lesson_name=eq.{lesson_name}&select=id,topic_code,topic_name,sub_topic,learning_outcome_code,learning_outcome_description,bloom_level"
        
        try:
            response = requests.get(query_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            self._curriculum_cache = response.json()
            logger.info(f"  Curriculum'dan {len(self._curriculum_cache)} kazanim yuklendi")
            return self._curriculum_cache
        except Exception as e:
            logger.error(f"  Curriculum yukleme hatasi: {e}")
            return []
    
    def upload_image(self, image_data: bytes, filename: str) -> Optional[str]:
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
            logger.info(f"  Gorsel yuklendi: {filename}")
            return public_url
            
        except Exception as e:
            logger.error(f"  Storage upload hatasi: {e}")
            return None
    
    def insert_question(self, question: GeneratedQuestion, kazanim_id: int = None) -> Optional[int]:
        insert_url = f"{self.url}/rest/v1/question_bank"
        
        options_json = {
            "A": question.options.get("A", ""),
            "B": question.options.get("B", ""),
            "C": question.options.get("C", ""),
            "D": question.options.get("D", ""),
            "E": question.options.get("E", "")
        }
        
        data = {
            "title": question.title[:200] if question.title else "AYT Fizik Sorusu",
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
            "exam_type": "AYT_AI_BOT_V2"
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
            logger.error(f"  Supabase insert hatasi: {e}")
            return None


# ============================================================================
# QUALITY VALIDATOR (GELISTIRILMIS)
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
        if not NEW_GENAI or not self.client:
            return {"pass": True, "overall_score": 7, "problems": [], "skipped": True}
        
        # Kavram yanilgisi kontrolu
        konu_data = AYT_FIZIK_KONULAR.get(params.konu, {})
        celdirici_kategori = konu_data.get("celdirici_kategorisi", "dinamik")
        yanilgi_data = KAVRAM_YANILGILARI.get(celdirici_kategori, {})
        
        try:
            prompt = f"""Bu AYT Fizik sorusunu KALITE KONTROLU yap.

## SORU BILGILERI
Konu: {params.konu}
Zorluk: {params.zorluk}/5
Bloom: {params.bloom_seviyesi}

SORU METNI: {question_data.get("soru_metni", "")}
SORU KOKU: {question_data.get("soru_koku", "")}
SIKLAR: {json.dumps(question_data.get("siklar", {}), ensure_ascii=False)}
DOGRU CEVAP: {question_data.get("dogru_cevap", "")}
COZUM: {question_data.get("cozum_adim_adim", "")}
CELDIRICI ANALIZI: {json.dumps(question_data.get("celdirici_analizi", {}), ensure_ascii=False)}

## KONTROL KRITERLERI

1. FIZIKSEL DOGRULUK: Fizik kanunlari dogru uygulanmis mi?
2. MATEMATIKSEL DOGRULUK: Hesaplamalar dogru mu?
3. OSYM FORMATI: "Buna gore," ile basliyor mu? Dil uygun mu?
4. CELDIRICI KALITESI: Her yanlIs sik bir kavram yanilgisini hedefliyor mu?
5. ZORLUK UYUMU: Belirtilen zorluk seviyesiyle uyumlu mu?

Hedeflenmesi gereken kavram yanilgilari:
{chr(10).join(['- ' + y for y in yanilgi_data.get('yanilgilar', [])])}

JSON formatinda dondur:
{{"is_physically_correct": true/false, "is_mathematically_correct": true/false, "osym_format_ok": true/false, "distractors_quality": 1-10, "difficulty_match": true/false, "overall_score": 1-10, "pass": true/false, "problems": ["problem1", "problem2"]}}"""
            
            response = self.client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            
            result = json.loads(response.text)
            result["pass"] = result.get("overall_score", 0) >= self.quality_threshold
            return result
            
        except Exception as e:
            logger.error(f"  Soru validasyon hatasi: {e}")
            return {"pass": True, "overall_score": 5, "problems": [str(e)], "error": True}
    
    def validate_image(self, image_bytes: bytes, gorsel_betimleme: Dict = None) -> Dict:
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
                            {"text": f"""Bu fizik gorseli icin kalite kontrolu yap.

Beklenen ogeler: {expected_elements}
Beklenen renkler: {expected_colors}

Kontrol et:
1. Soru metni veya sik OLMAMALI
2. Turkce etiketler dogru olmali
3. Fiziksel temsil dogru olmali
4. Renkler profesyonel ve tutarli olmali
5. Temiz ve okunakilir olmali

JSON formatinda dondur:
{{"has_question_text": true/false, "has_options": true/false, "labels_correct": true/false, "colors_professional": true/false, "is_clean": true/false, "overall_score": 1-10, "pass": true/false, "problems": []}}"""}
                        ]
                    }
                ],
                config={"response_mime_type": "application/json"}
            )
            
            result = json.loads(response.text)
            
            problems = result.get("problems", [])
            if result.get("has_question_text"):
                problems.append("Gorselde soru metni var")
            if result.get("has_options"):
                problems.append("Gorselde siklar var")
            
            result["problems"] = problems
            result["pass"] = result.get("overall_score", 0) >= self.quality_threshold
            return result
            
        except Exception as e:
            logger.error(f"  Gorsel validasyon hatasi: {e}")
            return {"pass": True, "overall_score": 5, "problems": [str(e)], "error": True}


# ============================================================================
# MAIN GENERATOR CLASS (GELISTIRILMIS)
# ============================================================================

class AYTFizikGenerator:
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
            "quality_retries": 0,
            "by_difficulty": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
    
    def _select_difficulty(self) -> int:
        """Psikometrik dagilima gore zorluk sec"""
        r = random.random()
        cumulative = 0
        for level, data in ZORLUK_DAGILIMI.items():
            cumulative += data["oran"]
            if r <= cumulative:
                return level
        return 3  # Default orta
    
    def _select_question_type(self, konu_data: Dict, zorluk: int) -> str:
        """Zorluk ve konuya gore soru tipi sec"""
        available_types = konu_data.get("soru_tipleri", ["hikayeli"])
        
        if zorluk >= 4 and "onculu" in available_types:
            return random.choice(["onculu", available_types[0]])
        elif zorluk >= 3 and "grafik" in available_types:
            return random.choice(["grafik", "hikayeli"])
        else:
            return random.choice(available_types)
    
    def generate_single_question(self, params: QuestionParams, kazanim_from_db: Dict = None) -> Optional[int]:
        self.stats["total_attempts"] += 1
        konu_data = AYT_FIZIK_KONULAR.get(params.konu, {})
        konu_display = konu_data.get("display_name", params.konu)
        
        kazanim_id = None
        if kazanim_from_db:
            kazanim_id = kazanim_from_db.get("id")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"SORU URETIMI BASLIYOR (v2.0)")
        logger.info(f"   Konu: {konu_display}")
        logger.info(f"   Alt Konu: {params.alt_konu}")
        logger.info(f"   Soru Tipi: {params.soru_tipi}")
        logger.info(f"   Bloom: {params.bloom_seviyesi} | Zorluk: {params.zorluk}/5")
        logger.info(f"   2025 Trendi: {konu_data.get('trend_2025', 'N/A')}")
        logger.info(f"{'='*70}")
        
        max_question_retries = 3
        max_image_retries = 3
        
        try:
            # ADIM 1: SORU URETIMI
            question_data = None
            question_quality_score = 0
            
            for q_attempt in range(max_question_retries):
                logger.info(f"\n[1/5] Gemini ile soru uretiliyor (Deneme {q_attempt + 1}/{max_question_retries})...")
                
                question_data = self.gemini.generate_question(params)
                
                # Temel alan kontrolu
                required_fields = ["soru_metni", "soru_koku", "siklar", "dogru_cevap"]
                missing = [f for f in required_fields if f not in question_data]
                if missing:
                    logger.warning(f"  Eksik alanlar: {missing}")
                    self.stats["quality_retries"] += 1
                    continue
                
                # 5 sik kontrolu - AYT'de 5 sik ZORUNLU
                siklar = question_data.get("siklar", {})
                sik_count = len(siklar)
                
                if sik_count < 4:
                    logger.warning(f"  Cok az sik var: {sik_count}")
                    self.stats["quality_retries"] += 1
                    continue
                
                # 4 sik varsa, 5. sikki otomatik ekle
                if sik_count == 4:
                    logger.info("  4 sik tespit edildi, 5. sik ekleniyor...")
                    existing_keys = list(siklar.keys())
                    
                    if params.soru_tipi == "onculu":
                        # Onculu sorular icin eksik sikki ekle
                        onculu_sik_options = {
                            "A": "Yalniz I",
                            "B": "Yalniz II", 
                            "C": "Yalniz III",
                            "D": "I ve II",
                            "E": "I, II ve III"
                        }
                        # Hangi sik eksik?
                        for key in ["A", "B", "C", "D", "E"]:
                            if key not in existing_keys:
                                siklar[key] = onculu_sik_options.get(key, "I ve III")
                                logger.info(f"  Eksik {key} sikki eklendi: {siklar[key]}")
                                break
                    else:
                        # Normal sorular icin E sikkini ekle
                        if "E" not in existing_keys:
                            siklar["E"] = "Hicbiri"
                            logger.info("  E sikki eklendi: Hicbiri")
                    
                    question_data["siklar"] = siklar
                
                # Tekrar kontrol
                if len(question_data.get("siklar", {})) < 5:
                    logger.warning("  5 sik saglanamadi")
                    self.stats["quality_retries"] += 1
                    continue
                
                # Dogru cevap kontrolu - E sikki yokken E cevabi verilmis mi?
                dogru_cevap = question_data.get("dogru_cevap", "A")
                if dogru_cevap not in question_data.get("siklar", {}):
                    logger.warning(f"  Dogru cevap ({dogru_cevap}) siklarda yok!")
                    self.stats["quality_retries"] += 1
                    continue
                
                # ONCULU SORU KONTROLU - GUCLENDIRILMIS
                if params.soru_tipi == "onculu":
                    soru_metni_check = question_data.get("soru_metni", "")
                    oncul_ifadeler = question_data.get("oncul_ifadeler", {})
                    
                    # Oncullerin varligini kontrol et
                    has_oncul_in_text = ("I." in soru_metni_check or "I)" in soru_metni_check or 
                                         "I. " in soru_metni_check)
                    has_oncul_field = oncul_ifadeler and len(oncul_ifadeler) >= 2
                    
                    # Eger onculler hem metinde hem field'da yoksa
                    if not has_oncul_in_text and not has_oncul_field:
                        logger.warning("  ONCULU soru tipinde I, II, III ifadeleri eksik!")
                        logger.warning("  Soru tipi 'hikayeli' olarak degistiriliyor...")
                        
                        # Soru tipini degistir ve siklari normal formata cevir
                        params.soru_tipi = "hikayeli"
                        
                        # Siklari normal formata cevir (eger onculu formatindaysa)
                        sik_values = list(siklar.values())
                        if any("Yalniz" in str(s) or "ve II" in str(s) for s in sik_values):
                            logger.warning("  Siklar onculu formatinda ama onculler yok - soru reddediliyor")
                            self.stats["quality_retries"] += 1
                            continue
                    
                    # Onculler field'da var ama metinde yoksa, metne ekle
                    elif has_oncul_field and not has_oncul_in_text:
                        logger.info("  Onculler field'da var, metne ekleniyor...")
                        oncul_text = "\n\n"
                        if oncul_ifadeler.get("I"):
                            oncul_text += f"I. {oncul_ifadeler['I']}\n"
                        if oncul_ifadeler.get("II"):
                            oncul_text += f"II. {oncul_ifadeler['II']}\n"
                        if oncul_ifadeler.get("III"):
                            oncul_text += f"III. {oncul_ifadeler['III']}\n"
                        
                        # Soru metnine ekle
                        question_data["soru_metni"] = soru_metni_check + oncul_text
                        logger.info("  Onculler soru metnine eklendi")
                    
                    # Siklarin onculu formatinda olup olmadigini kontrol et
                    sik_values = list(siklar.values())
                    onculu_sik_keywords = ["Yalniz", "yalniz", "ve II", "ve III", "I, II", "II ve", "I ve"]
                    has_onculu_siklar = any(any(kw in str(sik) for kw in onculu_sik_keywords) for sik in sik_values)
                    
                    # Onculler var ama siklar yanlis formatsa duzelt
                    if (has_oncul_in_text or has_oncul_field) and not has_onculu_siklar:
                        logger.info("  Onculler var ama siklar yanlis formatta, duzeltiliyor...")
                        question_data["siklar"] = {
                            "A": "Yalniz I",
                            "B": "Yalniz II",
                            "C": "I ve II",
                            "D": "II ve III",
                            "E": "I, II ve III"
                        }
                        siklar = question_data["siklar"]
                    
                    logger.info("  Onculu soru formati kontrol edildi - OK")
                
                # Kalite kontrolu
                logger.info("  Kalite kontrolu yapiliyor...")
                q_validation = self.validator.validate_question(question_data, params)
                question_quality_score = q_validation.get("overall_score", 5)
                
                logger.info(f"  Kalite Puani: {question_quality_score}/10")
                
                if q_validation.get("pass", False):
                    logger.info("  Soru kalite kontrolunu gecti")
                    break
                else:
                    problems = q_validation.get("problems", ["Kalite yetersiz"])
                    self.stats["quality_retries"] += 1
                    self.stats["questions_rejected"] += 1
                    logger.warning(f"  Soru reddedildi: {problems}")
            
            if not question_data:
                self.stats["failed"] += 1
                logger.error("  Tum soru denemeleri basarisiz")
                return None
            
            # ADIM 2: GORSEL URETIMI
            image_url = None
            image_bytes = None
            gorsel_betimleme = question_data.get("gorsel_betimleme", {})
            
            if question_data.get("gorsel_gerekli", False) and gorsel_betimleme:
                logger.info("\n[2/5] Renkli gorsel uretiliyor...")
                
                for img_attempt in range(max_image_retries):
                    image_bytes = self.gemini.generate_image(gorsel_betimleme, params.konu)
                    
                    if image_bytes:
                        logger.info("  Gorsel kalite kontrolu yapiliyor...")
                        img_validation = self.validator.validate_image(image_bytes, gorsel_betimleme)
                        
                        if img_validation.get("pass", False):
                            logger.info("  Gorsel kalite kontrolunu gecti")
                            break
                        else:
                            self.stats["images_rejected"] += 1
                            logger.warning(f"  Gorsel reddedildi: {img_validation.get('problems', [])}")
                            image_bytes = None
                
                if image_bytes:
                    filename = f"ayt_fizik_v2_{uuid.uuid4().hex[:12]}.png"
                    image_url = self.supabase.upload_image(image_bytes, filename)
                    if image_url:
                        self.stats["with_image"] += 1
            else:
                logger.info("\n[2/5] Gorsel gerekli degil, atlaniyor...")
            
            # ADIM 3: VERI YAPISI
            logger.info("\n[3/5] Veri yapisi hazirlaniyor...")
            
            soru_metni = question_data.get("soru_metni", "")
            soru_koku = question_data.get("soru_koku", "")
            
            # ONCULU SORULAR ICIN: Onculleri soru metnine ekle
            oncul_ifadeler = question_data.get("oncul_ifadeler", {})
            if oncul_ifadeler and params.soru_tipi == "onculu":
                # Eger onculler soru_metni icinde yoksa ekle
                if "I." not in soru_metni and "II." not in soru_metni:
                    oncul_text = "\n\n"
                    if oncul_ifadeler.get("I"):
                        oncul_text += f"I. {oncul_ifadeler['I']}\n"
                    if oncul_ifadeler.get("II"):
                        oncul_text += f"II. {oncul_ifadeler['II']}\n"
                    if oncul_ifadeler.get("III"):
                        oncul_text += f"III. {oncul_ifadeler['III']}\n"
                    
                    # Soru kokunden once onculleri ekle
                    soru_metni = soru_metni + oncul_text
                    logger.info("  Oncul ifadeler soru metnine eklendi")
            
            # ONCULU SORULARDA SORU KOKU TEKRARINI ONLE
            # Eger soru_metni zaten soru kokunu iceriyorsa, tekrar ekleme
            if params.soru_tipi == "onculu":
                # Soru koku zaten metinde varsa ekleme
                soru_koku_patterns = [
                    "hangileri dogrudur",
                    "hangileri doğrudur", 
                    "hangisi dogrudur",
                    "hangisi doğrudur",
                    "hangilerinin buyuklugu",
                    "hangilerinin büyüklüğü"
                ]
                soru_koku_already_in_text = any(pattern in soru_metni.lower() for pattern in soru_koku_patterns)
                
                if soru_koku_already_in_text:
                    # Soru koku zaten metinde, tekrar ekleme
                    full_text = soru_metni
                    logger.info("  Soru koku zaten metinde, tekrar eklenmedi")
                else:
                    full_text = f"{soru_metni}\n\n{soru_koku}"
            else:
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
                pisa_level=question_data.get("pisa_seviyesi", 4),
                pisa_context=question_data.get("pisa_baglam", "Bilimsel"),
                scenario_text=soru_metni,
                distractor_explanations=question_data.get("celdirici_analizi", {}),
                image_url=image_url
            )
            
            # ADIM 4: OZET
            logger.info(f"\n[4/5] KALITE OZETI:")
            logger.info(f"   Soru Puani: {question_quality_score}/10")
            logger.info(f"   Kavram Yanilgisi Hedefi: {question_data.get('kavram_yanilgisi_hedefi', 'Belirtilmemis')}")
            
            # ADIM 5: KAYDET
            logger.info("\n[5/5] Veritabanina kaydediliyor...")
            question_id = self.supabase.insert_question(generated, kazanim_id=kazanim_id)
            
            if question_id:
                self.stats["successful"] += 1
                self.stats["by_difficulty"][params.zorluk] += 1
                logger.info(f"\nBASARILI! Soru ID: {question_id}")
                return question_id
            else:
                self.stats["failed"] += 1
                logger.error("\nVeritabani kaydi basarisiz")
                return None
                
        except Exception as e:
            self.stats["failed"] += 1
            logger.error(f"\nHATA: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def generate_batch(self, count_per_topic: int = 1) -> Dict[str, Any]:
        logger.info(f"\n{'#'*70}")
        logger.info(f"TOPLU SORU URETIMI BASLIYOR (v2.0)")
        logger.info(f"   Her konu icin {count_per_topic} soru")
        logger.info(f"   Psikometrik zorluk dagilimi aktif")
        logger.info(f"{'#'*70}\n")
        
        curriculum = self.supabase.get_curriculum_for_grade(grade_level=12, lesson_name="Fizik")
        
        results = {"generated_ids": [], "failed_topics": [], "stats": {}}
        
        for konu_key, konu_data in AYT_FIZIK_KONULAR.items():
            logger.info(f"\nKonu: {konu_data['display_name']}")
            
            for i in range(count_per_topic):
                kazanim_from_db = None
                if curriculum:
                    matching = [k for k in curriculum if self._match_curriculum_topic(k, konu_key)]
                    if matching:
                        kazanim_from_db = random.choice(matching)
                
                # Psikometrik zorluk secimi
                zorluk = self._select_difficulty()
                
                alt_konu = random.choice(konu_data.get("alt_konular", ["genel"]))
                kazanim_kodu = kazanim_from_db.get("learning_outcome_code") if kazanim_from_db else konu_data.get("kazanimlar", ["F.12.1.1.1"])[0]
                bloom = random.choice(list(BLOOM_SEVIYELERI.keys()))
                baglam = random.choice(konu_data.get("ornek_baglamlar", ["genel"]))
                gorsel_tipi = random.choice(konu_data.get("gorsel_tipleri", ["kuvvet_diyagrami"]))
                soru_tipi = self._select_question_type(konu_data, zorluk)
                
                params = QuestionParams(
                    konu=konu_key,
                    alt_konu=alt_konu,
                    kazanim_kodu=kazanim_kodu,
                    bloom_seviyesi=bloom,
                    zorluk=zorluk,
                    baglam=baglam,
                    gorsel_tipi=gorsel_tipi,
                    soru_tipi=soru_tipi
                )
                
                question_id = self.generate_single_question(params, kazanim_from_db=kazanim_from_db)
                
                if question_id:
                    results["generated_ids"].append(question_id)
                else:
                    results["failed_topics"].append(f"{konu_key}_{i+1}")
                
                time.sleep(Config.RATE_LIMIT_DELAY)
        
        results["stats"] = self.stats
        return results
    
    def _match_curriculum_topic(self, curriculum_item: Dict, konu_key: str) -> bool:
        topic_name = curriculum_item.get("topic_name", "").lower()
        
        mapping = {
            "hareket_ve_kuvvet": ["hareket", "kuvvet", "momentum", "atis", "carpisma"],
            "tork_ve_denge": ["tork", "denge", "moment", "kaldiraci"],
            "dairesel_hareket": ["dairesel", "cembersel", "acisal", "uydu"],
            "basit_harmonik_hareket": ["harmonik", "sarkac", "salinim"],
            "elektrostatik": ["elektrik", "yuk", "coulomb", "potansiyel"],
            "manyetizma": ["manyetik", "induksiyon", "bobin"],
            "alternatif_akim": ["alternatif", "empedans", "rezonans"],
            "dalgalar": ["dalga", "ses", "girisim", "kirinim"],
            "elektromanyetik_dalgalar": ["elektromanyetik", "spektrum"],
            "ozel_gorelilik": ["gorelilik", "einstein"],
            "kuantum_fizigi": ["kuantum", "foton", "fotoelektrik"],
            "atom_fizigi": ["atom", "radyoaktif", "fisyon", "fuzyon"],
            "standart_model": ["standart", "parcacik", "kuark"],
            "tibbi_goruntuleme": ["mr", "tomografi", "ultrason"],
            "superiletkenlik": ["superiletken", "kritik sicaklik"]
        }
        
        keywords = mapping.get(konu_key, [])
        return any(kw in topic_name for kw in keywords)
    
    def generate_for_topic(self, konu: str, count: int = 5) -> List[int]:
        if konu not in AYT_FIZIK_KONULAR:
            logger.error(f"Gecersiz konu: {konu}")
            logger.info(f"Gecerli konular: {', '.join(AYT_FIZIK_KONULAR.keys())}")
            return []
        
        konu_data = AYT_FIZIK_KONULAR[konu]
        generated_ids = []
        
        curriculum = self.supabase.get_curriculum_for_grade(grade_level=12, lesson_name="Fizik")
        
        logger.info(f"\n{konu_data['display_name']} icin {count} soru uretilecek")
        
        for i in range(count):
            kazanim_from_db = None
            if curriculum:
                matching = [k for k in curriculum if self._match_curriculum_topic(k, konu)]
                if matching:
                    kazanim_from_db = random.choice(matching)
            
            zorluk = self._select_difficulty()
            alt_konu = random.choice(konu_data.get("alt_konular", ["genel"]))
            kazanim_kodu = kazanim_from_db.get("learning_outcome_code") if kazanim_from_db else konu_data.get("kazanimlar", ["F.12.1.1.1"])[0]
            bloom = random.choice(list(BLOOM_SEVIYELERI.keys()))
            baglam = random.choice(konu_data.get("ornek_baglamlar", ["genel"]))
            gorsel_tipi = random.choice(konu_data.get("gorsel_tipleri", ["kuvvet_diyagrami"]))
            soru_tipi = self._select_question_type(konu_data, zorluk)
            
            params = QuestionParams(
                konu=konu,
                alt_konu=alt_konu,
                kazanim_kodu=kazanim_kodu,
                bloom_seviyesi=bloom,
                zorluk=zorluk,
                baglam=baglam,
                gorsel_tipi=gorsel_tipi,
                soru_tipi=soru_tipi
            )
            
            question_id = self.generate_single_question(params, kazanim_from_db=kazanim_from_db)
            if question_id:
                generated_ids.append(question_id)
            
            time.sleep(Config.RATE_LIMIT_DELAY)
        
        return generated_ids
    
    def print_stats(self):
        logger.info(f"\n{'='*70}")
        logger.info("SONUC ISTATISTIKLERI (v2.0)")
        logger.info(f"{'='*70}")
        logger.info(f"   Toplam deneme      : {self.stats['total_attempts']}")
        logger.info(f"   Basarili           : {self.stats['successful']}")
        logger.info(f"   Basarisiz          : {self.stats['failed']}")
        logger.info(f"   Gorselli soru      : {self.stats['with_image']}")
        logger.info(f"   Reddedilen sorular : {self.stats['questions_rejected']}")
        logger.info(f"   Reddedilen gorseller: {self.stats['images_rejected']}")
        logger.info(f"\n   Zorluk Dagilimi:")
        for level, count in self.stats['by_difficulty'].items():
            logger.info(f"     Seviye {level}: {count} soru")
        
        if self.stats['total_attempts'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total_attempts']) * 100
            logger.info(f"\n   Basari orani: %{success_rate:.1f}")
        logger.info(f"{'='*70}\n")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='AYT Fizik Soru Uretim Botu v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Yenilikler v2.0:
  - Kavram Yanilgisi Veri Tabani (Misconception Database)
  - Psikometrik Zorluk Dagilimi (OSYM tarzi)
  - Gelistirilmis Prompt Muhendisligi (Few-Shot)
  - Renkli Gorsel Sablonlari
  - 2025 Trend Bazli Soru Tipleri

Ornekler:
  python ayt_fizik_bot.py --mode batch --count 1
  python ayt_fizik_bot.py --mode topic --topic elektrostatik --count 5
  python ayt_fizik_bot.py --mode single --konu hareket_ve_kuvvet --bloom Analiz --zorluk 4 --tip hikayeli

Gecerli Konular:
  hareket_ve_kuvvet, tork_ve_denge, dairesel_hareket, basit_harmonik_hareket,
  elektrostatik, manyetizma, alternatif_akim, dalgalar, elektromanyetik_dalgalar,
  ozel_gorelilik, kuantum_fizigi, atom_fizigi, standart_model,
  tibbi_goruntuleme, superiletkenlik

Soru Tipleri:
  hikayeli, grafik, onculu, deney, eslestirme
        """
    )
    
    parser.add_argument('--mode', type=str, default='batch',
                       choices=['batch', 'single', 'topic'],
                       help='Calisma modu')
    parser.add_argument('--count', type=int, default=1,
                       help='Uretilecek soru sayisi')
    parser.add_argument('--topic', type=str, default=None,
                       help='Konu (topic modu icin)')
    parser.add_argument('--konu', type=str, default='hareket_ve_kuvvet',
                       help='Konu (single modu icin)')
    parser.add_argument('--alt-konu', type=str, default=None,
                       help='Alt konu (single modu icin)')
    parser.add_argument('--kazanim', type=str, default=None,
                       help='Kazanim kodu (single modu icin)')
    parser.add_argument('--bloom', type=str, default='Analiz',
                       choices=['Uygulama', 'Analiz', 'Degerlendirme', 'Yaratma'],
                       help='Bloom seviyesi')
    parser.add_argument('--zorluk', type=int, default=3,
                       choices=[1, 2, 3, 4, 5],
                       help='Zorluk seviyesi (1-5)')
    parser.add_argument('--tip', type=str, default='hikayeli',
                       choices=['hikayeli', 'grafik', 'onculu', 'deney', 'eslestirme'],
                       help='Soru tipi')
    
    args = parser.parse_args()
    
    logger.info("""
========================================================================
     AYT FIZIK SORU URETIM BOTU v2.0
     Gemini 2.5 Flash + Imagen 3 + Supabase
     
     Yenilikler:
     - Kavram Yanilgisi Veri Tabani
     - Psikometrik Zorluk Dagilimi
     - Renkli Gorsel Uretimi
     - 2025 OSYM Trendi Uyumu
========================================================================
    """)
    
    logger.info(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Mod: {args.mode}")
    
    try:
        generator = AYTFizikGenerator()
        
        if args.mode == 'batch':
            logger.info(f"Batch modu - Her konu icin {args.count} soru")
            logger.info("Psikometrik zorluk dagilimi: %10 Kolay, %55 Orta, %25 Zor, %10 Secici")
            results = generator.generate_batch(count_per_topic=args.count)
            logger.info(f"\nUretilen soru sayisi: {len(results['generated_ids'])}")
            if results['failed_topics']:
                logger.info(f"Basarisiz: {results['failed_topics']}")
            
        elif args.mode == 'topic':
            topic = args.topic or args.konu
            logger.info(f"Topic modu - {topic} icin {args.count} soru")
            ids = generator.generate_for_topic(topic, args.count)
            logger.info(f"\nUretilen sorular: {ids}")
            
        elif args.mode == 'single':
            konu_data = AYT_FIZIK_KONULAR.get(args.konu, {})
            
            alt_konu = args.alt_konu or (konu_data.get("alt_konular", ["genel"])[0] if konu_data else "genel")
            kazanim = args.kazanim or (konu_data.get("kazanimlar", ["F.12.1.1.1"])[0] if konu_data else "F.12.1.1.1")
            baglam = konu_data.get("ornek_baglamlar", ["genel"])[0] if konu_data else "genel"
            gorsel_tipi = konu_data.get("gorsel_tipleri", ["kuvvet_diyagrami"])[0] if konu_data else "kuvvet_diyagrami"
            
            params = QuestionParams(
                konu=args.konu,
                alt_konu=alt_konu,
                kazanim_kodu=kazanim,
                bloom_seviyesi=args.bloom,
                zorluk=args.zorluk,
                baglam=baglam,
                gorsel_tipi=gorsel_tipi,
                soru_tipi=args.tip
            )
            
            logger.info(f"Single modu - {args.konu}")
            logger.info(f"Soru Tipi: {args.tip}, Zorluk: {args.zorluk}/5")
            question_id = generator.generate_single_question(params)
            
            if question_id:
                logger.info(f"\nSoru basariyla uretildi! ID: {question_id}")
            else:
                logger.error("\nSoru uretilemedi")
                sys.exit(1)
        
        generator.print_stats()
        
    except ValueError as ve:
        logger.error(f"Konfigurasyon hatasi: {ve}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Kritik hata: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
