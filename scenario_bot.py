"""
Senaryo Görsel Botu v5.0 - Imagen 4 + Gemini Hybrid Edition
============================================================
Geometri ve 3D çizimler için Imagen 4, düzenleme için Gemini kullanır.

ÖZELLİKLER:
✅ Imagen 4 Standard: Grafik, tablo, karşılaştırma
✅ Imagen 4 Ultra: 3D çizimler, geometri, karmaşık şekiller
✅ Gemini 3 Pro Image: Metin ağırlıklı, düzenleme gerektiren
✅ ÇÖZÜM dahil gösterilir (sayı doğrusu, sonuç aralığı vb.)
✅ Geometri sorularına DESTEK (artık işleniyor!)
✅ Türkçe metin desteği geliştirildi

MODEL SEÇİM KRİTERLERİ:
- Geometrik şekiller (üçgen, daire, prizma) → Imagen Ultra
- 3D objeler, perspektif çizimler → Imagen Ultra  
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
    """Soru tipine göre en uygun modeli seç"""
    
    # Imagen Ultra gerektiren durumlar (3D, geometri)
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


# ============== GÖRSEL PROMPT ŞABLONLARI ==============

# Imagen için prompt (İngilizce daha iyi sonuç veriyor)
IMAGEN_PROMPT_TEMPLATE = """Create a professional educational illustration for a mathematics problem.

## VISUAL TYPE: {tip}

## DETAILED DESCRIPTION:
{detay}

## DATA TO SHOW (RAW DATA ONLY!):
{veriler}

## ⚠️ CRITICAL RULE: NO SOLUTION IN IMAGE!
- Show ONLY the raw data given in the problem
- Do NOT show calculation results or answers
- Do NOT mark solution ranges on number lines
- Do NOT shade answer regions
- Student must solve the problem themselves!

## STYLE RULES:

### COLORS (VIBRANT & PROFESSIONAL):
- Background: White or very light cream (#FFFEF5)
- Shape fills: PASTEL TONES
  * Light blue: #E3F2FD
  * Light green: #E8F5E9  
  * Light orange: #FFF3E0
  * Light purple: #F3E5F5
  * Light pink: #FCE4EC
- Use DIFFERENT colors for different elements
- Lines: Dark gray (#424242), 2-3px thickness
- Text: Black, bold, readable

### 3D & MODERN LOOK:
- Add soft drop shadows
- Use rounded corners
- Add gradient for depth effect
- Professional infographic style

### GEOMETRY SPECIFIC:
- Clear shape outlines
- Labeled vertices (A, B, C...)
- Show GIVEN measurements only
- Right angle markers where needed

### TEXT IN IMAGE:
- Turkish characters: ş, ğ, ü, ö, ç, ı, İ
- Keep labels short
- Mathematical notation clear

### ✅ MUST INCLUDE:
- Given data (formulas, conditions, values from problem)
- Clear Turkish labels
- Professional design

### ❌ MUST NOT INCLUDE:
- Solution or answer
- Calculated results  
- Answer range markings
- Question text
- Multiple choice options"""


# Gemini Image için prompt (Türkçe)
GEMINI_PROMPT_TEMPLATE = """Matematik problemi için eğitim görseli oluştur.

## GÖRSEL TİPİ: {tip}

## DETAYLI BETİMLEME:
{detay}

## GÖRSELDE GÖRÜNECEK VERİLER (SADECE HAM VERİLER!):
{veriler}

## ⚠️ KRİTİK KURAL: ÇÖZÜM GÖSTERİLMEYECEK!
- Sadece problemde VERİLEN bilgiler olacak
- Hesaplama sonucu OLMAYACAK
- Sayı doğrusunda cevap aralığı İŞARETLENMEYECEK
- Öğrenci görsele bakarak cevabı BULAMAMALI!

## STİL KURALLARI:

### 🎨 RENKLER:
- Arka plan: Beyaz veya açık krem (#FFFEF5)
- PASTEL TONLAR kullan
- Her öğe için FARKLI renk

### 3D ve Modern:
- Hafif gölgeler
- Yuvarlak köşeler
- Profesyonel infografik tarzı

### ⚠️ TÜRKÇE YAZIM:
- ş, ğ, ü, ö, ç, ı, İ doğru yazılacak
- Kısa etiketler

### ✅ OLACAKLAR:
- Problemdeki veriler (formül, koşullar, değerler)
- Türkçe etiketler
- Temiz tasarım

### ❌ OLMAYACAKLAR:
- Çözüm veya cevap
- Hesaplama sonuçları
- Cevap aralığı işaretleri
- Soru metni
- A), B), C), D) şıkları"""


# ============== KAZANIM FİLTRESİ (GÜNCELLENDİ) ==============

class LearningOutcomeFilter:
    """Sadece fizik/bilim sorularını dışla - GEOMETRİ ARTIK DAHİL!"""
    
    # Sadece fizik/bilim dışla, geometri artık işlenecek
    EXCLUDED_PATTERNS = [
        # Fizik
        r'sarkaç', r'salınım', r'periyot',
        r'yerçekimi', r'ivme',
        r'kuvvet', r'newton',
        r'elektrik', r'manyetik',
        r'ısı', r'sıcaklık',
        # Kimya
        r'molekül', r'atom', r'element',
    ]
    
    @classmethod
    def should_process(cls, question: Dict) -> Tuple[bool, str]:
        text = ' '.join([
            question.get('original_text', ''),
            question.get('scenario_text', ''),
            question.get('learning_outcome', ''),
            question.get('tags', '')
        ]).lower()
        
        for pattern in cls.EXCLUDED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"Fizik/Bilim içerik: {pattern}"
        
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
        """Soruyu analiz et ve görsel bilgilerini çıkar"""
        
        full_text = question_text
        if scenario_text:
            full_text = f"SENARYO:\n{scenario_text}\n\nSORU:\n{question_text}"
        
        prompt = f"""Sen bir matematik eğitimi görsel tasarım uzmanısın.

Verilen soruyu analiz et ve bu soru için GÖRSEL GEREKLİ Mİ karar ver.

⚠️ KRİTİK KURALLAR:

1. GÖRSEL GEREKLİ DURUMLAR:
   - Karşılaştırma içeren problemler (firmalar, tarifeler, planlar)
   - Tablo/liste içeren veriler (fiyatlar, miktarlar)
   - İstatistik soruları (ortalama, yüzde, dağılım)
   - Senaryo bazlı problemler (market, okul, fabrika)
   - Oran/yüzde karşılaştırmaları
   - GEOMETRİ SORULARI (üçgen, daire, prizma vb.)
   - 3D objeler ve teknik çizimler
   - Sayı doğrusu gerektiren sorular
   - Koordinat sistemi soruları

2. GÖRSEL GEREKSİZ DURUMLAR:
   - Basit dört işlem (sadece hesaplama)
   - Sadece metin cevaplı sorular
   - Formül ezberi soruları

3. ⚠️ ÇÖZÜM DAHİL ETME - KESİNLİKLE YASAK!
   - Sayı doğrusunda çözüm aralığı GÖSTERME
   - Hesaplama sonucu, toplam, fark GÖSTERME
   - Cevabı ima eden hiçbir bilgi KOYMA
   - Sadece problemdeki HAM VERİLER olacak
   - Öğrenci görsele bakarak cevabı bulamamalı!

4. KARMAŞIKLIK DEĞERLENDİRMESİ:
   - "simple": Basit tablo, tek grafik
   - "standard": Sayı doğrusu, karşılaştırma, 2D şekil
   - "complex": 3D, perspektif, geometrik şekiller, mimari

SORU:
{full_text}

SADECE JSON FORMATINDA CEVAP VER:
{{
    "visual_needed": true/false,
    "visual_type": "comparison/table/chart/info/scene/geometry/number_line/coordinate",
    "complexity": "simple/standard/complex",
    "quality_score": 1-10,
    "title": "Kısa başlık",
    "gorsel_betimleme": {{
        "tip": "görsel tipi",
        "detay": "detaylı betimleme - ne çizilecek (SADECE VERİLER, ÇÖZÜM YOK!)",
        "veriler": "görselde olacak SADECE ham veriler - hesaplama sonucu YOK"
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
        """Model seçimine göre görsel üret"""
        
        tip = gorsel_info.get('tip', 'diagram')
        detay = gorsel_info.get('detay', '')
        veriler = gorsel_info.get('veriler', '')
        
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
                            safety_filter_level="BLOCK_ONLY_HIGH",
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
║         🎨 SENARYO GÖRSEL BOTU v5.0 - HYBRID                         ║
║         Imagen 4 + Gemini 3 Pro Image                                ║
╚══════════════════════════════════════════════════════════════════════╝
        """)
        logger.info(f"📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("✅ Imagen Standard: Grafikler, tablolar, sayı doğrusu")
        logger.info("✅ Imagen Ultra: 3D, geometri, mimari çizimler")
        logger.info("✅ Gemini Image: Metin ağırlıklı kartlar")
        logger.info("✅ ÇÖZÜM dahil gösterilecek")
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
