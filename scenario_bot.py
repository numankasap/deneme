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


# ============== MODEL TİPLERİ ==============

class ImageModel(Enum):
    """Görsel üretim modelleri - Sadece Gemini Image"""
    GEMINI_FLASH_IMAGE = "gemini-2.5-flash-image"   # Hızlı, standart
    GEMINI_PRO_IMAGE = "gemini-3-pro-image-preview"          # Yüksek kalite, karmaşık


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
    ANALYSIS_MODEL = 'gemini-3-flash-preview'
    
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

    # Pro model gerektiren durumlar (karmaşık 3D sahneler)
    PRO_PATTERNS = [
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
        if complexity == 'complex' or visual_type in ['geometry', '3d', 'scene', 'scenario_3d']:
            return ImageModel.GEMINI_PRO_IMAGE, f"Karmaşık görsel: {visual_type}"

        # 3. Varsayılan: Flash model (hızlı ve yeterli)
        return ImageModel.GEMINI_FLASH_IMAGE, "Standart görsel"


# ============== GÖRSEL PROMPT ŞABLONU (v6.0 - GERÇEKÇİ 3D) ==============

# Tek prompt şablonu - Gemini Image için optimize edilmiş
REALISTIC_3D_PROMPT = """Bir matematik problemi için FOTOGERÇEKÇİ 3D GÜNLÜK YAŞAM SAHNESİ oluştur.

## 🎯 GÖRSEL AMACI: SORUYU ANLAMAYA YARDIMCI OLMAK
Bu görsel sadece süs değil! Öğrencinin problemi ANLAMASINA yardımcı olmalı.
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
            question.get('original_text', ''),
            question.get('scenario_text', ''),
            question.get('learning_outcome', ''),
            question.get('tags', '')
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

🎯 GÖRSEL AMACI:
Görsel sadece süs DEĞİL! Öğrencinin problemi ANLAMASINA yardımcı olmalı.
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

2. GÖRSEL GEREKSİZ DURUMLAR (çok sınırlı):
   - SADECE basit dört işlem (5+3=?)
   - Tek satırlık formül
   - Görselleştirilecek HIÇBIR veri yok

3. ⚠️⚠️⚠️ ÇÖZÜM GÖSTERİLMEYECEK! ⚠️⚠️⚠️
   - Hesaplama sonucu YOK
   - Toplam, fark, sonuç YOK
   - Cevap ipucu YOK
   - Sadece HAM VERİLER

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

6. 🔢 BİRE BİR DOĞRU SAYILAR (ÇOK KRİTİK!):
   - Soruda "6 koli" diyorsa → detayda "TAM 6 ADET koli" yaz
   - Soruda "4 kutu" diyorsa → detayda "TAM 4 ADET kutu" yaz
   - Sayıları AÇIKÇA belirt, tahmine bırakma
   - YANLIŞ SAYIDA obje çizmek YASAK!

SORU:
{full_text}

SADECE JSON FORMATINDA CEVAP VER:
{{
    "visual_needed": true/false,
    "visual_type": "market_scene/factory_scene/garden_scene/classroom_scene/family_scene/geometry_real/chart_display/comparison_scene",
    "complexity": "simple/standard/complex",
    "quality_score": 1-10,
    "title": "Kısa başlık",
    "gorsel_betimleme": {{
        "tip": "Gerçekçi 3D sahne tipi (market sahnesi / fabrika sahnesi / bahçe / sınıf / aile / geometri objeleri / grafik ekranı)",
        "detay": "ÇOK DETAYLI gerçekçi sahne betimleme. ÖNEMLİ: Her objenin KESİN SAYISINI belirt! Örnek: 'TAM 6 ADET mavi koli (4-A için)' ve 'TAM 4 ADET turuncu koli (4-B için)' gibi. SAYI DOĞRU OLMALI!",
        "veriler": "BİRE BİR SAYILAR! Her objenin TAM ADEDİ yazılmalı. Örnek: '6 adet mavi koli (35 kitap etiketi), 4 adet turuncu koli (42 kitap etiketi)' - hesaplama sonucu YOK",
        "renkler": "Her grup için FARKLI renk (kolay ayırt etmek için)",
        "perspektif": "Göz seviyesi / kuş bakışı / 45 derece açı"
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
        """Görsel bekleyen soruları getir"""
        try:
            response = self.client.table('question_bank') \
                .select('*') \
                .is_('image_url', 'null') \
                .eq('is_active', True) \
                .not_.is_('scenario_text', 'null') \
                .limit(limit) \
                .execute()
            
            questions = response.data or []
            logger.info(f"📋 {len(questions)} soru bulundu")
            return questions
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
