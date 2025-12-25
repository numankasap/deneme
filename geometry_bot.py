#!/usr/bin/env python3
"""
Geometry Bot v4.0 - Hibrit Görselleştirme Sistemi
=================================================
Cairo tabanlı programatik çizim + Gemini AI Image Generation
GitHub Actions uyumlu

Yeni Özellikler:
- Gemini 2.5 Flash Image: Hızlı, yüksek hacimli geometri görselleri
- Gemini 3 Pro Image Preview: Yüksek kaliteli, karmaşık görseller
- Akıllı model seçimi: Soru karmaşıklığına göre otomatik seçim
- Fallback mekanizması: AI başarısız olursa Cairo'ya düş
"""

import os
import io
import json
import math
import time
import base64
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import cairo
import numpy as np
from supabase import create_client, Client

try:
    from google import genai
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
    
    # Analiz modeli (metin tabanlı)
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-exp')
    
    # Görsel üretim modelleri
    GEMINI_IMAGE_FLASH = 'gemini-2.5-flash-preview-05-20'  # Hızlı, yüksek hacim
    GEMINI_IMAGE_PRO = 'gemini-2.0-flash-exp-image-generation'  # Yüksek kalite (Pro henüz mevcut değilse flash kullan)
    
    # Görsel üretim stratejisi: 'cairo_only', 'ai_only', 'hybrid', 'ai_first'
    IMAGE_STRATEGY = os.environ.get('IMAGE_STRATEGY', 'hybrid')
    
    STORAGE_BUCKET = 'questions-images'
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '10'))
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    IMAGE_WIDTH = 900
    IMAGE_HEIGHT = 750


class Colors:
    PRIMARY = (0.10, 0.46, 0.82)
    SECONDARY = (0.83, 0.18, 0.18)
    TERTIARY = (0.30, 0.69, 0.31)
    
    POINT_COLORS = [
        (1.00, 0.34, 0.13), (0.30, 0.69, 0.31), (0.13, 0.59, 0.95),
        (0.61, 0.15, 0.69), (0.00, 0.74, 0.83), (1.00, 0.76, 0.03),
    ]
    
    PIE_COLORS = [
        ((0.90, 0.22, 0.20), (0.62, 0.14, 0.12)),
        ((0.18, 0.75, 0.93), (0.10, 0.50, 0.65)),
        ((0.55, 0.85, 0.22), (0.36, 0.58, 0.12)),
        ((0.95, 0.75, 0.12), (0.70, 0.52, 0.06)),
        ((0.68, 0.35, 0.85), (0.45, 0.22, 0.58)),
        ((0.95, 0.52, 0.22), (0.68, 0.35, 0.12)),
    ]
    
    BAR_COLORS = [(0.16, 0.50, 0.73), (0.20, 0.60, 0.86), (0.36, 0.68, 0.89)]
    FILL_LIGHT = (0.13, 0.59, 0.95, 0.15)
    WHITE = (1, 1, 1)
    GRID_DARK = (0.22, 0.25, 0.29)
    GRID_LIGHT = (0.85, 0.85, 0.85)
    HEIGHT_COLOR = (0.83, 0.18, 0.18)
    MEDIAN_COLOR = (0.61, 0.15, 0.69)
    BISECTOR_COLOR = (0.30, 0.69, 0.31)
    
    @classmethod
    def get_point_color(cls, i): return cls.POINT_COLORS[i % len(cls.POINT_COLORS)]
    @classmethod
    def get_pie_colors(cls, i): return cls.PIE_COLORS[i % len(cls.PIE_COLORS)]
    @classmethod
    def get_bar_color(cls, i): return cls.BAR_COLORS[i % len(cls.BAR_COLORS)]


# ═══════════════════════════════════════════════════════════════
# GEMINI AI IMAGE GENERATOR
# ═══════════════════════════════════════════════════════════════

class GeminiImageGenerator:
    """Gemini AI ile görsel üretim"""
    
    # Karmaşıklık eşikleri
    COMPLEXITY_THRESHOLDS = {
        'simple': ['triangle', 'rectangle', 'square', 'circle'],
        'medium': ['quadrilateral', 'polygon', 'parallelogram', 'trapezoid'],
        'complex': ['cube', 'pyramid', 'cylinder', 'cone', 'sphere', 'prism', 
                   'inscribed_circle', 'circumscribed', 'coordinate_plane']
    }
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        if NEW_GENAI:
            self.client = genai.Client(api_key=api_key)
        else:
            genai.configure(api_key=api_key)
        self.request_count = 0
        self.last_request_time = 0
        logger.info("GeminiImageGenerator başlatıldı")
    
    def _rate_limit(self, requests_per_minute: int = 5):
        """Rate limiting for image generation (daha düşük limit)"""
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= requests_per_minute:
            wait_time = 60 - (current_time - self.last_request_time) + 5
            if wait_time > 0:
                logger.info(f"⏳ Image Gen Rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        
        self.request_count += 1
    
    def _determine_complexity(self, analysis: Dict) -> str:
        """Soru karmaşıklığını belirle"""
        shape_type = analysis.get('shape_type', '')
        
        # Karmaşıklık faktörleri
        factors = 0
        
        # İç içe şekiller
        if analysis.get('inscribed_circle') or analysis.get('circumscribed_circle'):
            factors += 2
        
        # Çoklu daireler
        if len(analysis.get('circles', [])) > 1:
            factors += 1
        
        # Özel çizgiler (yükseklik, kenarortay, açıortay)
        if analysis.get('special_lines'):
            factors += len(analysis.get('special_lines', []))
        
        # Açı işaretleri
        if analysis.get('angles'):
            factors += 1
        
        # 3D şekiller
        if shape_type in self.COMPLEXITY_THRESHOLDS['complex']:
            factors += 3
        
        # Koordinat düzlemi
        if analysis.get('coordinate_plane') or analysis.get('show_grid'):
            factors += 1
        
        if factors >= 4:
            return 'complex'
        elif factors >= 2:
            return 'medium'
        return 'simple'
    
    def _select_model(self, complexity: str) -> str:
        """Karmaşıklığa göre model seç"""
        if complexity == 'complex':
            logger.info(f"🎨 Model: Pro (karmaşık şekil)")
            return Config.GEMINI_IMAGE_PRO
        else:
            logger.info(f"🎨 Model: Flash (basit/orta şekil)")
            return Config.GEMINI_IMAGE_FLASH
    
    def _build_image_prompt(self, analysis: Dict, question_text: str = "") -> str:
        """Görsel üretimi için prompt oluştur"""
        shape_type = analysis.get('shape_type', 'geometry')
        
        # Temel prompt
        prompt_parts = [
            "Matematiksel bir geometri görseli oluştur.",
            "Stil: Temiz, profesyonel, eğitim amaçlı.",
            "Arka plan: Beyaz.",
            "Çizgiler: Net, kalın, koyu mavi veya siyah.",
            "Etiketler: Büyük harflerle köşe noktaları (A, B, C, D...).",
            "Ölçüler: Varsa kenar uzunlukları ve açılar gösterilmeli.",
            "",
        ]
        
        # Şekil tipine göre özel talimatlar
        if shape_type == 'triangle':
            points = analysis.get('points', [])
            edges = analysis.get('edges', [])
            angles = analysis.get('angles', [])
            
            prompt_parts.append("Bir üçgen çiz.")
            if points:
                prompt_parts.append(f"Köşe noktaları: {', '.join([p['name'] for p in points])}")
            if edges:
                for e in edges:
                    prompt_parts.append(f"Kenar {e.get('start')}{e.get('end')}: {e.get('label', '')}")
            if angles:
                for a in angles:
                    if a.get('is_right'):
                        prompt_parts.append(f"{a.get('vertex')} köşesinde dik açı işareti göster.")
                    elif a.get('value'):
                        prompt_parts.append(f"{a.get('vertex')} açısı: {a.get('value')}")
            
            # Özel çizgiler
            special_lines = analysis.get('special_lines', [])
            for sl in special_lines:
                if sl['type'] == 'height':
                    prompt_parts.append(f"{sl.get('from')} köşesinden karşı kenara yükseklik çiz (kesikli çizgi).")
                elif sl['type'] == 'median':
                    prompt_parts.append(f"{sl.get('from')} köşesinden karşı kenarın ortasına kenarortay çiz.")
                elif sl['type'] == 'bisector':
                    prompt_parts.append(f"{sl.get('from')} açısının açıortayını çiz.")
        
        elif shape_type in ['rectangle', 'square', 'quadrilateral']:
            points = analysis.get('points', [])
            edges = analysis.get('edges', [])
            
            if shape_type == 'square':
                prompt_parts.append("Bir kare çiz.")
            elif shape_type == 'rectangle':
                prompt_parts.append("Bir dikdörtgen çiz.")
            else:
                prompt_parts.append("Bir dörtgen çiz.")
            
            if points:
                prompt_parts.append(f"Köşe noktaları saat yönünde: {', '.join([p['name'] for p in points])}")
            if edges:
                for e in edges:
                    prompt_parts.append(f"Kenar {e.get('start')}{e.get('end')}: {e.get('label', '')}")
            
            # İç teğet daire
            inscribed = analysis.get('inscribed_circle', {})
            if inscribed:
                prompt_parts.append(f"İçine teğet bir daire çiz, yarıçap: {inscribed.get('label', '')}")
        
        elif shape_type == 'circle':
            center = analysis.get('center', {})
            radius = analysis.get('radius', 4)
            
            prompt_parts.append("Bir çember çiz.")
            prompt_parts.append(f"Merkez noktası: {center.get('name', 'O')}")
            prompt_parts.append(f"Yarıçap: {radius}")
            prompt_parts.append("Merkez noktasını işaretle ve r= etiketiyle yarıçapı göster.")
            
            # Ek noktalar
            for p in analysis.get('points', []):
                prompt_parts.append(f"Çember üzerinde {p['name']} noktasını işaretle.")
        
        elif shape_type in ['cube', 'rectangular_prism', 'prism']:
            dims = analysis.get('dimensions', {})
            prompt_parts.append("3 boyutlu bir küp/prizma çiz (izometrik görünüm).")
            if dims.get('size'):
                prompt_parts.append(f"Kenar uzunluğu: {dims['size']} cm")
            if dims.get('width') and dims.get('height') and dims.get('depth'):
                prompt_parts.append(f"Boyutlar: {dims['width']}x{dims['height']}x{dims['depth']}")
            prompt_parts.append("Köşeleri A, B, C, D (alt) ve E, F, G, H (üst) olarak etiketle.")
            prompt_parts.append("Gizli kenarları kesikli çizgiyle göster.")
        
        elif shape_type == 'pyramid':
            dims = analysis.get('dimensions', {})
            prompt_parts.append("3 boyutlu bir piramit çiz.")
            prompt_parts.append(f"Taban kenarı: {dims.get('base_size', 4)} cm")
            prompt_parts.append(f"Yükseklik: {dims.get('height', 5)} cm")
            prompt_parts.append("Tepe noktasını T olarak etiketle.")
            prompt_parts.append("Yüksekliği kesikli çizgiyle göster.")
        
        elif shape_type == 'cylinder':
            dims = analysis.get('dimensions', {})
            prompt_parts.append("3 boyutlu bir silindir çiz.")
            prompt_parts.append(f"Yarıçap: {dims.get('radius', 3)} cm")
            prompt_parts.append(f"Yükseklik: {dims.get('height', 6)} cm")
        
        elif shape_type == 'cone':
            dims = analysis.get('dimensions', {})
            prompt_parts.append("3 boyutlu bir koni çiz.")
            prompt_parts.append(f"Taban yarıçapı: {dims.get('radius', 3)} cm")
            prompt_parts.append(f"Yükseklik: {dims.get('height', 5)} cm")
            prompt_parts.append("Tepe noktasını T olarak etiketle.")
        
        elif shape_type == 'sphere':
            dims = analysis.get('dimensions', {})
            prompt_parts.append("3 boyutlu bir küre çiz.")
            prompt_parts.append(f"Yarıçap: {dims.get('radius', 4)} cm")
            prompt_parts.append("Merkez noktasını O olarak işaretle.")
        
        elif shape_type == 'pie_chart':
            pie_data = analysis.get('pie_data', {})
            values = pie_data.get('values', [])
            labels = pie_data.get('labels', [])
            prompt_parts.append("3 boyutlu pasta grafiği çiz.")
            for i, (v, l) in enumerate(zip(values, labels)):
                prompt_parts.append(f"{l}: {v}%")
            prompt_parts.append("Her dilimi farklı renkle göster ve yüzdeleri etiketle.")
        
        elif shape_type == 'bar_chart':
            bar_data = analysis.get('bar_data', {})
            values = bar_data.get('values', [])
            labels = bar_data.get('labels', [])
            prompt_parts.append("Sütun grafiği çiz.")
            for v, l in zip(values, labels):
                prompt_parts.append(f"{l}: {v}")
        
        # Orijinal soru metni (bağlam için)
        if question_text:
            prompt_parts.append("")
            prompt_parts.append(f"Orijinal soru: {question_text[:200]}")
        
        return "\n".join(prompt_parts)
    
    def generate(self, analysis: Dict, question_text: str = "", max_retries: int = 2) -> Optional[bytes]:
        """AI ile görsel üret"""
        try:
            complexity = self._determine_complexity(analysis)
            model_id = self._select_model(complexity)
            prompt = self._build_image_prompt(analysis, question_text)
            
            logger.info(f"🎨 AI Image Generation başlıyor...")
            logger.debug(f"Prompt: {prompt[:200]}...")
            
            for attempt in range(max_retries):
                try:
                    self._rate_limit(requests_per_minute=5)
                    
                    if NEW_GENAI:
                        # Yeni API ile görsel üretimi
                        response = self.client.models.generate_content(
                            model=model_id,
                            contents=prompt,
                            config={
                                "response_modalities": ["IMAGE", "TEXT"],
                                "response_mime_type": "image/png"
                            }
                        )
                        
                        # Response'dan görsel çıkar
                        if response.candidates:
                            for part in response.candidates[0].content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    image_data = part.inline_data.data
                                    if isinstance(image_data, str):
                                        image_bytes = base64.b64decode(image_data)
                                    else:
                                        image_bytes = image_data
                                    logger.info(f"✅ AI görsel üretildi ({len(image_bytes)} bytes)")
                                    return image_bytes
                        
                        logger.warning("AI yanıtında görsel bulunamadı")
                        return None
                    else:
                        # Eski API - görsel üretimi sınırlı olabilir
                        model = genai.GenerativeModel(model_id)
                        response = model.generate_content(prompt)
                        
                        # Eski API genellikle metin döndürür, görsel için özel handling gerekebilir
                        logger.warning("Eski Gemini API ile görsel üretimi sınırlı")
                        return None
                        
                except Exception as e:
                    error_str = str(e)
                    if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                        wait_time = 60 + (attempt * 15)
                        logger.warning(f"⚠️ Rate limit. {wait_time}s bekleniyor... ({attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    elif 'not supported' in error_str.lower() or 'invalid' in error_str.lower():
                        logger.warning(f"Model görsel üretimi desteklemiyor: {model_id}")
                        return None
                    else:
                        logger.error(f"AI Image Generation hatası: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(5)
                        else:
                            return None
            
            return None
            
        except Exception as e:
            logger.error(f"GeminiImageGenerator.generate hatası: {e}")
            return None


# ═══════════════════════════════════════════════════════════════
# CAIRO RENDERER (Mevcut kod - değişiklik yok)
# ═══════════════════════════════════════════════════════════════

class CairoRenderer:
    def __init__(self, width=900, height=750):
        self.width = width
        self.height = height
        self.surface = None
        self.ctx = None
        self.scale = 50
        self.origin = (width // 2, height // 2)
        self.points = {}
    
    def setup(self, bounds=None, padding=80):
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        self.ctx = cairo.Context(self.surface)
        self.ctx.set_antialias(cairo.ANTIALIAS_BEST)
        self.ctx.set_source_rgb(*Colors.WHITE)
        self.ctx.paint()
        if bounds:
            x_min, x_max = bounds.get('x_min', -10), bounds.get('x_max', 10)
            y_min, y_max = bounds.get('y_min', -10), bounds.get('y_max', 10)
            self.scale = min((self.width - 2*padding) / max(x_max - x_min, 0.1),
                           (self.height - 2*padding) / max(y_max - y_min, 0.1))
            self.origin = (self.width/2 - (x_min + x_max)/2 * self.scale,
                          self.height/2 + (y_min + y_max)/2 * self.scale)
    
    def to_px(self, x, y):
        return (self.origin[0] + x * self.scale, self.origin[1] - y * self.scale)
    
    def add_point(self, name, x, y):
        self.points[name] = (x, y)
    
    def draw_line(self, p1, p2, color=None, width=2.5):
        color = color or Colors.PRIMARY
        self.ctx.set_source_rgb(*color[:3])
        self.ctx.set_line_width(width)
        self.ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        px1, py1 = self.to_px(*p1)
        px2, py2 = self.to_px(*p2)
        self.ctx.move_to(px1, py1)
        self.ctx.line_to(px2, py2)
        self.ctx.stroke()
    
    def draw_polygon(self, points, fill_color=None, stroke_color=None, stroke_width=3):
        if not points: return
        px, py = self.to_px(*points[0])
        self.ctx.move_to(px, py)
        for p in points[1:]:
            px, py = self.to_px(*p)
            self.ctx.line_to(px, py)
        self.ctx.close_path()
        if fill_color:
            if len(fill_color) == 4: self.ctx.set_source_rgba(*fill_color)
            else: self.ctx.set_source_rgb(*fill_color)
            if stroke_color: self.ctx.fill_preserve()
            else: self.ctx.fill()
        if stroke_color:
            self.ctx.set_source_rgb(*stroke_color[:3])
            self.ctx.set_line_width(stroke_width)
            self.ctx.set_line_join(cairo.LINE_JOIN_ROUND)
            self.ctx.stroke()
    
    def draw_circle(self, center, radius, fill_color=None, stroke_color=None, stroke_width=3):
        cx, cy = self.to_px(*center)
        self.ctx.arc(cx, cy, radius * self.scale, 0, 2 * math.pi)
        if fill_color:
            if len(fill_color) == 4: self.ctx.set_source_rgba(*fill_color)
            else: self.ctx.set_source_rgb(*fill_color)
            if stroke_color: self.ctx.fill_preserve()
            else: self.ctx.fill()
        if stroke_color:
            self.ctx.set_source_rgb(*stroke_color[:3])
            self.ctx.set_line_width(stroke_width)
            self.ctx.stroke()
    
    def draw_point(self, pos, color, radius=10):
        px, py = self.to_px(*pos)
        self.ctx.set_source_rgba(0, 0, 0, 0.25)
        self.ctx.arc(px + 2, py + 2, radius, 0, 2 * math.pi)
        self.ctx.fill()
        self.ctx.set_source_rgb(*Colors.WHITE)
        self.ctx.arc(px, py, radius + 2, 0, 2 * math.pi)
        self.ctx.fill()
        self.ctx.set_source_rgb(*color[:3])
        self.ctx.arc(px, py, radius, 0, 2 * math.pi)
        self.ctx.fill()
    
    def draw_point_label(self, pos, name, color, position='auto', font_size=20):
        px, py = self.to_px(*pos)
        offsets = {'top': (0,-28), 'bottom': (0,32), 'left': (-28,0), 'right': (28,0),
                   'top_left': (-22,-22), 'top_right': (22,-22), 'bottom_left': (-22,26), 'bottom_right': (22,26)}
        if position == 'auto':
            position = 'top_right' if px > self.origin[0] else 'top_left'
        dx, dy = offsets.get(position, (0,-28))
        self.ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        self.ctx.set_font_size(font_size)
        self.ctx.set_source_rgb(*color[:3])
        ext = self.ctx.text_extents(name)
        self.ctx.move_to(px + dx - ext.width/2, py + dy + ext.height/2)
        self.ctx.show_text(name)
    
    def draw_label(self, pos, text, color=None, font_size=16, offset=(0,0)):
        color = color or Colors.PRIMARY
        px, py = self.to_px(*pos)
        px += offset[0]
        py += offset[1]
        self.ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        self.ctx.set_font_size(font_size)
        ext = self.ctx.text_extents(text)
        pad = 8
        self._rounded_rect(px - ext.width/2 - pad, py - ext.height/2 - pad, ext.width + 2*pad, ext.height + 2*pad, 5)
        self.ctx.set_source_rgb(*Colors.WHITE)
        self.ctx.fill()
        self._rounded_rect(px - ext.width/2 - pad, py - ext.height/2 - pad, ext.width + 2*pad, ext.height + 2*pad, 5)
        self.ctx.set_source_rgb(*color[:3])
        self.ctx.set_line_width(2)
        self.ctx.stroke()
        self.ctx.move_to(px - ext.width/2, py + ext.height/2 - 2)
        self.ctx.show_text(text)
    
    def _rounded_rect(self, x, y, w, h, r):
        r = min(r, w/2, h/2)
        self.ctx.new_path()
        self.ctx.arc(x+r, y+r, r, math.pi, 1.5*math.pi)
        self.ctx.arc(x+w-r, y+r, r, 1.5*math.pi, 2*math.pi)
        self.ctx.arc(x+w-r, y+h-r, r, 0, 0.5*math.pi)
        self.ctx.arc(x+r, y+h-r, r, 0.5*math.pi, math.pi)
        self.ctx.close_path()
    
    def draw_right_angle(self, vertex, p1, p2, size=0.5, color=None):
        color = color or Colors.SECONDARY
        v = np.array(vertex)
        v1 = np.array(p1) - v
        v2 = np.array(p2) - v
        len1, len2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if len1 < 0.001 or len2 < 0.001: return
        v1, v2 = v1/len1*size, v2/len2*size
        c1, c2, cm = v + v1, v + v2, v + v1 + v2
        self.ctx.set_source_rgb(*color[:3])
        self.ctx.set_line_width(2)
        px1, py1 = self.to_px(*c1)
        px2, py2 = self.to_px(*cm)
        px3, py3 = self.to_px(*c2)
        self.ctx.move_to(px1, py1)
        self.ctx.line_to(px2, py2)
        self.ctx.line_to(px3, py3)
        self.ctx.stroke()
    
    def draw_angle_arc(self, vertex, p1, p2, radius=0.6, color=None, label=None, fill=False):
        color = color or Colors.SECONDARY
        v1 = np.array(p1) - np.array(vertex)
        v2 = np.array(p2) - np.array(vertex)
        a1 = math.atan2(v1[1], v1[0])
        a2 = math.atan2(v2[1], v2[0])
        if a2 - a1 > math.pi: a1 += 2*math.pi
        elif a1 - a2 > math.pi: a2 += 2*math.pi
        if a1 > a2: a1, a2 = a2, a1
        vx, vy = self.to_px(*vertex)
        r_px = radius * self.scale
        if fill:
            self.ctx.move_to(vx, vy)
            self.ctx.arc(vx, vy, r_px, -a2, -a1)
            self.ctx.close_path()
            self.ctx.set_source_rgba(*color[:3], 0.2)
            self.ctx.fill()
        self.ctx.set_source_rgb(*color[:3])
        self.ctx.set_line_width(2)
        self.ctx.arc(vx, vy, r_px, -a2, -a1)
        self.ctx.stroke()
        if label:
            mid = (a1 + a2) / 2
            lx = vertex[0] + radius*1.8*math.cos(mid)
            ly = vertex[1] + radius*1.8*math.sin(mid)
            self.draw_label((lx, ly), label, color, font_size=14)
    
    def draw_altitude(self, triangle, from_vertex, color=None, label=None):
        color = color or Colors.HEIGHT_COLOR
        v = triangle[from_vertex]
        others = [triangle[i] for i in range(3) if i != from_vertex]
        edge = np.array(others[1]) - np.array(others[0])
        edge_len = np.linalg.norm(edge)
        if edge_len < 0.001: return None
        edge_unit = edge / edge_len
        proj = np.dot(np.array(v) - np.array(others[0]), edge_unit)
        foot = np.array(others[0]) + proj * edge_unit
        self.draw_line(v, tuple(foot), color, width=2.5)
        self.draw_right_angle(tuple(foot), v, others[1], size=0.4, color=color)
        self.draw_point(tuple(foot), color, radius=6)
        if label:
            mid = ((v[0] + foot[0])/2, (v[1] + foot[1])/2)
            self.draw_label(mid, label, color, offset=(22, 0))
        return tuple(foot)
    
    def draw_median(self, triangle, from_vertex, color=None, label=None):
        color = color or Colors.MEDIAN_COLOR
        v = triangle[from_vertex]
        others = [triangle[i] for i in range(3) if i != from_vertex]
        mid = ((others[0][0] + others[1][0])/2, (others[0][1] + others[1][1])/2)
        self.draw_line(v, mid, color, width=2.5)
        self.draw_point(mid, color, radius=6)
        if label:
            lp = ((v[0] + mid[0])/2, (v[1] + mid[1])/2)
            self.draw_label(lp, label, color, offset=(22, 0))
        return mid
    
    def draw_angle_bisector(self, triangle, from_vertex, color=None, label=None):
        color = color or Colors.BISECTOR_COLOR
        v = np.array(triangle[from_vertex])
        others = [np.array(triangle[i]) for i in range(3) if i != from_vertex]
        d1 = others[0] - v
        d2 = others[1] - v
        d1 = d1 / np.linalg.norm(d1)
        d2 = d2 / np.linalg.norm(d2)
        bisector = d1 + d2
        bisector = bisector / np.linalg.norm(bisector)
        edge = others[1] - others[0]
        denom = bisector[0]*edge[1] - bisector[1]*edge[0]
        if abs(denom) > 1e-10:
            diff = others[0] - v
            t = (diff[0]*edge[1] - diff[1]*edge[0]) / denom
            end = v + t * bisector
        else:
            end = v + bisector * 5
        self.draw_line(tuple(v), tuple(end), color, width=2.5)
        if label:
            mid = ((v[0] + end[0])/2, (v[1] + end[1])/2)
            self.draw_label(mid, label, color, offset=(22, 0))
        return tuple(end)
    
    def get_png_bytes(self):
        buf = io.BytesIO()
        self.surface.write_to_png(buf)
        return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# 3D RENDERER (Matplotlib)
# ═══════════════════════════════════════════════════════════════

class Cube3DRenderer:
    """3D Küp çizici - Matplotlib ile"""
    
    def __init__(self, width=900, height=750):
        self.width = width
        self.height = height
        self.dpi = 100
        self.fig = None
        self.ax = None
    
    def setup(self, elev=20, azim=45):
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d import Axes3D
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection
            
            self.plt = plt
            self.Poly3DCollection = Poly3DCollection
            
            self.fig = plt.figure(figsize=(self.width/self.dpi, self.height/self.dpi), dpi=self.dpi)
            self.ax = self.fig.add_subplot(111, projection='3d')
            self.ax.view_init(elev=elev, azim=azim)
            self.ax.set_box_aspect([1, 1, 1])
            return True
        except ImportError:
            logger.warning("Matplotlib 3D mevcut değil")
            return False
    
    def draw_cube(self, size=4, origin=(0, 0, 0), color='#3498db', alpha=0.8, edge_label=None):
        if not self.ax: return
        ox, oy, oz = origin
        s = size
        vertices = [
            [ox, oy, oz], [ox+s, oy, oz], [ox+s, oy+s, oz], [ox, oy+s, oz],
            [ox, oy, oz+s], [ox+s, oy, oz+s], [ox+s, oy+s, oz+s], [ox, oy+s, oz+s]
        ]
        faces = [
            [vertices[0], vertices[1], vertices[2], vertices[3]],
            [vertices[4], vertices[5], vertices[6], vertices[7]],
            [vertices[0], vertices[1], vertices[5], vertices[4]],
            [vertices[2], vertices[3], vertices[7], vertices[6]],
            [vertices[0], vertices[3], vertices[7], vertices[4]],
            [vertices[1], vertices[2], vertices[6], vertices[5]]
        ]
        self.ax.add_collection3d(self.Poly3DCollection(
            faces, facecolors=color, linewidths=1, edgecolors='#2c3e50', alpha=alpha
        ))
        labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        point_colors = [Colors.get_point_color(i) for i in range(8)]
        for i, (v, lbl) in enumerate(zip(vertices, labels)):
            self.ax.scatter(*v, color=point_colors[i], s=80, depthshade=False)
            self.ax.text(v[0], v[1], v[2] + 0.3, lbl, fontsize=12, fontweight='bold',
                        color=point_colors[i], ha='center')
        if edge_label:
            mid = [(vertices[0][i] + vertices[1][i]) / 2 for i in range(3)]
            self.ax.text(mid[0], mid[1] - 0.5, mid[2], edge_label,
                        fontsize=11, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        margin = s * 0.3
        self.ax.set_xlim([ox - margin, ox + s + margin])
        self.ax.set_ylim([oy - margin, oy + s + margin])
        self.ax.set_zlim([oz - margin, oz + s + margin])
        self._clean_axes()
    
    def draw_pyramid(self, base_size=4, height=5, origin=(0, 0, 0), color='#9b59b6', alpha=0.7, n_sides=4):
        if not self.ax: return
        ox, oy, oz = origin
        s = base_size / 2
        apex = [ox, oy, oz + height]
        if n_sides == 4:
            base = [[ox - s, oy - s, oz], [ox + s, oy - s, oz], [ox + s, oy + s, oz], [ox - s, oy + s, oz]]
            labels = ['A', 'B', 'C', 'D']
        else:
            base = [[ox, oy + s, oz], [ox - s * 0.866, oy - s * 0.5, oz], [ox + s * 0.866, oy - s * 0.5, oz]]
            labels = ['A', 'B', 'C']
        
        base_face = [base]
        self.ax.add_collection3d(self.Poly3DCollection(base_face, facecolors=color, linewidths=1, edgecolors='#2c3e50', alpha=alpha))
        for i in range(len(base)):
            face = [base[i], base[(i + 1) % len(base)], apex]
            self.ax.add_collection3d(self.Poly3DCollection([face], facecolors=color, linewidths=1, edgecolors='#2c3e50', alpha=alpha * 0.9))
        
        point_colors = [Colors.get_point_color(i) for i in range(len(base) + 1)]
        for i, (v, lbl) in enumerate(zip(base, labels)):
            self.ax.scatter(*v, color=point_colors[i], s=80)
            self.ax.text(v[0], v[1], v[2] - 0.4, lbl, fontsize=12, fontweight='bold', color=point_colors[i], ha='center')
        self.ax.scatter(*apex, color=point_colors[-1], s=80)
        self.ax.text(apex[0], apex[1], apex[2] + 0.3, 'T', fontsize=12, fontweight='bold', color=point_colors[-1], ha='center')
        self.ax.plot([ox, ox], [oy, oy], [oz, oz + height], 'k--', linewidth=1.5)
        self._set_limits(ox, oy, oz, max(base_size, height))
    
    def draw_cylinder(self, radius=2, height=4, origin=(0, 0, 0), color='#3498db', alpha=0.7):
        if not self.ax: return
        ox, oy, oz = origin
        u = np.linspace(0, 2 * np.pi, 50)
        h = np.linspace(0, height, 2)
        x = ox + radius * np.outer(np.cos(u), np.ones(len(h)))
        y = oy + radius * np.outer(np.sin(u), np.ones(len(h)))
        z = oz + np.outer(np.ones(len(u)), h)
        self.ax.plot_surface(x, y, z, color=color, alpha=alpha, linewidth=0)
        
        theta = np.linspace(0, 2 * np.pi, 50)
        r = np.linspace(0, radius, 10)
        T, R = np.meshgrid(theta, r)
        X = ox + R * np.cos(T)
        Y = oy + R * np.sin(T)
        Z_bottom = oz + np.zeros_like(X)
        Z_top = oz + height + np.zeros_like(X)
        self.ax.plot_surface(X, Y, Z_bottom, color=color, alpha=alpha)
        self.ax.plot_surface(X, Y, Z_top, color=color, alpha=alpha)
        self._set_limits(ox, oy, oz, max(radius*2, height))
    
    def draw_sphere(self, radius=3, origin=(0, 0, 0), color='#3498db', alpha=0.7):
        if not self.ax: return
        ox, oy, oz = origin
        u = np.linspace(0, 2 * np.pi, 50)
        v = np.linspace(0, np.pi, 50)
        x = ox + radius * np.outer(np.cos(u), np.sin(v))
        y = oy + radius * np.outer(np.sin(u), np.sin(v))
        z = oz + radius * np.outer(np.ones(np.size(u)), np.cos(v))
        self.ax.plot_surface(x, y, z, color=color, alpha=alpha, linewidth=0)
        self.ax.scatter(ox, oy, oz, color='red', s=50)
        self.ax.text(ox, oy, oz + 0.5, 'O', fontsize=12, fontweight='bold', color='red')
        self._set_limits(ox, oy, oz, radius * 2)
    
    def draw_cone(self, radius=2, height=4, origin=(0, 0, 0), color='#e74c3c', alpha=0.7):
        if not self.ax: return
        ox, oy, oz = origin
        u = np.linspace(0, 2 * np.pi, 50)
        h = np.linspace(0, height, 50)
        U, H = np.meshgrid(u, h)
        R = radius * (1 - H / height)
        X = ox + R * np.cos(U)
        Y = oy + R * np.sin(U)
        Z = oz + H
        self.ax.plot_surface(X, Y, Z, color=color, alpha=alpha, linewidth=0)
        
        theta = np.linspace(0, 2 * np.pi, 50)
        r = np.linspace(0, radius, 10)
        T, R_base = np.meshgrid(theta, r)
        X_base = ox + R_base * np.cos(T)
        Y_base = oy + R_base * np.sin(T)
        Z_base = oz + np.zeros_like(X_base)
        self.ax.plot_surface(X_base, Y_base, Z_base, color=color, alpha=alpha)
        self.ax.scatter(ox, oy, oz + height, color='darkred', s=80)
        self.ax.text(ox, oy, oz + height + 0.3, 'T', fontsize=12, fontweight='bold')
        self._set_limits(ox, oy, oz, max(radius*2, height))
    
    def _clean_axes(self):
        self.ax.set_xlabel('')
        self.ax.set_ylabel('')
        self.ax.set_zlabel('')
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.set_zticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self.ax.xaxis.pane.fill = False
        self.ax.yaxis.pane.fill = False
        self.ax.zaxis.pane.fill = False
    
    def _set_limits(self, ox, oy, oz, size):
        margin = size * 0.3
        self.ax.set_xlim([ox - size/2 - margin, ox + size/2 + margin])
        self.ax.set_ylim([oy - size/2 - margin, oy + size/2 + margin])
        self.ax.set_zlim([oz - margin, oz + size + margin])
        self._clean_axes()
    
    def get_png_bytes(self):
        if not self.fig: return None
        buf = io.BytesIO()
        self.fig.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        buf.seek(0)
        self.plt.close(self.fig)
        return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# PIE & BAR CHART RENDERERS
# ═══════════════════════════════════════════════════════════════

class Pie3DRenderer:
    def __init__(self, width=700, height=620):
        self.width = width
        self.height = height
        self.surface = None
        self.ctx = None
    
    def setup(self, bg_color=None):
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        self.ctx = cairo.Context(self.surface)
        self.ctx.set_antialias(cairo.ANTIALIAS_BEST)
        if bg_color:
            self.ctx.set_source_rgb(*bg_color)
            self.ctx.paint()
    
    def draw(self, values, labels=None, center=None, radius=None, depth=45, gap=8,
             explode=None, start_angle=-90, title=None, value_type='percent', show_legend=True):
        center = center or (self.width // 2, self.height // 2 - 10)
        radius = radius or min(self.width, self.height) * 0.30
        labels = labels or [f"Dilim {i+1}" for i in range(len(values))]
        explode = explode or [0] * len(values)
        total = sum(values)
        if total == 0: return
        
        slices = []
        current = start_angle
        for i, val in enumerate(values):
            sweep = (val / total) * 360
            slices.append({'index': i, 'start': current, 'sweep': sweep, 'value': val})
            current += sweep
        
        draw_order = sorted(slices, key=lambda s: -math.sin(math.radians(s['start'] + s['sweep']/2)))
        
        for s in draw_order:
            idx = s['index']
            top, side = Colors.get_pie_colors(idx)
            exp = explode[idx]
            mid_rad = math.radians(s['start'] + s['sweep'] / 2)
            ox = (gap + exp) * math.cos(mid_rad)
            oy = (gap + exp) * math.sin(mid_rad)
            sc = (center[0] + ox, center[1] + oy)
            
            start_rad = math.radians(s['start'])
            end_rad = math.radians(s['start'] + s['sweep'])
            
            self.ctx.move_to(*sc)
            self.ctx.arc(*sc, radius, start_rad, end_rad)
            self.ctx.close_path()
            self.ctx.set_source_rgb(*top)
            self.ctx.fill()
        
        if show_legend:
            self.ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            self.ctx.set_font_size(12)
            x = 20
            y = self.height - 38
            for i, (lbl, val) in enumerate(zip(labels, values)):
                top, _ = Colors.get_pie_colors(i)
                self.ctx.set_source_rgb(*top)
                self.ctx.rectangle(x, y, 16, 16)
                self.ctx.fill()
                self.ctx.set_source_rgb(*Colors.GRID_DARK)
                txt = f"{lbl}: %{(val/total)*100:.0f}"
                self.ctx.move_to(x + 22, y + 13)
                self.ctx.show_text(txt)
                x += 100
    
    def get_png_bytes(self):
        buf = io.BytesIO()
        self.surface.write_to_png(buf)
        return buf.getvalue()


class BarChartRenderer:
    def __init__(self, width=700, height=500):
        self.width = width
        self.height = height
        self.surface = None
        self.ctx = None
    
    def setup(self, bg_color=None):
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        self.ctx = cairo.Context(self.surface)
        self.ctx.set_antialias(cairo.ANTIALIAS_BEST)
        if bg_color:
            self.ctx.set_source_rgb(*bg_color)
            self.ctx.paint()
    
    def draw(self, values, labels, title=None, colors=None):
        colors = colors or [Colors.get_bar_color(i) for i in range(len(values))]
        padding = 60
        x = padding + 30
        y = padding + (40 if title else 0)
        w = self.width - x - padding
        h = self.height - y - padding - 30
        max_val = max(values) if values else 1
        n = len(values)
        bar_w = (w / n) * 0.6
        
        self.ctx.set_source_rgb(*Colors.GRID_DARK)
        self.ctx.set_line_width(2)
        self.ctx.move_to(x, y + h)
        self.ctx.line_to(x + w, y + h)
        self.ctx.stroke()
        
        for i, (val, lbl) in enumerate(zip(values, labels)):
            bar_h = (val / max_val) * (h - 20) if max_val > 0 else 0
            bx = x + i * (w / n) + (w / n - bar_w) / 2
            by = y + h - bar_h
            self.ctx.set_source_rgb(*colors[i % len(colors)])
            self._rounded_rect(bx, by, bar_w, bar_h, 4)
            self.ctx.fill()
            
            self.ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            self.ctx.set_font_size(12)
            self.ctx.set_source_rgb(*Colors.GRID_DARK)
            val_text = str(int(val)) if val == int(val) else f"{val:.1f}"
            ext = self.ctx.text_extents(val_text)
            self.ctx.move_to(bx + bar_w/2 - ext.width/2, by - 8)
            self.ctx.show_text(val_text)
            
            self.ctx.set_font_size(11)
            ext = self.ctx.text_extents(lbl)
            self.ctx.move_to(bx + bar_w/2 - ext.width/2, y + h + 20)
            self.ctx.show_text(lbl)
    
    def _rounded_rect(self, x, y, w, h, r):
        if h <= 0: return
        r = min(r, w/2, h/2)
        self.ctx.new_path()
        self.ctx.arc(x+r, y+r, r, math.pi, 1.5*math.pi)
        self.ctx.arc(x+w-r, y+r, r, 1.5*math.pi, 2*math.pi)
        self.ctx.arc(x+w-r, y+h-r, r, 0, 0.5*math.pi)
        self.ctx.arc(x+r, y+h-r, r, 0.5*math.pi, math.pi)
        self.ctx.close_path()
    
    def get_png_bytes(self):
        buf = io.BytesIO()
        self.surface.write_to_png(buf)
        return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# SUPABASE MANAGER
# ═══════════════════════════════════════════════════════════════

class SupabaseManager:
    def __init__(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("Supabase credentials eksik!")
        self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_questions_without_images(self, limit=30):
        try:
            shape_topics = ['Üçgen', 'Dörtgen', 'Çember', 'Daire', 'Çokgen',
                           'Alan', 'Çevre', 'Hacim', 'Prizma', 'Piramit', 
                           'Silindir', 'Koni', 'Küre', 'Açı', 'Koordinat']
            
            for topic in shape_topics:
                result = self.client.table('question_bank').select(
                    'id', 'original_text', 'topic', 'topic_group', 'grade_level', 'image_url'
                ).is_('image_url', 'null').eq('is_active', True).ilike(
                    'topic', f'%{topic}%'
                ).limit(limit).execute()
                
                if result.data and len(result.data) > 0:
                    logger.info(f"Şekil konusu ({topic}): {len(result.data)} soru bulundu")
                    return result.data
            
            result = self.client.table('question_bank').select(
                'id', 'original_text', 'topic', 'topic_group', 'grade_level', 'image_url'
            ).is_('image_url', 'null').eq('is_active', True).limit(limit).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Sorgu hatası: {e}")
            return []
    
    def update_question_image(self, question_id, image_url):
        try:
            self.client.table('question_bank').update({
                'image_url': image_url
            }).eq('id', question_id).execute()
            return True
        except Exception as e:
            logger.error(f"Güncelleme hatası (id={question_id}): {e}")
            return False
    
    def upload_image(self, image_bytes, filename):
        try:
            self.client.storage.from_(Config.STORAGE_BUCKET).upload(
                path=filename, file=image_bytes, 
                file_options={"content-type": "image/png"}
            )
            return self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
        except Exception as e:
            if 'Duplicate' in str(e):
                try:
                    self.client.storage.from_(Config.STORAGE_BUCKET).update(
                        path=filename, file=image_bytes,
                        file_options={"content-type": "image/png"}
                    )
                    return self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
                except: pass
            logger.error(f"Upload hatası: {e}")
            return None


# ═══════════════════════════════════════════════════════════════
# GEMINI ANALYZER (Metin Analizi)
# ═══════════════════════════════════════════════════════════════

class GeminiAnalyzer:
    ANALYSIS_PROMPT = """Bu matematik sorusunu oku ve analiz et.

SORU: Geometrik bir çizim/şekil bu soruyu anlamayı veya çözmeyi kolaylaştırır mı?

EVET ise → cizim_pisinilir: true + çizim talimatları
HAYIR ise → cizim_pisinilir: false

## JSON FORMATLARI:

Dikdörtgen/Kare:
{"cizim_pisinilir": true, "shape_type": "rectangle", "points": [{"name": "A", "x": 0, "y": 0}, {"name": "B", "x": 20, "y": 0}, {"name": "C", "x": 20, "y": 20}, {"name": "D", "x": 0, "y": 20}], "edges": [{"start": "A", "end": "B", "label": "20 m"}]}

Üçgen:
{"cizim_pisinilir": true, "shape_type": "triangle", "points": [{"name": "A", "x": 0, "y": 0}, {"name": "B", "x": 6, "y": 0}, {"name": "C", "x": 3, "y": 5}], "edges": [{"start": "A", "end": "B", "label": "6 cm"}]}

Daire/Çember:
{"cizim_pisinilir": true, "shape_type": "circle", "center": {"name": "O", "x": 5, "y": 5}, "radius": 4}

Küp:
{"cizim_pisinilir": true, "shape_type": "cube", "dimensions": {"size": 4}}

Piramit:
{"cizim_pisinilir": true, "shape_type": "pyramid", "dimensions": {"base_size": 4, "height": 5}}

Silindir:
{"cizim_pisinilir": true, "shape_type": "cylinder", "dimensions": {"radius": 3, "height": 6}}

Koni:
{"cizim_pisinilir": true, "shape_type": "cone", "dimensions": {"radius": 3, "height": 5}}

Küre:
{"cizim_pisinilir": true, "shape_type": "sphere", "dimensions": {"radius": 4}}

Pasta Grafik:
{"cizim_pisinilir": true, "shape_type": "pie_chart", "pie_data": {"values": [40, 30, 20], "labels": ["A", "B", "C"], "value_type": "percent"}}

Sütun Grafik:
{"cizim_pisinilir": true, "shape_type": "bar_chart", "bar_data": {"values": [25, 40, 35], "labels": ["X", "Y", "Z"]}}

Çizim gereksiz:
{"cizim_pisinilir": false, "neden": "kısa açıklama"}

NOT: SADECE JSON döndür!

SORU: """
    
    def __init__(self):
        if not Config.GEMINI_API_KEY:
            raise ValueError("Gemini API key eksik!")
        if NEW_GENAI:
            self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        else:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        self.request_count = 0
        self.last_request_time = 0
        logger.info(f"Gemini Analyzer başlatıldı (model: {Config.GEMINI_MODEL})")
    
    def _rate_limit(self):
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        if self.request_count >= 8:
            wait_time = 60 - (current_time - self.last_request_time) + 2
            if wait_time > 0:
                logger.info(f"⏳ Rate limit - {wait_time:.0f}s bekleniyor...")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()
        self.request_count += 1
    
    def analyze(self, question_text, max_retries=3):
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                prompt = self.ANALYSIS_PROMPT + question_text
                
                if NEW_GENAI:
                    response = self.client.models.generate_content(model=Config.GEMINI_MODEL, contents=prompt)
                    text = response.text
                else:
                    response = self.model.generate_content(prompt)
                    text = response.text
                
                text = text.strip()
                if text.startswith('```'):
                    lines = text.split('\n')
                    text = '\n'.join(lines[1:-1])
                    if text.startswith('json'): text = text[4:].strip()
                return json.loads(text)
                
            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                    wait_time = 60 + (attempt * 10)
                    logger.warning(f"⚠️ Rate limit. {wait_time}s bekleniyor... ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    self.request_count = 0
                    self.last_request_time = time.time()
                else:
                    logger.error(f"Gemini hatası: {e}")
                    return None
        return None


# ═══════════════════════════════════════════════════════════════
# HYBRID IMAGE GENERATOR
# ═══════════════════════════════════════════════════════════════

class HybridImageGenerator:
    """Hibrit görsel üretici: AI + Cairo fallback"""
    
    def __init__(self):
        self.ai_generator = None
        if Config.GEMINI_API_KEY and Config.IMAGE_STRATEGY != 'cairo_only':
            try:
                self.ai_generator = GeminiImageGenerator(Config.GEMINI_API_KEY)
            except Exception as e:
                logger.warning(f"AI Image Generator başlatılamadı: {e}")
        
        self.cairo_enabled = Config.IMAGE_STRATEGY != 'ai_only'
        logger.info(f"HybridImageGenerator başlatıldı (strateji: {Config.IMAGE_STRATEGY})")
    
    def generate(self, analysis: Dict, question_text: str = "") -> Optional[bytes]:
        """Görsel üret - stratejiye göre"""
        shape_type = analysis.get('shape_type', '')
        strategy = Config.IMAGE_STRATEGY
        
        logger.info(f"🖼️ Görsel üretimi: {shape_type} (strateji: {strategy})")
        
        # Strateji: ai_first - Önce AI dene, başarısız olursa Cairo
        if strategy == 'ai_first' and self.ai_generator:
            ai_result = self.ai_generator.generate(analysis, question_text)
            if ai_result:
                logger.info("✅ AI görsel üretimi başarılı")
                return ai_result
            logger.info("⚠️ AI başarısız, Cairo'ya düşülüyor...")
        
        # Strateji: hybrid - Karmaşıklığa göre karar ver
        elif strategy == 'hybrid':
            # Karmaşık şekiller için AI, basit şekiller için Cairo
            complex_shapes = ['pyramid', 'cone', 'sphere', 'cylinder', 'prism', 
                            'inscribed_circle', 'circumscribed']
            
            use_ai = (
                self.ai_generator and 
                (shape_type in complex_shapes or analysis.get('inscribed_circle'))
            )
            
            if use_ai:
                ai_result = self.ai_generator.generate(analysis, question_text)
                if ai_result:
                    logger.info("✅ AI görsel üretimi başarılı (karmaşık şekil)")
                    return ai_result
                logger.info("⚠️ AI başarısız, Cairo'ya düşülüyor...")
        
        # Strateji: ai_only
        elif strategy == 'ai_only' and self.ai_generator:
            return self.ai_generator.generate(analysis, question_text)
        
        # Cairo ile çizim (fallback veya cairo_only)
        if self.cairo_enabled:
            return self._cairo_generate(analysis)
        
        return None
    
    def _cairo_generate(self, analysis: Dict) -> Optional[bytes]:
        """Cairo ile programatik çizim"""
        shape_type = analysis.get('shape_type', '')
        
        try:
            # 3D şekiller
            if shape_type in ['cube', 'pyramid', 'cylinder', 'sphere', 'cone', 'prism', 
                             'rectangular_prism', 'triangular_prism']:
                return self._render_3d(analysis)
            
            # Grafikler
            if shape_type == 'pie_chart':
                return self._pie(analysis)
            elif shape_type == 'bar_chart':
                return self._bar(analysis)
            
            # 2D geometri
            if shape_type == 'circle':
                return self._circle(analysis)
            
            return self._geometry(analysis)
            
        except Exception as e:
            logger.error(f"Cairo çizim hatası: {e}")
            return None
    
    def _render_3d(self, analysis):
        shape_type = analysis.get('shape_type', '')
        dimensions = analysis.get('dimensions', {})
        
        renderer = Cube3DRenderer(800, 700)
        if not renderer.setup():
            return None
        
        if shape_type == 'cube':
            size = dimensions.get('size', 4)
            renderer.draw_cube(size=size, edge_label=f"{size} cm")
        elif shape_type == 'pyramid':
            renderer.draw_pyramid(
                base_size=dimensions.get('base_size', 4),
                height=dimensions.get('height', 5)
            )
        elif shape_type == 'cylinder':
            renderer.draw_cylinder(
                radius=dimensions.get('radius', 2),
                height=dimensions.get('height', 4)
            )
        elif shape_type == 'sphere':
            renderer.draw_sphere(radius=dimensions.get('radius', 3))
        elif shape_type == 'cone':
            renderer.draw_cone(
                radius=dimensions.get('radius', 2),
                height=dimensions.get('height', 4)
            )
        else:
            renderer.draw_cube(size=4)
        
        return renderer.get_png_bytes()
    
    def _pie(self, analysis):
        pd = analysis.get('pie_data', {})
        if not pd.get('values'): return None
        r = Pie3DRenderer(700, 620)
        r.setup(bg_color=Colors.WHITE)
        r.draw(values=pd.get('values', []), labels=pd.get('labels', []))
        return r.get_png_bytes()
    
    def _bar(self, analysis):
        bd = analysis.get('bar_data', {})
        if not bd.get('values'): return None
        r = BarChartRenderer(700, 500)
        r.setup(bg_color=Colors.WHITE)
        r.draw(values=bd.get('values', []), labels=bd.get('labels', []))
        return r.get_png_bytes()
    
    def _circle(self, analysis):
        center_data = analysis.get('center', {})
        radius = analysis.get('radius', 4)
        cx = center_data.get('x', 5)
        cy = center_data.get('y', 5)
        
        bounds = {'x_min': cx - radius - 2, 'x_max': cx + radius + 2,
                 'y_min': cy - radius - 2, 'y_max': cy + radius + 2}
        
        r = CairoRenderer(Config.IMAGE_WIDTH, Config.IMAGE_HEIGHT)
        r.setup(bounds)
        r.draw_circle((cx, cy), radius, Colors.FILL_LIGHT, Colors.PRIMARY, stroke_width=3)
        r.draw_point((cx, cy), Colors.get_point_color(0))
        r.draw_point_label((cx, cy), center_data.get('name', 'O'), Colors.get_point_color(0))
        r.draw_line((cx, cy), (cx + radius, cy), Colors.SECONDARY, width=2)
        r.draw_label((cx + radius/2, cy + 0.3), f"r={radius}", Colors.SECONDARY)
        
        return r.get_png_bytes()
    
    def _geometry(self, analysis):
        pts = analysis.get('points', [])
        if not pts: return None
        
        xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
        bounds = {'x_min': min(xs)-2, 'x_max': max(xs)+2, 
                 'y_min': min(ys)-2, 'y_max': max(ys)+2}
        
        r = CairoRenderer(Config.IMAGE_WIDTH, Config.IMAGE_HEIGHT)
        r.setup(bounds)
        
        points = {p['name']: (p['x'], p['y']) for p in pts}
        for name, pos in points.items():
            r.add_point(name, *pos)
        
        # Polygon
        if len(pts) >= 3:
            coords = [(p['x'], p['y']) for p in pts]
            r.draw_polygon(coords, Colors.FILL_LIGHT, Colors.PRIMARY, stroke_width=3)
        
        # İç teğet daire
        inscribed = analysis.get('inscribed_circle', {})
        if inscribed:
            ic_center = inscribed.get('center', {})
            ic_radius = inscribed.get('radius', 0)
            if ic_center and ic_radius:
                cx = ic_center.get('x', (min(xs) + max(xs)) / 2)
                cy = ic_center.get('y', (min(ys) + max(ys)) / 2)
                r.draw_circle((cx, cy), ic_radius, (0.13, 0.59, 0.95, 0.15), (0.13, 0.59, 0.95), stroke_width=2)
                r.draw_point((cx, cy), (0.13, 0.59, 0.95))
        
        # Özel çizgiler
        for sl in analysis.get('special_lines', []):
            from_name = sl.get('from')
            if from_name and len(pts) >= 3:
                from_idx = ord(from_name) - ord('A')
                if 0 <= from_idx < len(pts):
                    coords = [(p['x'], p['y']) for p in pts[:3]]
                    if sl['type'] == 'height':
                        r.draw_altitude(coords, from_idx, label=sl.get('label'))
                    elif sl['type'] == 'median':
                        r.draw_median(coords, from_idx, label=sl.get('label'))
                    elif sl['type'] == 'bisector':
                        r.draw_angle_bisector(coords, from_idx, label=sl.get('label'))
        
        # Açılar
        for ang in analysis.get('angles', []):
            v_name = ang.get('vertex')
            if v_name and v_name in points:
                vertex = points[v_name]
                idx = next((i for i, p in enumerate(pts) if p['name'] == v_name), -1)
                if idx >= 0 and len(pts) >= 3:
                    p1 = (pts[(idx-1) % len(pts)]['x'], pts[(idx-1) % len(pts)]['y'])
                    p2 = (pts[(idx+1) % len(pts)]['x'], pts[(idx+1) % len(pts)]['y'])
                    if ang.get('is_right'):
                        r.draw_right_angle(vertex, p1, p2)
                    elif ang.get('value'):
                        r.draw_angle_arc(vertex, p1, p2, label=ang['value'], fill=True)
        
        # Kenar etiketleri
        for edge in analysis.get('edges', []):
            s, e, label = edge.get('start'), edge.get('end'), edge.get('label')
            if s in points and e in points and label:
                p1, p2 = points[s], points[e]
                mid = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
                ev = np.array(p2) - np.array(p1)
                normal = np.array([-ev[1], ev[0]])
                nl = np.linalg.norm(normal)
                if nl > 0: normal = normal / nl * 0.5
                r.draw_label((mid[0]+normal[0], mid[1]+normal[1]), label, Colors.PRIMARY)
        
        # Noktalar ve etiketler
        for i, p in enumerate(pts):
            color = Colors.get_point_color(i)
            pos = (p['x'], p['y'])
            r.draw_point(pos, color)
            r.draw_point_label(pos, p['name'], color, p.get('label_position', 'auto'))
        
        return r.get_png_bytes()


# ═══════════════════════════════════════════════════════════════
# GEOMETRY BOT
# ═══════════════════════════════════════════════════════════════

class GeometryBot:
    def __init__(self):
        logger.info("=" * 60)
        logger.info("Geometry Bot v4.0 - Hibrit Sistem")
        logger.info(f"Strateji: {Config.IMAGE_STRATEGY}")
        logger.info("=" * 60)
        
        self.supabase = SupabaseManager()
        self.analyzer = GeminiAnalyzer()
        self.generator = HybridImageGenerator()
        self.stats = {
            'processed': 0, 
            'success': 0, 
            'skipped': 0, 
            'error': 0,
            'ai_success': 0,
            'cairo_success': 0,
            'start_time': datetime.now()
        }
    
    def run(self):
        logger.info("Bot başlatılıyor...")
        batch = 10 if Config.TEST_MODE else Config.BATCH_SIZE
        questions = self.supabase.get_questions_without_images(batch)
        
        if not questions:
            logger.info("İşlenecek soru yok")
            return
        
        logger.info(f"{len(questions)} soru işlenecek")
        
        for i, q in enumerate(questions, 1):
            self._process(q)
            if i < len(questions):
                time.sleep(1)
        
        elapsed = datetime.now() - self.stats['start_time']
        logger.info("=" * 60)
        logger.info(f"TAMAMLANDI")
        logger.info(f"Süre: {elapsed}")
        logger.info(f"Başarılı: {self.stats['success']}/{self.stats['processed']}")
        logger.info(f"  - AI: {self.stats['ai_success']}")
        logger.info(f"  - Cairo: {self.stats['cairo_success']}")
        logger.info(f"Atlanan: {self.stats['skipped']}")
        logger.info(f"Hata: {self.stats['error']}")
        logger.info("=" * 60)
    
    def _process(self, question):
        q_id = question.get('id')
        q_text = question.get('original_text', '')
        
        if not q_text:
            logger.warning(f"[{q_id}] ⏭️ Soru metni boş")
            self.stats['skipped'] += 1
            return
        
        logger.info(f"[{q_id}] 📝 İşleniyor: {q_text[:80]}...")
        self.stats['processed'] += 1
        
        try:
            analysis = self.analyzer.analyze(q_text)
            
            if not analysis:
                logger.warning(f"[{q_id}] ❌ Analiz döndürmedi")
                self.stats['error'] += 1
                return
            
            if not analysis.get('cizim_pisinilir', False):
                logger.info(f"[{q_id}] ⏭️ Çizim gerekmiyor: {analysis.get('neden', '-')}")
                self.stats['skipped'] += 1
                return
            
            # Hibrit görsel üretimi
            image_bytes = self.generator.generate(analysis, q_text)
            
            if not image_bytes:
                logger.warning(f"[{q_id}] ❌ Görsel oluşturulamadı")
                self.stats['error'] += 1
                return
            
            logger.info(f"[{q_id}] 🎨 Görsel oluşturuldu ({len(image_bytes)} bytes)")
            
            filename = f"geometry_{q_id}_{int(time.time())}.png"
            image_url = self.supabase.upload_image(image_bytes, filename)
            
            if image_url and self.supabase.update_question_image(q_id, image_url):
                logger.info(f"[{q_id}] ✅ Başarılı: {image_url}")
                self.stats['success'] += 1
            else:
                logger.warning(f"[{q_id}] ❌ Yükleme/güncelleme başarısız")
                self.stats['error'] += 1
                
        except Exception as e:
            logger.error(f"[{q_id}] ❌ Hata: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['error'] += 1


if __name__ == "__main__":
    GeometryBot().run()
