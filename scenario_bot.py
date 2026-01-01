"""
Senaryo Görsel Botu v4.0 - Gemini Image Preview Edition
========================================================
Gemini 2.0 Flash Preview Image Generation modeli ile renkli, 3D görseller üretir.

ÖZELLİKLER:
✅ Gemini Image Preview ile görsel üretimi
✅ Sadece gerekli sorular için görsel üretir
✅ Geometri kazanımlarına DOKUNMAZ
✅ Sadece sorudaki VERİLERİ içerir (çözüm YOK!)
✅ Kalite kontrolü ile gereksiz üretim engellenir

HEDEF SORULAR:
- Problem soruları (senaryo bazlı)
- Tablo gerektiren sorular
- Grafik gerektiren sorular (istatistik, fonksiyon)
- Karşılaştırma soruları (tarifeler, planlar, fiyatlar)

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


# ============== YAPILANDIRMA ==============

class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Modeller
    ANALYSIS_MODEL = 'gemini-2.5-flash'
    IMAGE_MODEL = 'gemini-3-pro-image-preview'
    
    STORAGE_BUCKET = 'questions-images'
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '20'))
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 3
    
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    RATE_LIMIT_DELAY = 3
    MIN_PNG_SIZE = 5000
    MIN_QUALITY_SCORE = 7


# ============== GÖRSEL PROMPT ŞABLONU ==============

IMAGE_PROMPT_TEMPLATE = """Matematik problemi için eğitim görseli oluştur.

## GÖRSEL TİPİ: {tip}

## DETAYLI BETİMLEME:
{detay}

## GÖRSELDE GÖRÜNECEK VERİLER (SADECE BUNLAR!):
{veriler}

## KRİTİK KURALLAR:

### 🎯 İÇERİK KURALLARI (ÇOK ÖNEMLİ!):
- Görselde SADECE yukarıdaki "veriler" kısmındaki bilgiler olmalı
- ASLA hesaplama sonucu, toplam, fark, oran gösterme
- ASLA cevabı veya çözümü ima eden bilgi koyma
- Sadece ham veriler: fiyatlar, miktarlar, isimler, kategoriler

### 🎨 STİL KURALLARI:
**Renkler (CANLI VE PROFESYONEL):**
- Arka plan: Beyaz veya çok açık krem (#FFFEF5)
- Şekil dolguları için PASTEL TONLAR:
  * Açık mavi: #E3F2FD
  * Açık yeşil: #E8F5E9
  * Açık turuncu: #FFF3E0
  * Açık mor: #F3E5F5
  * Açık pembe: #FCE4EC
- Her farklı öğe için FARKLI renk kullan
- Çizgiler: Koyu gri (#424242), 2-3px kalınlık
- Yazılar: Siyah, kalın, okunaklı

**3D ve Modern Görünüm:**
- Hafif gölgeler ekle (drop shadow)
- Yuvarlak köşeler kullan
- Derinlik hissi için gradyan kullan
- Profesyonel infografik tarzı

**Boyutlandırma:**
- Görsel alanının %70-80'ini kapla
- Etiketler için yeterli boşluk bırak
- Dengeli kompozisyon

### 📊 GÖRSEL TİPLERİNE GÖRE TASARIM:

**KARŞILAŞTIRMA (comparison):**
- 2-4 renkli kart yan yana
- Her kartta: Başlık + veriler (fiyat, özellik vb.)
- Kartlar farklı renklerde
- "VS" veya karşılaştırma simgesi ortada
- Modern, temiz tasarım

**TABLO (table):**
- Başlık satırı renkli (açık mavi)
- Satırlar alternatif renk (beyaz/açık gri)
- Her hücrede net yazı
- Çerçeveli, profesyonel

**GRAFİK (chart):**
- Çubuk/pasta/çizgi grafik
- Her veri farklı pastel renk
- Eksen etiketleri net
- Lejant (açıklama) ekle

**BİLGİ KARTLARI (info):**
- Renkli kartlar grid düzeninde
- Her kartta: icon + etiket + değer
- Gölgeli, 3D efekt
- Modern flat design

**SENARYO (scene):**
- Basit, temiz illüstrasyon
- Konuyla ilgili objeler (market, okul vb.)
- Fiyat etiketleri görünür
- Karikatür/infografik tarzı

### ⚠️ TÜRKÇE YAZIM:
- "ı" harfini DOĞRU yaz (noktalı "i" DEĞİL)
- "ğ", "ş", "ü", "ö", "ç" harflerini DOĞRU yaz
- Kelimeleri TAM yaz, yarıda KESME
- Kısa etiketler kullan (sayılar, birimler)

### ❌ MUTLAK YASAKLAR:
❌ Soru metni veya uzun cümleler
❌ Hesaplama sonuçları (toplam, fark, oran)
❌ A), B), C), D) şıkları
❌ Çözüm adımları
❌ Cevabı veren bilgi
❌ Sıkıcı gri tonlar
❌ Tek renk kullanımı
❌ Bulanık veya karmaşık tasarım"""


# ============== KAZANIM FİLTRESİ ==============

class LearningOutcomeFilter:
    """Geometri ve Fizik sorularını dışla"""
    
    EXCLUDED_PATTERNS = [
        # Geometri
        r'M\.[5-8]\.3\.',
        r'geometri', r'üçgen', r'dörtgen', r'çokgen',
        r'açı(?!k)',
        r'kenar', r'köşegen',
        r'çember', r'daire',
        r'prizma', r'piramit', r'silindir', r'koni', r'küre',
        r'\balan\b', r'çevre',
        r'pythagoras', r'pisagor',
        r'benzerlik', r'eşlik',
        r'öteleme', r'yansıma', r'dönüşüm',
        # Fizik
        r'sarkaç', r'salınım', r'periyot',
        r'yerçekimi', r'ivme',
        r'kuvvet', r'newton',
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
                return False, f"Dışlanan içerik: {pattern}"
        
        return True, "OK"


# ============== GEMİNİ API ==============

class GeminiAPI:
    """Gemini API - Analiz ve Görsel Üretimi"""
    
    def __init__(self):
        if not NEW_GENAI:
            raise ValueError("google-genai paketi gerekli!")
        
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self._last_request = 0
        logger.info("✅ Gemini API başlatıldı")
    
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

2. GÖRSEL GEREKSİZ DURUMLAR:
   - Basit dört işlem
   - Tek adımlı hesaplamalar
   - Soyut cebirsel işlemler
   - Geometri soruları (bunları ATLA!)

3. VERİLER - SADECE HAM VERİLER:
   ✅ Fiyatlar (100 TL, 50 TL)
   ✅ Miktarlar (3 adet, 5 kg)
   ✅ İsimler (A Firması, B Planı)
   ✅ Kategoriler (Koşu, Yüzme, Yoga)
   
   ❌ ASLA hesaplama sonucu (toplam, fark, oran)
   ❌ ASLA "X × Y = Z" gibi işlemler
   ❌ ASLA ortalama, yüzde hesabı sonucu

JSON ÇIKTI:
{{
  "visual_needed": true/false,
  "quality_score": 8,
  "reason": "Neden görsel gerekli/gereksiz",
  
  "visual_type": "comparison|table|chart|info|scene",
  "title": "Görsel başlığı (Türkçe, kısa)",
  
  "gorsel_betimleme": {{
    "tip": "Görsel tipi",
    "detay": "Detaylı açıklama - ne çizilecek",
    "gorunen_veriler": "Görselde görünecek ham veriler listesi"
  }},
  
  "data_items": [
    {{"label": "A Firması", "values": ["Aylık: 50 TL", "Dakika: 0.5 TL"]}},
    {{"label": "B Firması", "values": ["Aylık: 30 TL", "Dakika: 1 TL"]}}
  ]
}}

SORU:
{full_text}"""
        
        self._rate_limit()
        
        try:
            response = self.client.models.generate_content(
                model=Config.ANALYSIS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json"
                )
            )
            
            result = json.loads(response.text)
            
            if not result.get('visual_needed', False):
                logger.info(f"ℹ️ Görsel gerekmez: {result.get('reason', 'N/A')}")
                return None
            
            quality = result.get('quality_score', 0)
            if quality < Config.MIN_QUALITY_SCORE:
                logger.info(f"ℹ️ Kalite düşük ({quality}/10)")
                return None
            
            if not result.get('gorsel_betimleme'):
                logger.warning("⚠️ Görsel betimleme boş!")
                return None
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {e}")
            return None
        except Exception as e:
            logger.error(f"Analiz hatası: {e}")
            return None
    
    def generate_image(self, gorsel_betimleme: Dict, title: str = "") -> Optional[bytes]:
        """Gemini Image Preview ile görsel üret"""
        
        tip = gorsel_betimleme.get("tip", "info")
        detay = gorsel_betimleme.get("detay", "")
        veriler = gorsel_betimleme.get("gorunen_veriler", "")
        
        # Renk talimatı ekle
        renk_talimat = """

🎨 RENK TALİMATI (ÇOK ÖNEMLİ!):
- GRİ TONLARI KULLANMA! Sıkıcı görünüyor.
- Her farklı öğe için FARKLI PASTEL renk kullan
- Örnek renkler: Açık mavi #E3F2FD, Açık yeşil #E8F5E9, Açık turuncu #FFF3E0, Açık mor #F3E5F5
- Çizgiler koyu renk olsun (koyu mavi #1565C0, koyu yeşil #2E7D32)
- 3D efekt ve gölge ekle
- Modern, profesyonel infografik tarzı"""
        
        full_detay = f"{detay}{renk_talimat}"
        prompt = IMAGE_PROMPT_TEMPLATE.format(tip=tip, detay=full_detay, veriler=veriler)
        
        self._rate_limit()
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                logger.info(f"  🎨 Görsel üretiliyor (deneme {attempt + 1}/{Config.MAX_RETRIES})...")
                
                response = self.client.models.generate_content(
                    model=Config.IMAGE_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    )
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


# ============== VERİTABANI ==============

class DatabaseManager:
    """Supabase işlemleri"""
    
    def __init__(self):
        self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("✅ Supabase bağlantısı kuruldu")
    
    def get_questions(self, limit: int = 20) -> List[Dict]:
        """Görsel bekleyen senaryo sorularını getir"""
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
        """Sadece image_url güncelle - METİNE DOKUNMA!"""
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
    """Senaryo soruları için görsel üreten bot"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.gemini = GeminiAPI()
        self.stats = {
            'total': 0,
            'success': 0,
            'filtered': 0,
            'no_visual': 0,
            'failed': 0
        }
    
    def run(self):
        """Botu çalıştır"""
        logger.info("""
╔══════════════════════════════════════════════════════════════════════╗
║         🎨 SENARYO GÖRSEL BOTU v4.0                                  ║
║         Gemini Image Preview + Supabase                              ║
╚══════════════════════════════════════════════════════════════════════╝
        """)
        logger.info(f"📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("✅ Renkli, 3D, profesyonel görseller")
        logger.info("✅ Sadece VERİLER (çözüm YOK)")
        logger.info("✅ Geometri soruları atlanıyor")
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
        quality = analysis.get('quality_score', 0)
        title = analysis.get('title', 'Problem')
        logger.info(f"📊 Tip: {visual_type}, Kalite: {quality}/10")
        
        # 3. Görsel üret
        gorsel_betimleme = analysis.get('gorsel_betimleme', {})
        image_bytes = self.gemini.generate_image(gorsel_betimleme, title)
        
        if not image_bytes:
            logger.error("❌ Görsel üretilemedi!")
            self.stats['failed'] += 1
            return
        
        # 4. Upload
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"scenario/q_{qid}_{timestamp}.png"
        
        logger.info("☁️ Yükleniyor...")
        image_url = self.db.upload_image(image_bytes, filename)
        
        if not image_url:
            logger.error("❌ Upload başarısız!")
            self.stats['failed'] += 1
            return
        
        # 5. Veritabanı güncelle
        if self.db.update_image_url(qid, image_url):
            logger.info(f"✅ #{qid}: BAŞARILI ({visual_type})")
            self.stats['success'] += 1
        else:
            logger.error("❌ DB güncelleme başarısız!")
            self.stats['failed'] += 1
    
    def _print_report(self):
        """Sonuç raporu"""
        logger.info(f"\n{'=' * 60}")
        logger.info("📊 SONUÇ RAPORU")
        logger.info(f"{'=' * 60}")
        logger.info(f"   Toplam soru      : {self.stats['total']}")
        logger.info(f"   Başarılı         : {self.stats['success']}")
        logger.info(f"   Filtrelenen      : {self.stats['filtered']}")
        logger.info(f"   Görsel gerekmez  : {self.stats['no_visual']}")
        logger.info(f"   Başarısız        : {self.stats['failed']}")
        
        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"   ─────────────────────────────")
            logger.info(f"   Başarı oranı     : %{rate:.1f}")
        
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
