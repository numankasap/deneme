"""
Senaryo Görsel Botu v6.0 - GEMINI REALISTIC 3D Edition
======================================================
Gerçekçi 3D günlük yaşam görselleri üreten bot.

YENİLİKLER v6.0:
✅ SADECE GEMINI IMAGE: Imagen kaldırıldı, Gemini Image kullanılıyor
✅ GERÇEKÇİ 3D GÖRSELLER: Fotogerçekçi günlük yaşam sahneleri
✅ SORUYU ANLAMAYA YARDIMCI: Görsel süs değil, problemi anlatan tasvirler
✅ VERİLER NET GÖSTERİLİYOR: Soruda verilenler açıkça görselde
✅ ÇÖZÜM YOK: Cevap veya ipucu kesinlikle gösterilmiyor

MODELLER:
✅ Gemini 2.5 Flash Image: Hızlı, standart görseller
✅ Gemini 3 Pro Image: Yüksek kalite, karmaşık sahneler

GÖRSEL FELSEFESİ:
- Görsel sadece süs değil, soruyu ANLAMAYA yardımcı
- Soruda verilen TÜM değerler görselde görünür
- Günlük yaşamdan GERÇEKÇI 3D sahneler
- Fotogerçekçi render kalitesi

GitHub Actions ile çalışır.
"""

import os
import json
import time
import logging
import re
import base64
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from enum import Enum

from supabase import create_client, Client

try:
    from google import genai
    from google.genai import types
    NEW_GENAI = True
except ImportError:
    NEW_GENAI = False
    print("⚠️ google-genai paketi bulunamadı. pip install google-genai yapın.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============== MATEMATİKSEL NOTASYON DÖNÜŞTÜRÜCÜ ==============

def convert_math_notation(text: str) -> str:
    """
    Matematiksel notasyonları düzgün üst/alt simge formatına dönüştürür.

    Örnekler:
    - 8^6 → 8⁶
    - 4^9 → 4⁹
    - 2^14 → 2¹⁴
    - 8^3 . 8^2 → 8³ · 8²
    - x_1 → x₁
    """
    # Üst simge karakterleri
    superscript_map = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
        'n': 'ⁿ', 'x': 'ˣ', 'y': 'ʸ'
    }

    # Alt simge karakterleri
    subscript_map = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
        '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎'
    }

    result = text

    # Üslü ifadeleri dönüştür: 8^6 → 8⁶, 2^14 → 2¹⁴
    def replace_superscript(match):
        base = match.group(1)
        exp = match.group(2)
        sup_exp = ''.join(superscript_map.get(c, c) for c in exp)
        return base + sup_exp

    # Parantezli üsler: (8)^6, 8^(12)
    result = re.sub(r'(\d+)\^(\d+)', replace_superscript, result)
    result = re.sub(r'(\w)\^(\d+)', replace_superscript, result)

    # Alt indisleri dönüştür: x_1 → x₁
    def replace_subscript(match):
        base = match.group(1)
        sub = match.group(2)
        sub_chars = ''.join(subscript_map.get(c, c) for c in sub)
        return base + sub_chars

    result = re.sub(r'(\w)_(\d+)', replace_subscript, result)

    # Çarpma işaretini düzelt: . → · (orta nokta)
    result = re.sub(r'\s*\.\s*(?=\d)', ' · ', result)

    # Kesir gösterimi: 1/2 → ½ (yaygın kesirler)
    fraction_map = {
        '1/2': '½', '1/3': '⅓', '2/3': '⅔', '1/4': '¼', '3/4': '¾',
        '1/5': '⅕', '2/5': '⅖', '3/5': '⅗', '4/5': '⅘',
        '1/6': '⅙', '5/6': '⅚', '1/8': '⅛', '3/8': '⅜', '5/8': '⅝', '7/8': '⅞'
    }
    for frac, symbol in fraction_map.items():
        result = result.replace(frac, symbol)

    return result


# ============== MODEL TİPLERİ ==============

class ImageModel(Enum):
    """Görsel üretim modelleri - Sadece Gemini Image"""
    GEMINI_FLASH_IMAGE = "gemini-2.5-flash-preview-image-generation"  # Hızlı, standart
    GEMINI_PRO_IMAGE = "gemini-2.0-flash-exp-image-generation"         # Yüksek kalite, karmaşık


class VisualComplexity(Enum):
    """Görsel karmaşıklık seviyeleri"""
    SIMPLE = "simple"           # Basit grafik, tablo
    STANDARD = "standard"       # Standart çizim, sayı doğrusu
    COMPLEX = "complex"         # 3D, geometri, perspektif
    TEXT_HEAVY = "text_heavy"   # Çok metin içeren


# ============== YAPILANDIRMA ==============

class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Modeller
    ANALYSIS_MODEL = 'gemini-2.5-flash'
    
    # Storage
    STORAGE_BUCKET = 'questions-images'
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '20'))
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 3
    
    # Ayarlar
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    RATE_LIMIT_DELAY = 3
    MIN_PNG_SIZE = 5000
    MIN_QUALITY_SCORE = 6


# ============== MODEL SEÇİCİ ==============

class ModelSelector:
    """Soru tipine göre en uygun Gemini Image modelini seç - v6.0"""

    # Pro model gerektiren durumlar (karmaşık 3D sahneler ve grafikler)
    PRO_PATTERNS = [
        # Fonksiyon grafikleri (matematiksel doğruluk gerektirir)
        r'fonksiyon', r'f\(x\)', r'g\(x\)', r'grafik.*çiz',
        r'parabol', r'doğru.*denklemi', r'eğri',
        r'koordinat\s*düzlem', r'koordinat\s*sistem',
        r'integral', r'türev', r'limit',
        # 3D objeler
        r'3[dD]', r'üç boyut', r'perspektif',
        r'prizma', r'piramit', r'silindir', r'koni', r'küre', r'küp',
        # Geometrik şekiller (karmaşık)
        r'üçgen(?!sel)', r'dörtgen', r'çokgen', r'beşgen', r'altıgen',
        r'paralelkenar', r'yamuk', r'eşkenar', r'ikizkenar',
        # Daire/çember
        r'daire', r'çember', r'yay', r'dilim',
        # Mimari/teknik çizim
        r'mimar', r'bina', r'ev ', r'oda', r'bahçe', r'havuz',
        r'korkuluk', r'merdiven', r'balkon', r'teras',
        # Perspektif gerektiren
        r'kuş bakışı', r'yan görünüş', r'üstten', r'önden',
        # Senaryo sahneleri (gerçekçi 3D için)
        r'market', r'mağaza', r'fabrika', r'atölye', r'depo',
        r'araba', r'araç', r'tren', r'otobüs',
        r'tarla', r'arazi', r'alan\s+m²',
        r'tank', r'hazne', r'kap', r'kutu',
        r'yol', r'park', r'cadde', r'sokak',
        # Günlük yaşam sahneleri
        r'aile', r'çocuk', r'öğrenci', r'öğretmen',
        r'mutfak', r'salon', r'yatak', r'banyo',
        r'okul', r'hastane', r'restoran', r'kafe',
    ]

    @classmethod
    def select_model(cls, question_text: str, analysis: Dict) -> Tuple[ImageModel, str]:
        """
        Soru ve analize göre Gemini Image model seç
        Returns: (model, reason)
        """
        text = question_text.lower()
        visual_type = analysis.get('visual_type', '').lower()
        complexity = analysis.get('complexity', 'standard')

        # 1. Pro model kontrol (karmaşık 3D sahneler)
        for pattern in cls.PRO_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return ImageModel.GEMINI_PRO_IMAGE, f"Karmaşık sahne: {pattern}"

        # 2. Analiz complexity'ye göre
        if complexity == 'complex' or visual_type in ['geometry', '3d', 'scene', 'scenario_3d', 'function_graph', 'coordinate_system']:
            return ImageModel.GEMINI_PRO_IMAGE, f"Karmaşık görsel: {visual_type}"

        # 3. Varsayılan: Flash model (hızlı ve yeterli)
        return ImageModel.GEMINI_FLASH_IMAGE, "Standart görsel"


# ============== GÖRSEL PROMPT ŞABLONU (v6.0 - GERÇEKÇİ 3D) ==============

# Tek prompt şablonu - Gemini Image için optimize edilmiş
REALISTIC_3D_PROMPT = """Bir matematik problemi için FOTOGERÇEKÇİ 3D GÜNLÜK YAŞAM SAHNESİ oluştur.

## 🎯🎯🎯 GÖRSEL AMACI: SORUYU ANLAMAYA YARDIMCI OLMAK 🎯🎯🎯
⚠️ BU EN ÖNEMLİ KURAL! ⚠️

Görsel SADECE SÜS DEĞİL! Görsel şunları yapmalı:
1. Öğrencinin problemi ANLAMASINA yardımcı olmalı
2. Sorunun MANTIK ve YAPISINI göstermeli
3. Öğrencinin kafasında problemi CANLANDIRMALI
4. Çözüme giden yolda YARDIMCI olmalı (ama cevabı vermeden!)

❌ YANLIŞ GÖRSEL:
- Sadece "güzel" görünen ama soruyu anlatmayan görseller
- Sorunun özünü göstermeyen dekoratif sahneler
- Verileri rastgele gösteren "şablon" görseller

✅ DOĞRU GÖRSEL:
- Sorunun MANTIĞINI gösteren görsel
- Elemanlar arası İLİŞKİLERİ gösteren oklar/çizgiler
- Eşleştirme varsa → Hangi elemanların nasıl eşleşebileceğini göster
- Gruplama varsa → Grupları ve bağlantıları göster
- Kısıtlar varsa → Kısıtları görsel olarak ifade et

ÖRNEK - "10 veri seti, 5 işlem birimi, eşleştir" problemi için:
❌ YANLIŞ: Sadece veri merkezi görseli, kutular rastgele dizilmiş
✅ DOĞRU:
- 10 veri seti KARTI (her biri etiketli: 1TB, 2TB, 3TB...)
- 5 işlem birimi KUTUSU
- Aralarında EŞLEŞTİRME OKLARI
- "Büyük/Küçük = Tam Sayı" kuralı görsel olarak
- "Hedef: Toplam Minimum" etiketi

Soruda verilen TÜM bilgiler görselde NET olarak görünmeli.

## GÖRSEL TİPİ: {tip}

## SAHNE BETİMLEMESİ:
{detay}

## 📊 GÖRSELDE GÖRÜNECEK VERİLER (ÇOK ÖNEMLİ!):
{veriler}

## 🔢🔢🔢 HAYATI ÖNEM: BİRE BİR DOĞRU SAYILAR! 🔢🔢🔢
⚠️ SORUDA GEÇEN SAYILAR BİRE BİR AYNI OLMALI! ⚠️

ÖRNEK:
- "6 koli" diyorsa → SADECE 6 TANE koli çiz, 5 değil, 7 değil, TAM 6!
- "4 kutu" diyorsa → SADECE 4 TANE kutu çiz, 3 değil, 5 değil, TAM 4!
- "3 elma" diyorsa → SADECE 3 TANE elma çiz!

BU KURALI İHLAL ETME! Öğrenci görseldeki objeleri sayarak problemi anlayacak.
Yanlış sayıda obje göstermek öğrenciyi YANILTIR!

SAY VE KONTROL ET:
- Çizmeden önce soruda kaç tane obje var say
- Çizdikten sonra tekrar say
- Sayılar MUTLAKA eşleşmeli

## ⚠️⚠️⚠️ KRİTİK: ÇÖZÜM GÖSTERİLMEYECEK! ⚠️⚠️⚠️
- Sadece problemde VERİLEN bilgiler olacak
- Hesaplama sonucu KESİNLİKLE YOK
- Toplam, fark, sonuç değeri YOK
- Cevabı gösteren ok/vurgu YOK
- Öğrenci görselden cevabı BULAMAMALI!

## 🚫🚫🚫 HESAPLANMIŞ DEĞERLER YASAK! 🚫🚫🚫
Bu çok önemli! Soruda AÇIKÇA YAZILMAYAN hiçbir değer görselde OLMAMALI!

### TİP 1: HESAPLANMIŞ DEĞERLER
ÖRNEK - g(x) = x² - 6x + 11 fonksiyonu için:
❌ YASAK - Bunları GÖSTERME:
- Tepe noktası (3, 2) → CEVAP! Öğrenci bunu hesaplayacak!
- g(0) = 11 → Hesaplanmış, soruda yok
- (6, 11) noktası → Hesaplanmış, soruda yok
- Herhangi bir (x, y) koordinatı → Hesaplanmış
- "Minimum = 2" → CEVAP!

✅ İZİNLİ - Sadece bunları göster:
- g(x) = x² - 6x + 11 (formül AYNEN soruda yazıldığı gibi)
- Genel parabol şekli (noktalar İŞARETLENMEDEN)
- Koordinat eksenleri (x, y)
- Senaryo görseli (kolektör, fabrika vb.)

### TİP 2: SÖZEL İFADEDEN TÜRETİLEN FORMÜLLER YASAK! ⚠️⚠️⚠️
Bu ÇOK KRİTİK bir kural! Öğrenci problemi ANLAMALI ve formülü KENDİSİ oluşturmalı!

ÖRNEK - "Sapma miktarının mutlak değerinden 5 çıkarılınca 1 elde ediliyor" sorunu için:
❌ YASAK - Bunları GÖSTERME:
- |x - 3| - 5 = 1 → Bu formül soruda YAZMIYOR, öğrenci TÜRETMELİ!
- |sapma| - 5 = 1 → Bu da türetilmiş formül!
- Herhangi bir matematiksel eşitlik/denklem

✅ İZİNLİ - Sadece bunları göster:
- Sayı doğrusu (sadece doğru, işaretlenmemiş)
- "Hedef: 3" etiketi (soruda verildiyse)
- "5 birim" mesafe gösterimi (ok ile)
- "Sonuç: 1" etiketi (soruda verildiyse)
- Senaryo görseli (ok atan kişi, hedef vb.)

KURAL: Eğer soru bir durumu SÖZLÜ/KELİMELERLE anlatıyorsa ve matematiksel formül YAZMIYORSA:
→ O formülü sen de YAZMA!
→ Öğrenci o formülü KENDİSİ türetecek!
→ Sadece GÖRSEL/BETİMLEYİCİ öğeler göster!

### TİP 3: SAYI DOĞRUSU KURALLARI 📏
Sayı doğrusu içeren sorularda ÖLÇEK ve KONUMLANDIRMA çok önemli!

DOĞRU ÖLÇEK:
- Birim mesafeler EŞİT olmalı (1 birim = 1 birim uzaklık)
- "9 birim" diyorsa → 0'dan 9'a kadar TAM 9 birim uzaklık
- Sayılar doğru konumda olmalı

ÖRNEK - "Hedef 3, sapma x, mesafe 9 birim" için:
❌ YANLIŞ:
- 9 rakamını sayı doğrusu DIŞINDA göstermek
- Mesafeyi yanlış konumda göstermek
- Ölçeği bozuk çizmek

✅ DOĞRU:
- Sayı doğrusu: ... -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 ...
- Hedef noktası işaretli (örn: 3)
- Mesafe oku sayı doğrusu ÜZERİNDE
- Ölçek tutarlı ve eşit aralıklı

KURAL: Eğer bir değer soruda AÇIKÇA YAZILMAMIŞSA → GÖSTERME!
Öğrenci o değeri KENDİSİ hesaplayacak, sen ipucu VERME!

### TİP 4: GERÇEK SAYILAR KURALI - YER TUTUCU YASAK! 🔢🔢🔢
Bu EN KRİTİK kuraldır! Görseldeki sayılar soruda verilen GERÇEK sayılar olmalı!

⚠️⚠️⚠️ YER TUTUCU / GENERİC DEĞERLER YASAK! ⚠️⚠️⚠️
Görsel bir "şablon" veya "örnek" DEĞİL! Soruya ÖZEL olmalı!

ÖRNEK - "Drone 500 metre yükseklikte, ±15 metre tolerans" sorusu için:
❌ YASAK - Bunları YAPMA:
- Cetvel 0-50 metre arası → 500 metre olmalıydı!
- "İdeal irtifa" 10m seviyesinde → 500m seviyesinde olmalı!
- Rastgele/genel değerler kullanmak
- Ölçeği küçültmek veya değiştirmek

✅ DOĞRU - Bunları YAP:
- Cetvel 480m - 520m arası göstermeli (500 ± 20 civarı)
- "İdeal İrtifa: 500m" etiketi TAM 500m noktasında
- "Tolerans: ±15m" etiketi doğru ölçekte (485m - 515m arası)
- Drone 500m seviyesinde görünmeli

NEDEN ÖNEMLİ?
- Öğrenci görselden SORUYU anlamalı
- Görseldeki 50 ≠ Sorudaki 500!
- Yanlış değerler öğrenciyi YANILTIR!
- Her soru ÖZEL görsel hak eder, şablon değil!

KURAL: Soruda hangi SAYILAR varsa → Görselde BİREBİR AYNI sayılar olacak!
- "500 metre" → görselde 500
- "15 metre tolerans" → görselde 15 metre aralık
- "3 kilo" → görselde 3 kilo
- Generic/placeholder değerler KESİNLİKLE YASAK!

### TİP 5: GÖRSEL SORUNUN ÖZÜNÜ ANLATMALI - SÜS DEĞİL! 🎯🎯🎯
Bu kural ÇOK ÖNEMLİ! Görsel sadece "güzel" olmamalı, soruyu ANLATMALI!

⚠️ SORUNUN MANTIK YAPISINI GÖSTER:

EŞLEŞTİRME/GRUPLAMA PROBLEMLERİ İÇİN:
- Elemanları KARTLAR/KUTULAR olarak göster
- Eşleştirmeleri OKLAR ile göster
- Hangi elemanların birbiriyle eşleşebileceğini ima et
- Kural varsa (örn: "Büyük/Küçük = Tam Sayı") görsel olarak göster

OPTİMİZASYON PROBLEMLERİ İÇİN:
- Hedefi göster: "Minimum", "Maksimum", "En az", "En çok"
- Kısıtları göster
- Elemanlar arası ilişkileri göster

ÖRNEK - "10 veri seti (1,2,3,4,5,6,9,12,15,18) TB, 5 çift oluştur, oran tam sayı" için:
✅ DOĞRU GÖRSEL:
- Sol: 10 kart (1TB, 2TB, 3TB, 4TB, 5TB, 6TB, 9TB, 12TB, 15TB, 18TB)
- Sağ: 5 işlem birimi kutusu
- Ortada: Eşleştirme okları (boş veya örnek bir iki ok)
- Alt panel: "Katsayı = Büyük ÷ Küçük = TAM SAYI"
- Üst panel: "🎯 Hedef: Σ Katsayılar → MİNİMUM"

❌ YANLIŞ GÖRSEL:
- Sadece veri merkezi fotoğrafı
- Kutular rastgele dizilmiş
- Eşleştirme konsepti yok
- Sorunun mantığı görünmüyor

## 🎨 FOTOGERÇEKÇİ 3D STİL:

### RENDER KALİTESİ:
- Fotogerçekçi 3D render (Pixar/Disney kalitesi)
- Yumuşak global aydınlatma
- Gerçekçi gölgeler ve yansımalar
- Depth of field efekti
- Ambient occlusion
- Subsurface scattering (ciltler için)

### GÜNLÜK YAŞAM SAHNESİ:
- Gerçek dünyadan tanıdık mekanlar
- Market: Raflar, ürünler, fiyat etiketleri
- Mutfak: Tencere, bardak, malzemeler
- Bahçe: Çimler, çiçekler, ağaçlar
- Okul: Sıralar, tahta, defterler
- Sokak: Arabalar, binalar, tabelalar

### OBJELER:
- Gerçekçi malzeme dokuları
- Doğru ölçek ve oranlar
- Tanınabilir günlük objeler
- Detaylı yüzey işlemeleri

### RENKLER:
- Doğal, gerçekçi renkler
- Sıcak aydınlatma tonu
- Kontrast ama göz yormayan
- Her öğe farklı renkle ayırt edilebilir

### ETİKETLER VE SAYILAR:
- Temiz, okunabilir fontlar
- 3D yüzer etiketler veya sahneye entegre
- Türkçe karakterler: ş, ğ, ü, ö, ç, ı, İ
- Fiyat etiketleri, ölçüm çizgileri gerçekçi

### 📐 MATEMATİKSEL NOTASYON (ÇOK ÖNEMLİ!):
- Üslü ifadelerde DOĞRU üst simge kullan:
  * 8⁶ (DOĞRU) - 8^6 (YANLIŞ)
  * 4⁹ (DOĞRU) - 4^9 (YANLIŞ)
  * 2¹⁴ (DOĞRU) - 2^14 (YANLIŞ)
- Çarpma işareti: · (orta nokta) kullan, . (nokta) değil
  * 8³ · 8² (DOĞRU) - 8^3 . 8^2 (YANLIŞ)
- Kesirler: ½, ⅓, ¼ gibi semboller kullan
- Karekök: √ sembolü kullan
- Pi: π sembolü kullan

### ⚠️ VERİLER BİRE BİR SORUDA YAZDIĞI GİBİ!
- Soruda hangi değerler varsa AYNEN o değerleri göster
- Değerleri UYDURMA veya DEĞİŞTİRME!
- Soruda "4⁹, 2¹⁴, 16⁴, 8³·8², 64²" varsa → AYNEN bunları göster
- Başka değerler KOYMA!

### 🚫🚫🚫 FONKSİYON GRAFİĞİ ÇİZME! 🚫🚫🚫
⚠️⚠️⚠️ BU ÇOK ÖNEMLİ! ⚠️⚠️⚠️

AI görsel modelleri matematiksel olarak DOĞRU grafik ÇİZEMEZ!
- g'(x) = x + 1 doğrusunu YANLIŞ çizer!
- Parabolün tepe noktası YANLIŞ konumda olur!
- x ve y kesişimleri YANLIŞ olur!

YANLIŞ GRAFİK = YANLIŞ ÖĞRENME!
Öğrenci yanlış grafik şeklini öğrenir ve sınavda HATA yapar!

❌ YAPMA:
- Koordinat sistemi çizme
- Parabol, doğru, eğri çizme
- f(x), g(x), f'(x) grafikleri çizme
- x-y ekseni çizme

✅ BUNUN YERİNE:
- SADECE senaryo görseli göster (fabrika, laboratuvar, ofis)
- Formülü metin olarak yaz (g(x) = x² - 6x + 11)
- GRAFİK ÇİZME!

### GEOMETRİ İÇİN:
- Gerçek dünya objeleri olarak şekiller
  * Üçgen → Çatı, pizza dilimi, trafik levhası
  * Dikdörtgen → Kapı, pencere, kitap
  * Daire → Tekerlek, saat, tabak
  * Küp → Zar, kutu, bina
  * Silindir → Bardak, kalem, sütun
- Ölçümler gerçekçi etiketlerle

### TABLO VE GRAFİK İÇİN:
- Dijital ekran veya poster olarak entegre
- Veya fiziksel objelerle temsil
  * Çubuk grafik → Farklı boyutlu kutular
  * Pasta grafik → Gerçek pasta dilimleri
  * Tablo → Beyaz tahta veya kağıt

### KOMPOZİSYON:
- Merkeze odaklı düzen
- Tüm veriler görünür
- Dağınık değil, organize
- Arka plan bulanık (odak ön planda)

## ✅ MUTLAKA OLMALI:
- Soruda verilen TÜM değerler görünür
- Gerçekçi 3D günlük yaşam sahnesi
- Problemi anlamaya yardımcı tasarım
- Türkçe etiketler doğru karakterlerle
- Profesyonel render kalitesi

## ❌ KESİNLİKLE OLMAMALI:
- Çözüm veya cevap
- Hesaplanmış değerler
- Soru metni aynen
- A, B, C, D şıkları
- Cevabı ima eden herhangi bir şey"""


# ============== KAZANIM FİLTRESİ (v5.1 - AKILLI FİLTRELEME) ==============

class LearningOutcomeFilter:
    """
    Akıllı filtreleme sistemi - Matematik sorularını yanlışlıkla filtrelemeyi önler.

    Yeni yaklaşım:
    - Sadece GERÇEK fizik/kimya soruları dışlanır
    - Matematik bağlamında geçen fizik terimleri işlenir
    - Bağlam analizi yapılır
    """

    # Kesin fizik/kimya soruları - bu kelimeler SADECE fizik bağlamında kullanılır
    STRICT_PHYSICS_PATTERNS = [
        r'sarkaç', r'salınım',
        r'elektrik\s*akım', r'elektrik\s*devre', r'voltaj', r'amper',
        r'manyetik\s*alan', r'mıknatıs',
        r'dalga\s*boyu', r'frekans\s*hz',
        r'molekül\s*yapı', r'atom\s*modeli', r'elektron\s*sayısı',
        r'kimyasal\s*tepkime', r'element\s*sembol',
        r'ışık\s*hızı', r'optik',
    ]

    # Bu kelimeler varsa matematik sorusu olma ihtimali yüksek (override)
    MATH_OVERRIDE_PATTERNS = [
        r'toplam', r'fark', r'çarp', r'böl',
        r'oran', r'yüzde', r'kesir', r'ondalık',
        r'denklem', r'eşitsizlik', r'fonksiyon',
        r'sayı\s*doğrusu', r'koordinat',
        r'üçgen', r'dörtgen', r'daire', r'çember',
        r'alan', r'çevre', r'hacim',
        r'tablo', r'grafik', r'karşılaştır',
        r'kaç\s*tl', r'kaç\s*lira', r'kaç\s*kg', r'kaç\s*metre',
        r'firma', r'market', r'mağaza', r'fabrika',
        r'indirim', r'fiyat', r'maliyet', r'kar', r'zarar',
        r'yaş\s*problem', r'sayı\s*problem',
        r'olasılık', r'istatistik', r'ortalama',
    ]

    # Bağlam gerektiren kelimeler - tek başına filtreleme için yeterli değil
    # Bu kelimeler SADECE fizik bağlamı ile birlikte dışlanır
    CONTEXT_DEPENDENT = {
        'ısı': [r'ısı\s*transfer', r'ısı\s*ilet', r'kalori', r'joule', r'termodinamik'],
        'sıcaklık': [r'derece\s*celsius', r'termometre', r'ısın', r'soğu'],
        'kuvvet': [r'newton', r'sürtünme\s*kuvvet', r'yer\s*çekim', r'itme', r'çekme\s*kuvvet'],
        'ivme': [r'm/s²', r'metre.*saniye.*kare', r'hız\s*değişim', r'düzgün\s*ivme'],
        'hız': [r'km/sa', r'm/s', r'hız\s*zaman\s*grafik', r'anlık\s*hız'],
        'periyot': [r'periyodik\s*hareket', r'periyot\s*formül'],
    }

    @classmethod
    def should_process(cls, question: Dict) -> Tuple[bool, str]:
        """
        Sorunun işlenip işlenmeyeceğini belirle.

        Returns:
            (True, "OK") - İşlenecek
            (False, reason) - Filtrelendi
        """
        text = ' '.join([
            question.get('original_text') or '',
            question.get('scenario_text') or '',
            question.get('learning_outcome') or '',
            question.get('tags') or ''
        ]).lower()

        # 1. Matematik override kontrolü - bu kelimeler varsa işle
        for pattern in cls.MATH_OVERRIDE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, f"Matematik içerik tespit: {pattern}"

        # 2. Kesin fizik/kimya kontrolü
        for pattern in cls.STRICT_PHYSICS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"Fizik/Kimya içerik (kesin): {pattern}"

        # 3. Bağlam bağımlı kelime kontrolü
        for word, physics_contexts in cls.CONTEXT_DEPENDENT.items():
            if word in text:
                # Fizik bağlamı var mı kontrol et
                is_physics = False
                for physics_pattern in physics_contexts:
                    if re.search(physics_pattern, text, re.IGNORECASE):
                        is_physics = True
                        break

                if is_physics:
                    return False, f"Fizik bağlamı tespit: {word}"
                # Fizik bağlamı yoksa matematik problemi olarak işle

        return True, "OK"


# ============== GEMİNİ API ==============

class GeminiAPI:
    """Gemini API - Analiz ve Görsel Üretimi (Hybrid)"""
    
    def __init__(self):
        if not NEW_GENAI:
            raise ValueError("google-genai paketi gerekli!")
        
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self._last_request = 0
        logger.info("✅ Gemini API başlatıldı (Hybrid Mode)")
    
    def _rate_limit(self):
        """Rate limiting"""
        elapsed = time.time() - self._last_request
        if elapsed < Config.RATE_LIMIT_DELAY:
            time.sleep(Config.RATE_LIMIT_DELAY - elapsed)
        self._last_request = time.time()
    
    def analyze_question(self, question_text: str, scenario_text: str = None) -> Optional[Dict]:
        """Soruyu analiz et ve gerçekçi 3D görsel bilgilerini çıkar - v6.0"""

        full_text = question_text
        if scenario_text:
            full_text = f"SENARYO:\n{scenario_text}\n\nSORU:\n{question_text}"

        prompt = f"""Sen bir matematik eğitimi için GERÇEKÇİ 3D GÜNLÜK YAŞAM GÖRSEL tasarımcısısın.

Verilen soruyu analiz et ve bu soruyu ANLAMAYA YARDIMCI OLACAK gerçekçi bir görsel tasarla.

🎯🎯🎯 GÖRSEL AMACI - EN ÖNEMLİ KURAL! 🎯🎯🎯
Görsel SADECE SÜS DEĞİL! Görsel şunları yapmalı:
1. Öğrencinin problemi ANLAMASINA yardımcı olmalı
2. Sorunun MANTIK ve YAPISINI göstermeli
3. Öğrencinin kafasında problemi CANLANDIRMALI
4. Çözüme giden yolda YARDIMCI olmalı (cevabı vermeden!)

EŞLEŞTİRME/GRUPLAMA PROBLEMLERİ İÇİN:
- Elemanları KARTLAR olarak göster
- Eşleştirmeleri OKLAR ile göster
- İlişkileri görsel olarak ifade et

ÖRNEK - "10 veri seti, 5 çift oluştur" problemi:
❌ YANLIŞ: Sadece veri merkezi görseli
✅ DOĞRU: 10 kart + 5 kutu + eşleştirme okları + kural etiketi

Soruda verilen TÜM bilgiler görselde NET olarak görünmeli.

⚠️ KRİTİK KURALLAR:

1. GÖRSEL GEREKLİ DURUMLAR (geniş kapsamlı düşün):
   - Market/alışveriş problemleri → Gerçekçi market rafları, ürünler, fiyat etiketleri
   - Fabrika/üretim → Makineler, işçiler, ürünler
   - Bahçe/tarla → Gerçekçi açık alan, bitkiler, ölçümler
   - Havuz/su deposu → Gerçekçi su konteynerleri
   - Okul/sınıf → Öğrenciler, sıralar, tahta
   - Aile/yaş problemleri → Gerçekçi aile üyeleri
   - Geometri → Gerçek dünya objeleri olarak şekiller
   - Tablo/grafik → Dijital ekran veya poster olarak
   - Para/bütçe → Fiyat etiketleri, kasiyerler
   - Karşılaştırma → Yan yana objeler

2. ⚠️⚠️⚠️ FONKSİYON GRAFİĞİ / KOORDİNAT SİSTEMİ SORULARI → GÖRSEL YAPMA! ⚠️⚠️⚠️
   AI görsel modelleri matematiksel olarak DOĞRU grafik ÇİZEMEZ!
   Yanlış grafik öğrenciyi YANILTIR ve YANLIŞ ÖĞRENME riski oluşturur!

   Bu tür soruları "visual_needed: false" olarak işaretle:
   - Fonksiyon grafikleri: f(x), g(x), parabola, doğru grafiği
   - Koordinat sistemi çizimleri
   - Türev/integral grafikleri: f'(x), g'(x)
   - Eğri çizimleri
   - x-y ekseni üzerinde çizim gerektiren sorular

   ❌ YAPMA: Grafiği çizmeye çalışma - YANLIŞ çizeceksin!
   ✅ YAP: "visual_needed: false" döndür, reason: "Fonksiyon grafiği matematiksel doğruluk gerektirir, AI çizemez"

3. GÖRSEL GEREKSİZ DİĞER DURUMLAR:
   - SADECE basit dört işlem (5+3=?)
   - Tek satırlık formül
   - Görselleştirilecek HIÇBIR veri yok

3. ⚠️⚠️⚠️ ÇÖZÜM ve HESAPLANMIŞ DEĞERLER YASAK! ⚠️⚠️⚠️
   - Hesaplama sonucu YOK
   - Toplam, fark, sonuç YOK
   - Cevap ipucu YOK
   - Sadece SORUDA AÇIKÇA YAZILAN değerler

   ÖRNEK: g(x) = x² - 6x + 11 için:
   ❌ Tepe noktası (3,2) GÖSTERME → Bu CEVAP!
   ❌ g(0)=11 GÖSTERME → Hesaplanmış
   ✅ Sadece "g(x) = x² - 6x + 11" formülü göster

4. ⚠️⚠️⚠️ SÖZEL İFADEDEN TÜRETİLEN FORMÜLLER YASAK! ⚠️⚠️⚠️
   Eğer soru bir durumu KELİMELERLE anlatıyor ve matematiksel formül YAZMIYORSA:
   → O formülü sen de YAZMA! Öğrenci TÜRETMELİ!

   ÖRNEK: "sapma miktarının mutlak değerinden 5 çıkarılınca 1 oluyor" için:
   ❌ |x - 3| - 5 = 1 GÖSTERME → Bu formül soruda YOK, öğrenci türetecek!
   ✅ Sadece sayı doğrusu, hedef işareti, mesafe oku göster

5. 📏 SAYI DOĞRUSU KURALLARI:
   - Birim mesafeler EŞİT olmalı
   - Sayılar DOĞRU konumda olmalı
   - "9 birim" diyorsa → sayı doğrusu üzerinde 9 birim mesafe göster
   - Mesafe okları sayı doğrusu ÜZERİNDE olmalı

4. KARMAŞIKLIK:
   - "simple": Tek obje, basit sahne
   - "standard": Birkaç obje, basit sahne
   - "complex": Çok objeli detaylı sahne

5. 🎬 GERÇEKÇİ SAHNE BETİMLEME:
   Detaylı betimleme yazarken:
   - GÜNLÜK YAŞAMDAN tanıdık bir mekan seç
   - Gerçekçi objeler ve insanlar ekle
   - Soruda verilen TÜM sayıları nerede göstereceğini belirt
   - Fotogerçekçi 3D render olarak düşün
   - Pixar/Disney animasyon kalitesi

6. 🔢🔢🔢 GERÇEK SAYILAR - YER TUTUCU YASAK! (EN KRİTİK KURAL!) 🔢🔢🔢
   ⚠️ Görseldeki sayılar soruda verilen GERÇEK sayılar olmalı! ⚠️
   ⚠️ Generic/placeholder/şablon değerler KESİNLİKLE YASAK! ⚠️

   ÖRNEK - "Drone 500 metre yükseklikte, ±15 metre tolerans" için:
   ❌ YASAK:
     - Cetvel 0-50m arası göstermek (500 olmalı!)
     - "İdeal irtifa" 10m seviyesinde (500m olmalı!)
     - Rastgele/örnek değerler kullanmak
   ✅ DOĞRU:
     - Cetvel ~480m-520m arası göstermeli
     - "İdeal İrtifa: 500m" TAM 500m noktasında
     - "Tolerans: ±15m" doğru ölçekte

   ÖRNEK - "6 koli, 4 kutu" için:
   ❌ YASAK: 9 koli, 5 kutu çizmek
   ✅ DOĞRU: TAM 6 koli, TAM 4 kutu

   NEDEN? Öğrenci görselden SORUYU anlamalı. Yanlış değerler YANILTIR!

7. 📐 MATEMATİKSEL NOTASYON:
   - Soruda hangi matematiksel ifadeler varsa AYNEN yaz
   - 8^6 → 8⁶ şeklinde üst simge kullan
   - Çarpma: · (orta nokta) kullan
   - Soruda "4^9, 2^14, 16^4" varsa → "4⁹, 2¹⁴, 16⁴" yaz
   - Değerleri DEĞİŞTİRME, UYDURMA, AYNEN kopyala!

8. 🚫🚫🚫 FONKSİYON GRAFİĞİ / KOORDİNAT SİSTEMİ → "visual_needed: false"! 🚫🚫🚫
   AI görsel modelleri matematiksel olarak DOĞRU grafik ÇİZEMEZ!
   YANLIŞ grafik öğrenciyi YANILTIR ve YANLIŞ ÖĞRENME riski oluşturur!

   Bu sorular için → "visual_needed": false döndür:
   - f(x), g(x), f'(x), g'(x) grafikleri
   - Parabol, doğru, eğri çizimleri
   - Koordinat sistemi gerektiren sorular
   - Türev/integral grafikleri

   ⚠️ NEDEN? Görsellerdeki hatalar:
   - g'(x) = x + 1 doğrusunu YANLIŞ çiziyor
   - Parabol tepe noktası YANLIŞ konumda
   - Eksen kesişimleri YANLIŞ

   → "visual_needed": false, "reason": "Fonksiyon grafiği - AI doğru çizemez"

SORU:
{full_text}

SADECE JSON FORMATINDA CEVAP VER:
{{
    "visual_needed": true/false,
    "visual_type": "market_scene/factory_scene/garden_scene/classroom_scene/family_scene/geometry_real/chart_display/comparison_scene/function_graph/coordinate_system/number_line",
    "complexity": "simple/standard/complex",
    "quality_score": 1-10,
    "title": "Kısa başlık",
    "gorsel_betimleme": {{
        "tip": "Sahne tipi. Drone/yükseklik: 'dikey yükseklik cetveli ile drone'. GRAFİK: 'fonksiyon grafiği'",
        "detay": "ÇOK DETAYLI sahne. ⚠️ SORUDA VERİLEN GERÇEK SAYILARI BİREBİR KULLAN! 500 metre diyorsa 500 yaz, 50 değil! ⚠️ HESAPLANMIŞ DEĞER YAZMA! ⚠️ Generic/placeholder değerler YASAK!",
        "veriler": "SORUDA VERİLEN GERÇEK DEĞERLER! Örn: '500 metre yükseklik', '15 metre tolerans' → görselde TAM bu sayılar! Generic 0-50 gibi değerler YASAK!",
        "renkler": "Her öğe için FARKLI renk",
        "perspektif": "Yükseklik: 'dikey cetvel 480m-520m arası, drone 500m seviyesinde'. Grafik: 'düz koordinat düzlemi'"
    }},
    "reason": "neden görsel gerekli/gereksiz"
}}"""

        self._rate_limit()
        
        try:
            response = self.client.models.generate_content(
                model=Config.ANALYSIS_MODEL,
                contents=prompt
            )
            
            text = response.text.strip()
            
            # JSON çıkar
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            result = json.loads(text)
            
            if not result.get('visual_needed', False):
                logger.info(f"  ⏭️ Görsel gerekmiyor: {result.get('reason', 'Belirtilmedi')}")
                return None
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"  ⚠️ JSON parse hatası: {e}")
            return None
        except Exception as e:
            logger.error(f"  ❌ Analiz hatası: {e}")
            return None
    
    def generate_image(self, gorsel_info: Dict, title: str, model: ImageModel) -> Optional[bytes]:
        """Gemini Image ile gerçekçi 3D görsel üret"""

        tip = gorsel_info.get('tip', 'realistic 3D scene')
        detay = gorsel_info.get('detay', '')
        veriler = gorsel_info.get('veriler', '')
        renkler = gorsel_info.get('renkler', '')
        perspektif = gorsel_info.get('perspektif', 'eye-level realistic view')

        # Matematiksel notasyonları düzelt (8^6 → 8⁶)
        detay = convert_math_notation(detay)
        veriler = convert_math_notation(veriler)

        # Detayı zenginleştir
        if renkler:
            detay = f"{detay}\n\nRENKLER: {renkler}"
        if perspektif:
            detay = f"{detay}\n\nPERSPEKTİF: {perspektif}"

        # Tek prompt şablonu kullan
        prompt = REALISTIC_3D_PROMPT.format(
            tip=tip,
            detay=detay,
            veriler=veriler
        )

        logger.info(f"  🎨 Model: {model.value}")
        logger.info(f"  📐 Tip: {tip}")

        self._rate_limit()

        for attempt in range(Config.MAX_RETRIES):
            try:
                # Tüm modeller Gemini Image API kullanıyor
                response = self.client.models.generate_content(
                    model=model.value,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    )
                )

                # Response'dan görsel çıkar
                image_bytes = self._extract_image(response)

                if image_bytes:
                    if len(image_bytes) < Config.MIN_PNG_SIZE:
                        logger.warning(f"  ⚠️ Görsel çok küçük: {len(image_bytes)} bytes")
                        continue

                    logger.info(f"  ✅ Görsel üretildi ({len(image_bytes) / 1024:.1f} KB)")
                    return image_bytes

                logger.warning("  ⚠️ Görsel response'da bulunamadı")

            except Exception as e:
                logger.error(f"  ❌ Görsel üretim hatası (deneme {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_DELAY)

        return None

    def _extract_image(self, response) -> Optional[bytes]:
        """Gemini response'dan görsel byte'larını çıkar"""

        try:
            # Gemini Image response yapısı
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        inline = part.inline_data
                        if hasattr(inline, 'data') and inline.data:
                            image_data = inline.data
                            if isinstance(image_data, str):
                                return base64.b64decode(image_data)
                            else:
                                return bytes(image_data) if not isinstance(image_data, bytes) else image_data

        except Exception as e:
            logger.error(f"  ❌ Görsel çıkarma hatası: {e}")

        return None


# ============== VERİTABANI ==============

class DatabaseManager:
    """Supabase işlemleri"""
    
    def __init__(self):
        self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("✅ Supabase bağlantısı kuruldu")
    
    def get_questions(self, limit: int = 20) -> List[Dict]:
        """Görsel bekleyen soruları getir - TÜM sorular (scenario_text olsun olmasın)"""
        try:
            # Önce scenario_text olan sorulara bak, yoksa tüm sorulara
            response = self.client.table('question_bank') \
                .select('*') \
                .is_('image_url', 'null') \
                .eq('is_active', True) \
                .order('id', desc=False) \
                .limit(limit) \
                .execute()

            questions = response.data or []

            # Sadece original_text veya scenario_text olan soruları filtrele
            valid_questions = [
                q for q in questions
                if q.get('original_text') or q.get('scenario_text')
            ]

            logger.info(f"📋 {len(valid_questions)} soru bulundu (toplam çekilen: {len(questions)})")
            return valid_questions
        except Exception as e:
            logger.error(f"Soru çekme hatası: {e}")
            return []
    
    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Görseli storage'a yükle"""
        try:
            self.client.storage.from_(Config.STORAGE_BUCKET).upload(
                filename,
                image_bytes,
                {'content-type': 'image/png', 'upsert': 'true'}
            )
            url = self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
            return url
        except Exception as e:
            logger.error(f"Upload hatası: {e}")
            return None
    
    def update_image_url(self, question_id: int, image_url: str) -> bool:
        """image_url güncelle"""
        try:
            self.client.table('question_bank') \
                .update({'image_url': image_url}) \
                .eq('id', question_id) \
                .execute()
            return True
        except Exception as e:
            logger.error(f"Güncelleme hatası: {e}")
            return False


# ============== ANA BOT ==============

class ScenarioImageBot:
    """Senaryo soruları için gerçekçi 3D görsel üreten bot - Gemini Image"""

    def __init__(self):
        self.db = DatabaseManager()
        self.gemini = GeminiAPI()
        self.stats = {
            'total': 0,
            'success': 0,
            'filtered': 0,
            'no_visual': 0,
            'failed': 0,
            'by_model': {
                'gemini_flash': 0,
                'gemini_pro': 0
            }
        }

    def run(self):
        """Botu çalıştır"""
        logger.info("""
╔══════════════════════════════════════════════════════════════════════╗
║         🎨 SENARYO GÖRSEL BOTU v6.0 - GERÇEKÇİ 3D Edition            ║
║         Gemini 2.5 Flash + Gemini 2.0 Pro Image                      ║
╚══════════════════════════════════════════════════════════════════════╝
        """)
        logger.info(f"📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("✅ Gemini Flash Image: Standart görseller, grafikler")
        logger.info("✅ Gemini Pro Image: Karmaşık 3D sahneler, geometri")
        logger.info("✅ Gerçekçi 3D: Fotogerçekçi günlük yaşam sahneleri")
        logger.info("✅ Veriler NET: Soruda verilenler açıkça görünür")
        logger.info("⚠️ ÇÖZÜM YOK: Sadece ham veriler, cevap ipucu yok!")
        logger.info("=" * 60)
        
        try:
            batch_size = Config.TEST_BATCH_SIZE if Config.TEST_MODE else Config.BATCH_SIZE
            logger.info(f"⚙️ Mod: {'TEST' if Config.TEST_MODE else 'PRODUCTION'}")
            logger.info(f"📦 Batch: {batch_size}")
            
            questions = self.db.get_questions(batch_size)
            if not questions:
                logger.warning("⚠️ İşlenecek soru yok!")
                return
            
            self.stats['total'] = len(questions)
            
            for i, q in enumerate(questions):
                logger.info(f"\n{'─' * 60}")
                logger.info(f"📝 Soru {i+1}/{len(questions)} (ID: {q['id']})")
                logger.info(f"{'─' * 60}")
                
                self._process_question(q)
                
                time.sleep(Config.RATE_LIMIT_DELAY)
            
            self._print_report()
            
        except Exception as e:
            logger.error(f"Bot hatası: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _process_question(self, question: Dict):
        """Tek soruyu işle"""
        qid = question['id']
        text = question.get('original_text', '')
        scenario = question.get('scenario_text', '')
        
        if not text:
            logger.warning("⚠️ Soru metni boş!")
            self.stats['filtered'] += 1
            return
        
        # 1. Kazanım filtresi
        should_process, reason = LearningOutcomeFilter.should_process(question)
        if not should_process:
            logger.info(f"⏭️ Filtrelendi: {reason}")
            self.stats['filtered'] += 1
            return
        
        # 2. Analiz
        logger.info("🔍 Analiz ediliyor...")
        analysis = self.gemini.analyze_question(text, scenario)
        
        if not analysis:
            self.stats['no_visual'] += 1
            return
        
        visual_type = analysis.get('visual_type', 'unknown')
        complexity = analysis.get('complexity', 'standard')
        quality = analysis.get('quality_score', 0)
        title = analysis.get('title', 'Problem')

        logger.info(f"📊 Tip: {visual_type}, Karmaşıklık: {complexity}, Kalite: {quality}/10")

        # 2.5 FONKSİYON GRAFİĞİ FİLTRESİ - Matematiksel doğruluk riski!
        SKIP_VISUAL_TYPES = ['function_graph', 'coordinate_system', 'graph', 'parabola', 'line_graph']
        if visual_type.lower() in SKIP_VISUAL_TYPES or 'graph' in visual_type.lower() or 'grafik' in visual_type.lower():
            logger.warning(f"⚠️ GRAFİK SORULARI ATLANIYOR: {visual_type}")
            logger.warning("⚠️ Sebep: AI modelleri matematiksel olarak doğru grafik çizemiyor!")
            logger.warning("⚠️ Yanlış grafik öğrenciyi yanıltır - görsel üretilmedi.")
            self.stats['filtered'] += 1
            return

        # 3. Model seç
        full_text = f"{scenario}\n{text}" if scenario else text
        selected_model, model_reason = ModelSelector.select_model(full_text, analysis)
        logger.info(f"🎯 Model seçimi: {selected_model.name} - {model_reason}")
        
        # 4. Görsel üret
        gorsel_betimleme = analysis.get('gorsel_betimleme', {})
        image_bytes = self.gemini.generate_image(gorsel_betimleme, title, selected_model)
        
        if not image_bytes:
            logger.error("❌ Görsel üretilemedi!")
            self.stats['failed'] += 1
            return
        
        # 5. Upload
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        model_prefix = selected_model.name.lower().replace('_', '-')
        filename = f"scenario/{model_prefix}/q_{qid}_{timestamp}.png"
        
        logger.info("☁️ Yükleniyor...")
        image_url = self.db.upload_image(image_bytes, filename)
        
        if not image_url:
            logger.error("❌ Upload başarısız!")
            self.stats['failed'] += 1
            return
        
        # 6. Veritabanı güncelle
        if self.db.update_image_url(qid, image_url):
            logger.info(f"✅ #{qid}: BAŞARILI ({visual_type} / {selected_model.name})")
            self.stats['success'] += 1

            # Model istatistiği
            if selected_model == ImageModel.GEMINI_FLASH_IMAGE:
                self.stats['by_model']['gemini_flash'] += 1
            else:
                self.stats['by_model']['gemini_pro'] += 1
        else:
            logger.error("❌ DB güncelleme başarısız!")
            self.stats['failed'] += 1

    def _print_report(self):
        """Sonuç raporu"""
        logger.info(f"\n{'=' * 60}")
        logger.info("📊 SONUÇ RAPORU")
        logger.info(f"{'=' * 60}")
        logger.info(f"   Toplam soru        : {self.stats['total']}")
        logger.info(f"   Başarılı           : {self.stats['success']}")
        logger.info(f"   Filtrelenen        : {self.stats['filtered']}")
        logger.info(f"   Görsel gerekmez    : {self.stats['no_visual']}")
        logger.info(f"   Başarısız          : {self.stats['failed']}")
        logger.info(f"   ─────────────────────────────────────")
        logger.info(f"   MODEL DAĞILIMI:")
        logger.info(f"     Gemini Flash     : {self.stats['by_model']['gemini_flash']}")
        logger.info(f"     Gemini Pro       : {self.stats['by_model']['gemini_pro']}")

        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"   ─────────────────────────────────────")
            logger.info(f"   Başarı oranı       : %{rate:.1f}")

        # Maliyet tahmini (Gemini Image fiyatları)
        cost = (
            self.stats['by_model']['gemini_flash'] * 0.04 +
            self.stats['by_model']['gemini_pro'] * 0.08
        )
        logger.info(f"   Tahmini maliyet    : ${cost:.2f}")

        logger.info(f"{'=' * 60}\n")


# ============== ÇALIŞTIR ==============

if __name__ == "__main__":
    try:
        bot = ScenarioImageBot()
        bot.run()
    except ValueError as ve:
        logger.error(f"Konfigürasyon hatası: {ve}")
        exit(1)
    except Exception as e:
        logger.error(f"Kritik hata: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
