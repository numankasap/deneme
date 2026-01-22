"""
Senaryo Görsel Botu v5.1 - PRO 3D Edition
==========================================
Profesyonel 3D görseller üreten gelişmiş görsel bot.

YENİLİKLER v5.1:
✅ AKILLI FİLTRELEME: Matematik soruları artık yanlışlıkla filtrelenmiyor
✅ PRO 3D GÖRSELLER: İzometrik, perspektif, stüdyo aydınlatmalı
✅ ZENGİN RENK PALETİ: Canlı gradyanlar, gölgeler, yansımalar
✅ ÇÖZÜM YOK: Görselde kesinlikle cevap veya ipucu gösterilmiyor
✅ DETAYLI BETİMLEME: Perspektif, renkler, malzemeler tanımlanıyor

ÖZELLİKLER:
✅ Imagen 4 Standard: Grafik, tablo, karşılaştırma
✅ Imagen 4 Ultra: 3D çizimler, geometri, karmaşık şekiller, sahneler
✅ Gemini 3 Pro Image: Metin ağırlıklı, düzenleme gerektiren
✅ Geometri sorularına tam DESTEK
✅ Senaryo/günlük hayat problemleri 3D sahneler
✅ Türkçe metin desteği (ş, ğ, ü, ö, ç, ı, İ)

MODEL SEÇİM KRİTERLERİ:
- Geometrik şekiller (üçgen, daire, prizma) → Imagen Ultra
- 3D objeler, perspektif çizimler → Imagen Ultra
- Senaryo sahneleri (market, fabrika, havuz) → Imagen Ultra
- Standart grafikler, tablolar → Imagen Standard
- Sayı doğrusu, koordinat sistemi → Imagen Standard
- Metin ağırlıklı kartlar → Gemini 3 Pro Image

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
    """Görsel üretim modelleri"""
    IMAGEN_FAST = "imagen-4.0-fast-generate-001"      # $0.02 - Hızlı prototip
    IMAGEN_STANDARD = "imagen-4.0-generate-001"       # $0.04 - Standart kalite
    IMAGEN_ULTRA = "imagen-4.0-ultra-generate-001"    # $0.06 - En yüksek kalite
    GEMINI_IMAGE = "gemini-3-pro-image-preview"       # $0.134 - Metin/düzenleme


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
    """Soru tipine göre en uygun modeli seç - v5.1 PRO 3D"""

    # Imagen Ultra gerektiren durumlar (3D, geometri, sahneler)
    ULTRA_PATTERNS = [
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
        # Senaryo sahneleri (3D diorama için)
        r'market', r'mağaza', r'fabrika', r'atölye', r'depo',
        r'araba', r'araç', r'tren', r'otobüs',
        r'tarla', r'arazi', r'alan\s+m²',
        r'tank', r'hazne', r'kap', r'kutu',
        r'yol', r'park', r'cadde', r'sokak',
    ]
    
    # Gemini Image gerektiren durumlar (metin ağırlıklı)
    GEMINI_PATTERNS = [
        r'kart.*bilgi', r'bilgi.*kart',
        r'menü', r'liste.*detay',
        r'açıklama.*kutu', r'not.*ekle',
    ]
    
    # Standart grafikler (Imagen Standard yeterli)
    STANDARD_PATTERNS = [
        r'grafik', r'tablo', r'çubuk', r'pasta', r'histogram',
        r'sayı doğrusu', r'koordinat', r'eksen',
        r'karşılaştır', r'fiyat', r'tarife',
        r'oran', r'yüzde', r'istatistik',
    ]
    
    @classmethod
    def select_model(cls, question_text: str, analysis: Dict) -> Tuple[ImageModel, str]:
        """
        Soru ve analize göre model seç
        Returns: (model, reason)
        """
        text = question_text.lower()
        visual_type = analysis.get('visual_type', '').lower()
        complexity = analysis.get('complexity', 'standard')
        
        # 1. Ultra kontrol (3D, geometri)
        for pattern in cls.ULTRA_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return ImageModel.IMAGEN_ULTRA, f"3D/Geometri tespit: {pattern}"
        
        # 2. Analiz complexity'ye göre
        if complexity == 'complex' or visual_type in ['geometry', '3d', 'technical']:
            return ImageModel.IMAGEN_ULTRA, f"Karmaşık görsel: {visual_type}"
        
        # 3. Gemini kontrol (metin ağırlıklı)
        for pattern in cls.GEMINI_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return ImageModel.GEMINI_IMAGE, f"Metin ağırlıklı: {pattern}"
        
        # 4. Varsayılan: Imagen Standard
        return ImageModel.IMAGEN_STANDARD, "Standart görsel"


# ============== GÖRSEL PROMPT ŞABLONLARI (v5.1 - PRO 3D) ==============

# Imagen için prompt (İngilizce daha iyi sonuç veriyor)
IMAGEN_PROMPT_TEMPLATE = """Create a STUNNING professional 3D educational illustration for a mathematics problem.

## VISUAL TYPE: {tip}

## DETAILED DESCRIPTION:
{detay}

## DATA TO SHOW (RAW DATA ONLY!):
{veriler}

## ⚠️⚠️⚠️ ABSOLUTE CRITICAL RULE: ZERO SOLUTION IN IMAGE! ⚠️⚠️⚠️
- Show ONLY the raw data given in the problem
- NEVER show calculation results, totals, sums, or answers
- NEVER mark solution ranges on number lines
- NEVER shade answer regions or highlight correct options
- NEVER show arrows pointing to answers
- NEVER include result values (like "= 42" or "Total: 150")
- The student MUST be able to solve the problem by looking at the visual
- The visual is ONLY for understanding the problem, NOT for revealing the answer!

## 🎨 3D PROFESSIONAL STYLE RULES:

### RENDERING STYLE:
- Modern 3D isometric or perspective view
- Soft ambient occlusion shadows
- Subtle reflections on surfaces
- Depth of field effect (background slightly blurred)
- Studio lighting: main light from top-left, fill light from right
- Anti-aliased smooth edges

### COLOR PALETTE (VIBRANT & RICH):
- Background: Soft gradient from #F8FAFC to #E2E8F0
- PRIMARY COLORS (for main elements):
  * Vibrant Blue: #3B82F6 with #1D4ED8 shadow
  * Bright Green: #22C55E with #15803D shadow
  * Warm Orange: #F97316 with #C2410C shadow
  * Rich Purple: #8B5CF6 with #6D28D9 shadow
  * Coral Pink: #F472B6 with #DB2777 shadow
- ACCENT COLORS:
  * Gold highlights: #FCD34D
  * Silver accents: #94A3B8
- Each element MUST have a DIFFERENT color
- Use color gradients for 3D depth effect

### 3D EFFECTS:
- Extrusion depth: 20-40px for 3D objects
- Bevel edges for polish
- Soft drop shadows (offset: 8px, blur: 16px, opacity: 20%)
- Inner shadows for depth
- Glass/glossy effect for important elements
- Metallic finish for labels/badges

### MATERIALS & TEXTURES:
- Matte finish for backgrounds
- Semi-glossy for shapes and objects
- Subtle texture for surfaces (paper grain, fabric weave)
- Frosted glass effect for overlays

### GEOMETRY SPECIFIC:
- 3D extruded shapes with proper perspective
- Clear vertex labels (A, B, C) in metallic badges
- Measurements shown as floating 3D labels
- Right angle markers as small 3D cubes
- Dashed lines for hidden edges
- Gradient fills showing 3D form

### TABLES & CHARTS:
- 3D bar charts with rounded tops
- Floating table cells with shadows
- Glossy headers with gradient
- Alternating row colors for readability
- 3D pie chart slices with depth

### NUMBER LINE & COORDINATE:
- 3D extruded axis lines
- Spherical point markers
- Floating number labels
- Grid lines with subtle transparency

### SCENE & SCENARIO:
- Isometric 3D scene view
- Miniature diorama style
- Cartoon-realistic objects
- Consistent lighting across scene
- Depth layering (foreground/background)

### TYPOGRAPHY:
- Bold sans-serif font (like Montserrat or Inter)
- Turkish characters: ş, ğ, ü, ö, ç, ı, İ
- Text with subtle shadow for readability
- Number labels in rounded badges
- Mathematical symbols in clean notation

### COMPOSITION:
- Rule of thirds layout
- Clear visual hierarchy
- Adequate white space
- Balanced element distribution
- Focus point in center

### ✅ MUST INCLUDE:
- Given data beautifully visualized in 3D
- Clear Turkish labels with proper characters
- Professional magazine-quality design
- Rich colors and depth effects
- All measurements and values from problem

### ❌ ABSOLUTELY MUST NOT INCLUDE:
- ANY solution, answer, or result
- Calculated values or totals
- Highlighted answer regions
- Solution indicators or arrows
- Question text verbatim
- Multiple choice options (A, B, C, D)
- Any hint about the correct answer"""


# Gemini Image için prompt (Türkçe - v5.1 PRO 3D)
GEMINI_PROMPT_TEMPLATE = """Matematik problemi için MUHTEŞEM profesyonel 3D eğitim görseli oluştur.

## GÖRSEL TİPİ: {tip}

## DETAYLI BETİMLEME:
{detay}

## GÖRSELDE GÖRÜNECEK VERİLER (SADECE HAM VERİLER!):
{veriler}

## ⚠️⚠️⚠️ MUTLAK KRİTİK KURAL: SIFIR ÇÖZÜM! ⚠️⚠️⚠️
- Sadece problemde VERİLEN bilgiler olacak
- Hesaplama sonucu KESİNLİKLE OLMAYACAK
- Toplam, fark, sonuç değerleri GÖSTERİLMEYECEK
- Sayı doğrusunda cevap aralığı İŞARETLENMEYECEK
- Cevaba işaret eden ok veya vurgulama OLMAYACAK
- Öğrenci görsele bakarak cevabı BULAMAMALI!
- Görsel SADECE problemi anlamak için, cevabı vermek için DEĞİL!

## 🎨 3D PROFESYONEL STİL KURALLARI:

### RENDER STİLİ:
- Modern 3D izometrik veya perspektif görünüm
- Yumuşak ortam gölgeleri
- Yüzeylerde ince yansımalar
- Stüdyo aydınlatması: sol üstten ana ışık
- Pürüzsüz kenarlar

### RENK PALETİ (CANLI & ZENGİN):
- Arka plan: Yumuşak gradyan #F8FAFC → #E2E8F0
- ANA RENKLER:
  * Canlı Mavi: #3B82F6 (gölge: #1D4ED8)
  * Parlak Yeşil: #22C55E (gölge: #15803D)
  * Sıcak Turuncu: #F97316 (gölge: #C2410C)
  * Zengin Mor: #8B5CF6 (gölge: #6D28D9)
  * Mercan Pembe: #F472B6 (gölge: #DB2777)
- VURGU RENKLER:
  * Altın: #FCD34D
  * Gümüş: #94A3B8
- Her eleman FARKLI renkte olacak
- 3D derinlik için renk gradyanları

### 3D EFEKTLER:
- Objeler için 20-40px derinlik
- Kenar yuvarlatma (bevel)
- Yumuşak gölgeler (8px offset, 16px blur)
- İç gölgeler
- Önemli elemanlar için cam/parlak efekt
- Etiketler için metalik görünüm

### GEOMETRİ İÇİN:
- 3D çıkıntılı şekiller
- Köşe etiketleri (A, B, C) metalik rozetlerde
- Ölçümler yüzer 3D etiketlerde
- Dik açı işaretleri küçük 3D küpler
- Gizli kenarlar için kesikli çizgi
- 3D form gösteren gradyan dolgular

### TABLO & GRAFİK:
- 3D çubuk grafikler (yuvarlatılmış üst)
- Gölgeli yüzer tablo hücreleri
- Gradyanlı parlak başlıklar
- Okunabilirlik için alternatif satır renkleri

### SAYI DOĞRUSU & KOORDİNAT:
- 3D çıkıntılı eksen çizgileri
- Küresel nokta işaretçileri
- Yüzer sayı etiketleri
- Saydam ızgara çizgileri

### SENARYO & SAHNE:
- İzometrik 3D sahne görünümü
- Minyatür diorama stili
- Karikatür-gerçekçi objeler
- Tutarlı aydınlatma
- Derinlik katmanları

### TİPOGRAFİ:
- Kalın sans-serif font
- Türkçe karakterler: ş, ğ, ü, ö, ç, ı, İ DOĞRU yazılacak
- Okunabilirlik için metin gölgesi
- Yuvarlatılmış rozetlerde sayılar

### ✅ OLACAKLAR:
- Problemdeki veriler 3D olarak güzelce görselleştirilmiş
- Türkçe etiketler doğru karakterlerle
- Dergi kalitesinde profesyonel tasarım
- Zengin renkler ve derinlik efektleri
- Problemdeki tüm ölçümler ve değerler

### ❌ KESİNLİKLE OLMAYACAKLAR:
- HİÇBİR çözüm, cevap veya sonuç
- Hesaplanmış değerler veya toplamlar
- Vurgulanmış cevap bölgeleri
- Çözüm göstergeleri veya oklar
- Aynen soru metni
- Çoktan seçmeli şıklar (A, B, C, D)
- Doğru cevap hakkında HİÇBİR ipucu"""


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
        """Soruyu analiz et ve görsel bilgilerini çıkar - v5.1 PRO 3D"""

        full_text = question_text
        if scenario_text:
            full_text = f"SENARYO:\n{scenario_text}\n\nSORU:\n{question_text}"

        prompt = f"""Sen bir matematik eğitimi için PROFESYONEL 3D GÖRSEL TASARIM uzmanısın.

Verilen soruyu analiz et ve bu soru için ETKİLEYİCİ 3D GÖRSEL tasarla.

⚠️ KRİTİK KURALLAR:

1. GÖRSEL GEREKLİ DURUMLAR (geniş kapsamlı düşün):
   - Karşılaştırma içeren problemler (firmalar, tarifeler, planlar)
   - Tablo/liste içeren veriler (fiyatlar, miktarlar)
   - İstatistik soruları (ortalama, yüzde, dağılım)
   - Senaryo bazlı problemler (market, okul, fabrika, bahçe, havuz)
   - Oran/yüzde karşılaştırmaları
   - GEOMETRİ SORULARI (üçgen, daire, prizma vb.)
   - 3D objeler ve teknik çizimler
   - Sayı doğrusu gerektiren sorular
   - Koordinat sistemi soruları
   - GÜNLÜK HAYAT PROBLEMLERİ (ısı, hız, mesafe içeren matematik)
   - Para/bütçe problemleri
   - Yaş problemleri (aile şeması olabilir)

2. GÖRSEL GEREKSİZ DURUMLAR (çok sınırlı):
   - SADECE basit dört işlem (örn: 5+3=?)
   - Tek satırlık formül ezberi
   - Görselleştirilecek HIÇBIR veri olmayan sorular

3. ⚠️⚠️⚠️ ÇÖZÜM DAHİL ETME - KESİNLİKLE YASAK! ⚠️⚠️⚠️
   - Sayı doğrusunda çözüm aralığı GÖSTERME
   - Hesaplama sonucu, toplam, fark, çarpım GÖSTERME
   - Cevabı ima eden HİÇBİR bilgi KOYMA
   - "= ?" veya "= X" gibi sonuç ifadeleri KOYMA
   - Sadece problemdeki HAM VERİLER olacak
   - Öğrenci görsele bakarak cevabı KESİNLİKLE bulamamalı!

4. KARMAŞIKLIK DEĞERLENDİRMESİ:
   - "simple": Basit tablo, tek grafik
   - "standard": Sayı doğrusu, karşılaştırma, 2D şekil
   - "complex": 3D, perspektif, geometrik şekiller, mimari, sahneler

5. 🎨 3D BETİMLEME İÇİN:
   Detaylı betimleme yazarken şunları belirt:
   - 3D perspektif açısı (izometrik, kuş bakışı, ön görünüş)
   - Objelerin konumları ve boyutları
   - Renkler ve malzemeler
   - Işık kaynağı yönü
   - Arka plan detayları
   - Etiketlerin yerleri

SORU:
{full_text}

SADECE JSON FORMATINDA CEVAP VER:
{{
    "visual_needed": true/false,
    "visual_type": "comparison/table/chart/info/scene/geometry/number_line/coordinate/scenario_3d",
    "complexity": "simple/standard/complex",
    "quality_score": 1-10,
    "title": "Kısa başlık",
    "gorsel_betimleme": {{
        "tip": "görsel tipi (3D scene / isometric diagram / comparison chart / geometry / number line / table / infographic)",
        "detay": "ÇOK DETAYLI 3D betimleme - perspektif, objeler, renkler, ışık, arka plan, etiket yerleri (SADECE VERİLER, ÇÖZÜM YOK!)",
        "veriler": "görselde olacak SADECE ham veriler listesi - hesaplama sonucu KESİNLİKLE YOK",
        "renkler": "her öğe için önerilen renkler (mavi: X, yeşil: Y gibi)",
        "perspektif": "izometrik / kuş bakışı / ön görünüş / 45 derece açı"
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
        """Model seçimine göre PRO 3D görsel üret"""

        tip = gorsel_info.get('tip', 'diagram')
        detay = gorsel_info.get('detay', '')
        veriler = gorsel_info.get('veriler', '')
        renkler = gorsel_info.get('renkler', '')
        perspektif = gorsel_info.get('perspektif', 'isometric')

        # Detayı zenginleştir
        if renkler:
            detay = f"{detay}\n\nÖNERİLEN RENKLER: {renkler}"
        if perspektif:
            detay = f"{detay}\n\nPERSPEKTİF: {perspektif}"
        
        # Model'e göre prompt seç
        if model == ImageModel.GEMINI_IMAGE:
            prompt = GEMINI_PROMPT_TEMPLATE.format(
                tip=tip,
                detay=detay,
                veriler=veriler
            )
        else:
            # Imagen için İngilizce prompt
            prompt = IMAGEN_PROMPT_TEMPLATE.format(
                tip=tip,
                detay=detay,
                veriler=veriler
            )
        
        logger.info(f"  🎨 Model: {model.value}")
        logger.info(f"  📐 Tip: {tip}")
        
        self._rate_limit()
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                if model == ImageModel.GEMINI_IMAGE:
                    # Gemini Image API
                    response = self.client.models.generate_content(
                        model=model.value,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE", "TEXT"],
                        )
                    )
                else:
                    # Imagen API
                    response = self.client.models.generate_images(
                        model=model.value,
                        prompt=prompt,
                        config=types.GenerateImagesConfig(
                            number_of_images=1,
                            aspect_ratio="16:9",  # Geniş format
                            safety_filter_level="BLOCK_LOW_AND_ABOVE",
                        )
                    )
                
                # Response'dan görsel çıkar
                image_bytes = self._extract_image(response, model)
                
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
    
    def _extract_image(self, response, model: ImageModel) -> Optional[bytes]:
        """Response'dan görsel byte'larını çıkar"""
        
        try:
            if model == ImageModel.GEMINI_IMAGE:
                # Gemini response yapısı
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
            else:
                # Imagen response yapısı
                if hasattr(response, 'generated_images') and response.generated_images:
                    img = response.generated_images[0]
                    if hasattr(img, 'image') and hasattr(img.image, 'image_bytes'):
                        return img.image.image_bytes
                    elif hasattr(img, 'image_bytes'):
                        return img.image_bytes
                        
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
    """Senaryo soruları için görsel üreten bot - Hybrid Model"""
    
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
                'imagen_standard': 0,
                'imagen_ultra': 0,
                'gemini_image': 0
            }
        }
    
    def run(self):
        """Botu çalıştır"""
        logger.info("""
╔══════════════════════════════════════════════════════════════════════╗
║         🎨 SENARYO GÖRSEL BOTU v5.1 - PRO 3D Edition                 ║
║         Imagen 4 + Gemini 3 Pro Image                                ║
╚══════════════════════════════════════════════════════════════════════╝
        """)
        logger.info(f"📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("✅ Imagen Standard: Grafikler, tablolar, sayı doğrusu")
        logger.info("✅ Imagen Ultra: 3D, geometri, sahneler, mimari")
        logger.info("✅ Gemini Image: Metin ağırlıklı kartlar")
        logger.info("✅ Akıllı filtreleme: Matematik soruları korunuyor")
        logger.info("⚠️ ÇÖZÜM GÖSTERİLMEYECEK - Sadece veriler!")
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
            if selected_model == ImageModel.IMAGEN_STANDARD:
                self.stats['by_model']['imagen_standard'] += 1
            elif selected_model == ImageModel.IMAGEN_ULTRA:
                self.stats['by_model']['imagen_ultra'] += 1
            else:
                self.stats['by_model']['gemini_image'] += 1
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
        logger.info(f"     Imagen Standard  : {self.stats['by_model']['imagen_standard']}")
        logger.info(f"     Imagen Ultra     : {self.stats['by_model']['imagen_ultra']}")
        logger.info(f"     Gemini Image     : {self.stats['by_model']['gemini_image']}")
        
        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"   ─────────────────────────────────────")
            logger.info(f"   Başarı oranı       : %{rate:.1f}")
        
        # Maliyet tahmini
        cost = (
            self.stats['by_model']['imagen_standard'] * 0.04 +
            self.stats['by_model']['imagen_ultra'] * 0.06 +
            self.stats['by_model']['gemini_image'] * 0.134
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
