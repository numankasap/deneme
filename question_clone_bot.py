#!/usr/bin/env python3
"""
Question Clone Bot v1.0 - Fotoğraftan Benzer Soru Üretici
=========================================================
1. Veritabanındaki örnek soru fotoğraflarını analiz eder
2. Soru tipini, şekil stilini ve parametreleri çıkarır
3. Benzer ama farklı parametrelerle yeni sorular üretir
4. Aynı görsel stilde şekiller çizer
5. Veritabanına kaydeder

Kullanılan API'ler:
- Gemini Vision: Fotoğraf analizi
- Gemini Text: Yeni soru üretimi
- Gemini Image: Görsel üretimi
"""

import os
import io
import json
import math
import time
import base64
import random
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

from supabase import create_client, Client

try:
    from google import genai
    from google.genai import types
    NEW_GENAI = True
except ImportError:
    import google.generativeai as genai
    NEW_GENAI = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Modeller
    GEMINI_VISION = os.environ.get('GEMINI_VISION', 'gemini-2.5-flash')  # Fotoğraf analizi
    GEMINI_TEXT = os.environ.get('GEMINI_TEXT', 'gemini-2.5-flash')  # Soru üretimi
    GEMINI_IMAGE = 'gemini-2.5-flash-image'  # Görsel üretimi
    
    # Ayarlar
    STORAGE_BUCKET_TEMPLATES = 'question-templates'  # Örnek fotoğraflar
    STORAGE_BUCKET_GENERATED = 'questions-images'  # Üretilen görseller
    
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '5'))
    VARIATIONS_PER_TEMPLATE = int(os.environ.get('VARIATIONS', '3'))  # Her şablondan kaç varyasyon
    
    # Zorluk seviyeleri
    DIFFICULTY_LEVELS = ['easy', 'medium', 'hard']
    
    # Hedef sınıflar
    TARGET_GRADES = [5, 6, 7, 8]  # LGS için


class SupabaseManager:
    """Veritabanı işlemleri - Kazanım bazlı sistem"""
    
    def __init__(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("Supabase credentials eksik!")
        self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_template_questions(self, limit: int = 10) -> List[Dict]:
        """İşlenmemiş şablon soruları getir - kazanım bilgileriyle birlikte"""
        try:
            # Şablonları çek
            result = self.client.table('question_templates').select(
                'id', 'image_url', 'kazanim_id', 'processed', 'variations_created', 'notes'
            ).eq('processed', False).limit(limit).execute()
            
            if not result.data:
                return []
            
            templates = result.data
            
            # Her şablon için kazanım bilgilerini çek
            for template in templates:
                kazanim_id = template.get('kazanim_id')
                if kazanim_id:
                    kazanim_info = self.get_kazanim_info(kazanim_id)
                    if kazanim_info:
                        template['kazanim_info'] = kazanim_info
                    else:
                        logger.warning(f"Kazanım bulunamadı: {kazanim_id}")
            
            return templates
            
        except Exception as e:
            logger.error(f"Template sorgu hatası: {e}")
            return []
    
    def get_kazanim_info(self, kazanim_id: int) -> Optional[Dict]:
        """Curriculum tablosundan kazanım bilgilerini getir"""
        try:
            result = self.client.table('curriculum').select(
                'id', 'grade_level', 'category', 'lesson_name', 
                'topic_code', 'topic_name', 'sub_topic',
                'learning_outcome_code', 'learning_outcome_description',
                'key_concepts', 'cognitive_level', 'bloom_level', 'difficulty_range'
            ).eq('id', kazanim_id).single().execute()
            
            if not result.data:
                return None
            
            # Veriyi standart formata dönüştür
            data = result.data
            return {
                'id': data.get('id'),
                'code': data.get('learning_outcome_code') or data.get('topic_code') or f"K{data.get('id')}",
                'description': data.get('sub_topic') or data.get('learning_outcome_description', ''),
                'topic': data.get('topic_name', 'Matematik'),
                'subtopic': data.get('sub_topic', ''),
                'grade_level': data.get('grade_level', 8),
                'category': data.get('category', 'LGS'),
                'lesson_name': data.get('lesson_name', 'Matematik'),
                'learning_domain': data.get('topic_name', ''),
                'unit': data.get('topic_name', ''),
                'keywords': data.get('key_concepts', '[]'),
                'bloom_level': data.get('bloom_level', ''),
                'cognitive_level': data.get('cognitive_level', ''),
                'difficulty_range': data.get('difficulty_range', [])
            }
            
        except Exception as e:
            logger.error(f"Kazanım sorgu hatası ({kazanim_id}): {e}")
            return None
    
    def mark_template_processed(self, template_id: str, variations_count: int):
        """Şablonu işlendi olarak işaretle"""
        try:
            self.client.table('question_templates').update({
                'processed': True,
                'variations_created': variations_count,
                'processed_at': datetime.now().isoformat()
            }).eq('id', template_id).execute()
        except Exception as e:
            logger.error(f"Template güncelleme hatası: {e}")
    
    def save_generated_question(self, question_data: Dict) -> Optional[str]:
        """Üretilen soruyu kaydet - question_bank tablosuna"""
        try:
            # Senin question_bank yapın:
            insert_data = {
                # Temel alanlar
                'original_text': question_data.get('question_text', ''),
                'subject': 'Matematik',
                'grade_level': question_data.get('grade_level', 8),
                'topic': question_data.get('topic', 'Genel'),
                'topic_group': question_data.get('topic_group'),
                
                # Kazanım bilgileri
                'kazanim_id': question_data.get('kazanim_id'),  # INTEGER
                
                # Cevap ve şıklar
                'correct_answer': question_data.get('answer'),
                'options': question_data.get('options') if isinstance(question_data.get('options'), dict) else None,
                
                # Çözüm
                'solution_text': question_data.get('solution'),
                'solution_short': question_data.get('solution_short'),
                'solution_detailed': question_data.get('solution'),
                
                # Zorluk (1-5 arası integer)
                'difficulty': self._convert_difficulty(question_data.get('difficulty', 'medium')),
                
                # Görsel
                'image_url': question_data.get('image_url'),
                
                # Soru tipi
                'question_type': question_data.get('question_type', 'çoktan_seçmeli'),
                
                # Durum
                'is_active': True,
                'verified': False,
                
                # Kaynak bilgisi (title alanına yazalım)
                'title': f"AI Generated - Template: {question_data.get('template_id', 'unknown')}"
            }
            
            # None değerleri temizle
            insert_data = {k: v for k, v in insert_data.items() if v is not None}
            
            result = self.client.table('question_bank').insert(insert_data).execute()
            
            if result.data:
                return result.data[0].get('id')
            return None
        except Exception as e:
            logger.error(f"Soru kaydetme hatası: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _convert_difficulty(self, difficulty: str) -> int:
        """Zorluk seviyesini string'den integer'a çevir (1-5)"""
        mapping = {
            'very_easy': 1,
            'easy': 2,
            'medium': 3,
            'hard': 4,
            'very_hard': 5
        }
        return mapping.get(difficulty.lower(), 3)
    
    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Görseli storage'a yükle"""
        try:
            self.client.storage.from_(Config.STORAGE_BUCKET_GENERATED).upload(
                path=filename, 
                file=image_bytes,
                file_options={"content-type": "image/png"}
            )
            return self.client.storage.from_(Config.STORAGE_BUCKET_GENERATED).get_public_url(filename)
        except Exception as e:
            if 'Duplicate' in str(e):
                try:
                    self.client.storage.from_(Config.STORAGE_BUCKET_GENERATED).update(
                        path=filename,
                        file=image_bytes,
                        file_options={"content-type": "image/png"}
                    )
                    return self.client.storage.from_(Config.STORAGE_BUCKET_GENERATED).get_public_url(filename)
                except:
                    pass
            logger.error(f"Upload hatası: {e}")
            return None
    
    def download_image(self, image_url: str) -> Optional[bytes]:
        """URL'den görsel indir"""
        try:
            import urllib.request
            with urllib.request.urlopen(image_url) as response:
                return response.read()
        except Exception as e:
            logger.error(f"Görsel indirme hatası: {e}")
            return None


class VisionAnalyzer:
    """Gemini Vision ile fotoğraf analizi"""
    
    ANALYSIS_PROMPT = """Bu matematik soru fotoğrafını detaylı analiz et.

ÇIKART:
1. SORU TİPİ: (pasta_grafik, sütun_grafik, üçgen, dörtgen, daire, piramit, vb.)
2. GÖRSEL STİL: (kareli zemin, düz arka plan, renkli, siyah-beyaz, 3D, 2D)
3. VERİLEN BİLGİLER: (sayılar, açılar, uzunluklar, yüzdeler, etiketler)
4. SORU METNİ: (görseldeki Türkçe metin)
5. ŞEKİL DETAYLARI: (renkler, etiket pozisyonları, çizgi stilleri)
6. ZORLUK: (easy, medium, hard)
7. SINIF SEVİYESİ: (5, 6, 7, 8)
8. KONU: (Veri Analizi, Geometri, Oran-Orantı, vb.)

JSON formatında döndür:
{
    "question_type": "pasta_grafik",
    "visual_style": {
        "background": "kareli_zemin",
        "colors": ["sarı", "mavi", "yeşil", "pembe"],
        "is_3d": false,
        "has_legend": true,
        "label_style": "inside"
    },
    "given_data": {
        "type": "percentages",
        "values": [{"label": "Futbol", "value": 30}, {"label": "Basketbol", "value": 25}],
        "total": 100
    },
    "question_text": "Buna göre, bu kursa katılan öğrenciler arasından...",
    "topic": "Veri Analizi",
    "subtopic": "Pasta Grafiği",
    "difficulty": "medium",
    "grade_level": 7,
    "shape_properties": {
        "segments": 4,
        "center_visible": false,
        "border_style": "solid"
    }
}

SADECE JSON döndür!"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            genai.configure(api_key=api_key)
        self.request_count = 0
        self.last_request_time = 0
        logger.info("VisionAnalyzer başlatıldı")
    
    def _rate_limit(self):
        """Rate limiting"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= 5:
            wait_time = 65 - (current_time - self.last_request_time)
            if wait_time > 0:
                logger.info(f"⏳ Vision rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        
        if self.request_count > 0:
            time.sleep(4)
        
        self.request_count += 1
    
    def analyze_image(self, image_bytes: bytes) -> Optional[Dict]:
        """Fotoğrafı analiz et"""
        try:
            self._rate_limit()
            
            # Base64 encode
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            if NEW_GENAI:
                response = self.client.models.generate_content(
                    model=Config.GEMINI_VISION,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_image(
                                    image=types.Image(
                                        image_bytes=image_bytes,
                                        mime_type="image/png"
                                    )
                                ),
                                types.Part.from_text(self.ANALYSIS_PROMPT)
                            ]
                        )
                    ]
                )
                text = response.text
            else:
                model = genai.GenerativeModel(Config.GEMINI_VISION)
                response = model.generate_content([
                    {"mime_type": "image/png", "data": image_b64},
                    self.ANALYSIS_PROMPT
                ])
                text = response.text
            
            # JSON parse
            text = text.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
                if text.startswith('json'):
                    text = text[4:].strip()
            
            return json.loads(text)
            
        except Exception as e:
            logger.error(f"Vision analiz hatası: {e}")
            return None


class QuestionGenerator:
    """Benzer soru üretici - Kazanım bazlı"""
    
    GENERATION_PROMPT = """Aşağıdaki soru analizine ve KAZANIM BİLGİLERİNE dayanarak, BENZER AMA FARKLI bir matematik sorusu üret.

ORIJINAL SORU ANALİZİ:
{analysis}

KAZANIM BİLGİLERİ:
- Kazanım Kodu: {kazanim_code}
- Kazanım Açıklaması: {kazanim_description}
- Konu: {topic}
- Alt Konu: {subtopic}
- Sınıf Seviyesi: {grade_level}. sınıf
- Öğrenme Alanı: {learning_domain}
- Ünite: {unit}
- Anahtar Kelimeler: {keywords}
- Bloom Seviyesi: {bloom_level}

KURALLAR:
1. Aynı soru tipini kullan ({question_type})
2. Aynı görsel stili koru
3. FARKLI sayılar/değerler kullan
4. FARKLI bir senaryo/bağlam kullan (güncel, öğrenci ilgisini çekecek)
5. Kazanım açıklamasına UYGUN olmalı
6. Türkçe olmalı
7. LGS stilinde olmalı
8. Zorluk: {difficulty}

ÜRETİLECEK:
1. Yeni soru metni (kazanıma uygun)
2. Yeni değerler (görsel için)
3. Doğru cevap
4. 4 şık (A, B, C, D) - çeldiriciler mantıklı olmalı
5. Adım adım çözüm

JSON formatında döndür:
{{
    "question_text": "Yeni soru metni...",
    "visual_data": {{
        "type": "{question_type}",
        "values": [...],
        "labels": [...],
        "title": "Grafik başlığı"
    }},
    "answer": "C",
    "options": {{
        "A": "seçenek 1",
        "B": "seçenek 2", 
        "C": "seçenek 3 (doğru)",
        "D": "seçenek 4"
    }},
    "solution": "Adım adım çözüm..."
}}

SADECE JSON döndür!"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            genai.configure(api_key=api_key)
        self.request_count = 0
        self.last_request_time = 0
        logger.info("QuestionGenerator başlatıldı")
    
    def _rate_limit(self):
        """Rate limiting"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= 5:
            wait_time = 65 - (current_time - self.last_request_time)
            if wait_time > 0:
                logger.info(f"⏳ Generator rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        
        if self.request_count > 0:
            time.sleep(4)
        
        self.request_count += 1
    
    def generate_variation(self, analysis: Dict, kazanim_info: Dict, difficulty: str = None) -> Optional[Dict]:
        """Analiz ve kazanım bilgisine dayanarak yeni soru üret"""
        try:
            self._rate_limit()
            
            # Kazanım bilgilerini al
            kazanim_code = kazanim_info.get('code', '')
            kazanim_description = kazanim_info.get('description', '')
            topic = kazanim_info.get('topic', 'Matematik')
            subtopic = kazanim_info.get('subtopic', '')
            grade_level = kazanim_info.get('grade_level', 8)
            learning_domain = kazanim_info.get('learning_domain', '')
            unit = kazanim_info.get('unit', '')
            keywords = kazanim_info.get('keywords', '')
            bloom_level = kazanim_info.get('bloom_level', '')
            
            # Zorluk seviyesi
            difficulty = difficulty or kazanim_info.get('difficulty_level', 'medium')
            question_type = analysis.get('question_type', 'unknown')
            
            prompt = self.GENERATION_PROMPT.format(
                analysis=json.dumps(analysis, ensure_ascii=False, indent=2),
                kazanim_code=kazanim_code,
                kazanim_description=kazanim_description,
                topic=topic,
                subtopic=subtopic,
                grade_level=grade_level,
                learning_domain=learning_domain,
                unit=unit,
                keywords=keywords,
                bloom_level=bloom_level,
                question_type=question_type,
                difficulty=difficulty
            )
            
            if NEW_GENAI:
                response = self.client.models.generate_content(
                    model=Config.GEMINI_TEXT,
                    contents=prompt
                )
                text = response.text
            else:
                model = genai.GenerativeModel(Config.GEMINI_TEXT)
                response = model.generate_content(prompt)
                text = response.text
            
            # JSON parse
            text = text.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
                if text.startswith('json'):
                    text = text[4:].strip()
            
            result = json.loads(text)
            
            # Kazanım bilgilerini sonuca ekle
            result['kazanim_id'] = kazanim_info.get('id')
            result['kazanim_code'] = kazanim_code
            result['topic'] = topic
            result['subtopic'] = subtopic
            result['topic_group'] = learning_domain
            result['grade_level'] = grade_level
            result['difficulty'] = difficulty
            result['learning_domain'] = learning_domain
            result['unit'] = unit
            result['keywords'] = keywords
            result['bloom_level'] = bloom_level
            
            return result
            
        except Exception as e:
            logger.error(f"Soru üretim hatası: {e}")
            return None


class ImageGenerator:
    """Görsel üretici - Gemini Image API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        self.request_count = 0
        self.last_request_time = 0
        logger.info("ImageGenerator başlatıldı")
    
    def _rate_limit(self):
        """Rate limiting - Image gen için daha yavaş"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= 4:
            wait_time = 65 - (current_time - self.last_request_time)
            if wait_time > 0:
                logger.info(f"⏳ ImageGen rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        
        if self.request_count > 0:
            time.sleep(6)
        
        self.request_count += 1
    
    def _build_prompt(self, visual_data: Dict, visual_style: Dict) -> str:
        """Görsel üretim prompt'u oluştur"""
        q_type = visual_data.get('type', 'chart')
        
        prompt_parts = [
            "Matematik eğitimi için profesyonel bir görsel oluştur.",
            "",
            "KRİTİK KURALLAR:",
            "1. Sadece geometrik şekil veya grafik çiz",
            "2. Soru metnini YAZMA",
            "3. Temiz, net çizgiler kullan",
            "4. Etiketleri okunaklı yap",
            "",
        ]
        
        # Görsel stil
        bg = visual_style.get('background', 'beyaz')
        if bg == 'kareli_zemin':
            prompt_parts.append("ARKA PLAN: Açık gri kareli zemin (milimetrik kağıt gibi)")
        else:
            prompt_parts.append("ARKA PLAN: Beyaz")
        
        # Şekil tipine göre
        if q_type == 'pasta_grafik':
            values = visual_data.get('values', [])
            labels = visual_data.get('labels', [])
            title = visual_data.get('title', '')
            colors = visual_style.get('colors', ['sarı', 'mavi', 'yeşil', 'pembe'])
            
            prompt_parts.append("")
            prompt_parts.append("ŞEKİL: Pasta Grafiği (Pie Chart)")
            if title:
                prompt_parts.append(f"BAŞLIK: {title}")
            prompt_parts.append("DİLİMLER:")
            for i, (val, label) in enumerate(zip(values, labels)):
                color = colors[i % len(colors)] if colors else 'renkli'
                prompt_parts.append(f"  - {label}: %{val} ({color})")
            
            prompt_parts.append("")
            prompt_parts.append("STİL:")
            prompt_parts.append("- Her dilimin içine etiket yaz")
            prompt_parts.append("- Yüzdeleri göster")
            prompt_parts.append("- Renkler: " + ", ".join(colors))
            if visual_style.get('is_3d'):
                prompt_parts.append("- 3D perspektif kullan")
        
        elif q_type == 'sütun_grafik':
            values = visual_data.get('values', [])
            labels = visual_data.get('labels', [])
            title = visual_data.get('title', '')
            
            prompt_parts.append("")
            prompt_parts.append("ŞEKİL: Sütun Grafiği (Bar Chart)")
            if title:
                prompt_parts.append(f"BAŞLIK: {title}")
            prompt_parts.append("SÜTUNLAR:")
            for val, label in zip(values, labels):
                prompt_parts.append(f"  - {label}: {val}")
            prompt_parts.append("")
            prompt_parts.append("- X ekseni: Kategoriler")
            prompt_parts.append("- Y ekseni: Değerler (sayı göster)")
        
        elif q_type in ['üçgen', 'triangle']:
            points = visual_data.get('points', ['A', 'B', 'C'])
            edges = visual_data.get('edges', [])
            angles = visual_data.get('angles', [])
            
            prompt_parts.append("")
            prompt_parts.append("ŞEKİL: Üçgen")
            prompt_parts.append(f"KÖŞELER: {', '.join(points)}")
            if edges:
                prompt_parts.append("KENARLAR:")
                for e in edges:
                    prompt_parts.append(f"  - {e.get('from', '')}{e.get('to', '')}: {e.get('value', '')} cm")
            if angles:
                prompt_parts.append("AÇILAR:")
                for a in angles:
                    prompt_parts.append(f"  - {a.get('vertex', '')}: {a.get('value', '')}°")
        
        elif q_type in ['dörtgen', 'kare', 'dikdörtgen']:
            points = visual_data.get('points', ['A', 'B', 'C', 'D'])
            edges = visual_data.get('edges', [])
            
            prompt_parts.append("")
            prompt_parts.append(f"ŞEKİL: {q_type.title()}")
            prompt_parts.append(f"KÖŞELER: {', '.join(points)}")
            if edges:
                prompt_parts.append("KENARLAR:")
                for e in edges:
                    prompt_parts.append(f"  - {e.get('label', '')}: {e.get('value', '')} cm")
        
        elif q_type in ['daire', 'çember']:
            center = visual_data.get('center', 'O')
            radius = visual_data.get('radius', 'r')
            
            prompt_parts.append("")
            prompt_parts.append("ŞEKİL: Çember")
            prompt_parts.append(f"MERKEZ: {center}")
            prompt_parts.append(f"YARIÇAP: r = {radius}")
        
        # Genel hatırlatma
        prompt_parts.append("")
        prompt_parts.append("HATIRLATMA: Soru metni veya açıklama YAZMA, sadece şekil!")
        
        return "\n".join(prompt_parts)
    
    def generate(self, visual_data: Dict, visual_style: Dict) -> Optional[bytes]:
        """Görsel üret"""
        try:
            self._rate_limit()
            
            prompt = self._build_prompt(visual_data, visual_style)
            logger.info(f"🎨 Görsel üretiliyor: {visual_data.get('type', 'unknown')}")
            
            if NEW_GENAI:
                response = self.client.models.generate_content(
                    model=Config.GEMINI_IMAGE,
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
                                logger.info(f"✅ Görsel üretildi ({len(image_bytes)} bytes)")
                                return image_bytes
                
                logger.warning("Görsel response'da bulunamadı")
                return None
            else:
                logger.warning("Eski API ile görsel üretimi desteklenmiyor")
                return None
                
        except Exception as e:
            logger.error(f"Görsel üretim hatası: {e}")
            return None


class QuestionCloneBot:
    """Ana bot - tüm bileşenleri koordine eder"""
    
    def __init__(self):
        logger.info("=" * 60)
        logger.info("Question Clone Bot v1.0")
        logger.info("Fotoğraftan Benzer Soru Üretici")
        logger.info("=" * 60)
        
        self.supabase = SupabaseManager()
        self.vision = VisionAnalyzer(Config.GEMINI_API_KEY)
        self.generator = QuestionGenerator(Config.GEMINI_API_KEY)
        self.image_gen = ImageGenerator(Config.GEMINI_API_KEY)
        
        self.stats = {
            'templates_processed': 0,
            'questions_generated': 0,
            'images_created': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
    
    def run(self):
        """Ana çalışma döngüsü"""
        logger.info("Bot başlatılıyor...")
        
        # Şablon soruları getir
        templates = self.supabase.get_template_questions(Config.BATCH_SIZE)
        
        if not templates:
            logger.info("İşlenecek şablon soru yok")
            return
        
        logger.info(f"{len(templates)} şablon soru işlenecek")
        
        for i, template in enumerate(templates, 1):
            logger.info(f"\n{'='*40}")
            logger.info(f"Şablon {i}/{len(templates)}: {template.get('id')}")
            logger.info(f"{'='*40}")
            
            self._process_template(template)
            
            # Şablonlar arası bekleme
            if i < len(templates):
                logger.info("⏳ Sonraki şablon için 10s bekleniyor...")
                time.sleep(10)
        
        # Sonuç raporu
        elapsed = datetime.now() - self.stats['start_time']
        logger.info("\n" + "=" * 60)
        logger.info("TAMAMLANDI")
        logger.info(f"Süre: {elapsed}")
        logger.info(f"Şablonlar: {self.stats['templates_processed']}")
        logger.info(f"Üretilen Sorular: {self.stats['questions_generated']}")
        logger.info(f"Üretilen Görseller: {self.stats['images_created']}")
        logger.info(f"Hatalar: {self.stats['errors']}")
        logger.info("=" * 60)
    
    def _process_template(self, template: Dict):
        """Tek bir şablonu işle - kazanım bazlı"""
        template_id = template.get('id')
        image_url = template.get('image_url')
        kazanim_id = template.get('kazanim_id')
        kazanim_info = template.get('kazanim_info', {})
        
        if not image_url:
            logger.warning(f"[{template_id}] Görsel URL'si yok")
            return
        
        if not kazanim_info:
            logger.warning(f"[{template_id}] Kazanım bilgisi bulunamadı (kazanim_id: {kazanim_id})")
            return
        
        logger.info(f"[{template_id}] 📚 Kazanım: {kazanim_info.get('code')} - {kazanim_info.get('description', '')[:50]}...")
        
        try:
            # 1. Görseli indir
            logger.info(f"[{template_id}] 📥 Görsel indiriliyor...")
            image_bytes = self.supabase.download_image(image_url)
            
            if not image_bytes:
                logger.error(f"[{template_id}] Görsel indirilemedi")
                self.stats['errors'] += 1
                return
            
            # 2. Görseli analiz et
            logger.info(f"[{template_id}] 🔍 Görsel analiz ediliyor...")
            analysis = self.vision.analyze_image(image_bytes)
            
            if not analysis:
                logger.error(f"[{template_id}] Analiz başarısız")
                self.stats['errors'] += 1
                return
            
            logger.info(f"[{template_id}] ✅ Analiz: tip={analysis.get('question_type')}")
            
            # 3. Varyasyonlar üret
            variations_created = 0
            
            for v in range(Config.VARIATIONS_PER_TEMPLATE):
                logger.info(f"[{template_id}] 📝 Varyasyon {v+1}/{Config.VARIATIONS_PER_TEMPLATE} üretiliyor...")
                
                # Zorluk seviyesi varyasyonu
                difficulty = Config.DIFFICULTY_LEVELS[v % len(Config.DIFFICULTY_LEVELS)]
                
                # Yeni soru üret (kazanım bilgisiyle)
                new_question = self.generator.generate_variation(
                    analysis=analysis,
                    kazanim_info=kazanim_info,
                    difficulty=difficulty
                )
                
                if not new_question:
                    logger.warning(f"[{template_id}] Varyasyon {v+1} üretilemedi")
                    continue
                
                logger.info(f"[{template_id}] ✅ Soru üretildi: {new_question.get('question_text', '')[:50]}...")
                
                # 4. Görsel üret
                visual_data = new_question.get('visual_data', {})
                visual_style = analysis.get('visual_style', {})
                
                image_bytes_new = self.image_gen.generate(visual_data, visual_style)
                
                image_url_new = None
                if image_bytes_new:
                    filename = f"cloned_{kazanim_info.get('code', 'unknown')}_{template_id}_{v+1}_{int(time.time())}.png"
                    image_url_new = self.supabase.upload_image(image_bytes_new, filename)
                    if image_url_new:
                        self.stats['images_created'] += 1
                        logger.info(f"[{template_id}] 🖼️ Görsel yüklendi")
                
                # 5. Veritabanına kaydet (question_bank yapısına uygun)
                question_data = {
                    'question_text': new_question.get('question_text', ''),
                    'kazanim_id': kazanim_info.get('id'),  # INTEGER
                    'topic': kazanim_info.get('topic'),  # topic_name
                    'topic_group': kazanim_info.get('topic'),  # topic_name
                    'grade_level': kazanim_info.get('grade_level', 8),
                    'difficulty': difficulty,  # easy/medium/hard -> 1-5'e çevrilecek
                    'question_type': 'çoktan_seçmeli',
                    'image_url': image_url_new,
                    'answer': new_question.get('answer'),  # correct_answer olacak
                    'options': new_question.get('options', {}),  # JSONB
                    'solution': new_question.get('solution'),  # solution_text + solution_detailed
                    'template_id': template_id
                }
                
                saved_id = self.supabase.save_generated_question(question_data)
                
                if saved_id:
                    variations_created += 1
                    self.stats['questions_generated'] += 1
                    logger.info(f"[{template_id}] 💾 Soru kaydedildi: {saved_id}")
                    logger.info(f"    📚 Kazanım: {kazanim_info.get('code')}")
                    logger.info(f"    📖 Konu: {kazanim_info.get('topic')} > {kazanim_info.get('subtopic')}")
                
                # Varyasyonlar arası bekleme
                time.sleep(5)
            
            # Şablonu işlendi olarak işaretle
            self.supabase.mark_template_processed(template_id, variations_created)
            self.stats['templates_processed'] += 1
            
            logger.info(f"[{template_id}] ✅ Tamamlandı: {variations_created} varyasyon üretildi")
            
        except Exception as e:
            logger.error(f"[{template_id}] Hata: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1


# Veritabanı şeması için SQL
CREATE_TABLES_SQL = """
-- ============================================
-- QUESTION TEMPLATES TABLOSU
-- ============================================
-- Sadece image_url ve kazanim_id gerekli!

CREATE TABLE IF NOT EXISTS question_templates (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    image_url TEXT NOT NULL,                        -- Beğenilen soru fotoğrafı
    kazanim_id INTEGER REFERENCES curriculum(id),   -- curriculum.id (INTEGER)
    processed BOOLEAN DEFAULT FALSE,
    variations_created INTEGER DEFAULT 0,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_templates_processed ON question_templates(processed);
CREATE INDEX IF NOT EXISTS idx_templates_kazanim ON question_templates(kazanim_id);

-- ============================================
-- SENİN TABLOLARIN (Zaten mevcut)
-- ============================================

-- curriculum tablosu:
-- id: INTEGER (931 gibi)
-- topic_name: TEXT ('Veri Analizi')
-- sub_topic: TEXT ('Verileri sütun, daire veya çizgi grafiği ile gösterir...')
-- grade_level: INTEGER (8)
-- category: TEXT ('LGS')

-- question_bank tablosu:
-- id: BIGSERIAL
-- original_text: TEXT (soru metni)
-- options: JSONB ({"A": "...", "B": "...", "C": "...", "D": "..."})
-- correct_answer: TEXT ("A", "B", "C" veya "D")
-- solution_text: TEXT
-- solution_detailed: TEXT
-- difficulty: INTEGER (1-5)
-- grade_level: INTEGER
-- topic: TEXT
-- topic_group: TEXT
-- kazanim_id: INTEGER
-- image_url: TEXT
-- question_type: TEXT ('çoktan_seçmeli')
-- is_active: BOOLEAN
-- verified: BOOLEAN
-- title: TEXT

-- ============================================
-- ÖRNEK KULLANIM
-- ============================================

-- 1. Fotoğrafı storage'a yükle
-- 2. Curriculum'dan kazanım ID'sini bul:
--    SELECT id, topic_name, sub_topic FROM curriculum 
--    WHERE topic_name = 'Veri Analizi' AND grade_level = 8;
--    -> id: 931

-- 3. Template ekle:
INSERT INTO question_templates (image_url, kazanim_id)
VALUES (
    'https://xxx.supabase.co/storage/v1/object/public/question-templates/pasta_grafik.png',
    931
);

-- Bot otomatik olarak:
-- ✅ Fotoğrafı analiz eder
-- ✅ curriculum'dan bilgileri çeker (topic_name, sub_topic, grade_level)
-- ✅ 3 benzer soru üretir (easy=2, medium=3, hard=4 zorluk)
-- ✅ Görselleri Gemini ile çizer
-- ✅ question_bank'a kaydeder:
--    - original_text: Yeni soru metni
--    - options: {"A": "...", "B": "...", "C": "...", "D": "..."}
--    - correct_answer: "C"
--    - solution_text: Çözüm
--    - difficulty: 2/3/4
--    - topic: 'Veri Analizi'
--    - topic_group: 'Veri Analizi'
--    - kazanim_id: 931
--    - image_url: Üretilen görsel URL
--    - question_type: 'çoktan_seçmeli'
"""


if __name__ == "__main__":
    print("\n📋 Veritabanı şeması için SQL:")
    print("-" * 40)
    print(CREATE_TABLES_SQL)
    print("-" * 40)
    print("\nBot'u çalıştırmak için önce tabloları oluşturun.\n")
    
    QuestionCloneBot().run()
