"""
Geometri Görsel Botu
====================
Supabase'deki geometri sorularını tarar, Gemini ile analiz eder,
Sympy + Matplotlib ile matematiksel olarak doğru çizimler üretir.

GitHub Actions ile çalışır.
Günde 3 seans, her seansta 30 soru işler.
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

# Supabase
from supabase import create_client, Client

# Gemini
try:
    from google import genai
    from google.genai import types
    NEW_GENAI = True
except ImportError:
    import google.generativeai as genai
    NEW_GENAI = False

# Geometri çizim
import matplotlib
matplotlib.use('Agg')  # GUI olmadan çalışması için
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Arc, FancyBboxPatch, Circle as MplCircle
import numpy as np
from sympy import Point, Triangle, Line, Segment, Circle, pi, sqrt, N, Rational
from sympy.geometry import Polygon

# Resim işleme
from io import BytesIO
import base64

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== YAPILANDIRMA ==============

class Config:
    """Bot yapılandırması"""
    # Supabase
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    
    # Gemini
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    GEMINI_MODEL = 'gemini-2.0-flash'
    
    # Storage
    STORAGE_BUCKET = 'questions-images'
    
    # İşlem limitleri
    BATCH_SIZE = 30  # Her seansta işlenecek soru sayısı
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 10
    
    # Görsel ayarları
    IMAGE_WIDTH = 800
    IMAGE_HEIGHT = 600
    IMAGE_DPI = 150
    
    # Renk paleti
    COLORS = {
        'primary': '#3b82f6',      # Ana şekil (mavi)
        'secondary': '#10b981',    # İkincil şekil (yeşil)
        'highlight': '#ef4444',    # Yükseklik/önemli (kırmızı)
        'auxiliary': '#f59e0b',    # Yardımcı çizgi (turuncu)
        'angle': '#8b5cf6',        # Açı yayları (mor)
        'unknown': '#dc2626',      # Bilinmeyen (koyu kırmızı)
        'text': '#1e293b',         # Metin (koyu gri)
        'background': '#ffffff',   # Arka plan (beyaz)
        'grid': '#e2e8f0'          # Grid (açık gri)
    }


# ============== VERİTABANI İŞLEMLERİ ==============

class DatabaseManager:
    """Supabase veritabanı işlemleri"""
    
    def __init__(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("SUPABASE_URL ve SUPABASE_KEY environment variable'ları gerekli!")
        
        self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_geometry_questions(self, limit: int) -> List[Dict]:
        """Görsel oluşturulmamış geometri sorularını çek"""
        
        # Geometri konuları
        geometry_topics = [
            '%Üçgen%', '%üçgen%', '%Dörtgen%', '%dörtgen%',
            '%Çember%', '%çember%', '%Daire%', '%daire%',
            '%Geometri%', '%geometri%', '%Açı%', '%açı%',
            '%Kenar%', '%kenar%', '%Alan%', '%Çevre%',
            '%Prizma%', '%Piramit%', '%Silindir%', '%Koni%', '%Küre%',
            '%Koordinat%', '%koordinat%', '%Doğru%', '%doğru%',
            '%Analitik%', '%analitik%'
        ]
        
        try:
            # Geometri sorularını çek (image_url NULL olanlar)
            query = self.client.table('question_bank').select('*')
            query = query.is_('image_url', 'null')
            query = query.eq('is_active', True)
            
            # Topic filtresi için OR koşulu
            topic_filter = ' or '.join([f"topic.ilike.{t}" for t in geometry_topics])
            
            response = self.client.table('question_bank').select('*').is_('image_url', 'null').eq('is_active', True).or_(
                'topic.ilike.%Üçgen%,topic.ilike.%üçgen%,topic.ilike.%Dörtgen%,topic.ilike.%dörtgen%,'
                'topic.ilike.%Çember%,topic.ilike.%çember%,topic.ilike.%Daire%,topic.ilike.%daire%,'
                'topic.ilike.%Geometri%,topic.ilike.%geometri%,topic.ilike.%Açı%,topic.ilike.%açı%,'
                'topic.ilike.%Koordinat%,topic.ilike.%koordinat%,topic.ilike.%Analitik%,topic.ilike.%analitik%,'
                'topic.ilike.%Prizma%,topic.ilike.%Piramit%,topic.ilike.%Silindir%'
            ).limit(limit).execute()
            
            questions = response.data
            logger.info(f"{len(questions)} geometri sorusu bulundu")
            return questions
            
        except Exception as e:
            logger.error(f"Soru çekme hatası: {e}")
            # Alternatif basit sorgu
            try:
                response = self.client.table('question_bank').select('*').is_('image_url', 'null').eq('is_active', True).limit(limit * 3).execute()
                
                # Manuel filtreleme
                geometry_keywords = ['üçgen', 'dörtgen', 'çember', 'daire', 'açı', 'kenar', 
                                    'geometri', 'koordinat', 'doğru', 'analitik', 'alan', 'çevre',
                                    'prizma', 'piramit', 'silindir', 'koni', 'küre', 'abc', 'ab', 'bc']
                
                filtered = []
                for q in response.data:
                    topic = (q.get('topic') or '').lower()
                    text = (q.get('original_text') or '').lower()
                    
                    if any(kw in topic or kw in text for kw in geometry_keywords):
                        filtered.append(q)
                        if len(filtered) >= limit:
                            break
                
                logger.info(f"{len(filtered)} geometri sorusu bulundu (manuel filtreleme)")
                return filtered
                
            except Exception as e2:
                logger.error(f"Alternatif sorgu hatası: {e2}")
                return []
    
    def update_image_url(self, question_id: int, image_url: str) -> bool:
        """Soru kaydına görsel URL'i ekle"""
        try:
            self.client.table('question_bank').update({
                'image_url': image_url
            }).eq('id', question_id).execute()
            
            logger.info(f"Soru #{question_id} güncellendi: {image_url}")
            return True
            
        except Exception as e:
            logger.error(f"Güncelleme hatası (Soru #{question_id}): {e}")
            return False
    
    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Görseli Supabase Storage'a yükle"""
        try:
            # Yükle
            response = self.client.storage.from_(Config.STORAGE_BUCKET).upload(
                path=filename,
                file=image_bytes,
                file_options={"content-type": "image/png"}
            )
            
            # Public URL al
            public_url = self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
            
            logger.info(f"Görsel yüklendi: {filename}")
            return public_url
            
        except Exception as e:
            # Dosya zaten varsa üzerine yaz
            if 'Duplicate' in str(e) or 'already exists' in str(e):
                try:
                    self.client.storage.from_(Config.STORAGE_BUCKET).update(
                        path=filename,
                        file=image_bytes,
                        file_options={"content-type": "image/png"}
                    )
                    public_url = self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
                    logger.info(f"Görsel güncellendi: {filename}")
                    return public_url
                except Exception as e2:
                    logger.error(f"Görsel güncelleme hatası: {e2}")
                    return None
            else:
                logger.error(f"Görsel yükleme hatası: {e}")
                return None


# ============== GEMİNİ ANALİZ ==============

class GeminiAnalyzer:
    """Gemini ile soru analizi"""
    
    ANALYSIS_PROMPT = """Sen bir geometri soru analiz uzmanısın.

GÖREV: Verilen geometri sorusunu analiz et ve çizim için gerekli bilgileri JSON formatında çıkar.

ÖNEMLİ KURALLAR:
1. Sadece VERİLENLERİ çıkar - ÇÖZÜMÜ YAPMA!
2. Bilinmeyenleri "?" ile işaretle
3. Koordinatları mantıklı ve dengeli belirle (görsel güzel görünsün)
4. Nokta isimlerini soruda geçtiği gibi kullan (A, B, C, vb.)
5. Türkçe karakterleri düzgün kullan

DESTEKLENEN ŞEKİL TİPLERİ:
- ucgen: Üçgen (genel, dik, ikizkenar, eşkenar)
- dortgen: Dörtgen (kare, dikdörtgen, paralelkenar, yamuk, eşkenar dörtgen)
- cember: Çember/Daire
- analitik: Koordinat düzleminde nokta/doğru
- cokgen: Çokgen (beşgen, altıgen, vb.)

JSON ÇIKTI FORMATI:
{
  "cizim_pisinilir": true/false,
  "neden": "Eğer çizilemiyorsa neden",
  "sekil_tipi": "ucgen|dortgen|cember|analitik|cokgen",
  "alt_tip": "genel|dik|ikizkenar|eskenar|kare|dikdortgen|paralelkenar|yamuk",
  "noktalar": [
    {"isim": "A", "x": 0, "y": 4, "konum": "tepe"},
    {"isim": "B", "x": -3, "y": 0, "konum": "sol_alt"},
    {"isim": "C", "x": 3, "y": 0, "konum": "sag_alt"}
  ],
  "kenarlar": [
    {"baslangic": "A", "bitis": "B", "uzunluk": "5 cm", "goster_uzunluk": true},
    {"baslangic": "B", "bitis": "C", "uzunluk": "6 cm", "goster_uzunluk": true}
  ],
  "acilar": [
    {"kose": "B", "deger": "90°", "goster": true, "dik_aci": true}
  ],
  "ozel_cizgiler": [
    {"tip": "yukseklik", "baslangic": "A", "bitis": "H", "bitis_koordinat": [0, 0], "etiket": "h = ?", "kenar_uzerinde": "BC"}
  ],
  "daireler": [
    {"merkez": "O", "yaricap": 3, "yaricap_goster": true, "yaricap_etiketi": "r = 5 cm"}
  ],
  "ek_etiketler": [
    {"metin": "Alan = 24 cm²", "konum": "sag_ust"}
  ],
  "bilinmeyenler": ["h", "x"]
}

NOT: 
- Eğer soru geometrik çizim gerektirmiyorsa (sadece hesaplama), "cizim_pisinilir": false yap
- Koordinatlar -10 ile 10 arasında olsun
- Şekil merkezi (0,0) civarında olsun

SORU:
"""
    
    def __init__(self):
        if not Config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable gerekli!")
        
        if NEW_GENAI:
            self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        else:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        
        logger.info(f"Gemini model hazır: {Config.GEMINI_MODEL}")
    
    def analyze_question(self, question_text: str) -> Optional[Dict]:
        """Soruyu analiz et ve çizim bilgilerini çıkar"""
        try:
            prompt = self.ANALYSIS_PROMPT + question_text
            
            if NEW_GENAI:
                response = self.client.models.generate_content(
                    model=Config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                response_text = response.text
            else:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                response_text = response.text
            
            # JSON parse
            result = json.loads(response_text)
            
            # Çizilebilirlik kontrolü
            if not result.get('cizim_pisinilir', True):
                logger.info(f"Soru çizilemez: {result.get('neden', 'Bilinmiyor')}")
                return None
            
            logger.info(f"Analiz tamamlandı: {result.get('sekil_tipi', 'bilinmiyor')}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {e}")
            logger.error(f"Ham yanıt: {response.text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Gemini analiz hatası: {e}")
            return None


# ============== GEOMETRİ ÇİZİCİ ==============

class GeometryRenderer:
    """Sympy + Matplotlib ile geometri çizimi"""
    
    def __init__(self):
        # Font ayarları
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['font.size'] = 12
        plt.rcParams['axes.unicode_minus'] = False
    
    def render(self, analysis: Dict) -> Optional[bytes]:
        """Analiz sonucuna göre görsel oluştur"""
        try:
            sekil_tipi = analysis.get('sekil_tipi', 'ucgen')
            
            if sekil_tipi == 'ucgen':
                return self._render_triangle(analysis)
            elif sekil_tipi == 'dortgen':
                return self._render_quadrilateral(analysis)
            elif sekil_tipi == 'cember':
                return self._render_circle(analysis)
            elif sekil_tipi == 'analitik':
                return self._render_analytic(analysis)
            elif sekil_tipi == 'cokgen':
                return self._render_polygon(analysis)
            else:
                logger.warning(f"Bilinmeyen şekil tipi: {sekil_tipi}")
                return self._render_triangle(analysis)  # Varsayılan
                
        except Exception as e:
            logger.error(f"Çizim hatası: {e}")
            return None
    
    def _create_figure(self) -> tuple:
        """Yeni figure oluştur"""
        fig, ax = plt.subplots(figsize=(Config.IMAGE_WIDTH/Config.IMAGE_DPI, 
                                         Config.IMAGE_HEIGHT/Config.IMAGE_DPI), 
                               dpi=Config.IMAGE_DPI)
        ax.set_aspect('equal')
        ax.set_facecolor(Config.COLORS['background'])
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--', color=Config.COLORS['grid'])
        
        return fig, ax
    
    def _finalize_figure(self, fig, ax) -> bytes:
        """Figure'ı PNG olarak kaydet"""
        # Eksenleri ayarla
        ax.autoscale()
        
        # Margin ekle
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        margin_x = (xlim[1] - xlim[0]) * 0.15
        margin_y = (ylim[1] - ylim[0]) * 0.15
        ax.set_xlim(xlim[0] - margin_x, xlim[1] + margin_x)
        ax.set_ylim(ylim[0] - margin_y, ylim[1] + margin_y)
        
        # Eksen etiketlerini kaldır
        ax.set_xticks([])
        ax.set_yticks([])
        
        # Çerçeveyi kaldır
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # PNG'ye çevir
        buffer = BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', 
                   facecolor='white', edgecolor='none', dpi=Config.IMAGE_DPI)
        plt.close(fig)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _get_point_coords(self, analysis: Dict) -> Dict[str, tuple]:
        """Nokta koordinatlarını al"""
        coords = {}
        for nokta in analysis.get('noktalar', []):
            isim = nokta['isim']
            x = float(nokta['x'])
            y = float(nokta['y'])
            coords[isim] = (x, y)
        return coords
    
    def _draw_point(self, ax, x: float, y: float, label: str, color: str = None, 
                    offset: tuple = (5, 5), size: int = 80):
        """Nokta ve etiket çiz"""
        color = color or Config.COLORS['highlight']
        ax.scatter([x], [y], c=color, s=size, zorder=5, edgecolors='white', linewidths=2)
        ax.annotate(label, (x, y), xytext=offset, textcoords='offset points',
                   fontsize=14, fontweight='bold', color=color)
    
    def _draw_line(self, ax, p1: tuple, p2: tuple, color: str = None, 
                   linewidth: float = 2.5, linestyle: str = '-', label: str = None):
        """Çizgi çiz"""
        color = color or Config.COLORS['primary']
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color, linewidth=linewidth,
               linestyle=linestyle, zorder=3, label=label)
    
    def _draw_length_label(self, ax, p1: tuple, p2: tuple, label: str, 
                           offset: float = 0.3, color: str = None):
        """Kenar uzunluk etiketi"""
        color = color or Config.COLORS['text']
        
        # Orta nokta
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        
        # Dik yönde offset
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = np.sqrt(dx**2 + dy**2)
        if length > 0:
            nx, ny = -dy / length * offset, dx / length * offset
        else:
            nx, ny = 0, offset
        
        ax.annotate(label, (mx + nx, my + ny), fontsize=11, fontweight='bold',
                   color=color, ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor=color, alpha=0.9))
    
    def _draw_right_angle(self, ax, vertex: tuple, p1: tuple, p2: tuple, 
                          size: float = 0.4, color: str = None):
        """Dik açı işareti"""
        color = color or Config.COLORS['highlight']
        
        vx, vy = vertex
        
        # p1 yönünde birim vektör
        v1 = np.array([p1[0] - vx, p1[1] - vy])
        norm1 = np.linalg.norm(v1)
        if norm1 > 0:
            v1 = v1 / norm1 * size
        
        # p2 yönünde birim vektör
        v2 = np.array([p2[0] - vx, p2[1] - vy])
        norm2 = np.linalg.norm(v2)
        if norm2 > 0:
            v2 = v2 / norm2 * size
        
        # Kare çiz
        square = patches.Polygon([
            (vx, vy),
            (vx + v1[0], vy + v1[1]),
            (vx + v1[0] + v2[0], vy + v1[1] + v2[1]),
            (vx + v2[0], vy + v2[1])
        ], fill=False, edgecolor=color, linewidth=1.5, zorder=4)
        ax.add_patch(square)
    
    def _draw_angle_arc(self, ax, vertex: tuple, p1: tuple, p2: tuple,
                        radius: float = 0.5, color: str = None, label: str = None):
        """Açı yayı çiz"""
        color = color or Config.COLORS['angle']
        
        vx, vy = vertex
        
        # Açıları hesapla
        angle1 = np.degrees(np.arctan2(p1[1] - vy, p1[0] - vx))
        angle2 = np.degrees(np.arctan2(p2[1] - vy, p2[0] - vx))
        
        # Küçük açıyı bul
        if angle2 < angle1:
            angle1, angle2 = angle2, angle1
        if angle2 - angle1 > 180:
            angle1, angle2 = angle2, angle1 + 360
        
        arc = Arc((vx, vy), radius*2, radius*2, angle=0,
                 theta1=angle1, theta2=angle2, color=color, linewidth=2, zorder=4)
        ax.add_patch(arc)
        
        if label:
            mid_angle = np.radians((angle1 + angle2) / 2)
            lx = vx + radius * 1.5 * np.cos(mid_angle)
            ly = vy + radius * 1.5 * np.sin(mid_angle)
            ax.annotate(label, (lx, ly), fontsize=11, color=color,
                       fontweight='bold', ha='center', va='center')
    
    def _render_triangle(self, analysis: Dict) -> bytes:
        """Üçgen çiz"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        noktalar = list(coords.keys())
        
        if len(noktalar) < 3:
            logger.warning("Üçgen için en az 3 nokta gerekli")
            plt.close(fig)
            return None
        
        # İlk 3 noktayı al
        A, B, C = noktalar[0], noktalar[1], noktalar[2]
        pA, pB, pC = coords[A], coords[B], coords[C]
        
        # Üçgen çiz
        triangle = patches.Polygon([pA, pB, pC], fill=True,
                                   facecolor=Config.COLORS['primary'], alpha=0.1,
                                   edgecolor=Config.COLORS['primary'], linewidth=2.5)
        ax.add_patch(triangle)
        
        # Kenar uzunlukları
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords and kenar.get('goster_uzunluk', True):
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    self._draw_length_label(ax, coords[bas], coords[bit], uzunluk)
        
        # Açılar
        for aci in analysis.get('acilar', []):
            kose = aci.get('kose')
            if kose in coords and aci.get('goster', True):
                # Köşenin diğer iki noktasını bul
                diger = [n for n in [A, B, C] if n != kose]
                if len(diger) >= 2:
                    if aci.get('dik_aci', False):
                        self._draw_right_angle(ax, coords[kose], coords[diger[0]], coords[diger[1]])
                    else:
                        deger = aci.get('deger', '')
                        self._draw_angle_arc(ax, coords[kose], coords[diger[0]], coords[diger[1]], 
                                           label=deger)
        
        # Özel çizgiler (yükseklik, kenarortay, vb.)
        for ozel in analysis.get('ozel_cizgiler', []):
            tip = ozel.get('tip')
            bas = ozel.get('baslangic')
            
            if bas in coords:
                # Bitiş koordinatı
                if 'bitis_koordinat' in ozel:
                    bit_coord = tuple(ozel['bitis_koordinat'])
                elif ozel.get('bitis') in coords:
                    bit_coord = coords[ozel['bitis']]
                else:
                    # Yükseklik için hesapla
                    kenar = ozel.get('kenar_uzerinde', '')
                    if len(kenar) == 2 and kenar[0] in coords and kenar[1] in coords:
                        # Sympy ile yükseklik ayağını hesapla
                        p_bas = Point(coords[bas])
                        p_k1 = Point(coords[kenar[0]])
                        p_k2 = Point(coords[kenar[1]])
                        kenar_line = Line(p_k1, p_k2)
                        dik_line = kenar_line.perpendicular_line(p_bas)
                        ayak = dik_line.intersection(kenar_line)
                        if ayak:
                            bit_coord = (float(ayak[0].x), float(ayak[0].y))
                        else:
                            continue
                    else:
                        continue
                
                # Çizgi çiz
                renk = Config.COLORS['highlight'] if tip == 'yukseklik' else Config.COLORS['auxiliary']
                stil = '-' if tip == 'yukseklik' else '--'
                self._draw_line(ax, coords[bas], bit_coord, color=renk, linestyle=stil, linewidth=2)
                
                # Etiket
                etiket = ozel.get('etiket', '')
                if etiket:
                    self._draw_length_label(ax, coords[bas], bit_coord, etiket, color=renk)
                
                # Dik açı işareti (yükseklik için)
                if tip == 'yukseklik':
                    # En yakın köşeyi bul
                    kenar = ozel.get('kenar_uzerinde', '')
                    if len(kenar) == 2:
                        self._draw_right_angle(ax, bit_coord, coords[bas], coords[kenar[0]])
                
                # Bitiş noktası
                bit_isim = ozel.get('bitis', 'H')
                if bit_isim not in coords:
                    self._draw_point(ax, bit_coord[0], bit_coord[1], bit_isim, 
                                   color=renk, size=60, offset=(5, -15))
        
        # Ana noktalar
        point_colors = [Config.COLORS['highlight'], '#16a34a', '#2563eb']
        offsets = [(0, 10), (-15, -10), (10, -10)]
        
        for i, (isim, coord) in enumerate([(A, pA), (B, pB), (C, pC)]):
            color = point_colors[i % len(point_colors)]
            offset = offsets[i % len(offsets)]
            self._draw_point(ax, coord[0], coord[1], isim, color=color, offset=offset)
        
        # Ek etiketler
        for ek in analysis.get('ek_etiketler', []):
            metin = ek.get('metin', '')
            konum = ek.get('konum', 'sag_ust')
            
            # Konum belirleme
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            
            if konum == 'sag_ust':
                x, y = xlim[1] * 0.7, ylim[1] * 0.9
            elif konum == 'sol_ust':
                x, y = xlim[0] * 0.7, ylim[1] * 0.9
            else:
                x, y = 0, ylim[1] * 0.9
            
            ax.annotate(metin, (x, y), fontsize=12, fontweight='bold',
                       color=Config.COLORS['text'],
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='#fef3c7',
                                edgecolor='#f59e0b', alpha=0.9))
        
        return self._finalize_figure(fig, ax)
    
    def _render_quadrilateral(self, analysis: Dict) -> bytes:
        """Dörtgen çiz"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        noktalar = list(coords.keys())
        
        if len(noktalar) < 4:
            logger.warning("Dörtgen için en az 4 nokta gerekli")
            # 4'ten az varsa üçgen olarak çiz
            if len(noktalar) >= 3:
                return self._render_triangle(analysis)
            plt.close(fig)
            return None
        
        # İlk 4 noktayı al
        points = [coords[n] for n in noktalar[:4]]
        
        # Dörtgen çiz
        quad = patches.Polygon(points, fill=True,
                              facecolor=Config.COLORS['secondary'], alpha=0.1,
                              edgecolor=Config.COLORS['secondary'], linewidth=2.5)
        ax.add_patch(quad)
        
        # Kenar uzunlukları
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords and kenar.get('goster_uzunluk', True):
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    self._draw_length_label(ax, coords[bas], coords[bit], uzunluk,
                                          color=Config.COLORS['secondary'])
        
        # Açılar
        for aci in analysis.get('acilar', []):
            kose = aci.get('kose')
            if kose in coords and aci.get('goster', True):
                # Köşenin komşu noktalarını bul
                idx = noktalar.index(kose)
                onceki = noktalar[(idx - 1) % 4]
                sonraki = noktalar[(idx + 1) % 4]
                
                if aci.get('dik_aci', False):
                    self._draw_right_angle(ax, coords[kose], coords[onceki], coords[sonraki],
                                          color=Config.COLORS['secondary'])
                else:
                    deger = aci.get('deger', '')
                    self._draw_angle_arc(ax, coords[kose], coords[onceki], coords[sonraki],
                                        label=deger, color=Config.COLORS['angle'])
        
        # Noktalar
        for i, isim in enumerate(noktalar[:4]):
            coord = coords[isim]
            offset_options = [(0, 10), (-15, 5), (0, -15), (15, 5)]
            self._draw_point(ax, coord[0], coord[1], isim,
                           color=Config.COLORS['secondary'],
                           offset=offset_options[i % 4])
        
        return self._finalize_figure(fig, ax)
    
    def _render_circle(self, analysis: Dict) -> bytes:
        """Çember/Daire çiz"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        
        # Daireleri çiz
        for daire in analysis.get('daireler', []):
            merkez_isim = daire.get('merkez', 'O')
            if merkez_isim in coords:
                mx, my = coords[merkez_isim]
            else:
                mx, my = 0, 0
            
            yaricap = float(daire.get('yaricap', 3))
            
            # Çember
            circle = MplCircle((mx, my), yaricap, fill=False,
                              edgecolor=Config.COLORS['primary'], linewidth=2.5)
            ax.add_patch(circle)
            
            # Dolgu (isteğe bağlı)
            circle_fill = MplCircle((mx, my), yaricap, fill=True,
                                    facecolor=Config.COLORS['primary'], alpha=0.1)
            ax.add_patch(circle_fill)
            
            # Merkez noktası
            self._draw_point(ax, mx, my, merkez_isim, color=Config.COLORS['primary'])
            
            # Yarıçap gösterimi
            if daire.get('yaricap_goster', True):
                # Yarıçap çizgisi
                rx, ry = mx + yaricap, my
                self._draw_line(ax, (mx, my), (rx, ry), color=Config.COLORS['auxiliary'],
                              linestyle='--', linewidth=2)
                
                # Yarıçap etiketi
                etiket = daire.get('yaricap_etiketi', f'r = {yaricap}')
                self._draw_length_label(ax, (mx, my), (rx, ry), etiket,
                                       color=Config.COLORS['auxiliary'])
        
        # Diğer noktalar (çember üzerindeki noktalar vb.)
        for isim, coord in coords.items():
            if isim not in [d.get('merkez', 'O') for d in analysis.get('daireler', [])]:
                self._draw_point(ax, coord[0], coord[1], isim, color=Config.COLORS['highlight'])
        
        # Kenarlar (kiriş, teğet vb.)
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords:
                self._draw_line(ax, coords[bas], coords[bit],
                              color=Config.COLORS['highlight'], linewidth=2)
                
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk and kenar.get('goster_uzunluk', True):
                    self._draw_length_label(ax, coords[bas], coords[bit], uzunluk)
        
        return self._finalize_figure(fig, ax)
    
    def _render_analytic(self, analysis: Dict) -> bytes:
        """Koordinat düzleminde çizim"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        
        # Koordinat eksenleri
        xlim = (-10, 10)
        ylim = (-10, 10)
        
        # X ekseni
        ax.axhline(y=0, color='#64748b', linewidth=1.5, zorder=1)
        ax.axvline(x=0, color='#64748b', linewidth=1.5, zorder=1)
        
        # Eksen etiketleri
        ax.annotate('x', (xlim[1] - 0.5, 0.3), fontsize=12, fontweight='bold', color='#64748b')
        ax.annotate('y', (0.3, ylim[1] - 0.5), fontsize=12, fontweight='bold', color='#64748b')
        ax.annotate('O', (-0.5, -0.5), fontsize=10, color='#64748b')
        
        # Noktalar
        for isim, coord in coords.items():
            self._draw_point(ax, coord[0], coord[1], isim, color=Config.COLORS['highlight'])
            
            # Koordinat etiketi
            ax.annotate(f'({coord[0]:.0f}, {coord[1]:.0f})', (coord[0], coord[1]),
                       xytext=(10, -15), textcoords='offset points',
                       fontsize=9, color='#64748b')
        
        # Doğrular/Kenarlar
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords:
                self._draw_line(ax, coords[bas], coords[bit],
                              color=Config.COLORS['primary'], linewidth=2)
        
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        
        # Grid'i daha belirgin yap
        ax.grid(True, alpha=0.5, linestyle='-', color=Config.COLORS['grid'])
        ax.set_xticks(range(-10, 11, 2))
        ax.set_yticks(range(-10, 11, 2))
        
        return self._finalize_figure(fig, ax)
    
    def _render_polygon(self, analysis: Dict) -> bytes:
        """Çokgen çiz (5gen, 6gen, vb.)"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        noktalar = list(coords.keys())
        
        if len(noktalar) < 3:
            plt.close(fig)
            return None
        
        # Tüm noktaları al
        points = [coords[n] for n in noktalar]
        
        # Çokgen çiz
        poly = patches.Polygon(points, fill=True,
                              facecolor=Config.COLORS['primary'], alpha=0.1,
                              edgecolor=Config.COLORS['primary'], linewidth=2.5)
        ax.add_patch(poly)
        
        # Noktalar
        for isim in noktalar:
            coord = coords[isim]
            self._draw_point(ax, coord[0], coord[1], isim, color=Config.COLORS['primary'])
        
        # Kenar uzunlukları
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords and kenar.get('goster_uzunluk', True):
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    self._draw_length_label(ax, coords[bas], coords[bit], uzunluk)
        
        return self._finalize_figure(fig, ax)


# ============== ANA BOT ==============

class GeometryBot:
    """Ana geometri görsel botu"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.analyzer = GeminiAnalyzer()
        self.renderer = GeometryRenderer()
        
        self.stats = {
            'total': 0,
            'success': 0,
            'skipped': 0,
            'failed': 0
        }
    
    def run(self):
        """Botu çalıştır"""
        logger.info("="*60)
        logger.info("GEOMETRİ GÖRSEL BOTU BAŞLADI")
        logger.info("="*60)
        
        # Batch boyutunu belirle
        batch_size = Config.TEST_BATCH_SIZE if Config.TEST_MODE else Config.BATCH_SIZE
        logger.info(f"Mod: {'TEST' if Config.TEST_MODE else 'PRODUCTION'}")
        logger.info(f"Batch boyutu: {batch_size}")
        
        # Soruları çek
        questions = self.db.get_geometry_questions(batch_size)
        
        if not questions:
            logger.warning("İşlenecek geometri sorusu bulunamadı!")
            return
        
        self.stats['total'] = len(questions)
        logger.info(f"İşlenecek soru sayısı: {len(questions)}")
        
        # Her soruyu işle
        for i, question in enumerate(questions):
            logger.info(f"\n--- Soru {i+1}/{len(questions)} (ID: {question['id']}) ---")
            self._process_question(question)
            
            # Rate limiting
            time.sleep(1)
        
        # Sonuçları raporla
        self._report_results()
    
    def _process_question(self, question: Dict):
        """Tek bir soruyu işle"""
        question_id = question['id']
        question_text = question.get('original_text', '')
        
        if not question_text:
            logger.warning(f"Soru #{question_id}: Metin boş, atlandı")
            self.stats['skipped'] += 1
            return
        
        # 1. Gemini ile analiz
        logger.info("Gemini analizi yapılıyor...")
        analysis = self.analyzer.analyze_question(question_text)
        
        if not analysis:
            logger.warning(f"Soru #{question_id}: Analiz başarısız veya çizilemez")
            self.stats['skipped'] += 1
            return
        
        logger.info(f"Şekil tipi: {analysis.get('sekil_tipi', 'bilinmiyor')}")
        
        # 2. Görsel oluştur
        logger.info("Görsel oluşturuluyor...")
        image_bytes = self.renderer.render(analysis)
        
        if not image_bytes:
            logger.error(f"Soru #{question_id}: Görsel oluşturulamadı")
            self.stats['failed'] += 1
            return
        
        # 3. Storage'a yükle
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"geometry/q_{question_id}_{timestamp}.png"
        
        logger.info("Storage'a yükleniyor...")
        image_url = self.db.upload_image(image_bytes, filename)
        
        if not image_url:
            logger.error(f"Soru #{question_id}: Yükleme başarısız")
            self.stats['failed'] += 1
            return
        
        # 4. Veritabanını güncelle
        logger.info("Veritabanı güncelleniyor...")
        success = self.db.update_image_url(question_id, image_url)
        
        if success:
            logger.info(f"✅ Soru #{question_id}: BAŞARILI")
            self.stats['success'] += 1
        else:
            logger.error(f"Soru #{question_id}: Güncelleme başarısız")
            self.stats['failed'] += 1
    
    def _report_results(self):
        """Sonuç raporu"""
        logger.info("\n" + "="*60)
        logger.info("SONUÇ RAPORU")
        logger.info("="*60)
        logger.info(f"Toplam soru: {self.stats['total']}")
        logger.info(f"✅ Başarılı: {self.stats['success']}")
        logger.info(f"⏭️  Atlanan: {self.stats['skipped']}")
        logger.info(f"❌ Başarısız: {self.stats['failed']}")
        
        if self.stats['total'] > 0:
            success_rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"Başarı oranı: %{success_rate:.1f}")
        
        logger.info("="*60)


# ============== ÇALIŞTIR ==============

if __name__ == "__main__":
    try:
        bot = GeometryBot()
        bot.run()
    except Exception as e:
        logger.error(f"Bot hatası: {e}")
        raise
