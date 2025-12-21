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
    
    ANALYSIS_PROMPT = """Sen bir geometri soru analiz uzmanısın. Görevin geometri sorularını görselleştirmek için analiz etmek.

GÖREV: Verilen geometri sorusunu analiz et ve çizim için gerekli bilgileri JSON formatında çıkar.

KRİTİK KURAL - ÇİZİM KARARI:
Aşağıdaki durumlarda KESİNLİKLE "cizim_pisinilir": true olmalı:
- Soruda üçgen, dörtgen, çember, kare, dikdörtgen, paralelkenar geçiyorsa → ÇİZ
- Soruda A, B, C gibi köşe noktaları varsa → ÇİZ
- Soruda kenar uzunluğu, açı ölçüsü, alan, çevre verilmişse → ÇİZ
- Soruda yükseklik, kenarortay, açıortay geçiyorsa → ÇİZ
- Soruda prizma, piramit, silindir, koni, küre geçiyorsa → ÇİZ
- Soruda koordinat düzlemi, nokta, doğru geçiyorsa → ÇİZ
- Hesaplama gerektirse bile şekil varsa → ÇİZ

SADECE şu durumlarda "cizim_pisinilir": false:
- Soruda hiçbir geometrik şekil veya figür yoksa
- Tamamen cebirsel/sayısal bir problemse (örn: "3x + 5 = 11")

ÖRNEK: "ABC üçgeninin alanı 48 cm², taban 8 cm ise yükseklik kaçtır?" 
→ Bu soru ÇİZİLMELİ çünkü üçgen var, alan ve taban verilmiş, yükseklik sorulmuş.

ÖNEMLİ KURALLAR:
1. Sadece VERİLENLERİ çıkar - ÇÖZÜMÜ YAPMA!
2. Bilinmeyenleri "?" ile işaretle
3. Koordinatları mantıklı ve dengeli belirle (görsel güzel görünsün)
4. Nokta isimlerini soruda geçtiği gibi kullan (A, B, C, vb.)
5. Türkçe karakterleri düzgün kullan
6. Şüphe durumunda ÇİZ!

DESTEKLENEN ŞEKİL TİPLERİ:
- ucgen: Üçgen (genel, dik, ikizkenar, eşkenar)
- dortgen: Dörtgen (kare, dikdörtgen, paralelkenar, yamuk, eşkenar dörtgen)
- cember: Çember/Daire
- analitik: Koordinat düzleminde nokta/doğru
- cokgen: Çokgen (beşgen, altıgen, vb.)
- kati_cisim: 3D katı cisimler (alt_tip belirt: kup, prizma, silindir, koni, kure, piramit)

ÖNEMLİ: Katı cisimler için:
- Soruda küp, prizma, silindir, koni, küre, piramit geçiyorsa → sekil_tipi: "kati_cisim"
- alt_tip alanına cisim türünü yaz: "kup", "prizma", "silindir", "koni", "kure", "piramit"
- Boyutları kenarlar listesinde belirt (uzunluk, genişlik, yükseklik, yarıçap vb.)

JSON ÇIKTI FORMATI:
{
  "cizim_pisinilir": true,
  "neden": "",
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
- Geometri sorusu ise MUTLAKA çizim yap, hesaplama gerektirse bile!
- Koordinatlar -10 ile 10 arasında olsun
- Şekil merkezi (0,0) civarında olsun
- Eğer soruda şekil tipi belirsizse, en uygun olanı seç ve çiz

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
            
            # Çizilebilirlik kontrolü - geometri sorusu ise çiz
            if not result.get('cizim_pisinilir', True):
                # Yine de şekil tipi varsa çiz
                if result.get('sekil_tipi') and result.get('noktalar'):
                    logger.info("Şekil bilgisi mevcut, çizim yapılacak")
                    result['cizim_pisinilir'] = True
                else:
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
            alt_tip = analysis.get('alt_tip', 'genel')
            
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
            elif sekil_tipi == 'kati_cisim' or alt_tip in ['prizma', 'piramit', 'silindir', 'koni', 'kure', 'kup']:
                return self._render_3d_solid(analysis)
            else:
                logger.warning(f"Bilinmeyen şekil tipi: {sekil_tipi}")
                return self._render_triangle(analysis)
                
        except Exception as e:
            logger.error(f"Çizim hatası: {e}")
            import traceback
            traceback.print_exc()
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
        """Üçgen çiz - tek veya çoklu üçgen desteği"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        noktalar = list(coords.keys())
        
        # Ek etiketleri kontrol et - birden fazla üçgen var mı?
        ek_etiketler = analysis.get('ek_etiketler', [])
        coklu_ucgen = any('üçgen' in str(e.get('metin', '')).lower() for e in ek_etiketler)
        
        if len(noktalar) < 3:
            logger.warning("Üçgen için en az 3 nokta gerekli")
            plt.close(fig)
            return None
        
        # Birden fazla üçgen varsa yan yana çiz
        if len(noktalar) >= 6 or coklu_ucgen:
            return self._render_multiple_triangles(analysis)
        
        # Tek üçgen çizimi
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
                if 'bitis_koordinat' in ozel:
                    bit_coord = tuple(ozel['bitis_koordinat'])
                elif ozel.get('bitis') in coords:
                    bit_coord = coords[ozel['bitis']]
                else:
                    kenar = ozel.get('kenar_uzerinde', '')
                    if len(kenar) == 2 and kenar[0] in coords and kenar[1] in coords:
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
                
                renk = Config.COLORS['highlight'] if tip == 'yukseklik' else Config.COLORS['auxiliary']
                stil = '-' if tip == 'yukseklik' else '--'
                self._draw_line(ax, coords[bas], bit_coord, color=renk, linestyle=stil, linewidth=2)
                
                etiket = ozel.get('etiket', '')
                if etiket:
                    self._draw_length_label(ax, coords[bas], bit_coord, etiket, color=renk)
                
                if tip == 'yukseklik':
                    kenar = ozel.get('kenar_uzerinde', '')
                    if len(kenar) == 2:
                        self._draw_right_angle(ax, bit_coord, coords[bas], coords[kenar[0]])
                
                bit_isim = ozel.get('bitis', 'H')
                if bit_isim not in coords:
                    self._draw_point(ax, bit_coord[0], bit_coord[1], bit_isim, 
                                   color=renk, size=60, offset=(5, -15))
        
        # Ana noktalar - daha iyi offset hesaplama
        for i, (isim, coord) in enumerate([(A, pA), (B, pB), (C, pC)]):
            # Üçgenin merkezini hesapla
            center_x = (pA[0] + pB[0] + pC[0]) / 3
            center_y = (pA[1] + pB[1] + pC[1]) / 3
            
            # Noktadan merkeze vektör (ters yönde offset)
            dx = coord[0] - center_x
            dy = coord[1] - center_y
            norm = np.sqrt(dx**2 + dy**2)
            if norm > 0:
                offset = (int(dx/norm * 15), int(dy/norm * 15))
            else:
                offset = (5, 5)
            
            point_colors = [Config.COLORS['highlight'], '#16a34a', '#2563eb']
            color = point_colors[i % len(point_colors)]
            self._draw_point(ax, coord[0], coord[1], isim, color=color, offset=offset)
        
        # Ek etiketler
        for ek in analysis.get('ek_etiketler', []):
            metin = ek.get('metin', '')
            konum = ek.get('konum', 'sag_ust')
            
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            
            if konum == 'sag_ust':
                x, y = xlim[1] * 0.7, ylim[1] * 0.9
            elif konum == 'sol_ust':
                x, y = xlim[0] + (xlim[1]-xlim[0]) * 0.2, ylim[1] * 0.9
            else:
                x, y = (xlim[0] + xlim[1]) / 2, ylim[1] * 0.9
            
            ax.annotate(metin, (x, y), fontsize=12, fontweight='bold',
                       color=Config.COLORS['text'],
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='#fef3c7',
                                edgecolor='#f59e0b', alpha=0.9))
        
        return self._finalize_figure(fig, ax)
    
    def _render_multiple_triangles(self, analysis: Dict) -> bytes:
        """Birden fazla üçgen çiz (yan yana)"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        ek_etiketler = analysis.get('ek_etiketler', [])
        
        # Üçgen isimlerini bul
        ucgen_isimleri = []
        for ek in ek_etiketler:
            metin = ek.get('metin', '')
            if 'üçgen' in metin.lower():
                ucgen_isimleri.append(metin)
        
        if len(ucgen_isimleri) < 2:
            ucgen_isimleri = ['Üçgen 1', 'Üçgen 2']
        
        # İki üçgen için koordinatlar
        # Sol üçgen
        offset1 = -4
        t1_coords = {
            'A1': (offset1 + 2, 4),
            'B1': (offset1, 0),
            'C1': (offset1 + 4, 0)
        }
        
        # Sağ üçgen
        offset2 = 4
        t2_coords = {
            'A2': (offset2 + 2, 4),
            'B2': (offset2, 0),
            'C2': (offset2 + 4, 0)
        }
        
        colors = [Config.COLORS['primary'], Config.COLORS['secondary']]
        
        # Kenar bilgilerini ayır
        kenarlar = analysis.get('kenarlar', [])
        
        # Sol üçgen çiz
        t1 = patches.Polygon([t1_coords['A1'], t1_coords['B1'], t1_coords['C1']], 
                            fill=True, facecolor=colors[0], alpha=0.1,
                            edgecolor=colors[0], linewidth=2.5)
        ax.add_patch(t1)
        
        # Sağ üçgen çiz
        t2 = patches.Polygon([t2_coords['A2'], t2_coords['B2'], t2_coords['C2']], 
                            fill=True, facecolor=colors[1], alpha=0.1,
                            edgecolor=colors[1], linewidth=2.5)
        ax.add_patch(t2)
        
        # Üçgen başlıkları
        ax.annotate(ucgen_isimleri[0], (offset1 + 2, 5), fontsize=11, fontweight='bold',
                   color=colors[0], ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=colors[0]))
        
        ax.annotate(ucgen_isimleri[1], (offset2 + 2, 5), fontsize=11, fontweight='bold',
                   color=colors[1], ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=colors[1]))
        
        # Kenar uzunlukları - ilk yarısı sol üçgene, ikinci yarısı sağ üçgene
        mid = len(kenarlar) // 2 if len(kenarlar) > 1 else len(kenarlar)
        
        # Sol üçgen kenarları
        if mid > 0 and kenarlar:
            # Taban
            uzunluk = kenarlar[0].get('uzunluk', '')
            if uzunluk:
                self._draw_length_label(ax, t1_coords['B1'], t1_coords['C1'], uzunluk, color=colors[0])
        
        if mid > 1 and len(kenarlar) > 1:
            # Yükseklik
            uzunluk = kenarlar[1].get('uzunluk', '')
            if uzunluk:
                # Yükseklik çiz
                h_foot = (offset1 + 2, 0)
                self._draw_line(ax, t1_coords['A1'], h_foot, color=Config.COLORS['highlight'], linewidth=2)
                self._draw_length_label(ax, t1_coords['A1'], h_foot, uzunluk, color=Config.COLORS['highlight'])
                self._draw_right_angle(ax, h_foot, t1_coords['A1'], t1_coords['B1'], size=0.3)
        
        # Sağ üçgen kenarları
        if len(kenarlar) > mid:
            uzunluk = kenarlar[mid].get('uzunluk', '') if len(kenarlar) > mid else ''
            if uzunluk:
                self._draw_length_label(ax, t2_coords['B2'], t2_coords['C2'], uzunluk, color=colors[1])
        
        # Sağ üçgen yüksekliği (bilinmeyen)
        h_foot2 = (offset2 + 2, 0)
        self._draw_line(ax, t2_coords['A2'], h_foot2, color=Config.COLORS['highlight'], 
                       linewidth=2, linestyle='--')
        self._draw_length_label(ax, t2_coords['A2'], h_foot2, 'h = ?', color=Config.COLORS['unknown'])
        self._draw_right_angle(ax, h_foot2, t2_coords['A2'], t2_coords['B2'], size=0.3, 
                              color=Config.COLORS['highlight'])
        
        # Noktalar
        for isim, coord in t1_coords.items():
            self._draw_point(ax, coord[0], coord[1], isim[0], color=colors[0], size=60)
        
        for isim, coord in t2_coords.items():
            self._draw_point(ax, coord[0], coord[1], isim[0], color=colors[1], size=60)
        
        # H noktaları
        self._draw_point(ax, offset1 + 2, 0, 'H', color=Config.COLORS['highlight'], size=50, offset=(5, -15))
        self._draw_point(ax, offset2 + 2, 0, 'H', color=Config.COLORS['highlight'], size=50, offset=(5, -15))
        
        return self._finalize_figure(fig, ax)
    
    def _render_quadrilateral(self, analysis: Dict) -> bytes:
        """Dörtgen çiz - geliştirilmiş açı gösterimi"""
        fig, ax = self._create_figure()
        
        coords = self._get_point_coords(analysis)
        noktalar = list(coords.keys())
        
        if len(noktalar) < 4:
            logger.warning("Dörtgen için en az 4 nokta gerekli")
            if len(noktalar) >= 3:
                return self._render_triangle(analysis)
            plt.close(fig)
            return None
        
        # İlk 4 noktayı al
        points = [coords[n] for n in noktalar[:4]]
        
        # Dörtgen çiz
        quad = patches.Polygon(points, fill=True,
                              facecolor=Config.COLORS['secondary'], alpha=0.15,
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
        
        # Açılar - geliştirilmiş konumlandırma
        for aci in analysis.get('acilar', []):
            kose = aci.get('kose')
            if kose in coords and aci.get('goster', True):
                idx = noktalar.index(kose)
                onceki = noktalar[(idx - 1) % 4]
                sonraki = noktalar[(idx + 1) % 4]
                
                if aci.get('dik_aci', False):
                    self._draw_right_angle(ax, coords[kose], coords[onceki], coords[sonraki],
                                          color=Config.COLORS['secondary'], size=0.5)
                else:
                    deger = aci.get('deger', '')
                    # Açı yayı çiz - daha büyük radius
                    self._draw_angle_arc_improved(ax, coords[kose], coords[onceki], coords[sonraki],
                                                 radius=0.7, label=deger)
        
        # Noktalar - merkeze göre offset hesapla
        center_x = sum(p[0] for p in points) / 4
        center_y = sum(p[1] for p in points) / 4
        
        for i, isim in enumerate(noktalar[:4]):
            coord = coords[isim]
            # Merkezden uzağa doğru offset
            dx = coord[0] - center_x
            dy = coord[1] - center_y
            norm = np.sqrt(dx**2 + dy**2)
            if norm > 0:
                offset = (int(dx/norm * 18), int(dy/norm * 18))
            else:
                offset = (10, 10)
            
            self._draw_point(ax, coord[0], coord[1], isim,
                           color=Config.COLORS['secondary'], offset=offset)
        
        return self._finalize_figure(fig, ax)
    
    def _draw_angle_arc_improved(self, ax, vertex: tuple, p1: tuple, p2: tuple,
                                  radius: float = 0.6, color: str = None, label: str = None):
        """Geliştirilmiş açı yayı - etiket köşeye yakın"""
        color = color or Config.COLORS['angle']
        
        vx, vy = vertex
        
        # Açıları hesapla
        angle1 = np.degrees(np.arctan2(p1[1] - vy, p1[0] - vx))
        angle2 = np.degrees(np.arctan2(p2[1] - vy, p2[0] - vx))
        
        # Açıları normalize et
        if angle1 < 0:
            angle1 += 360
        if angle2 < 0:
            angle2 += 360
        
        # Küçük açıyı bul
        diff = abs(angle2 - angle1)
        if diff > 180:
            diff = 360 - diff
            if angle1 < angle2:
                angle1, angle2 = angle2, angle1
        else:
            if angle1 > angle2:
                angle1, angle2 = angle2, angle1
        
        arc = Arc((vx, vy), radius*2, radius*2, angle=0,
                 theta1=angle1, theta2=angle2, color=color, linewidth=2.5, zorder=4)
        ax.add_patch(arc)
        
        if label:
            # Etiket açının ortasında, köşeye yakın
            mid_angle = np.radians((angle1 + angle2) / 2)
            # Radius'un biraz dışında
            label_radius = radius * 1.8
            lx = vx + label_radius * np.cos(mid_angle)
            ly = vy + label_radius * np.sin(mid_angle)
            
            ax.annotate(label, (lx, ly), fontsize=12, color=color,
                       fontweight='bold', ha='center', va='center',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                edgecolor=color, alpha=0.9))
    
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
    
    def _render_3d_solid(self, analysis: Dict) -> bytes:
        """3D katı cisim çiz (izometrik görünüm)"""
        fig, ax = self._create_figure()
        
        alt_tip = analysis.get('alt_tip', 'kup').lower()
        
        # İzometrik açılar
        iso_angle = np.radians(30)  # 30 derece
        
        if alt_tip in ['kup', 'küp', 'kare_prizma']:
            return self._render_cube(analysis, fig, ax)
        elif alt_tip in ['dikdortgen_prizma', 'prizma']:
            return self._render_rectangular_prism(analysis, fig, ax)
        elif alt_tip in ['silindir', 'cylinder']:
            return self._render_cylinder(analysis, fig, ax)
        elif alt_tip in ['koni', 'cone']:
            return self._render_cone(analysis, fig, ax)
        elif alt_tip in ['kure', 'küre', 'sphere']:
            return self._render_sphere(analysis, fig, ax)
        elif alt_tip in ['piramit', 'pyramid']:
            return self._render_pyramid(analysis, fig, ax)
        else:
            # Varsayılan: dikdörtgen prizma
            return self._render_rectangular_prism(analysis, fig, ax)
    
    def _render_cube(self, analysis: Dict, fig, ax) -> bytes:
        """Küp çiz - izometrik"""
        # Küp boyutu
        kenarlar = analysis.get('kenarlar', [])
        a = 4  # Varsayılan kenar
        if kenarlar:
            try:
                a_str = kenarlar[0].get('uzunluk', '4')
                a = float(''.join(c for c in a_str if c.isdigit() or c == '.') or '4')
                a = min(a, 6)  # Maksimum 6 birim
            except:
                a = 4
        
        # İzometrik dönüşüm
        def iso(x, y, z):
            iso_x = (x - y) * np.cos(np.radians(30))
            iso_y = (x + y) * np.sin(np.radians(30)) + z
            return iso_x, iso_y
        
        # Küp köşeleri
        vertices = {
            'A': iso(0, 0, 0),      # Ön-sol-alt
            'B': iso(a, 0, 0),      # Ön-sağ-alt
            'C': iso(a, a, 0),      # Arka-sağ-alt
            'D': iso(0, a, 0),      # Arka-sol-alt
            'E': iso(0, 0, a),      # Ön-sol-üst
            'F': iso(a, 0, a),      # Ön-sağ-üst
            'G': iso(a, a, a),      # Arka-sağ-üst
            'H': iso(0, a, a),      # Arka-sol-üst
        }
        
        # Arka yüzeyler (önce çiz, silik)
        back_faces = [
            [vertices['D'], vertices['C'], vertices['G'], vertices['H']],  # Arka yüz
            [vertices['A'], vertices['D'], vertices['H'], vertices['E']],  # Sol yüz
            [vertices['E'], vertices['F'], vertices['G'], vertices['H']],  # Üst yüz
        ]
        
        for face in back_faces:
            poly = patches.Polygon(face, fill=True, facecolor='#e0f2fe', 
                                  edgecolor='#0284c7', linewidth=1.5, alpha=0.5)
            ax.add_patch(poly)
        
        # Ön yüzeyler (sonra çiz, belirgin)
        front_faces = [
            [vertices['A'], vertices['B'], vertices['F'], vertices['E']],  # Ön yüz
            [vertices['B'], vertices['C'], vertices['G'], vertices['F']],  # Sağ yüz
            [vertices['A'], vertices['B'], vertices['C'], vertices['D']],  # Alt yüz
        ]
        
        colors = ['#dbeafe', '#bfdbfe', '#93c5fd']
        for i, face in enumerate(front_faces):
            poly = patches.Polygon(face, fill=True, facecolor=colors[i % 3], 
                                  edgecolor='#1d4ed8', linewidth=2, alpha=0.8)
            ax.add_patch(poly)
        
        # Görünür kenarlar (kalın)
        visible_edges = [
            ('A', 'B'), ('B', 'C'), ('B', 'F'),
            ('A', 'E'), ('E', 'F'), ('F', 'G'),
            ('E', 'H'), ('A', 'D')
        ]
        
        for v1, v2 in visible_edges:
            ax.plot([vertices[v1][0], vertices[v2][0]], 
                   [vertices[v1][1], vertices[v2][1]], 
                   color='#1d4ed8', linewidth=2.5, zorder=5)
        
        # Gizli kenarlar (kesikli)
        hidden_edges = [
            ('D', 'C'), ('D', 'H'), ('C', 'G'), ('H', 'G')
        ]
        
        for v1, v2 in hidden_edges:
            ax.plot([vertices[v1][0], vertices[v2][0]], 
                   [vertices[v1][1], vertices[v2][1]], 
                   color='#64748b', linewidth=1, linestyle='--', zorder=3)
        
        # Köşe noktaları ve etiketleri
        visible_vertices = ['A', 'B', 'C', 'E', 'F', 'G']
        for v in visible_vertices:
            ax.scatter([vertices[v][0]], [vertices[v][1]], c='#1d4ed8', s=50, zorder=6)
            
            # Etiket offset
            if v in ['E', 'F', 'G', 'H']:
                offset = (3, 8)
            else:
                offset = (3, -12)
            
            ax.annotate(v, vertices[v], xytext=offset, textcoords='offset points',
                       fontsize=12, fontweight='bold', color='#1d4ed8')
        
        # Kenar uzunluğu etiketi
        kenar_str = kenarlar[0].get('uzunluk', f'{a} cm') if kenarlar else f'{a} cm'
        mid_x = (vertices['A'][0] + vertices['B'][0]) / 2
        mid_y = (vertices['A'][1] + vertices['B'][1]) / 2 - 0.5
        ax.annotate(kenar_str, (mid_x, mid_y), fontsize=11, fontweight='bold',
                   color='#1e40af', ha='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#3b82f6'))
        
        ax.set_aspect('equal')
        ax.axis('off')
        
        return self._finalize_figure(fig, ax)
    
    def _render_rectangular_prism(self, analysis: Dict, fig, ax) -> bytes:
        """Dikdörtgenler prizması çiz"""
        kenarlar = analysis.get('kenarlar', [])
        
        # Boyutlar
        a, b, c = 5, 3, 4  # Varsayılan
        
        if len(kenarlar) >= 3:
            try:
                dims = []
                for k in kenarlar[:3]:
                    val_str = k.get('uzunluk', '4')
                    val = float(''.join(ch for ch in val_str if ch.isdigit() or ch == '.') or '4')
                    dims.append(min(val, 6))
                a, b, c = dims[0], dims[1], dims[2]
            except:
                pass
        
        def iso(x, y, z):
            iso_x = (x - y) * np.cos(np.radians(30))
            iso_y = (x + y) * np.sin(np.radians(30)) + z
            return iso_x, iso_y
        
        vertices = {
            'A': iso(0, 0, 0), 'B': iso(a, 0, 0), 'C': iso(a, b, 0), 'D': iso(0, b, 0),
            'E': iso(0, 0, c), 'F': iso(a, 0, c), 'G': iso(a, b, c), 'H': iso(0, b, c),
        }
        
        # Yüzeyler
        faces = [
            ([vertices['A'], vertices['B'], vertices['F'], vertices['E']], '#dbeafe'),
            ([vertices['B'], vertices['C'], vertices['G'], vertices['F']], '#bfdbfe'),
            ([vertices['E'], vertices['F'], vertices['G'], vertices['H']], '#93c5fd'),
        ]
        
        for face, color in faces:
            poly = patches.Polygon(face, fill=True, facecolor=color, 
                                  edgecolor='#1d4ed8', linewidth=2, alpha=0.8)
            ax.add_patch(poly)
        
        # Gizli kenarlar
        for v1, v2 in [('D', 'C'), ('D', 'H'), ('D', 'A')]:
            ax.plot([vertices[v1][0], vertices[v2][0]], 
                   [vertices[v1][1], vertices[v2][1]], 
                   color='#94a3b8', linewidth=1, linestyle='--')
        
        # Boyut etiketleri
        labels = [
            (vertices['A'], vertices['B'], f'{a} cm'),
            (vertices['B'], vertices['C'], f'{b} cm'),
            (vertices['A'], vertices['E'], f'{c} cm'),
        ]
        
        for p1, p2, label in labels:
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            ax.annotate(label, (mx, my), fontsize=10, fontweight='bold',
                       color='#1e40af', ha='center',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='#3b82f6', alpha=0.9))
        
        ax.set_aspect('equal')
        ax.axis('off')
        
        return self._finalize_figure(fig, ax)
    
    def _render_cylinder(self, analysis: Dict, fig, ax) -> bytes:
        """Silindir çiz"""
        kenarlar = analysis.get('kenarlar', [])
        
        r, h = 2, 4  # Varsayılan yarıçap ve yükseklik
        
        # Elips parametreleri (üstten bakış için)
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Alt elips
        x_bottom = r * np.cos(theta)
        y_bottom = r * 0.3 * np.sin(theta)  # Perspektif için sıkıştırılmış
        
        # Üst elips
        x_top = x_bottom
        y_top = y_bottom + h
        
        # Silindir gövdesi (dolu)
        ax.fill_between(x_bottom, y_bottom, y_top, alpha=0.3, color='#3b82f6')
        
        # Alt elips (ön yarısı görünür)
        ax.plot(x_bottom, y_bottom, color='#1d4ed8', linewidth=2)
        
        # Üst elips
        ax.plot(x_top, y_top, color='#1d4ed8', linewidth=2)
        ax.fill(x_top, y_top, alpha=0.5, color='#93c5fd')
        
        # Yan kenarlar
        ax.plot([-r, -r], [0, h], color='#1d4ed8', linewidth=2)
        ax.plot([r, r], [0, h], color='#1d4ed8', linewidth=2)
        
        # Yarıçap çizgisi
        ax.plot([0, r], [h, h], color='#ef4444', linewidth=2, linestyle='--')
        ax.annotate('r', (r/2, h + 0.3), fontsize=12, fontweight='bold', color='#ef4444', ha='center')
        
        # Yükseklik
        ax.annotate('', xy=(r + 0.5, h), xytext=(r + 0.5, 0),
                   arrowprops=dict(arrowstyle='<->', color='#22c55e', lw=2))
        ax.annotate('h', (r + 0.8, h/2), fontsize=12, fontweight='bold', color='#22c55e')
        
        # Kenar değerleri
        if kenarlar:
            for k in kenarlar:
                uzunluk = k.get('uzunluk', '')
                if 'r' in k.get('etiket', '').lower() or 'yarıçap' in k.get('etiket', '').lower():
                    ax.annotate(uzunluk, (r/2, h + 0.6), fontsize=11, fontweight='bold',
                               color='#ef4444', ha='center',
                               bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='#ef4444'))
        
        ax.set_aspect('equal')
        ax.axis('off')
        
        return self._finalize_figure(fig, ax)
    
    def _render_cone(self, analysis: Dict, fig, ax) -> bytes:
        """Koni çiz"""
        r, h = 2, 4
        
        theta = np.linspace(0, 2*np.pi, 100)
        x_base = r * np.cos(theta)
        y_base = r * 0.3 * np.sin(theta)
        
        # Taban elipsi
        ax.plot(x_base, y_base, color='#1d4ed8', linewidth=2)
        ax.fill(x_base, y_base, alpha=0.3, color='#93c5fd')
        
        # Koni yüzeyi
        ax.fill([0, -r, r, 0], [h, 0, 0, h], alpha=0.4, color='#3b82f6')
        ax.plot([0, -r], [h, 0], color='#1d4ed8', linewidth=2)
        ax.plot([0, r], [h, 0], color='#1d4ed8', linewidth=2)
        
        # Tepe noktası
        ax.scatter([0], [h], c='#ef4444', s=80, zorder=5)
        ax.annotate('T', (0.2, h + 0.2), fontsize=12, fontweight='bold', color='#ef4444')
        
        # Yükseklik (kesikli)
        ax.plot([0, 0], [0, h], color='#22c55e', linewidth=2, linestyle='--')
        ax.annotate('h', (0.3, h/2), fontsize=12, fontweight='bold', color='#22c55e')
        
        # Yarıçap
        ax.plot([0, r], [0, 0], color='#f59e0b', linewidth=2)
        ax.annotate('r', (r/2, -0.4), fontsize=12, fontweight='bold', color='#f59e0b', ha='center')
        
        ax.set_aspect('equal')
        ax.axis('off')
        
        return self._finalize_figure(fig, ax)
    
    def _render_sphere(self, analysis: Dict, fig, ax) -> bytes:
        """Küre çiz"""
        r = 3
        
        # Ana daire
        theta = np.linspace(0, 2*np.pi, 100)
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        
        ax.plot(x, y, color='#1d4ed8', linewidth=2.5)
        ax.fill(x, y, alpha=0.2, color='#3b82f6')
        
        # Yatay elips (ekvator)
        x_eq = r * np.cos(theta)
        y_eq = r * 0.3 * np.sin(theta)
        ax.plot(x_eq, y_eq, color='#1d4ed8', linewidth=1.5, linestyle='--')
        
        # Dikey elips
        y_vert = r * np.cos(theta)
        x_vert = r * 0.3 * np.sin(theta)
        ax.plot(x_vert, y_vert, color='#1d4ed8', linewidth=1.5, linestyle='--')
        
        # Merkez
        ax.scatter([0], [0], c='#ef4444', s=60, zorder=5)
        ax.annotate('O', (0.3, 0.3), fontsize=12, fontweight='bold', color='#ef4444')
        
        # Yarıçap
        ax.plot([0, r], [0, 0], color='#22c55e', linewidth=2)
        ax.annotate('r', (r/2, 0.4), fontsize=12, fontweight='bold', color='#22c55e', ha='center')
        
        ax.set_aspect('equal')
        ax.axis('off')
        
        return self._finalize_figure(fig, ax)
    
    def _render_pyramid(self, analysis: Dict, fig, ax) -> bytes:
        """Piramit çiz (kare tabanlı)"""
        a, h = 4, 5  # Taban kenarı ve yükseklik
        
        def iso(x, y, z):
            iso_x = (x - y) * np.cos(np.radians(30))
            iso_y = (x + y) * np.sin(np.radians(30)) + z
            return iso_x, iso_y
        
        # Taban köşeleri
        A = iso(0, 0, 0)
        B = iso(a, 0, 0)
        C = iso(a, a, 0)
        D = iso(0, a, 0)
        
        # Tepe noktası
        T = iso(a/2, a/2, h)
        
        # Taban
        base = patches.Polygon([A, B, C, D], fill=True, facecolor='#93c5fd', 
                              edgecolor='#1d4ed8', linewidth=2, alpha=0.5)
        ax.add_patch(base)
        
        # Görünür yan yüzler
        face1 = patches.Polygon([A, B, T], fill=True, facecolor='#dbeafe', 
                               edgecolor='#1d4ed8', linewidth=2, alpha=0.7)
        face2 = patches.Polygon([B, C, T], fill=True, facecolor='#bfdbfe', 
                               edgecolor='#1d4ed8', linewidth=2, alpha=0.7)
        ax.add_patch(face1)
        ax.add_patch(face2)
        
        # Gizli kenarlar
        ax.plot([D[0], T[0]], [D[1], T[1]], color='#94a3b8', linewidth=1.5, linestyle='--')
        ax.plot([C[0], D[0]], [C[1], D[1]], color='#94a3b8', linewidth=1.5, linestyle='--')
        ax.plot([D[0], A[0]], [D[1], A[1]], color='#94a3b8', linewidth=1.5, linestyle='--')
        
        # Yükseklik (kesikli)
        base_center = iso(a/2, a/2, 0)
        ax.plot([base_center[0], T[0]], [base_center[1], T[1]], 
               color='#22c55e', linewidth=2, linestyle='--')
        ax.annotate('h', (T[0] + 0.3, (base_center[1] + T[1])/2), 
                   fontsize=12, fontweight='bold', color='#22c55e')
        
        # Noktalar
        for name, point in [('A', A), ('B', B), ('C', C), ('T', T)]:
            ax.scatter([point[0]], [point[1]], c='#1d4ed8', s=50, zorder=5)
            offset = (5, 8) if name == 'T' else (5, -12)
            ax.annotate(name, point, xytext=offset, textcoords='offset points',
                       fontsize=12, fontweight='bold', color='#1d4ed8')
        
        ax.set_aspect('equal')
        ax.axis('off')
        
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
    
    def _create_default_triangle_analysis(self, question_text: str) -> Dict:
        """Varsayılan üçgen analizi oluştur"""
        import re
        
        # Metinden sayıları ve nokta isimlerini çıkarmaya çalış
        numbers = re.findall(r'\d+', question_text)
        points = re.findall(r'\b([A-Z])\b', question_text)
        
        # Varsayılan noktalar
        if len(points) >= 3:
            p1, p2, p3 = points[0], points[1], points[2]
        else:
            p1, p2, p3 = 'A', 'B', 'C'
        
        # Varsayılan kenar uzunlukları
        if len(numbers) >= 2:
            side1 = numbers[0]
            side2 = numbers[1] if len(numbers) > 1 else numbers[0]
        else:
            side1, side2 = '6', '8'
        
        # Soru metninden ne sorulduğunu anlamaya çalış
        text_lower = question_text.lower()
        bilinmeyen = '?'
        ozel_cizgiler = []
        
        if 'yükseklik' in text_lower or 'yüksekliği' in text_lower:
            ozel_cizgiler.append({
                "tip": "yukseklik",
                "baslangic": p1,
                "kenar_uzerinde": f"{p2}{p3}",
                "etiket": "h = ?"
            })
        
        return {
            "cizim_pisinilir": True,
            "sekil_tipi": "ucgen",
            "alt_tip": "genel",
            "noktalar": [
                {"isim": p1, "x": 3, "y": 5, "konum": "tepe"},
                {"isim": p2, "x": 0, "y": 0, "konum": "sol_alt"},
                {"isim": p3, "x": 6, "y": 0, "konum": "sag_alt"}
            ],
            "kenarlar": [
                {"baslangic": p2, "bitis": p3, "uzunluk": f"{side1} cm", "goster_uzunluk": True}
            ],
            "acilar": [],
            "ozel_cizgiler": ozel_cizgiler,
            "ek_etiketler": []
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
        topic = question.get('topic', '')
        
        if not question_text:
            logger.warning(f"Soru #{question_id}: Metin boş, atlandı")
            self.stats['skipped'] += 1
            return
        
        # 1. Gemini ile analiz
        logger.info("Gemini analizi yapılıyor...")
        analysis = self.analyzer.analyze_question(question_text)
        
        # Eğer analiz başarısız ama geometri konusuysa, varsayılan çizim yap
        if not analysis:
            # Konu geometri ile ilgiliyse basit bir şekil çiz
            geo_keywords = ['üçgen', 'dörtgen', 'çember', 'kare', 'dikdörtgen', 'alan', 'çevre', 'açı', 'kenar']
            text_lower = question_text.lower()
            topic_lower = topic.lower()
            
            if any(kw in text_lower or kw in topic_lower for kw in geo_keywords):
                logger.info("Varsayılan üçgen çizimi yapılıyor...")
                analysis = self._create_default_triangle_analysis(question_text)
            else:
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
