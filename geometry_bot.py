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
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30'))  # Varsayılan 30 soru
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 10
    
    # Görsel ayarları
    IMAGE_WIDTH = 800
    IMAGE_HEIGHT = 600
    IMAGE_DPI = 150
    
    # Renk paleti - CANLI RENKLER
    COLORS = {
        'primary': '#2563eb',      # Ana şekil (parlak mavi)
        'secondary': '#16a34a',    # İkincil şekil (parlak yeşil)
        'tertiary': '#dc2626',     # Üçüncü şekil (parlak kırmızı)
        'quaternary': '#9333ea',   # Dördüncü şekil (parlak mor)
        'highlight': '#ea580c',    # Vurgulu (parlak turuncu)
        'auxiliary': '#0891b2',    # Yardımcı çizgi (cyan)
        'angle': '#c026d3',        # Açı yayları (magenta)
        'unknown': '#dc2626',      # Bilinmeyen (kırmızı)
        'text': '#1e293b',         # Metin (koyu gri)
        'background': '#ffffff',   # Arka plan (beyaz)
        'grid': '#e2e8f0',         # Grid (açık gri)
        'label_bg': '#fef9c3',     # Etiket arka plan (açık sarı)
        'label_border': '#ca8a04'  # Etiket kenarlık (koyu sarı)
    }
    
    # Şekil renk paleti (birden fazla şekil için)
    SHAPE_COLORS = [
        {'fill': '#dbeafe', 'stroke': '#2563eb', 'text': '#1d4ed8'},  # Mavi
        {'fill': '#dcfce7', 'stroke': '#16a34a', 'text': '#166534'},  # Yeşil
        {'fill': '#fee2e2', 'stroke': '#dc2626', 'text': '#991b1b'},  # Kırmızı
        {'fill': '#f3e8ff', 'stroke': '#9333ea', 'text': '#7e22ce'},  # Mor
        {'fill': '#ffedd5', 'stroke': '#ea580c', 'text': '#c2410c'},  # Turuncu
        {'fill': '#cffafe', 'stroke': '#0891b2', 'text': '#0e7490'},  # Cyan
    ]


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
    
    ANALYSIS_PROMPT = """Sen profesyonel bir geometri illüstratörüsün. Bir öğrenci soruyu okuduğunda, şekli zihninde canlandırmasına yardımcı olacak MÜKEMMEL bir çizim tasarlayacaksın.

🎨 GÖREV: Soruyu oku, şekli zihninde adım adım canlandır, sonra çizim talimatlarını JSON olarak ver.

═══════════════════════════════════════════════════════════════
📐 ADIM 1: ÇİZİM GEREKLİ Mİ? (DİKKATLİCE DÜŞÜN!)
═══════════════════════════════════════════════════════════════

❌ ASLA ÇİZİM YAPMA eğer:
• Soruda "x cm", "a metre", "n tane" gibi DEĞİŞKEN varsa
• "Hacim", "kapasite", "litre", "cm³" hesaplanıyorsa
• "Prizma", "kutu", "depo", "tank" hacmi soruluyorsa
• İki kişi/şirket karşılaştırması yapılıyorsa (Ali ve Veli, Yusuf ve Mustafa)
• Şeklin boyutu/tipi HESAPLANACAKSA (örn: "köşegen sayısı X olan çokgen")
• Formül uygulaması ise (n köşeli çokgenin özellikleri)

✅ ÇİZİM YAP eğer:
• SABİT SAYISAL değerler verilmişse (6 cm, 8 m, 45°)
• Koordinatlar açıkça verilmişse: A(2,3), B(5,1)
• Tek bir geometrik şekil net tanımlanmışsa
• Öğrencinin görmesi gereken somut bir şekil varsa

Emin değilsen → cizim_pisinilir: false

═══════════════════════════════════════════════════════════════
🖼️ ADIM 2: ŞEKLİ ZİHNİNDE CANLANDIR (ÇİZİM YAPILACAKSA)
═══════════════════════════════════════════════════════════════

Kendine şu soruları sor:

📍 KONUM VE YERLEŞİM:
• Şekil nasıl duruyor? (bir kenarı yatay mı, tepe yukarıda mı?)
• Merkez nerede olmalı?
• En dengeli ve anlaşılır görünüm hangisi?

📐 BOYUT VE ORANLAR:
• Kenarlar birbirine göre nasıl orantılı?
• Verilen ölçüler şekle nasıl yansıyacak?
• Şekil çok uzun mu, kısa mı, kare gibi mi görünmeli?

🔺 ÖZEL NOKTALAR:
• Hangi noktalar kritik? (tepe, taban köşeleri, merkez)
• Yükseklik ayağı nerede?
• Açıortay/kenarortay nereye düşüyor?

✏️ ÖZEL ÇİZGİLER:
• Yükseklik çizilecek mi? Nereden nereye?
• Açıortay var mı? Hangi açıdan?
• Kenarortay gösterilecek mi?
• Dik açı işareti nereye konulacak?

🏷️ ETİKETLER:
• Hangi uzunluklar yazılacak? (SADECE VERİLENLER!)
• Hangi açılar gösterilecek?
• "?" ile neyi işaretleyeceğiz?
• Etiketler çakışmadan nasıl yerleştirilecek?

═══════════════════════════════════════════════════════════════
⚠️ ADIM 3: ALTIN KURALLAR
═══════════════════════════════════════════════════════════════

🚫 KESİNLİKLE YAPMA:
• Hesaplanan değerleri gösterme (cevabı vermiş olursun!)
• Çözüm adımlarını ima etme
• Sorudan fazlasını çizme
• Bilinmeyenlere değer atama

✅ KESİNLİKLE YAP:
• Sadece VERİLEN bilgileri çiz
• Bilinmeyenleri "?" ile işaretle
• Soruyu ANLAMAYI kolaylaştır, ÇÖZMEYI değil!
• Profesyonel, temiz, orantılı çizim tasarla

═══════════════════════════════════════════════════════════════
📋 ADIM 4: KOORDİNAT HESAPLAMA (ÇOK ÖNEMLİ!)
═══════════════════════════════════════════════════════════════

🔺 ÜÇGEN KOORDİNATLARI:
Verilen bilgilere göre koordinatları HESAPLA:

• Eşkenar üçgen (kenar a):
  B = (0, 0), C = (a, 0), A = (a/2, a×√3/2)
  
• İkizkenar üçgen (taban c, eşit kenarlar a):
  B = (0, 0), C = (c, 0), A = (c/2, √(a²-(c/2)²))
  
• Dik üçgen (dik kenarlar a, b):
  B = (0, 0) [dik açı], A = (0, a), C = (b, 0)
  
• Genel üçgen: Tabanı yatay koy, tepeyi yukarı yerleştir

▭ DÖRTGEN KOORDİNATLARI:
• Dikdörtgen (a×b): (0,0), (a,0), (a,b), (0,b)
• Kare (kenar a): (0,0), (a,0), (a,a), (0,a)
• Paralelkenar: Alt kenarı yatay, üst kenarı paralel kaydır
• Yamuk: Alt tabanı yatay, üst tabanı ortala

⭕ ÇEMBER:
• Merkez ve yarıçap belirle
• Çap, kiriş, teğet çizgilerini hesapla

═══════════════════════════════════════════════════════════════
📊 JSON ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════

{
  "cizim_pisinilir": true/false,
  "neden": "Çizim yapma/yapmama sebebi",
  "dusunce_sureci": "Şekli nasıl canlandırdığımın açıklaması",
  "sekil_tipi": "ucgen|dortgen|cember|analitik|cokgen|kati_cisim|birlesik",
  "alt_tip": "dik|ikizkenar|eskenar|genel|kare|dikdortgen|paralelkenar|yamuk",
  "sekil_ozellikleri": {
    "yon": "tepe_yukari|tepe_asagi|saga_yatik|sola_yatik",
    "taban_yatay": true,
    "merkez_x": 0,
    "merkez_y": 0,
    "olcek": "Şeklin yaklaşık boyutu"
  },
  "noktalar": [
    {
      "isim": "A",
      "x": 0,
      "y": 5,
      "konum_aciklama": "Tepe noktası, üçgenin en üst köşesi",
      "etiket_yonu": "yukari"
    }
  ],
  "kenarlar": [
    {
      "baslangic": "A",
      "bitis": "B",
      "uzunluk": "6 cm",
      "goster_uzunluk": true,
      "etiket_konum": "ortada_disinda"
    }
  ],
  "acilar": [
    {
      "kose": "B",
      "deger": "90°",
      "dik_aci": true,
      "goster": true,
      "yay_boyutu": "kucuk"
    }
  ],
  "ozel_cizgiler": [
    {
      "tip": "yukseklik|aciortay|kenarortay|orta_dikme",
      "baslangic": "A",
      "bitis": "H",
      "kenar_uzerinde": "BC",
      "etiket": "h = ?",
      "dik_aci_goster": true
    }
  ],
  "ek_etiketler": [
    {
      "metin": "Alan = ?",
      "konum": "ic_merkez|dis_sag|dis_ust"
    }
  ]
}

═══════════════════════════════════════════════════════════════
📝 ÖRNEK ANALİZLER
═══════════════════════════════════════════════════════════════

SORU: "ABC ikizkenar üçgeninde |AB|=|AC|=10 cm, |BC|=12 cm. A'dan BC'ye yükseklik h kaç cm?"

DÜŞÜNCE SÜRECİ:
"İkizkenar üçgen var. Eşit kenarlar AB ve AC (10'ar cm), taban BC (12 cm).
Şekli zihnimde canlandırıyorum: Taban BC yatay olmalı, A tepesi tam ortada yukarıda.
İkizkenar olduğu için A noktası, BC'nin tam ortasının üzerinde.
BC = 12 cm ise B=(-6,0), C=(6,0), A=(0,h) olmalı.
Pisagor: h² + 6² = 10² → h = 8... AMA BU CEVAP! Göstermeyeceğim.
A'yı yaklaşık (0, 8) civarına koyayım ama etikette 'h = ?' yazacağım.
Yükseklik AH çizgisi, H noktası BC'nin ortası (0,0).
H noktasında dik açı işareti olacak."

JSON ÇIKTI:
{
  "cizim_pisinilir": true,
  "dusunce_sureci": "İkizkenar üçgen, taban yatay, tepe ortada yukarıda, yükseklik dik iniyor",
  "sekil_tipi": "ucgen",
  "alt_tip": "ikizkenar",
  "noktalar": [
    {"isim": "A", "x": 0, "y": 7, "konum_aciklama": "Tepe, ortada yukarıda"},
    {"isim": "B", "x": -6, "y": 0, "konum_aciklama": "Sol alt köşe"},
    {"isim": "C", "x": 6, "y": 0, "konum_aciklama": "Sağ alt köşe"},
    {"isim": "H", "x": 0, "y": 0, "konum_aciklama": "Yükseklik ayağı, BC ortası"}
  ],
  "kenarlar": [
    {"baslangic": "A", "bitis": "B", "uzunluk": "10 cm", "goster_uzunluk": true},
    {"baslangic": "A", "bitis": "C", "uzunluk": "10 cm", "goster_uzunluk": true},
    {"baslangic": "B", "bitis": "C", "uzunluk": "12 cm", "goster_uzunluk": true}
  ],
  "ozel_cizgiler": [
    {"tip": "yukseklik", "baslangic": "A", "bitis": "H", "kenar_uzerinde": "BC", "etiket": "h = ?", "dik_aci_goster": true}
  ]
}

---

SORU: "Bir kutunun hacmi x³ cm³. Kenar uzunluğu 2x olursa hacim kaç olur?"

DÜŞÜNCE SÜRECİ:
"Bu bir hacim hesaplama sorusu. Değişken 'x' var. Somut boyut yok.
3D kutu çizimi zaten zor ve bu soru cebirsel.
ÇİZİM YAPILMAYACAK."

JSON ÇIKTI:
{
  "cizim_pisinilir": false,
  "neden": "Değişken (x) içeren hacim hesaplama sorusu. Somut boyut yok, çizim anlamsız."
}

═══════════════════════════════════════════════════════════════

Şimdi aşağıdaki soruyu analiz et. Önce düşün, şekli zihninde canlandır, sonra JSON çıktı ver.

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
            
            if sekil_tipi == 'birlesik':
                return self._render_composite(analysis)
            elif sekil_tipi == 'ucgen':
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
    
    def _render_composite(self, analysis: Dict) -> bytes:
        """Birden fazla şekil içeren kompozit çizim"""
        fig, ax = self._create_figure()
        
        sekiller = analysis.get('sekiller', [])
        
        if not sekiller:
            logger.warning("Birleşik şekilde hiç şekil yok")
            plt.close(fig)
            return None
        
        all_points = {}  # Tüm noktaları topla
        
        # Her şekli çiz
        for idx, sekil in enumerate(sekiller):
            tip = sekil.get('tip', 'dikdortgen')
            renk_idx = sekil.get('renk_index', idx) % len(Config.SHAPE_COLORS)
            colors = Config.SHAPE_COLORS[renk_idx]
            
            noktalar = sekil.get('noktalar', [])
            
            if len(noktalar) < 3:
                continue
            
            # Koordinatları al - ? işaretini işle
            coords = []
            for n in noktalar:
                x = self._parse_coordinate(n.get('x', 0))
                y = self._parse_coordinate(n.get('y', 0))
                coords.append((x, y))
                all_points[n.get('isim', f'P{idx}')] = (x, y)
            
            # Tüm noktalar aynıysa varsayılan koordinat oluştur
            if all(c == coords[0] for c in coords):
                # Varsayılan koordinatlar
                if tip in ['dikdortgen', 'kare']:
                    offset_x = idx * 8
                    coords = [(offset_x, 0), (offset_x + 6, 0), (offset_x + 6, 4), (offset_x, 4)]
                elif tip == 'yamuk':
                    offset_x = idx * 8
                    coords = [(offset_x + 1, 4), (offset_x + 5, 4), (offset_x + 7, 0), (offset_x, 0)]
                else:
                    offset_x = idx * 6
                    coords = [(offset_x, 0), (offset_x + 4, 0), (offset_x + 2, 3)]
                
                # Noktaları güncelle
                for i, n in enumerate(noktalar):
                    if i < len(coords):
                        all_points[n.get('isim', f'P{i}')] = coords[i]
            
            # Şekli çiz
            polygon = patches.Polygon(coords, fill=True,
                                      facecolor=colors['fill'],
                                      edgecolor=colors['stroke'],
                                      linewidth=3, alpha=0.7, zorder=2)
            ax.add_patch(polygon)
            
            # Şekil ismi etiketi
            sekil_isim = sekil.get('isim', f'Şekil {idx+1}')
            center_x = sum(c[0] for c in coords) / len(coords)
            center_y = sum(c[1] for c in coords) / len(coords)
            
            ax.annotate(sekil_isim, (center_x, center_y), fontsize=11, 
                       fontweight='bold', color=colors['text'],
                       ha='center', va='center', alpha=0.7,
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                edgecolor=colors['stroke'], alpha=0.8))
            
            # Kenar uzunlukları
            for kenar in sekil.get('kenarlar', []):
                bas = kenar.get('baslangic')
                bit = kenar.get('bitis')
                uzunluk = kenar.get('uzunluk', '')
                
                if bas in all_points and bit in all_points and uzunluk:
                    p1, p2 = all_points[bas], all_points[bit]
                    self._draw_length_label_colored(ax, p1, p2, uzunluk, colors['stroke'])
        
        # Tüm noktaları çiz (farklı renklerle)
        drawn_points = set()
        for idx, sekil in enumerate(sekiller):
            renk_idx = sekil.get('renk_index', idx) % len(Config.SHAPE_COLORS)
            colors = Config.SHAPE_COLORS[renk_idx]
            
            for n in sekil.get('noktalar', []):
                isim = n.get('isim', f'P{idx}')
                if isim not in drawn_points:
                    drawn_points.add(isim)
                    
                    # Koordinatları all_points'ten al (düzeltilmiş koordinatlar)
                    if isim in all_points:
                        x, y = all_points[isim]
                    else:
                        x = self._parse_coordinate(n.get('x', 0))
                        y = self._parse_coordinate(n.get('y', 0))
                    
                    # Nokta
                    ax.scatter([x], [y], c=colors['stroke'], s=120, zorder=5,
                              edgecolors='white', linewidths=2)
                    
                    # Etiket - konuma göre offset
                    if all_points:
                        center_x = sum(p[0] for p in all_points.values()) / len(all_points)
                        center_y = sum(p[1] for p in all_points.values()) / len(all_points)
                        
                        dx = x - center_x
                        dy = y - center_y
                        norm = np.sqrt(dx**2 + dy**2)
                        if norm > 0:
                            offset = (int(dx/norm * 20), int(dy/norm * 20))
                        else:
                            offset = (10, 10)
                    else:
                        offset = (10, 10)
                    
                    ax.annotate(isim, (x, y), xytext=offset, textcoords='offset points',
                               fontsize=14, fontweight='bold', color=colors['stroke'], zorder=6)
        
        # Başlık
        baslik = analysis.get('baslik', '')
        if baslik:
            ax.set_title(baslik, fontsize=14, fontweight='bold', color='#1e293b', pad=10)
        
        # Ek etiketler
        for ek in analysis.get('ek_etiketler', []):
            metin = ek.get('metin', '')
            konum = ek.get('konum', 'ust')
            
            if metin:
                xlim = ax.get_xlim()
                ylim = ax.get_ylim()
                
                if konum == 'ust':
                    x, y = (xlim[0] + xlim[1]) / 2, ylim[1] * 0.95
                elif konum == 'alt':
                    x, y = (xlim[0] + xlim[1]) / 2, ylim[0] * 1.1
                else:
                    x, y = xlim[1] * 0.7, ylim[1] * 0.9
                
                ax.annotate(metin, (x, y), fontsize=11, fontweight='bold',
                           color='#1e40af', ha='center',
                           bbox=dict(boxstyle='round,pad=0.4', facecolor='#fef3c7',
                                    edgecolor='#f59e0b', alpha=0.95), zorder=7)
        
        return self._finalize_figure(fig, ax)
    
    def _draw_length_label_colored(self, ax, p1: tuple, p2: tuple, label: str, color: str):
        """Renkli kenar uzunluk etiketi"""
        # Orta nokta
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        
        # Dik yönde offset
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = np.sqrt(dx**2 + dy**2)
        if length > 0:
            offset = 0.5
            nx, ny = -dy / length * offset, dx / length * offset
        else:
            nx, ny = 0, 0.5
        
        ax.annotate(label, (mx + nx, my + ny), fontsize=12, fontweight='bold',
                   color=color, ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor=color, linewidth=2, alpha=0.95), zorder=4)
    
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
        """Nokta koordinatlarını al - bilinmeyenleri akıllıca işle"""
        coords = {}
        noktalar = analysis.get('noktalar', [])
        
        for nokta in noktalar:
            isim = nokta.get('isim', 'X')
            x = nokta.get('x', 0)
            y = nokta.get('y', 0)
            
            # "?" veya string bilinmeyenleri sayıya çevir
            x = self._parse_coordinate(x)
            y = self._parse_coordinate(y)
            
            coords[isim] = (x, y)
        
        # Eğer koordinatlar anlamsızsa varsayılan şekil oluştur
        if len(coords) >= 3:
            values = list(coords.values())
            all_same = all(v == values[0] for v in values)
            all_zero = all(v == (0, 0) for v in values)
            if all_same or all_zero:
                coords = self._generate_default_coords(analysis, noktalar)
        
        return coords
    
    def _parse_coordinate(self, value) -> float:
        """Koordinat değerini float'a çevir"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            v = value.strip()
            if v in ['?', '', 'x', 'y', 'a', 'b']:
                return 0.0
            try:
                return float(v.replace(',', '.'))
            except:
                return 0.0
        return 0.0
    
    def _generate_default_coords(self, analysis: Dict, noktalar: list) -> Dict[str, tuple]:
        """Şekil tipine göre varsayılan koordinatlar üret"""
        sekil_tipi = analysis.get('sekil_tipi', 'ucgen')
        alt_tip = analysis.get('alt_tip', 'genel')
        n = len(noktalar)
        
        coords = {}
        
        if n == 0:
            return coords
        
        # Nokta isimlerini al
        names = [n.get('isim', f'P{i}') for i, n in enumerate(noktalar)]
        
        if sekil_tipi == 'ucgen' or n == 3:
            if alt_tip in ['ikizkenar', 'eskenar']:
                # İkizkenar üçgen (simetrik)
                coords = {
                    names[0]: (0, 5),
                    names[1]: (-4, 0),
                    names[2]: (4, 0)
                }
            elif alt_tip == 'dik':
                coords = {
                    names[0]: (0, 4),
                    names[1]: (0, 0),
                    names[2]: (5, 0)
                }
            else:
                coords = {
                    names[0]: (0, 5),
                    names[1]: (-3, 0),
                    names[2]: (5, 0)
                }
        elif sekil_tipi == 'dortgen' or n == 4:
            if alt_tip == 'kare':
                coords = {names[0]: (0, 4), names[1]: (4, 4), names[2]: (4, 0), names[3]: (0, 0)}
            elif alt_tip == 'dikdortgen':
                coords = {names[0]: (0, 3), names[1]: (6, 3), names[2]: (6, 0), names[3]: (0, 0)}
            elif alt_tip == 'yamuk':
                coords = {names[0]: (1, 4), names[1]: (5, 4), names[2]: (7, 0), names[3]: (0, 0)}
            else:
                coords = {names[0]: (0, 4), names[1]: (5, 4), names[2]: (6, 0), names[3]: (-1, 0)}
        else:
            # Çokgen için dairesel dağılım
            import math
            for i, name in enumerate(names):
                angle = 2 * math.pi * i / n - math.pi / 2
                coords[name] = (4 * math.cos(angle), 4 * math.sin(angle))
        
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
        """Üçgen çiz - profesyonel kalitede"""
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
        
        # Tek üçgen çizimi - canlı renkler
        A, B, C = noktalar[0], noktalar[1], noktalar[2]
        pA, pB, pC = coords[A], coords[B], coords[C]
        
        # Renk teması
        fill_color = '#dbeafe'   # Açık mavi
        stroke_color = '#2563eb'  # Parlak mavi
        highlight_color = '#dc2626'  # Kırmızı (vurgular için)
        auxiliary_color = '#0891b2'  # Cyan (yardımcı çizgiler)
        
        # Üçgen çiz
        triangle = patches.Polygon([pA, pB, pC], fill=True,
                                   facecolor=fill_color, alpha=0.6,
                                   edgecolor=stroke_color, linewidth=3)
        ax.add_patch(triangle)
        
        # Kenar uzunlukları
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords and kenar.get('goster_uzunluk', True):
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    p1, p2 = coords[bas], coords[bit]
                    self._draw_styled_label(ax, p1, p2, uzunluk, stroke_color)
        
        # Açılar - geliştirilmiş
        for aci in analysis.get('acilar', []):
            kose = aci.get('kose')
            if kose in coords and aci.get('goster', True):
                diger = [n for n in [A, B, C] if n != kose]
                if len(diger) >= 2:
                    if aci.get('dik_aci', False):
                        self._draw_right_angle(ax, coords[kose], coords[diger[0]], coords[diger[1]], 
                                              color=highlight_color, size=0.5)
                    else:
                        deger = aci.get('deger', '')
                        self._draw_angle_arc(ax, coords[kose], coords[diger[0]], coords[diger[1]], 
                                           label=deger, color='#c026d3')  # Mor açı
        
        # Özel çizgiler (yükseklik, kenarortay, açıortay)
        for ozel in analysis.get('ozel_cizgiler', []):
            tip = ozel.get('tip', '')
            bas = ozel.get('baslangic', '')
            bitis = ozel.get('bitis', '')
            
            if bas in coords:
                bit_coord = None
                bit_name = None
                
                # Bitiş noktasını belirle
                if 'bitis_koordinat' in ozel:
                    bc = ozel['bitis_koordinat']
                    bit_coord = (self._parse_coordinate(bc[0]), self._parse_coordinate(bc[1]))
                    bit_name = bitis if bitis else 'S'
                elif bitis in coords:
                    bit_coord = coords[bitis]
                    bit_name = bitis
                elif bitis:
                    # Bitiş noktası belirtilmiş ama koordinatı yok - hesapla
                    kenar = ozel.get('kenar_uzerinde', '')
                    if len(kenar) >= 2 and kenar[0] in coords and kenar[1] in coords:
                        bit_coord = self._calculate_special_point(
                            tip, coords[bas], coords[kenar[0]], coords[kenar[1]]
                        )
                        bit_name = bitis
                
                if bit_coord is None:
                    # Kenar üzerinde otomatik hesapla
                    kenar = ozel.get('kenar_uzerinde', '')
                    if len(kenar) >= 2 and kenar[0] in coords and kenar[1] in coords:
                        bit_coord = self._calculate_special_point(
                            tip, coords[bas], coords[kenar[0]], coords[kenar[1]]
                        )
                        bit_name = ozel.get('bitis', 'H')
                
                if bit_coord:
                    # Çizgi stili
                    if tip == 'yukseklik':
                        renk = highlight_color
                        stil = '-'
                    elif tip == 'aciortay':
                        renk = '#9333ea'  # Mor
                        stil = '--'
                    elif tip == 'kenarortay':
                        renk = '#16a34a'  # Yeşil
                        stil = '-.'
                    else:
                        renk = auxiliary_color
                        stil = '--'
                    
                    self._draw_line(ax, coords[bas], bit_coord, color=renk, linestyle=stil, linewidth=2.5)
                    
                    # Etiket
                    etiket = ozel.get('etiket', '')
                    if etiket:
                        self._draw_styled_label(ax, coords[bas], bit_coord, etiket, renk)
                    
                    # Dik açı işareti (yükseklik için)
                    if tip == 'yukseklik':
                        kenar = ozel.get('kenar_uzerinde', '')
                        if len(kenar) >= 2 and kenar[0] in coords:
                            self._draw_right_angle(ax, bit_coord, coords[bas], coords[kenar[0]], 
                                                  size=0.4, color=highlight_color)
                    
                    # Bitiş noktası
                    if bit_name and bit_name not in coords:
                        ax.scatter([bit_coord[0]], [bit_coord[1]], c=renk, s=100, zorder=5,
                                  edgecolors='white', linewidths=2)
                        ax.annotate(bit_name, bit_coord, xytext=(8, -12), textcoords='offset points',
                                   fontsize=13, fontweight='bold', color=renk)
        
        # Ana noktalar - profesyonel görünüm
        center_x = (pA[0] + pB[0] + pC[0]) / 3
        center_y = (pA[1] + pB[1] + pC[1]) / 3
        
        point_colors = ['#ea580c', '#16a34a', '#2563eb']  # Turuncu, Yeşil, Mavi
        
        for i, (isim, coord) in enumerate([(A, pA), (B, pB), (C, pC)]):
            # Offset hesapla
            dx = coord[0] - center_x
            dy = coord[1] - center_y
            norm = np.sqrt(dx**2 + dy**2)
            if norm > 0:
                offset = (int(dx/norm * 18), int(dy/norm * 18))
            else:
                offset = (10, 10)
            
            color = point_colors[i % 3]
            ax.scatter([coord[0]], [coord[1]], c=color, s=140, zorder=6,
                      edgecolors='white', linewidths=2.5)
            ax.annotate(isim, coord, xytext=offset, textcoords='offset points',
                       fontsize=15, fontweight='bold', color=color, zorder=7)
        
        # Ek etiketler
        for ek in ek_etiketler:
            metin = ek.get('metin', '')
            konum = ek.get('konum', 'sag_ust')
            
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            
            if konum == 'sag_ust':
                x, y = xlim[1] * 0.7, ylim[1] * 0.9
            elif konum == 'sol_ust':
                x, y = xlim[0] + (xlim[1]-xlim[0]) * 0.2, ylim[1] * 0.9
            else:
                x, y = (xlim[0] + xlim[1]) / 2, ylim[1] * 0.95
            
            ax.annotate(metin, (x, y), fontsize=12, fontweight='bold',
                       color='#1e40af',
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='#fef3c7',
                                edgecolor='#f59e0b', alpha=0.95), zorder=8)
        
        return self._finalize_figure(fig, ax)
    
    def _calculate_special_point(self, tip: str, p_start: tuple, p_edge1: tuple, p_edge2: tuple) -> tuple:
        """Özel nokta hesapla (yükseklik ayağı, açıortay kesişimi vb.)"""
        try:
            if tip == 'yukseklik':
                # Başlangıç noktasından kenara dik
                A = Point(p_start)
                B = Point(p_edge1)
                C = Point(p_edge2)
                kenar = Line(B, C)
                dik = kenar.perpendicular_line(A)
                kesisim = dik.intersection(kenar)
                if kesisim:
                    return (float(kesisim[0].x), float(kesisim[0].y))
            
            elif tip == 'kenarortay':
                # Kenarın orta noktası
                mid_x = (p_edge1[0] + p_edge2[0]) / 2
                mid_y = (p_edge1[1] + p_edge2[1]) / 2
                return (mid_x, mid_y)
            
            elif tip == 'aciortay':
                # Açıortayın karşı kenarı kestiği nokta
                # İç açıortay teoremi: |BE|/|EC| = |AB|/|AC|
                A = np.array(p_start)
                B = np.array(p_edge1)
                C = np.array(p_edge2)
                
                AB = np.linalg.norm(B - A)
                AC = np.linalg.norm(C - A)
                
                if AB + AC > 0:
                    # Kesişim noktası BC üzerinde
                    t = AB / (AB + AC)
                    S = B + t * (C - B)
                    return (float(S[0]), float(S[1]))
            
            # Varsayılan: orta nokta
            return ((p_edge1[0] + p_edge2[0]) / 2, (p_edge1[1] + p_edge2[1]) / 2)
            
        except Exception as e:
            logger.warning(f"Özel nokta hesaplama hatası: {e}")
            return ((p_edge1[0] + p_edge2[0]) / 2, (p_edge1[1] + p_edge2[1]) / 2)
    
    def _draw_styled_label(self, ax, p1: tuple, p2: tuple, label: str, color: str):
        """Profesyonel kenar etiketi"""
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = np.sqrt(dx**2 + dy**2)
        if length > 0:
            nx, ny = -dy / length * 0.5, dx / length * 0.5
        else:
            nx, ny = 0, 0.5
        
        ax.annotate(label, (mx + nx, my + ny), fontsize=13, fontweight='bold',
                   color=color, ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor=color, linewidth=2, alpha=0.95), zorder=5)
    
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
        """Dörtgen çiz - canlı renkler ve geliştirilmiş gösterim"""
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
        
        # Canlı renk paleti (yeşil tema)
        fill_color = '#dcfce7'
        stroke_color = '#16a34a'
        text_color = '#166534'
        
        # Dörtgen çiz
        quad = patches.Polygon(points, fill=True,
                              facecolor=fill_color, alpha=0.7,
                              edgecolor=stroke_color, linewidth=3)
        ax.add_patch(quad)
        
        # Kenar uzunlukları
        for kenar in analysis.get('kenarlar', []):
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords and kenar.get('goster_uzunluk', True):
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    p1, p2 = coords[bas], coords[bit]
                    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                    length = np.sqrt(dx**2 + dy**2)
                    if length > 0:
                        nx, ny = -dy / length * 0.5, dx / length * 0.5
                    else:
                        nx, ny = 0, 0.5
                    
                    ax.annotate(uzunluk, (mx + nx, my + ny), fontsize=13, fontweight='bold',
                               color=stroke_color, ha='center', va='center',
                               bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                        edgecolor=stroke_color, linewidth=2, alpha=0.95), zorder=4)
        
        # Açılar - geliştirilmiş konumlandırma
        for aci in analysis.get('acilar', []):
            kose = aci.get('kose')
            if kose in coords and aci.get('goster', True):
                idx = noktalar.index(kose)
                onceki = noktalar[(idx - 1) % 4]
                sonraki = noktalar[(idx + 1) % 4]
                
                if aci.get('dik_aci', False):
                    self._draw_right_angle(ax, coords[kose], coords[onceki], coords[sonraki],
                                          color='#dc2626', size=0.5)
                else:
                    deger = aci.get('deger', '')
                    self._draw_angle_arc_improved(ax, coords[kose], coords[onceki], coords[sonraki],
                                                 radius=0.7, label=deger)
        
        # Noktalar - merkeze göre offset hesapla
        center_x = sum(p[0] for p in points) / 4
        center_y = sum(p[1] for p in points) / 4
        
        for i, isim in enumerate(noktalar[:4]):
            coord = coords[isim]
            dx = coord[0] - center_x
            dy = coord[1] - center_y
            norm = np.sqrt(dx**2 + dy**2)
            if norm > 0:
                offset = (int(dx/norm * 22), int(dy/norm * 22))
            else:
                offset = (12, 12)
            
            # Canlı nokta
            ax.scatter([coord[0]], [coord[1]], c=stroke_color, s=130, zorder=5,
                      edgecolors='white', linewidths=2)
            ax.annotate(isim, coord, xytext=offset, textcoords='offset points',
                       fontsize=15, fontweight='bold', color=stroke_color, zorder=6)
        
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
        """Koordinat düzleminde profesyonel çizim - kareli zemin"""
        fig, ax = plt.subplots(1, 1, figsize=(12, 10), facecolor='white')
        
        coords = self._get_point_coords(analysis)
        kenarlar = analysis.get('kenarlar', [])
        ek_etiketler = analysis.get('ek_etiketler', [])
        sekiller = analysis.get('sekiller', [])
        
        # Koordinat sınırlarını belirle
        if coords:
            all_x = [c[0] for c in coords.values()]
            all_y = [c[1] for c in coords.values()]
            x_min = min(all_x) - 2
            x_max = max(all_x) + 2
            y_min = min(all_y) - 2
            y_max = max(all_y) + 2
        else:
            x_min, x_max = -2, 10
            y_min, y_max = -2, 8
        
        # Biraz daha padding ekle
        x_min = min(x_min, -1)
        y_min = min(y_min, -1)
        
        # Tam sayılara yuvarla
        x_min, x_max = int(x_min) - 1, int(x_max) + 1
        y_min, y_max = int(y_min) - 1, int(y_max) + 1
        
        # KARELI ZEMİN - Profesyonel grid
        # Ana grid çizgileri (her birim)
        for i in range(x_min, x_max + 1):
            lw = 1.5 if i == 0 else 0.5
            color = '#374151' if i == 0 else '#d1d5db'
            ax.axvline(x=i, color=color, linewidth=lw, zorder=1)
        
        for i in range(y_min, y_max + 1):
            lw = 1.5 if i == 0 else 0.5
            color = '#374151' if i == 0 else '#d1d5db'
            ax.axhline(y=i, color=color, linewidth=lw, zorder=1)
        
        # Eksen ok uçları
        ax.annotate('', xy=(x_max + 0.3, 0), xytext=(x_max, 0),
                   arrowprops=dict(arrowstyle='->', color='#374151', lw=2))
        ax.annotate('', xy=(0, y_max + 0.3), xytext=(0, y_max),
                   arrowprops=dict(arrowstyle='->', color='#374151', lw=2))
        
        # Eksen etiketleri
        ax.text(x_max + 0.5, -0.3, 'x', fontsize=16, fontweight='bold', color='#374151')
        ax.text(0.3, y_max + 0.4, 'y', fontsize=16, fontweight='bold', color='#374151')
        
        # Eksen sayıları
        for i in range(x_min, x_max + 1):
            if i != 0:
                ax.text(i, -0.4, str(i), fontsize=10, ha='center', va='top', color='#6b7280')
        for i in range(y_min, y_max + 1):
            if i != 0:
                ax.text(-0.3, i, str(i), fontsize=10, ha='right', va='center', color='#6b7280')
        
        # O noktası
        ax.text(-0.4, -0.4, 'O', fontsize=12, fontweight='bold', color='#374151')
        
        # Birleşik şekiller varsa çiz
        if sekiller:
            for idx, sekil in enumerate(sekiller):
                self._draw_analytic_shape(ax, sekil, idx)
        
        # Kenarlardan polygon oluştur (eğer şekiller yoksa)
        elif len(coords) >= 3:
            # Koordinatlardan şekil çiz
            noktalar = list(coords.keys())
            points = [coords[n] for n in noktalar]
            
            # Şekil dolgusu
            polygon = patches.Polygon(points, fill=True,
                                     facecolor='#dbeafe', alpha=0.5,
                                     edgecolor='#2563eb', linewidth=3, zorder=2)
            ax.add_patch(polygon)
        
        # Kenarları çiz
        for kenar in kenarlar:
            bas = kenar.get('baslangic')
            bit = kenar.get('bitis')
            if bas in coords and bit in coords:
                p1, p2 = coords[bas], coords[bit]
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 
                       color='#2563eb', linewidth=2.5, zorder=3)
                
                # Kenar uzunluğu
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    self._draw_styled_label(ax, p1, p2, uzunluk, '#2563eb')
        
        # Noktaları çiz - profesyonel görünüm
        point_colors = ['#dc2626', '#16a34a', '#2563eb', '#9333ea', '#ea580c', '#0891b2']
        
        for i, (isim, coord) in enumerate(coords.items()):
            x, y = coord
            color = point_colors[i % len(point_colors)]
            
            # Büyük, belirgin nokta
            ax.scatter([x], [y], c=color, s=150, zorder=6,
                      edgecolors='white', linewidths=3)
            
            # Nokta ismi
            # Offset'i şeklin merkezine göre ayarla
            if coords:
                cx = sum(c[0] for c in coords.values()) / len(coords)
                cy = sum(c[1] for c in coords.values()) / len(coords)
                dx, dy = x - cx, y - cy
                norm = np.sqrt(dx**2 + dy**2)
                if norm > 0:
                    offset = (int(dx/norm * 20), int(dy/norm * 20))
                else:
                    offset = (12, 12)
            else:
                offset = (12, 12)
            
            ax.annotate(isim, (x, y), xytext=offset, textcoords='offset points',
                       fontsize=16, fontweight='bold', color=color, zorder=7)
            
            # Koordinat etiketi - küçük, altında
            coord_label = f'({x:.0f},{y:.0f})'
            ax.annotate(coord_label, (x, y), xytext=(offset[0], offset[1] - 18),
                       textcoords='offset points', fontsize=10, color='#64748b',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', 
                                edgecolor='#e5e7eb', alpha=0.9), zorder=7)
        
        # Ek etiketler (Alan bilgisi vb.)
        for ek in ek_etiketler:
            metin = ek.get('metin', '')
            konum = ek.get('konum', 'ust')
            
            if metin:
                if konum == 'ust':
                    x, y = (x_min + x_max) / 2, y_max - 0.5
                elif konum == 'alt':
                    x, y = (x_min + x_max) / 2, y_min + 1
                else:
                    x, y = x_max - 2, y_max - 1
                
                ax.annotate(metin, (x, y), fontsize=12, fontweight='bold',
                           color='#1e40af', ha='center',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='#fef3c7',
                                    edgecolor='#f59e0b', linewidth=2, alpha=0.95), zorder=8)
        
        # Başlık
        baslik = analysis.get('baslik', '')
        if baslik:
            ax.set_title(baslik, fontsize=16, fontweight='bold', color='#1e293b', pad=15)
        
        ax.set_xlim(x_min - 0.5, x_max + 0.8)
        ax.set_ylim(y_min - 0.5, y_max + 0.8)
        ax.set_aspect('equal')
        ax.axis('off')
        
        return self._finalize_figure(fig, ax)
    
    def _draw_analytic_shape(self, ax, sekil: Dict, idx: int):
        """Analitik düzlemde şekil çiz"""
        noktalar = sekil.get('noktalar', [])
        if len(noktalar) < 3:
            return
        
        # Koordinatları al
        coords = []
        for n in noktalar:
            x = self._parse_coordinate(n.get('x', 0))
            y = self._parse_coordinate(n.get('y', 0))
            coords.append((x, y))
        
        # Renk seç
        colors = Config.SHAPE_COLORS[idx % len(Config.SHAPE_COLORS)]
        
        # Şekil çiz
        polygon = patches.Polygon(coords, fill=True,
                                 facecolor=colors['fill'], alpha=0.6,
                                 edgecolor=colors['stroke'], linewidth=3, zorder=2)
        ax.add_patch(polygon)
        
        # Şekil ismi
        sekil_isim = sekil.get('isim', f'Şekil {idx+1}')
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        
        ax.annotate(sekil_isim, (cx, cy), fontsize=11, fontweight='bold',
                   color=colors['text'], ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor=colors['stroke'], alpha=0.9), zorder=5)
        
        # Kenar uzunlukları
        for kenar in sekil.get('kenarlar', []):
            bas_idx = None
            bit_idx = None
            
            for i, n in enumerate(noktalar):
                if n.get('isim') == kenar.get('baslangic'):
                    bas_idx = i
                if n.get('isim') == kenar.get('bitis'):
                    bit_idx = i
            
            if bas_idx is not None and bit_idx is not None:
                p1, p2 = coords[bas_idx], coords[bit_idx]
                uzunluk = kenar.get('uzunluk', '')
                if uzunluk:
                    self._draw_styled_label(ax, p1, p2, uzunluk, colors['stroke'])
    
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
