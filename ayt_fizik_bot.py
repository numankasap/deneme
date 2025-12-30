"""
AYT Fizik Soru Üretim Botu
==========================
Gemini 2.5 Flash (soru) + Gemini 3 Pro Image Preview (görsel) + Supabase
GitHub Actions ile otomatik çalışır

YKS/AYT Fizik müfredatına uygun, ÖSYM formatında sorular üretir.

Kullanım:
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
GEMINI_IMAGE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent"

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
# AYT FIZIK MUFREDATI - KONULAR VE KAZANIMLAR
# ============================================================================

AYT_FIZIK_KONULAR: Dict[str, Dict[str, Any]] = {
    
    "hareket_ve_kuvvet": {
        "display_name": "Hareket ve Kuvvet",
        "alt_konular": [
            "dusey_atis", "yatay_atis", "egik_atis", "bagil_hiz",
            "newton_kanunlari", "surtunme_kuvveti", "momentum", "carpismalar"
        ],
        "kazanimlar": ["F.12.1.1.1", "F.12.1.1.2", "F.12.1.1.3", "F.12.1.1.4", "F.12.1.2.1", "F.12.1.2.2", "F.12.1.2.3"],
        "kazanim_aciklamalari": {
            "F.12.1.1.1": "Dusey atis hareketini analiz eder.",
            "F.12.1.1.2": "Yatay atis hareketini analiz eder.",
            "F.12.1.1.3": "Egik atis hareketini analiz eder.",
            "F.12.1.1.4": "Bagil hiz problemlerini cozer.",
            "F.12.1.2.1": "Newton hareket yasalarini uygular.",
            "F.12.1.2.2": "Momentum ve impuls kavramlarini uygular.",
            "F.12.1.2.3": "Esnek ve esnek olmayan carpismalari analiz eder."
        },
        "ornek_baglamlar": [
            "Basketbol atisi ve yorunge analizi",
            "Futbolda kaleye sut ve egik atis",
            "Ucaktan yardim paketi atisi",
            "Golf topu atisi ve ruzgar etkisi"
        ],
        "gorsel_tipleri": ["yorunge_diyagrami", "hiz_vektoru", "kuvvet_diyagrami", "carpma_oncesi_sonrasi"],
        "gorsel_aciklamalari": {
            "yorunge_diyagrami": "Parabolik yorunge, baslangic noktasi, maksimum yukseklik, menzil gosterilmeli.",
            "kuvvet_diyagrami": "Cisim uzerine etkiyen tum kuvvetler oklu vektorler olarak."
        },
        "celdirici_hatalari": [
            "Yatay ve dusey hareketi ayirmama",
            "g ivmesinin isaretini yanlis alma",
            "sin ve cos aci fonksiyonlarini karistirma",
            "Momentum korunumunda isaret hatasi"
        ],
        "soru_kaliplari": [
            "Buna gore, cismin yere carpma hizi kac m/s'dir?",
            "Buna gore, topun menzili kac m'dir?",
            "Buna gore, ortalama hizin buyuklugu kac m/s'dir?"
        ],
        "formul_bilgisi": "Egik Atis: v_x = v0*cos(theta), v_y = v0*sin(theta) - gt, Menzil = v0^2*sin(2*theta)/g"
    },
    
    "tork_ve_denge": {
        "display_name": "Tork ve Denge",
        "alt_konular": ["tork_kavrami", "denge_kosullari", "agirlik_merkezi", "kaldiraci_sistemleri"],
        "kazanimlar": ["F.12.1.3.1", "F.12.1.3.2", "F.12.1.3.3"],
        "kazanim_aciklamalari": {
            "F.12.1.3.1": "Tork kavramini aciklar ve hesaplar.",
            "F.12.1.3.2": "Denge kosullarini analiz eder.",
            "F.12.1.3.3": "Agirlik merkezi kavramini uygular."
        },
        "ornek_baglamlar": ["El arabasi dengeleme", "Tahterevalli dengesi", "Kapi mentesesi ve tork"],
        "gorsel_tipleri": ["kaldiraci_diyagrami", "tork_vektoru", "denge_sistemi"],
        "gorsel_aciklamalari": {"kaldiraci_diyagrami": "Destek noktasi, kuvvet kolu, yuk kolu gosterilmeli."},
        "celdirici_hatalari": ["Tork yonunu karistirma", "Kuvvet kolunu yanlis belirleme"],
        "soru_kaliplari": ["Buna gore, uygulanan kuvvet kac N'dur?", "Buna gore, torkun buyuklugu kac N*m'dir?"]
    },
    
    "dairesel_hareket": {
        "display_name": "Dairesel Hareket",
        "alt_konular": ["duzgun_dairesel_hareket", "acisal_hiz", "merkezcil_ivme", "uydu_hareketi"],
        "kazanimlar": ["F.12.1.4.1", "F.12.1.4.2", "F.12.1.4.3"],
        "kazanim_aciklamalari": {
            "F.12.1.4.1": "Duzgun cembersel hareketi analiz eder.",
            "F.12.1.4.2": "Acisal hiz ve cizgisel hiz iliskisini kurar.",
            "F.12.1.4.3": "Uydu ve gezegen hareketlerini analiz eder."
        },
        "ornek_baglamlar": ["Televizyon uydusu yorungesi", "Lunaparktaki donme dolap", "ISS yorungesi"],
        "gorsel_tipleri": ["cembersel_yorunge", "uydu_diyagrami", "hiz_ivme_vektorleri"],
        "gorsel_aciklamalari": {"cembersel_yorunge": "Cember yorunge, merkez, yaricap, hiz vektoru teget yonde."},
        "celdirici_hatalari": ["Acisal hiz ile cizgisel hizi karistirma", "Merkezcil ivme yonunu yanlis alma"],
        "soru_kaliplari": ["Buna gore, acisal hizlari arasindaki iliski nedir?", "Buna gore, uydu hangi yorungede dolanmalidir?"]
    },
    
    "basit_harmonik_hareket": {
        "display_name": "Basit Harmonik Hareket",
        "alt_konular": ["yayli_sarkac", "basit_sarkac", "periyod_ve_frekans", "enerji_donusumleri"],
        "kazanimlar": ["F.12.1.5.1", "F.12.1.5.2", "F.12.1.5.3"],
        "kazanim_aciklamalari": {
            "F.12.1.5.1": "Basit harmonik hareketin ozelliklerini aciklar.",
            "F.12.1.5.2": "Yayli ve basit sarkac sistemlerini analiz eder.",
            "F.12.1.5.3": "BHH'de enerji donusumlerini inceler."
        },
        "ornek_baglamlar": ["Metronom salinimi", "Saat sarkaci periyodu", "Arac suspansiyon sistemi"],
        "gorsel_tipleri": ["konum_zaman_grafigi", "sarkac_diyagrami", "yayli_sistem", "enerji_grafigi"],
        "gorsel_aciklamalari": {"konum_zaman_grafigi": "Sinuzoidal grafik, genlik A, periyod T gosterilmeli."},
        "celdirici_hatalari": ["Periyod formulunde genlik kullanma", "Denge konumunda ivmenin maksimum oldugunu sanma"],
        "soru_kaliplari": ["Buna gore, periyodu T_K / T_L orani kactir?", "Buna gore, hareketin genligi kac cm'dir?"]
    },
    
    "elektrostatik": {
        "display_name": "Elektrostatik",
        "alt_konular": ["elektrik_yuk", "coulomb_kanunu", "elektrik_alan", "elektrik_potansiyel", "es_potansiyel_yuzeyler"],
        "kazanimlar": ["F.12.2.1.1", "F.12.2.1.2", "F.12.2.1.3", "F.12.2.1.4"],
        "kazanim_aciklamalari": {
            "F.12.2.1.1": "Coulomb yasasini uygular.",
            "F.12.2.1.2": "Elektrik alan kavramini aciklar ve hesaplar.",
            "F.12.2.1.3": "Elektriksel potansiyel ve potansiyel enerji kavramlarini aciklar.",
            "F.12.2.1.4": "Es potansiyel yuzeyleri analiz eder."
        },
        "ornek_baglamlar": ["Yuklu cisimler arasi kuvvet", "Elektrik alan cizgileri analizi", "Noktasal yuk potansiyeli"],
        "gorsel_tipleri": ["yuk_diyagrami", "alan_cizgileri", "es_potansiyel_cemberler", "kuvvet_vektorleri"],
        "gorsel_aciklamalari": {"yuk_diyagrami": "X, Y, Z noktasal yukleri, (+) ve (-) isaretleri, aralarindaki mesafeler."},
        "celdirici_hatalari": ["Kuvvet ve alan yonunu karistirma", "Potansiyel farki hesabinda isaret hatasi"],
        "soru_kaliplari": ["Buna gore, bileske kuvvetin yonu hangisidir?", "Buna gore, potansiyel farki sifir olabilecek noktalar hangileridir?"]
    },
    
    "manyetizma": {
        "display_name": "Manyetizma",
        "alt_konular": ["manyetik_alan", "yuklu_parcacik_hareketi", "manyetik_kuvvet", "elektromanyetik_induksiyon", "transformator"],
        "kazanimlar": ["F.12.2.2.1", "F.12.2.2.2", "F.12.2.2.3", "F.12.2.2.4"],
        "kazanim_aciklamalari": {
            "F.12.2.2.1": "Manyetik alan ve manyetik kuvvet kavramlarini aciklar.",
            "F.12.2.2.2": "Yuklu parcacigin manyetik alandaki hareketini analiz eder.",
            "F.12.2.2.3": "Elektromanyetik induksiyon olayini aciklar.",
            "F.12.2.2.4": "Transformator calisma prensibini aciklar."
        },
        "ornek_baglamlar": ["Bobin ve manyetik alan", "Yuklu parcacik sapmasi", "Elektrik santralinde enerji iletimi"],
        "gorsel_tipleri": ["manyetik_alan_cizgileri", "parcacik_yolu", "transformator_sema", "bobin_devresi"],
        "gorsel_aciklamalari": {"manyetik_alan_cizgileri": "Iceri veya disari sembolleri, duzgun manyetik alan bolgesi."},
        "celdirici_hatalari": ["Manyetik kuvvet yonunu bulmada sag el kuralini yanlis uygulama"],
        "soru_kaliplari": ["Buna gore, alan cizgilerinin yonu hangisi olabilir?", "Buna gore, parcacik hangi yolu izler?"]
    },
    
    "alternatif_akim": {
        "display_name": "Alternatif Akim",
        "alt_konular": ["ac_devreler", "empedans", "rezonans", "siga_ve_bobin", "guc_hesabi"],
        "kazanimlar": ["F.12.2.3.1", "F.12.2.3.2", "F.12.2.3.3"],
        "kazanim_aciklamalari": {
            "F.12.2.3.1": "Alternatif akim devrelerini analiz eder.",
            "F.12.2.3.2": "Empedans ve rezonans kavramlarini aciklar.",
            "F.12.2.3.3": "RLC devrelerinde guc hesabi yapar."
        },
        "ornek_baglamlar": ["Ev tipi elektrik prizleri", "Hoparlor empedansi", "Radyo alicisi ve rezonans frekansi"],
        "gorsel_tipleri": ["devre_semasi", "empedans_ucgeni", "rezonans_grafigi"],
        "gorsel_aciklamalari": {"devre_semasi": "AC kaynak, direnc, bobin, sigac sembolleri."},
        "celdirici_hatalari": ["Rezonans frekansinda empedansin maksimum oldugunu sanma"],
        "soru_kaliplari": ["Buna gore, ampulun parlakligi hangileriyle ayni olabilir?", "Buna gore, rezonans frekansi kac Hz'dir?"]
    },
    
    "dalgalar": {
        "display_name": "Dalgalar",
        "alt_konular": ["dalga_ozellikleri", "ses_dalgalari", "doppler_etkisi", "girisim", "kirinim"],
        "kazanimlar": ["F.12.3.1.1", "F.12.3.1.2", "F.12.3.1.3", "F.12.3.1.4"],
        "kazanim_aciklamalari": {
            "F.12.3.1.1": "Dalga ozelliklerini aciklar.",
            "F.12.3.1.2": "Doppler etkisini aciklar.",
            "F.12.3.1.3": "Girisim olayini analiz eder.",
            "F.12.3.1.4": "Kirinim olayini aciklar."
        },
        "ornek_baglamlar": ["Ambulans sireni ve Doppler etkisi", "Cift yarik deneyi", "Radar hiz olcumu"],
        "gorsel_tipleri": ["dalga_grafigi", "girisim_deseni", "kirinim_deseni", "doppler_diyagrami"],
        "gorsel_aciklamalari": {"girisim_deseni": "Cift yarik, ekran, aydinlik ve karanlik sacaklar."},
        "celdirici_hatalari": ["Girisimde dalga boyunun degistigini sanma", "Dopplerde frekans ve dalga boyunu karistirma"],
        "soru_kaliplari": ["Buna gore, sacak genisligi nasil degisir?", "Buna gore, isitilen frekans kac Hz'dir?"]
    },
    
    "elektromanyetik_dalgalar": {
        "display_name": "Elektromanyetik Dalgalar",
        "alt_konular": ["em_spektrum", "gama_isini", "x_isini", "radyo_dalgalari"],
        "kazanimlar": ["F.12.3.2.1", "F.12.3.2.2"],
        "kazanim_aciklamalari": {
            "F.12.3.2.1": "Elektromanyetik spektrumu aciklar.",
            "F.12.3.2.2": "Elektromanyetik dalgalarin ozelliklerini ve kullanim alanlarini aciklar."
        },
        "ornek_baglamlar": ["Supernova patlamasi ve gama isini", "X-isini goruntuleme", "Radyo ve TV yayini"],
        "gorsel_tipleri": ["spektrum_diyagrami", "dalga_karsilastirma"],
        "gorsel_aciklamalari": {"spektrum_diyagrami": "EM spektrum, dalga boyu ve frekans ekseni."},
        "celdirici_hatalari": ["Dalga boyu ve frekans iliskisini ters kurma"],
        "soru_kaliplari": ["Buna gore, incelenen dalgalar hangisidir?", "Buna gore, enerji siralamasi nasildir?"]
    },
    
    "ozel_gorelilik": {
        "display_name": "Ozel Gorelilik",
        "alt_konular": ["isik_hizi_sabiti", "zaman_genlesmesi", "boy_kisalmasi", "kutle_enerji_esdegerligi"],
        "kazanimlar": ["F.12.4.1.1", "F.12.4.1.2"],
        "kazanim_aciklamalari": {
            "F.12.4.1.1": "Ozel gorelilik postulalarini aciklar.",
            "F.12.4.1.2": "Kutle-enerji esdegerliligini aciklar."
        },
        "ornek_baglamlar": ["Isik hizina yakin hareketli uzay gemisi", "GPS uyduları ve zaman duzeltmesi"],
        "gorsel_tipleri": ["referans_cerceve", "zaman_diyagrami"],
        "gorsel_aciklamalari": {"referans_cerceve": "Iki farkli referans cercevesi, hiz vektoru."},
        "celdirici_hatalari": ["Fizik yasalarinin hiza gore degistigini sanma"],
        "soru_kaliplari": ["Buna gore, hangileri postula arasindadir?", "Buna gore, E = mc^2 ifadesi neyi gosterir?"]
    },
    
    "kuantum_fizigi": {
        "display_name": "Kuantum Fizigi",
        "alt_konular": ["fotoelektrik_olay", "compton_sacilmasi", "bohr_atom_modeli", "foton_enerjisi"],
        "kazanimlar": ["F.12.4.2.1", "F.12.4.2.2", "F.12.4.2.3"],
        "kazanim_aciklamalari": {
            "F.12.4.2.1": "Fotoelektrik olayi aciklar.",
            "F.12.4.2.2": "Compton sacilmasini analiz eder.",
            "F.12.4.2.3": "Bohr atom modelini aciklar."
        },
        "ornek_baglamlar": ["Elektroskop ve mor otesi isik", "Gunes pili calisma prensibi", "Hidrojen atom spektrumu"],
        "gorsel_tipleri": ["enerji_grafigi", "foton_elektron_etkilesimi", "elektroskop_diyagrami"],
        "gorsel_aciklamalari": {"enerji_grafigi": "E_k - f grafigi, esik frekansi, dogrusal iliski."},
        "celdirici_hatalari": ["Esik frekansini astiktan sonra foton sayisinin hizi artirdigini sanma"],
        "soru_kaliplari": ["Buna gore, yapraklari kapanan elektroskobun yuku nedir?", "Buna gore, metalin esik enerjisi kac eV'dur?"]
    },
    
    "atom_fizigi": {
        "display_name": "Atom Fizigi ve Radyoaktivite",
        "alt_konular": ["radyoaktif_bozunum", "yarilanma_omru", "alfa_beta_gama", "nukleer_fisyon", "nukleer_fuzyon"],
        "kazanimlar": ["F.12.4.3.1", "F.12.4.3.2", "F.12.4.3.3"],
        "kazanim_aciklamalari": {
            "F.12.4.3.1": "Radyoaktif bozunma turlerini aciklar.",
            "F.12.4.3.2": "Yarilanma omru kavramini uygular.",
            "F.12.4.3.3": "Nukleer fisyon ve fuzyon tepkimelerini aciklar."
        },
        "ornek_baglamlar": ["Karbon-14 ile yas tayini", "Nukleer santral calisma prensibi", "Gunesteki fuzyon tepkimeleri"],
        "gorsel_tipleri": ["bozunma_serisi", "cekirdek_diyagrami", "yarilanma_grafigi"],
        "gorsel_aciklamalari": {"yarilanma_grafigi": "N-t grafigi, ustel azalma, T1/2 isareti."},
        "celdirici_hatalari": ["Fisyon ve fuzyonu karistirma", "Atom numarasi ve kutle numarasini karistirma"],
        "soru_kaliplari": ["Buna gore, ortak ozellikler hangileridir?", "Buna gore, atom numarasi toplami kactir?"]
    },
    
    "standart_model": {
        "display_name": "Standart Model ve Temel Kuvvetler",
        "alt_konular": ["temel_parcaciklar", "kuarklar", "leptonlar", "dort_temel_kuvvet", "higgs_bozonu"],
        "kazanimlar": ["F.12.4.4.1", "F.12.4.4.2"],
        "kazanim_aciklamalari": {
            "F.12.4.4.1": "Standart modeldeki temel parcaciklari tanir.",
            "F.12.4.4.2": "Dort temel kuvveti ve araci parcaciklari aciklar."
        },
        "ornek_baglamlar": ["CERN parcacik hizlandiricisi", "Higgs bozonu kesfi", "Kozmik isinlar"],
        "gorsel_tipleri": ["parcacik_tablosu", "kuvvet_karsilastirma"],
        "gorsel_aciklamalari": {"parcacik_tablosu": "Kuarklar, leptonlar, bozonlar tablosu."},
        "celdirici_hatalari": ["Fotonun Higgs ile etkilestigini sanma"],
        "soru_kaliplari": ["Buna gore, Higgs bozonu ile etkilesen parcaciklar hangileridir?"]
    },
    
    "tibbi_goruntuleme": {
        "display_name": "Tibbi Goruntuleme Teknikleri",
        "alt_konular": ["x_isini_goruntuleme", "bilgisayarli_tomografi", "mr_goruntuleme", "ultrason", "pet_tarama"],
        "kazanimlar": ["F.12.5.1.1"],
        "kazanim_aciklamalari": {
            "F.12.5.1.1": "Tibbi goruntuleme tekniklerinin fiziksel prensiplerini aciklar."
        },
        "ornek_baglamlar": ["MR cekimi ve manyetik alan", "X-isini ve kemik goruntuleme", "Ultrason ile bebek goruntuleme"],
        "gorsel_tipleri": ["cihaz_semasi", "dalga_karsilastirma"],
        "gorsel_aciklamalari": {"cihaz_semasi": "Goruntuleme cihazi semasi."},
        "celdirici_hatalari": ["MR'da X-isini kullanildigini sanma", "Ultrasonda elektromanyetik dalga kullanildigini sanma"],
        "soru_kaliplari": ["Buna gore, hangi yargilar dogru olabilir?", "Buna gore, hangi goruntuleme yontemi kullanilmaktadir?"]
    },
    
    "superleitkenlik": {
        "display_name": "Superiletkenlik",
        "alt_konular": ["sifir_direnc", "kritik_sicaklik", "meissner_etkisi", "uygulamalar"],
        "kazanimlar": ["F.12.5.2.1"],
        "kazanim_aciklamalari": {
            "F.12.5.2.1": "Superiletkenlik kavramini ve uygulamalarini aciklar."
        },
        "ornek_baglamlar": ["Superiletken miknatislar", "MR cihazlarinda superiletken", "Maglev trenleri"],
        "gorsel_tipleri": ["direnc_sicaklik_grafigi", "meissner_diyagrami"],
        "gorsel_aciklamalari": {"direnc_sicaklik_grafigi": "R-T grafigi, kritik sicaklik Tc noktasi."},
        "celdirici_hatalari": ["Kritik sicaklik ustunde superiletkenligin devam ettigini sanma"],
        "soru_kaliplari": ["Buna gore, T_C uzerinde ne olur?", "Buna gore, hangi yargilar dogrudur?"]
    }
}

# ============================================================================
# BLOOM TAKSONOMISI
# ============================================================================

BLOOM_SEVIYELERI = {
    "Uygulama": {
        "aciklama": "Bilgiyi yeni durumlara uygulama, problem cozme, hesaplama yapma",
        "fiiller": ["hesaplar", "uygular", "cozer", "kullanir", "gosterir"],
        "soru_kaliplari": ["Buna gore, degeri kac birimdir?", "Buna gore, buyuklugu kactir?"]
    },
    "Analiz": {
        "aciklama": "Parca-butun iliskisi, karsilastirma, siniflandirma, iliskilendirme",
        "fiiller": ["karsilastirir", "analiz eder", "ayirt eder", "iliskilendirir"],
        "soru_kaliplari": ["Buna gore, asagidaki ifadelerden hangisi dogrudur?", "Buna gore, I, II ve III ifadelerinden hangileri dogrudur?"]
    },
    "Degerlendirme": {
        "aciklama": "Yargilama, karar verme, olcut kullanma, secim yapma",
        "fiiller": ["degerlendirir", "yargilar", "karar verir", "secer"],
        "soru_kaliplari": ["Buna gore, en uygun secenek hangisidir?", "Buna gore, hangisi kesinlikle soylenebilir?"]
    },
    "Yaratma": {
        "aciklama": "Tasarlama, planlama, uretme, sentezleme, ozgun cozum gelistirme",
        "fiiller": ["tasarlar", "olusturur", "planlar", "uretir"],
        "soru_kaliplari": ["Buna gore, problem nasil duzeltilmelidir?", "Buna gore, sistem nasil degistirilmelidir?"]
    }
}

PISA_BAGLAMLAR = ["Kisisel", "Mesleki", "Toplumsal", "Bilimsel"]

# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SYSTEM_PROMPT_QUESTION = """Sen, OSYM'de gorev yapan, 20 yillik deneyimli kidemli bir fizik soru yazarisin. AYT Fizik sinavina uygun, universite giris sinavi kalitesinde sorular hazirlamakta uzmansin.

## TEMEL PRENSIPLER

### 1. OSYM SORU FORMATI
- 5 sik (A, B, C, D, E)
- Genellikle "Buna gore, ..." ile baslayan soru koku
- Senaryo/durum anlatimi + soru koku yapisi
- Matematiksel hesaplama gerektiren veya kavramsal sorular

### 2. BAGLAM ENTEGRASYONU
- Fiziksel problem GERCEK HAYAT senaryosu icinde sunulmali
- Turkiye kulturune uygun isimler (Efe, Ayse, Altay vb.)

### 3. GORSEL-METIN ILISKISI
- Gorselde VERI olmali
- Soru metninde BAHSEDILEN TUM veriler gorselde OLMALI

### 4. DIL VE USLUP
- %100 dogru Turkce dil bilgisi
- MEB/OSYM terminolojisi
- Soru koku MUTLAKA "Buna gore, ..." ile baslamali

### 5. CELDIRICI MANTIGI
5 yanlis sik, gercek ogrenci hatalarindan gelmeli:
- Isaret hatalari
- Formul karistirma
- Birim donusum hatalari

### 6. MATEMATIKSEL DEGERLER
- sin 30 = 0,5 ; cos 30 = 0,87
- sin 37 = 0,6 ; cos 37 = 0,8
- sin 53 = 0,8 ; cos 53 = 0,6
- g = 10 m/s^2

## CIKTI FORMATI
Yanitini YALNIZCA asagidaki JSON formatinda ver:

{
  "soru_metni": "Senaryo ve durum anlatimi.",
  "soru_koku": "Buna gore, ... seklinde biten soru cumlesi",
  "siklar": {
    "A": "Sik A icerigi",
    "B": "Sik B icerigi",
    "C": "Sik C icerigi",
    "D": "Sik D icerigi",
    "E": "Sik E icerigi"
  },
  "dogru_cevap": "A, B, C, D veya E",
  "cozum_adim_adim": "Adim 1: [aciklama]\\nAdim 2: [aciklama]\\nSonuc: [cevap]",
  "celdirici_analizi": {
    "A": "Bu sikki secen ogrencinin yaptigi hata",
    "B": "Bu sikki secen ogrencinin yaptigi hata",
    "C": "Bu sikki secen ogrencinin yaptigi hata",
    "D": "Bu sikki secen ogrencinin yaptigi hata",
    "E": "Bu sikki secen ogrencinin yaptigi hata"
  },
  "gorsel_gerekli": true,
  "gorsel_betimleme": {
    "tip": "yorunge_diyagrami / devre_semasi / kuvvet_diyagrami / grafik / vb.",
    "detay": "COK DETAYLI gorsel talimati.",
    "gorunen_veriler": ["Gorselde gorunecek TUM degerler listesi"],
    "gizli_bilgi": "Gorselde OLMAMASI gereken bilgiler"
  },
  "pisa_seviyesi": 4,
  "pisa_baglam": "Kisisel / Mesleki / Toplumsal / Bilimsel"
}"""

IMAGE_PROMPT_TEMPLATE = """AYT Fizik sorusu icin egitim gorseli olustur.

## GORSEL TIPI: {tip}

## DETAYLI BETIMLEME:
{detay}

## KRITIK KURALLAR:

### FIZIK GORSELI KURALLARI:
- Kuvvet vektorleri: Kalin oklar, ucu sivri
- Hiz vektorleri: Ince oklar
- x ve y eksenleri net cizilmeli
- Direnc: Zigzag cizgi
- Sigac: Iki paralel cizgi
- Bobin: Spiral
- Cisimler net geometrik sekillerle
- Kose noktalari harflerle (A, B, C, D)
- Acilar yay ile gosterilmeli

### STIL (OSYM TARZI):
- Arka plan: Beyaz
- Cizgiler: Siyah veya koyu gri
- Font: Net, okunaklı

### MUTLAK YASAKLAR:
- Soru metni veya cumleler
- A), B), C), D), E) siklari
- Cozum adimlari
- Cevabi veren dogrudan bilgi
- Ingilizce kelimeler

### OLMASI GEREKENLER:
- Net etiketler ve olculer
- Vektor yonleri acikca belirli
- Profesyonel ve temiz gorunum"""

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
        
        user_prompt = f"""
## SORU URETIM TALIMATI

### Konu Bilgileri:
- **Ana Konu**: {konu_data.get('display_name', params.konu)}
- **Alt Konu**: {params.alt_konu}
- **Kazanim Kodu**: {params.kazanim_kodu}

### Soru Parametreleri:
- **Bloom Seviyesi**: {params.bloom_seviyesi}
  - Aciklama: {bloom_data.get('aciklama', '')}
- **Zorluk (1-5)**: {params.zorluk}
- **Sinif Seviyesi**: {params.grade_level}. sinif (AYT)

### Baglam Talimati:
- **Onerilen baglam**: {params.baglam}

### Gorsel Talimati:
- **Gorsel tipi**: {params.gorsel_tipi}

### Dikkat Edilecek Yaygin Ogrenci Hatalari:
{chr(10).join(['- ' + h for h in konu_data.get('celdirici_hatalari', [])])}

### Ornek Soru Kokleri:
{chr(10).join(['- ' + k for k in konu_data.get('soru_kaliplari', [])])}

---

Yukaridaki kriterlere uygun, ozgun ve yaratici bir AYT Fizik sorusu olustur.
5 sikli (A, B, C, D, E) olmali.
Tek bir dogru cevap olmali.
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
        gorunen_veriler = gorsel_betimleme.get("gorunen_veriler", "")
        
        full_detay = f"{detay}\n\nGorselde gorunecek degerler: {gorunen_veriler}"
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
            "exam_type": "AYT_AI_BOT"
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
    
    def validate_question(self, question_data: Dict) -> Dict:
        if not NEW_GENAI or not self.client:
            return {"pass": True, "overall_score": 7, "problems": [], "skipped": True}
        
        try:
            prompt = f"""Bu AYT Fizik sorusunu KALITE KONTROLU yap.

SORU METNI: {question_data.get("soru_metni", "")}
SORU KOKU: {question_data.get("soru_koku", "")}
SIKLAR: {json.dumps(question_data.get("siklar", {}), ensure_ascii=False)}
DOGRU CEVAP: {question_data.get("dogru_cevap", "")}
COZUM: {question_data.get("cozum_adim_adim", "")}

JSON formatinda dondur:
{{"is_physically_correct": true, "is_mathematically_correct": true, "overall_score": 8, "pass": true, "problems": []}}"""
            
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
    
    def validate_image(self, image_bytes: bytes, question_text: str = "") -> Dict:
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
                            {"text": "Bu fizik gorseli icin kalite kontrolu yap. JSON formatinda dondur: {\"has_question_text\": false, \"has_options\": false, \"is_clean\": true, \"overall_score\": 8, \"pass\": true, \"problems\": []}"}
                        ]
                    }
                ],
                config={"response_mime_type": "application/json"}
            )
            
            result = json.loads(response.text)
            result["pass"] = result.get("overall_score", 0) >= self.quality_threshold
            return result
            
        except Exception as e:
            logger.error(f"  Gorsel validasyon hatasi: {e}")
            return {"pass": True, "overall_score": 5, "problems": [str(e)], "error": True}


# ============================================================================
# MAIN GENERATOR CLASS
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
            "quality_retries": 0
        }
    
    def generate_single_question(self, params: QuestionParams, kazanim_from_db: Dict = None) -> Optional[int]:
        self.stats["total_attempts"] += 1
        konu_display = AYT_FIZIK_KONULAR.get(params.konu, {}).get("display_name", params.konu)
        
        kazanim_id = None
        if kazanim_from_db:
            kazanim_id = kazanim_from_db.get("id")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"SORU URETIMI BASLIYOR")
        logger.info(f"   Konu: {konu_display}")
        logger.info(f"   Alt Konu: {params.alt_konu}")
        logger.info(f"   Bloom: {params.bloom_seviyesi} | Zorluk: {params.zorluk}/5")
        logger.info(f"{'='*70}")
        
        previous_question_problems = []
        max_question_retries = 3
        max_image_retries = 3
        
        try:
            # ADIM 1: SORU URETIMI
            question_data = None
            question_quality_score = 0
            
            for q_attempt in range(max_question_retries):
                logger.info(f"\n[1/5] Gemini ile soru uretiliyor (Deneme {q_attempt + 1}/{max_question_retries})...")
                
                question_data = self.gemini.generate_question(params)
                
                required_fields = ["soru_metni", "soru_koku", "siklar", "dogru_cevap"]
                missing = [f for f in required_fields if f not in question_data]
                if missing:
                    previous_question_problems.append(f"Eksik alanlar: {missing}")
                    self.stats["quality_retries"] += 1
                    continue
                
                siklar = question_data.get("siklar", {})
                if len(siklar) < 5:
                    previous_question_problems.append("5 sik olmali (A, B, C, D, E)")
                    self.stats["quality_retries"] += 1
                    continue
                
                logger.info("  Soru kalite kontrolu yapiliyor...")
                q_validation = self.validator.validate_question(question_data)
                question_quality_score = q_validation.get("overall_score", 5)
                
                logger.info(f"  Soru Kalite Puani: {question_quality_score}/10")
                
                if q_validation.get("pass", False):
                    logger.info("  Soru kalite kontrolunu gecti")
                    break
                else:
                    problems = q_validation.get("problems", ["Kalite yetersiz"])
                    previous_question_problems.extend(problems)
                    self.stats["quality_retries"] += 1
                    self.stats["questions_rejected"] += 1
            
            if not question_data:
                self.stats["failed"] += 1
                logger.error("  Tum soru denemeleri basarisiz")
                return None
            
            # ADIM 2: GORSEL URETIMI
            image_url = None
            image_bytes = None
            image_quality_score = 0
            gorsel_betimleme = question_data.get("gorsel_betimleme", {})
            
            if question_data.get("gorsel_gerekli", False) and gorsel_betimleme:
                logger.info("\n[2/5] Gorsel uretiliyor...")
                
                for img_attempt in range(max_image_retries):
                    image_bytes = self.gemini.generate_image(gorsel_betimleme, params.konu)
                    
                    if image_bytes:
                        logger.info("  Gorsel kalite kontrolu yapiliyor...")
                        img_validation = self.validator.validate_image(image_bytes)
                        image_quality_score = img_validation.get("overall_score", 5)
                        
                        logger.info(f"  Gorsel Kalite Puani: {image_quality_score}/10")
                        
                        if img_validation.get("pass", False):
                            logger.info("  Gorsel kalite kontrolunu gecti")
                            break
                        else:
                            self.stats["images_rejected"] += 1
                            image_bytes = None
                
                if image_bytes:
                    filename = f"ayt_fizik_{uuid.uuid4().hex[:12]}.png"
                    image_url = self.supabase.upload_image(image_bytes, filename)
                    if image_url:
                        self.stats["with_image"] += 1
            else:
                logger.info("\n[2/5] Gorsel gerekli degil, atlaniyor...")
            
            # ADIM 3: VERI YAPISI OLUSTUR
            logger.info("\n[3/5] Veri yapisi hazirlaniyor...")
            
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
                pisa_level=question_data.get("pisa_seviyesi", 4),
                pisa_context=question_data.get("pisa_baglam", "Bilimsel"),
                scenario_text=soru_metni,
                distractor_explanations=question_data.get("celdirici_analizi", {}),
                image_url=image_url
            )
            logger.info("  Veri yapisi hazir")
            
            # ADIM 4: KALITE OZET
            logger.info(f"\n[4/5] KALITE OZETI:")
            logger.info(f"   Soru Puani: {question_quality_score}/10")
            if image_bytes:
                logger.info(f"   Gorsel Puani: {image_quality_score}/10")
            
            # ADIM 5: VERITABANINA KAYDET
            logger.info("\n[5/5] Veritabanina kaydediliyor...")
            question_id = self.supabase.insert_question(generated, kazanim_id=kazanim_id)
            
            if question_id:
                self.stats["successful"] += 1
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
        logger.info(f"TOPLU SORU URETIMI BASLIYOR")
        logger.info(f"   Her konu icin {count_per_topic} soru uretilecek")
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
                
                alt_konu = random.choice(konu_data.get("alt_konular", ["genel"]))
                kazanim_kodu = kazanim_from_db.get("learning_outcome_code") if kazanim_from_db else konu_data.get("kazanimlar", ["F.12.1.1.1"])[0]
                bloom = random.choice(list(BLOOM_SEVIYELERI.keys()))
                zorluk = random.randint(3, 5)
                baglam = random.choice(konu_data.get("ornek_baglamlar", ["genel"]))
                gorsel_tipi = random.choice(konu_data.get("gorsel_tipleri", ["kuvvet_diyagrami"]))
                
                params = QuestionParams(
                    konu=konu_key,
                    alt_konu=alt_konu,
                    kazanim_kodu=kazanim_kodu,
                    bloom_seviyesi=bloom,
                    zorluk=zorluk,
                    baglam=baglam,
                    gorsel_tipi=gorsel_tipi
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
            "superleitkenlik": ["superiletken", "kritik sicaklik"]
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
            
            alt_konu = random.choice(konu_data.get("alt_konular", ["genel"]))
            kazanim_kodu = kazanim_from_db.get("learning_outcome_code") if kazanim_from_db else konu_data.get("kazanimlar", ["F.12.1.1.1"])[0]
            bloom = random.choice(list(BLOOM_SEVIYELERI.keys()))
            zorluk = random.randint(3, 5)
            baglam = random.choice(konu_data.get("ornek_baglamlar", ["genel"]))
            gorsel_tipi = random.choice(konu_data.get("gorsel_tipleri", ["kuvvet_diyagrami"]))
            
            params = QuestionParams(
                konu=konu,
                alt_konu=alt_konu,
                kazanim_kodu=kazanim_kodu,
                bloom_seviyesi=bloom,
                zorluk=zorluk,
                baglam=baglam,
                gorsel_tipi=gorsel_tipi
            )
            
            question_id = self.generate_single_question(params, kazanim_from_db=kazanim_from_db)
            if question_id:
                generated_ids.append(question_id)
            
            time.sleep(Config.RATE_LIMIT_DELAY)
        
        return generated_ids
    
    def print_stats(self):
        logger.info(f"\n{'='*70}")
        logger.info("SONUC ISTATISTIKLERI")
        logger.info(f"{'='*70}")
        logger.info(f"   Toplam deneme      : {self.stats['total_attempts']}")
        logger.info(f"   Basarili           : {self.stats['successful']}")
        logger.info(f"   Basarisiz          : {self.stats['failed']}")
        logger.info(f"   Gorselli soru      : {self.stats['with_image']}")
        logger.info(f"   Reddedilen sorular : {self.stats['questions_rejected']}")
        logger.info(f"   Reddedilen gorseller: {self.stats['images_rejected']}")
        
        if self.stats['total_attempts'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total_attempts']) * 100
            logger.info(f"   Basari orani       : %{success_rate:.1f}")
        logger.info(f"{'='*70}\n")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='AYT Fizik Soru Uretim Botu',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler:
  python ayt_fizik_bot.py --mode batch --count 1
  python ayt_fizik_bot.py --mode topic --topic elektrostatik --count 5
  python ayt_fizik_bot.py --mode single --konu hareket_ve_kuvvet --bloom Analiz --zorluk 4

Gecerli Konular:
  hareket_ve_kuvvet, tork_ve_denge, dairesel_hareket, basit_harmonik_hareket,
  elektrostatik, manyetizma, alternatif_akim, dalgalar, elektromanyetik_dalgalar,
  ozel_gorelilik, kuantum_fizigi, atom_fizigi, standart_model,
  tibbi_goruntuleme, superleitkenlik
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
    parser.add_argument('--zorluk', type=int, default=4,
                       choices=[1, 2, 3, 4, 5],
                       help='Zorluk seviyesi (1-5)')
    
    args = parser.parse_args()
    
    logger.info("""
========================================================================
         AYT FIZIK SORU URETIM BOTU v1.0
         Gemini 2.5 Flash + Imagen 3 + Supabase
         OSYM Formatinda AYT Fizik Sorulari
========================================================================
    """)
    
    logger.info(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Mod: {args.mode}")
    
    try:
        generator = AYTFizikGenerator()
        
        if args.mode == 'batch':
            logger.info(f"Batch modu - Her konu icin {args.count} soru")
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
                gorsel_tipi=gorsel_tipi
            )
            
            logger.info(f"Single modu - {args.konu}")
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
