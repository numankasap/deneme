#!/usr/bin/env python3
"""
Geometry Visual Bot v2.0
========================
Question Bank'teki görselsiz geometrik sorulara görsel üreten bot.
Curriculum tablosundaki geometri kazanımlarını kullanır.

Özellikler:
- Curriculum'dan geometri kazanımlarını çeker
- Bu kazanımlara ait görselsiz soruları bulur
- Soru metnini analiz ederek uygun görsel üretir
- Kalite kontrolü yapar (Türkçe, matematiksel doğruluk)
- Başarılı görselleri veritabanına kaydeder

Kullanım:
    python geometry_visual_bot.py
"""

import os
import json
import time
import base64
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# Supabase
from supabase import create_client, Client

# Google Generative AI
from google import genai

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """Yapılandırma"""
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Model ayarları
    GEMINI_TEXT = "gemini-2.5-flash"
    GEMINI_IMAGE = "gemini-2.5-flash-preview-05-20"
    GEMINI_VISION = "gemini-2.5-flash"
    
    # Bot ayarları
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '10'))
    QUALITY_THRESHOLD = 7
    MAX_RETRY_ATTEMPTS = 3
    
    # Geometri konu anahtar kelimeleri (curriculum'da aranacak)
    GEOMETRY_KEYWORDS = [
        'Üçgen', 'Dörtgen', 'Çokgen', 'Daire', 'Çember',
        'Açı', 'Alan', 'Çevre', 'Hacim', 'Geometri', 'Prizma',
        'Piramit', 'Silindir', 'Koni', 'Küre', 'Koordinat',
        'Kenar', 'Köşegen', 'Yüzey', 'Doğru', 'Paralel', 'Dik',
        'Eşkenar', 'İkizkenar', 'Yamuk', 'Paralelkenar', 'Dikdörtgen',
        'Kare', 'Deltoid', 'Teğet', 'Kiriş', 'Yay', 'Dilim',
        'Perspektif', 'Simetri', 'Dönüşüm', 'Öteleme', 'Yansıma'
    ]


class SupabaseManager:
    """Supabase işlemleri - Curriculum tabanlı"""
    
    def __init__(self):
        self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_geometry_kazanims(self) -> List[Dict]:
        """Curriculum tablosundan geometri kazanımlarını getir"""
        try:
            # Tüm geometri anahtar kelimelerini içeren kazanımları bul
            all_kazanims = []
            
            for keyword in Config.GEOMETRY_KEYWORDS:
                # topic_name'de ara
                response1 = self.client.table('curriculum').select(
                    'id, learning_outcome_code, learning_outcome_description, topic_name, sub_topic, grade_level, bloom_level'
                ).ilike('topic_name', f'%{keyword}%').execute()
                
                if response1.data:
                    all_kazanims.extend(response1.data)
                
                # sub_topic'te ara
                response2 = self.client.table('curriculum').select(
                    'id, learning_outcome_code, learning_outcome_description, topic_name, sub_topic, grade_level, bloom_level'
                ).ilike('sub_topic', f'%{keyword}%').execute()
                
                if response2.data:
                    all_kazanims.extend(response2.data)
                
                # learning_outcome_description'da ara
                response3 = self.client.table('curriculum').select(
                    'id, learning_outcome_code, learning_outcome_description, topic_name, sub_topic, grade_level, bloom_level'
                ).ilike('learning_outcome_description', f'%{keyword}%').execute()
                
                if response3.data:
                    all_kazanims.extend(response3.data)
            
            # Tekrarları kaldır (id'ye göre)
            unique_kazanims = {k['id']: k for k in all_kazanims}.values()
            kazanim_list = list(unique_kazanims)
            
            logger.info(f"📚 {len(kazanim_list)} geometri kazanımı bulundu")
            return kazanim_list
            
        except Exception as e:
            logger.error(f"Kazanım getirme hatası: {e}")
            return []
    
    def get_questions_without_images_by_kazanim(self, kazanim_ids: List[int], limit: int = 10) -> List[Dict]:
        """Belirli kazanımlara ait görselsiz soruları getir"""
        try:
            if not kazanim_ids:
                return []
            
            # question_bank'teki sütun adları: content (soru metni), question_type, vb.
            response = self.client.table('question_bank').select(
                'id, content, topic, topic_group, grade_level, difficulty, kazanim_id'
            ).is_('image_url', 'null').in_('kazanim_id', kazanim_ids).limit(limit).execute()
            
            questions = response.data if response.data else []
            logger.info(f"📋 {len(questions)} görselsiz geometrik soru bulundu")
            return questions
            
        except Exception as e:
            logger.error(f"Soru getirme hatası: {e}")
            return []
    
    def get_kazanim_info(self, kazanim_id: int) -> Optional[Dict]:
        """Kazanım bilgisini getir"""
        try:
            response = self.client.table('curriculum').select(
                'id, learning_outcome_code, learning_outcome_description, topic_name, sub_topic, grade_level, bloom_level'
            ).eq('id', kazanim_id).single().execute()
            
            return response.data if response.data else None
            
        except Exception as e:
            logger.error(f"Kazanım bilgisi getirme hatası: {e}")
            return None
    
    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Görseli Supabase Storage'a yükle"""
        try:
            response = self.client.storage.from_('questions-images').upload(
                filename,
                image_bytes,
                {'content-type': 'image/png'}
            )
            
            public_url = self.client.storage.from_('questions-images').get_public_url(filename)
            return public_url
            
        except Exception as e:
            logger.error(f"Görsel yükleme hatası: {e}")
            return None
    
    def update_question_image(self, question_id: int, image_url: str) -> bool:
        """Sorunun görsel URL'sini güncelle"""
        try:
            self.client.table('question_bank').update({
                'image_url': image_url,
                'updated_at': datetime.now().isoformat()
            }).eq('id', question_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Soru güncelleme hatası: {e}")
            return False


class QuestionAnalyzer:
    """Soru metnini analiz ederek görsel bilgisi çıkarır"""
    
    ANALYSIS_PROMPT = """Bu matematik/geometri sorusunu analiz et ve görsel oluşturmak için gerekli bilgileri çıkar.

SORU METNİ:
{question_text}

KAZANIM BİLGİSİ:
{kazanim_info}

ANALİZ ET:
1. Soru tipi (üçgen, dörtgen, daire, açı, koordinat, prizma, vb.)
2. Şekil özellikleri (kenar sayısı, açılar, özel özellikler)
3. Verilen değerler (uzunluklar, açılar, koordinatlar)
4. Değişkenler (x, y, a, b, vb.)
5. Görsel için gerekli etiketler

JSON formatında döndür:
{{
    "shape_type": "üçgen",
    "shape_details": {{
        "type": "dik üçgen",
        "special_properties": ["dik açı", "ikizkenar"],
        "vertices": ["A", "B", "C"]
    }},
    "given_values": {{
        "angles": ["90°", "x°", "45°"],
        "sides": ["5 cm", "a", "b"],
        "other": []
    }},
    "variables": ["x", "a", "b"],
    "labels": ["A", "B", "C", "5 cm", "x°"],
    "visual_description": "ABC dik üçgeni, B'de dik açı, kenarlar etiketli",
    "complexity": "medium"
}}

SADECE JSON döndür!"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        logger.info("QuestionAnalyzer başlatıldı")
    
    def analyze(self, question_text: str, kazanim_info: Dict = None) -> Optional[Dict]:
        """Soru metnini analiz et"""
        try:
            kazanim_str = ""
            if kazanim_info:
                topic_name = kazanim_info.get('topic_name', '') or ''
                sub_topic = kazanim_info.get('sub_topic', '') or ''
                learning_desc = kazanim_info.get('learning_outcome_description', '') or ''
                kazanim_str = f"""
Konu: {topic_name}
Alt Konu: {sub_topic}
Kazanım: {learning_desc}
"""
            
            prompt = self.ANALYSIS_PROMPT.format(
                question_text=question_text,
                kazanim_info=kazanim_str
            )
            
            response = self.client.models.generate_content(
                model=Config.GEMINI_TEXT,
                contents=prompt
            )
            content = response.text
            
            # JSON parse
            content = content.strip()
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])
                if content.startswith('json'):
                    content = content[4:].strip()
            
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Soru analiz hatası: {e}")
            return None


class GeometryImageGenerator:
    """Geometrik görsel üretici"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.request_count = 0
        self.last_request_time = 0
        logger.info("GeometryImageGenerator başlatıldı")
    
    def _rate_limit(self):
        """Rate limiting"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= 4:
            wait_time = 65 - (current_time - self.last_request_time)
            if wait_time > 0:
                logger.info(f"⏳ Rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        
        self.request_count += 1
    
    def generate(self, question_text: str, analysis: Dict, kazanim_info: Dict = None,
                 previous_problems: list = None) -> Optional[bytes]:
        """Soru için görsel üret"""
        try:
            self._rate_limit()
            
            # Soru metninden değerleri çıkar
            numbers = re.findall(r'\d+', question_text)
            angles = re.findall(r'(\d+)\s*derece', question_text.lower())
            
            # Kazanım bilgisi
            kazanim_str = ""
            if kazanim_info:
                topic_name = kazanim_info.get('topic_name', '') or ''
                sub_topic = kazanim_info.get('sub_topic', '') or ''
                kazanim_str = f"""
KONU: {topic_name}
ALT KONU: {sub_topic}
"""
            
            # Feedback bölümü
            feedback_section = ""
            if previous_problems:
                feedback_section = f"""
════════════════════════════════════════════════════════════════
⚠️ ÖNCEKİ HATALARI YAPMA!
════════════════════════════════════════════════════════════════
{chr(10).join(['❌ ' + str(p) for p in previous_problems])}
════════════════════════════════════════════════════════════════
"""
            
            prompt = f"""Aşağıdaki geometri sorusu için TEMİZ bir matematiksel görsel çiz.
{feedback_section}
{kazanim_str}

SORU (SADECE REFERANS İÇİN - GÖRSELЕ YAZMA!):
{question_text[:300]}

ŞEKİL BİLGİLERİ:
- Tip: {analysis.get('shape_type', 'geometrik şekil')}
- Detaylar: {json.dumps(analysis.get('shape_details', {}), ensure_ascii=False)}
- Değerler: {json.dumps(analysis.get('given_values', {}), ensure_ascii=False)}
- Etiketler: {', '.join(analysis.get('labels', []))}
- Açıklama: {analysis.get('visual_description', '')}

════════════════════════════════════════════════════════════════
📊 SORUDA GEÇEN DEĞERLER - BUNLARI KULLAN!
════════════════════════════════════════════════════════════════
Sayılar: {', '.join(numbers[:10])}
Açılar: {', '.join([a + '°' for a in angles]) if angles else 'yok'}
Değişkenler: {', '.join(analysis.get('variables', []))}
════════════════════════════════════════════════════════════════

🚫 YASAKLAR:
❌ Soru metni YAZMA
❌ Türkçe cümle YAZMA (5+ kelime)
❌ A), B), C), D) şıkları YAZMA
❌ İngilizce kelime YAZMA
❌ Formül çözümü YAZMA
❌ "Buna göre...", "...kaçtır?" YAZMA

✅ SADECE BUNLAR OLMALI:
- Geometrik şekil ({analysis.get('shape_type', 'şekil')})
- Köşe etiketleri: A, B, C, D, ...
- Kenar uzunlukları: 5 cm, a, x
- Açı değerleri: 45°, x°, 90°
- Boyut okları

🎨 STİL:
- Temiz, kalın çizgiler
- Beyaz veya açık renkli arka plan  
- Profesyonel ders kitabı stili
- Türkçe etiketler (varsa)
- Her şekil parçası net görünür

TEMİZ, BASİT, MATEMATİKSEL, TÜRKÇE!"""

            logger.info(f"🎨 Geometrik görsel üretiliyor: {analysis.get('shape_type', 'unknown')}")
            
            response = self.client.models.generate_content(
                model=Config.GEMINI_IMAGE,
                contents=prompt,
                config={
                    "response_modalities": ["IMAGE", "TEXT"],
                }
            )
            
            return self._extract_image(response)
            
        except Exception as e:
            logger.error(f"Görsel üretim hatası: {e}")
            return None
    
    def _extract_image(self, response) -> Optional[bytes]:
        """Response'dan görsel çıkar"""
        try:
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_data = part.inline_data.data
                        if isinstance(image_data, str):
                            return base64.b64decode(image_data)
                        return image_data
            return None
        except Exception as e:
            logger.error(f"Görsel çıkarma hatası: {e}")
            return None


class ImageValidator:
    """Görsel kalite kontrolü"""
    
    VALIDATION_PROMPT = """Bu geometrik görseli değerlendir.

KONTROLLER:
1. has_sentences: 5+ kelimelik Türkçe cümle var mı?
2. has_options: A), B), C), D) şıkları var mı?
3. has_english: İngilizce kelimeler var mı?
4. is_clean: Görsel temiz ve profesyonel mi?
5. has_geometry: Geometrik şekil var mı?

JSON formatında döndür:
{{
    "has_sentences": false,
    "has_options": false,
    "has_english": false,
    "is_clean": true,
    "has_geometry": true,
    "detected_labels": ["A", "B", "C", "5 cm", "x°"],
    "detected_numbers": ["5", "45", "90"],
    "shape_type": "üçgen",
    "overall_quality": 9,
    "problems": []
}}

PUANLAMA:
- Temiz geometrik şekil → 9-10
- Küçük sorunlar → 7-8
- İngilizce var → 4-5
- Soru metni var → 0-3

SADECE JSON döndür!"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        logger.info("ImageValidator başlatıldı")
    
    def validate(self, image_bytes: bytes, question_text: str) -> Dict:
        """Görseli değerlendir"""
        try:
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            response = self.client.models.generate_content(
                model=Config.GEMINI_VISION,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                            {"text": self.VALIDATION_PROMPT}
                        ]
                    }
                ]
            )
            content = response.text
            
            # JSON parse
            content = content.strip()
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])
                if content.startswith('json'):
                    content = content[4:].strip()
            
            validation = json.loads(content)
            
            # Sorun tespiti
            problems = validation.get('problems', [])
            overall = validation.get('overall_quality', 5)
            
            if validation.get('has_sentences', False):
                problems.append("soru_cumlesi")
                overall = min(overall, 3)
            
            if validation.get('has_options', False):
                problems.append("siklar")
                overall = min(overall, 3)
            
            if validation.get('has_english', False):
                problems.append("ingilizce")
                overall = min(overall, 5)
            
            if not validation.get('has_geometry', True):
                problems.append("geometri_yok")
                overall = min(overall, 4)
            
            validation['overall_score'] = overall
            validation['pass'] = overall >= Config.QUALITY_THRESHOLD
            validation['problems'] = problems
            
            # Log
            if validation['pass']:
                logger.info(f"📊 Kalite: {overall}/10 - ✅ KABUL")
            else:
                logger.info(f"📊 Kalite: {overall}/10 - ❌ RED")
                if problems:
                    logger.info(f"   Sorunlar: {', '.join(problems)}")
            
            return validation
            
        except Exception as e:
            logger.error(f"Validasyon hatası: {e}")
            return {"overall_score": 5, "pass": False, "problems": ["hata"]}


class GeometryVisualBot:
    """Ana bot sınıfı - Curriculum tabanlı"""
    
    def __init__(self):
        logger.info("=" * 60)
        logger.info("Geometry Visual Bot v2.0")
        logger.info("Curriculum Tabanlı Geometrik Görsel Üretici")
        logger.info("=" * 60)
        
        self.supabase = SupabaseManager()
        self.analyzer = QuestionAnalyzer(Config.GEMINI_API_KEY)
        self.generator = GeometryImageGenerator(Config.GEMINI_API_KEY)
        self.validator = ImageValidator(Config.GEMINI_API_KEY)
        
        self.stats = {
            'kazanims_found': 0,
            'questions_processed': 0,
            'images_created': 0,
            'images_rejected': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
    
    def run(self):
        """Ana çalışma döngüsü"""
        logger.info("Bot başlatılıyor...")
        
        # 1. Geometri kazanımlarını getir
        logger.info("📚 Curriculum'dan geometri kazanımları alınıyor...")
        kazanims = self.supabase.get_geometry_kazanims()
        
        if not kazanims:
            logger.info("❌ Geometri kazanımı bulunamadı")
            return
        
        self.stats['kazanims_found'] = len(kazanims)
        kazanim_ids = [k['id'] for k in kazanims]
        
        # Kazanım örneklerini göster
        logger.info(f"\n📋 Örnek kazanımlar:")
        for k in kazanims[:5]:
            topic_name = k.get('topic_name', '') or ''
            sub_topic = k.get('sub_topic', '') or ''
            logger.info(f"   • K{k['id']}: {topic_name} - {sub_topic[:50]}")
        
        # 2. Bu kazanımlara ait görselsiz soruları getir
        logger.info(f"\n🔍 {len(kazanim_ids)} kazanıma ait görselsiz sorular aranıyor...")
        questions = self.supabase.get_questions_without_images_by_kazanim(
            kazanim_ids, Config.BATCH_SIZE
        )
        
        if not questions:
            logger.info("✅ Görselsiz geometrik soru yok - tüm sorular görsellendirilmiş!")
            return
        
        logger.info(f"📋 {len(questions)} soru işlenecek")
        
        # 3. Her soruyu işle
        for i, question in enumerate(questions, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"Soru {i}/{len(questions)}: ID={question.get('id')}")
            logger.info(f"{'='*50}")
            
            self._process_question(question)
            
            # Sorular arası bekleme
            if i < len(questions):
                logger.info("⏳ Sonraki soru için 5s bekleniyor...")
                time.sleep(5)
        
        # Sonuç raporu
        self._print_report()
    
    def _process_question(self, question: Dict):
        """Tek bir soruyu işle"""
        question_id = question.get('id')
        question_text = question.get('content', '')
        kazanim_id = question.get('kazanim_id')
        topic = question.get('topic', '')
        
        # Kazanım bilgisini al
        kazanim_info = None
        if kazanim_id:
            kazanim_info = self.supabase.get_kazanim_info(kazanim_id)
        
        if kazanim_info:
            topic_name = kazanim_info.get('topic_name', '') or ''
            sub_topic = kazanim_info.get('sub_topic', '') or ''
            logger.info(f"[{question_id}] 📚 Kazanım: K{kazanim_id} - {topic_name}")
            logger.info(f"[{question_id}] 📖 Alt Konu: {sub_topic[:60]}")
        else:
            logger.info(f"[{question_id}] 📝 Konu: {topic}")
        
        logger.info(f"[{question_id}] 📄 Soru: {question_text[:80]}...")
        
        try:
            # 1. Soruyu analiz et
            logger.info(f"[{question_id}] 🔍 Soru analiz ediliyor...")
            analysis = self.analyzer.analyze(question_text, kazanim_info)
            
            if not analysis:
                logger.warning(f"[{question_id}] Analiz başarısız")
                self.stats['errors'] += 1
                return
            
            logger.info(f"[{question_id}] ✅ Analiz: {analysis.get('shape_type', 'unknown')}")
            logger.info(f"[{question_id}]    Etiketler: {', '.join(analysis.get('labels', [])[:5])}")
            
            # 2. Görsel üret (kalite kontrollü)
            image_bytes = self._generate_with_quality_check(
                question_id, question_text, analysis, kazanim_info
            )
            
            if not image_bytes:
                logger.warning(f"[{question_id}] Görsel üretilemedi")
                return
            
            # 3. Görseli yükle
            kazanim_code = f"K{kazanim_id}" if kazanim_id else "geo"
            filename = f"geo_{kazanim_code}_{question_id}_{int(time.time())}.png"
            image_url = self.supabase.upload_image(image_bytes, filename)
            
            if not image_url:
                logger.error(f"[{question_id}] Görsel yüklenemedi")
                self.stats['errors'] += 1
                return
            
            logger.info(f"[{question_id}] 🖼️ Görsel yüklendi")
            
            # 4. Veritabanını güncelle
            if self.supabase.update_question_image(question_id, image_url):
                self.stats['images_created'] += 1
                logger.info(f"[{question_id}] ✅ Soru güncellendi")
            else:
                self.stats['errors'] += 1
            
            self.stats['questions_processed'] += 1
            
        except Exception as e:
            logger.error(f"[{question_id}] Hata: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
    
    def _generate_with_quality_check(self, question_id: int, question_text: str, 
                                      analysis: Dict, kazanim_info: Dict = None) -> Optional[bytes]:
        """Kalite kontrollü görsel üret"""
        best_image = None
        best_score = 0
        previous_problems = []
        
        for attempt in range(Config.MAX_RETRY_ATTEMPTS):
            logger.info(f"[{question_id}] 🎨 Görsel üretimi deneme {attempt + 1}/{Config.MAX_RETRY_ATTEMPTS}")
            
            # Görsel üret
            image_bytes = self.generator.generate(
                question_text, analysis, kazanim_info, previous_problems
            )
            
            if not image_bytes:
                logger.warning(f"[{question_id}] Görsel üretilemedi")
                continue
            
            logger.info(f"[{question_id}] ✅ Görsel üretildi ({len(image_bytes)} bytes)")
            
            # Kalite kontrolü
            logger.info(f"[{question_id}] 📊 Kalite kontrolü...")
            validation = self.validator.validate(image_bytes, question_text)
            
            score = validation.get('overall_score', 0)
            problems = validation.get('problems', [])
            
            # En iyi skoru takip et
            if score > best_score:
                best_score = score
                best_image = image_bytes
            
            if validation.get('pass', False):
                logger.info(f"[{question_id}] ✅ KABUL (Puan: {score}/10)")
                return image_bytes
            else:
                self.stats['images_rejected'] += 1
                logger.warning(f"[{question_id}] ❌ RED (Puan: {score}/10)")
                if problems:
                    logger.warning(f"[{question_id}]    Sorunlar: {', '.join(problems)}")
                
                # Feedback için sorunları biriktir
                previous_problems.extend(problems)
                previous_problems = list(set(previous_problems))
                
                if attempt < Config.MAX_RETRY_ATTEMPTS - 1:
                    logger.info(f"[{question_id}] 🔄 Yeniden deneniyor...")
                    time.sleep(3)
        
        # En iyi skoru kullan
        if best_image and best_score >= 5:
            logger.warning(f"[{question_id}] ⚠️ En iyi skor ({best_score}/10) kullanılıyor")
            return best_image
        
        logger.error(f"[{question_id}] ❌ Tüm denemeler başarısız")
        return None
    
    def _print_report(self):
        """Sonuç raporu"""
        elapsed = datetime.now() - self.stats['start_time']
        
        logger.info("\n" + "=" * 60)
        logger.info("TAMAMLANDI")
        logger.info("=" * 60)
        logger.info(f"⏱️  Süre: {elapsed}")
        logger.info(f"📚 Bulunan Kazanımlar: {self.stats['kazanims_found']}")
        logger.info(f"📝 İşlenen Sorular: {self.stats['questions_processed']}")
        logger.info(f"🖼️  Üretilen Görseller: {self.stats['images_created']}")
        logger.info(f"❌ Reddedilen Görseller: {self.stats['images_rejected']}")
        logger.info(f"⚠️  Hatalar: {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    """Ana fonksiyon"""
    print("🎨 Geometry Visual Bot v2.0 Başlatılıyor...")
    print("━" * 50)
    print(f"📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Batch Size: {Config.BATCH_SIZE} soru")
    print(f"🔍 Kalite Eşiği: {Config.QUALITY_THRESHOLD}/10")
    print(f"🔄 Maksimum Deneme: {Config.MAX_RETRY_ATTEMPTS}")
    print("━" * 50)
    
    # Yapılandırma kontrolü
    if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
        print("❌ SUPABASE_URL ve SUPABASE_SERVICE_KEY gerekli!")
        return
    
    if not Config.GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY gerekli!")
        return
    
    print("✅ Yapılandırma tamam")
    print("━" * 50)
    
    bot = GeometryVisualBot()
    bot.run()


if __name__ == "__main__":
    main()
