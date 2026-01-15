"""
🎯 BAĞLAM TEMELLİ SORU ÜRETİCİ BOT V6 - GÖRSEL DESTEKLİ
═══════════════════════════════════════════════════════════════════════════════

Temiz, sade ve etkili soru üretici.
- Gemini 2.5 Flash: Soru üretimi
- Gemini 3 Pro Image Preview: Görsel üretimi
- DeepSeek: Doğrulama ve geri bildirim (opsiyonel)
- 12 farklı bağlam türü
- Sınıf seviyesine uygun Bloom taksonomisi

@version 6.0.0
@author MATAİ PRO
"""

import os
import json
import random
import time
import hashlib
import base64
import uuid
import requests
from datetime import datetime
from openai import OpenAI
from google import genai
from google.genai import types
from supabase import create_client

# ═══════════════════════════════════════════════════════════════════════════════
# YAPILANDIRMA
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

SORU_PER_KAZANIM = int(os.environ.get('SORU_PER_KAZANIM', '3'))
MAX_KAZANIM = int(os.environ.get('MAX_ISLEM_PER_RUN', '10'))
BEKLEME = 2.0

# Sınıf filtresi (boş = tüm sınıflar)
SINIF_FILTRE = os.environ.get('SINIF_SEVIYESI', '').strip()
if SINIF_FILTRE:
    try:
        SINIF_FILTRE = int(SINIF_FILTRE)
    except ValueError:
        SINIF_FILTRE = None
else:
    SINIF_FILTRE = None

# Görsel ayarları
GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"   # Görsel üretimi için
STORAGE_BUCKET = "questions-images"  # Üretilen görseller için bucket
GORSEL_URETIM_AKTIF = True  # Görsel üretimini aç/kapat

# ═══════════════════════════════════════════════════════════════════════════════
# 12 BAĞLAM TÜRÜ
# ═══════════════════════════════════════════════════════════════════════════════

BAGLAMLAR = [
    {"id": "gunluk", "ad": "Günlük Yaşam", "ornekler": ["alışveriş", "ev işleri", "ulaşım", "yemek tarifi"]},
    {"id": "mesleki", "ad": "Mesleki", "ornekler": ["mühendislik", "mimarlık", "tarım", "ticaret"]},
    {"id": "cevre", "ad": "Çevresel", "ornekler": ["iklim", "geri dönüşüm", "enerji tasarrufu", "su kaynakları"]},
    {"id": "bilimsel", "ad": "Bilimsel", "ornekler": ["deney", "araştırma", "gözlem", "ölçüm"]},
    {"id": "tarihsel", "ad": "Tarihsel", "ornekler": ["antik yapılar", "eski uygarlıklar", "tarihsel olaylar"]},
    {"id": "kulturel", "ad": "Kültürel", "ornekler": ["sanat", "müzik", "gelenekler", "el sanatları"]},
    {"id": "sportif", "ad": "Sportif", "ornekler": ["maç istatistikleri", "antrenman", "yarışma"]},
    {"id": "teknolojik", "ad": "Teknolojik", "ornekler": ["yazılım", "robotik", "yapay zeka", "internet"]},
    {"id": "saglik", "ad": "Sağlık", "ornekler": ["beslenme", "egzersiz", "ilaç dozu", "hastane"]},
    {"id": "vatandaslik", "ad": "Vatandaşlık", "ornekler": ["belediye", "seçim", "vergi", "toplum"]},
    {"id": "ekonomik", "ad": "Ekonomik", "ornekler": ["bütçe", "faiz", "yatırım", "tasarruf"]},
    {"id": "oyun", "ad": "Oyunlaştırılmış", "ornekler": ["bulmaca", "strateji oyunu", "hazine avı"]}
]

# ═══════════════════════════════════════════════════════════════════════════════
# GÖRSEL TİPLERİ - Konuya göre uygun görsel tipleri
# ═══════════════════════════════════════════════════════════════════════════════

GORSEL_TIPLERI = {
    "geometri": ["geometrik_sekil", "ucgen", "dortgen", "daire", "prizma", "silindir", "koni", "koordinat_duzlemi"],
    "sayilar": ["sayi_dogrusu", "tablo", "grafik", "bilgi_kutusu"],
    "cebir": ["denklem_sema", "fonksiyon_grafigi", "koordinat_duzlemi", "tablo"],
    "veri": ["sutun_grafik", "pasta_grafik", "cizgi_grafik", "histogram", "tablo"],
    "olasilik": ["agac_sema", "tablo", "diagram"],
    "gunluk": ["senaryo_gorseli", "tablo", "bilgi_kutusu", "infografik"],
    "mesleki": ["teknik_cizim", "plan", "kesit", "3d_model"],
    "ekonomik": ["grafik", "tablo", "infografik"],
    "default": ["tablo", "bilgi_kutusu", "geometrik_sekil", "grafik"]
}

# ═══════════════════════════════════════════════════════════════════════════════
# SINIF SEVİYE AYARLARI
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_AYARLARI = {
    3: {"kelime": (80, 120), "bloom": ["hatırlama", "anlama"], "secenek": 4, "gorsel_oran": 0.3},
    4: {"kelime": (80, 120), "bloom": ["hatırlama", "anlama", "uygulama"], "secenek": 4, "gorsel_oran": 0.4},
    5: {"kelime": (120, 180), "bloom": ["anlama", "uygulama", "analiz"], "secenek": 4, "gorsel_oran": 0.5},
    6: {"kelime": (120, 180), "bloom": ["anlama", "uygulama", "analiz"], "secenek": 4, "gorsel_oran": 0.5},
    7: {"kelime": (150, 200), "bloom": ["uygulama", "analiz"], "secenek": 4, "gorsel_oran": 0.6},
    8: {"kelime": (150, 200), "bloom": ["uygulama", "analiz", "değerlendirme"], "secenek": 4, "gorsel_oran": 0.7},
    9: {"kelime": (180, 250), "bloom": ["uygulama", "analiz", "değerlendirme"], "secenek": 5, "gorsel_oran": 0.7},
    10: {"kelime": (180, 250), "bloom": ["analiz", "değerlendirme"], "secenek": 5, "gorsel_oran": 0.8},
    11: {"kelime": (200, 300), "bloom": ["analiz", "değerlendirme", "yaratma"], "secenek": 5, "gorsel_oran": 0.8},
    12: {"kelime": (200, 300), "bloom": ["analiz", "değerlendirme", "yaratma"], "secenek": 5, "gorsel_oran": 0.8}
}

ISIMLER = ["Elif", "Yusuf", "Zeynep", "Ahmet", "Ayşe", "Mehmet", "Fatma", "Ali", 
           "Defne", "Ege", "Ada", "Kerem", "Mira", "Baran", "Ela", "Deniz", "Can", "Su"]

# ═══════════════════════════════════════════════════════════════════════════════
# GÖRSEL ÜRETİM PROMPT ŞABLONU
# ═══════════════════════════════════════════════════════════════════════════════

IMAGE_PROMPT_TEMPLATE = """📐 MATEMATİK SORUSU GÖRSELİ - ÖĞRETİM MATERYALİ

### GÖREV:
Aşağıdaki betimlemelere uygun, profesyonel bir matematik sorusu görseli oluştur.

### GÖRSEL TİPİ: {tip}

### DETAYLI BETİMLEME:
{detay}

### 📏 TEKNİK GEREKSİNİMLER:

**Genel Kurallar:**
- Temiz, net çizgiler
- Profesyonel eğitim materyali görünümü
- Türkçe etiketler (varsa)
- Ölçüler ve değerler NET görünmeli

**Geometrik Şekiller için:**
- Köşe noktaları büyük harflerle (A, B, C, D...)
- Her köşede küçük siyah nokta (●)
- Kenar uzunlukları çift yönlü ok (↔) ile
- Ölçüler şeklin DIŞINDA yazılmalı

**Grafikler için:**
- X ve Y eksenleri etiketli
- Birimler belirtilmeli
- Veri noktaları net görünmeli

**Tablolar için:**
- Başlık satırı vurgulu
- Hücreler düzgün hizalı
- Okunabilir font boyutu

### 🎨 STİL KURALLARI (MEB DERS KİTABI):

**Renkler (CANLI AMA GÖZ YORMAYAN):**
- Arka plan: Beyaz veya çok açık krem (#FFFEF5)
- Şekil dolguları:
  * Açık mavi: #E3F2FD (su, gökyüzü temaları)
  * Açık yeşil: #E8F5E9 (doğa, bahçe temaları)
  * Açık turuncu: #FFF3E0 (enerji, sıcak temalar)
  * Açık mor: #F3E5F5 (bilim, teknoloji temaları)
  * Açık sarı: #FFFDE7 (güneş, ışık temaları)
- Çizgiler: Koyu gri (#424242), 2px kalınlık
- Etiketler: Siyah veya koyu gri, kalın font

**Boyutlandırma:**
- Şekil görsel alanının %60-70'ini kaplamalı
- Etiketler için yeterli boşluk bırak

### ❌ MUTLAK YASAKLAR:
❌ Soru metni veya cümleler
❌ "Buna göre...", "Aşağıdaki..." gibi ifadeler
❌ A), B), C), D) şıkları
❌ Çözüm adımları veya hesaplamalar
❌ Cevabı veren bilgi veya sonuç değerleri
❌ Çözümde hesaplanan ara değerler
❌ Doğru cevabı gösteren işaretlemeler (noktalar, oklar)
❌ Çözüm sonucunu içeren koordinat noktaları
❌ "Sonuç", "Cevap", "=" işaretleri ile sonuç gösterimi
❌ Gereksiz dekorasyon
❌ Bulanık çizgiler
❌ Türkçe karakter hatası

### ✅ SADECE BUNLAR OLABİLİR:
✅ Soruda VERİLEN bilgiler (fiyatlar, ölçüler, oranlar)
✅ Problemin BAŞLANGIÇ durumu
✅ Senaryodaki sabit değerler
✅ Şeklin boyutları (soruda verilmişse)
✅ Grafik eksenleri ve birimleri (sonuç noktası HARİÇ)"""

# ═══════════════════════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini = genai.Client(api_key=GEMINI_API_KEY)

deepseek = None
DEEPSEEK_AKTIF = False
if DEEPSEEK_API_KEY:
    try:
        deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
        test = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role': 'user', 'content': '2+2=?'}],
            max_tokens=10
        )
        DEEPSEEK_AKTIF = True
        print("✅ DeepSeek AKTİF")
    except Exception as e:
        print(f"⚠️ DeepSeek hatası: {e}")

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════════════

def json_parse(text):
    """JSON çıkar ve parse et"""
    if not text:
        return None
    
    text = text.strip()
    
    # ```json ... ``` bloğunu çıkar
    if '```' in text:
        import re
        pattern = r'```(?:json)?\s*([\s\S]*?)```'
        matches = re.findall(pattern, text)
        if matches:
            for match in matches:
                if '{' in match and '}' in match:
                    text = match.strip()
                    break
    
    # JSON objesini bul
    start = text.find('{')
    end = text.rfind('}')
    
    if start < 0 or end <= start:
        return None
    
    json_text = text[start:end+1]
    
    # Parse dene
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass
    
    # Temizle
    import re
    json_text = re.sub(r'[\x00-\x1f\x7f]', ' ', json_text)
    json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
    
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass
    
    # Satırları birleştir
    try:
        lines = [l.strip() for l in json_text.split('\n') if l.strip()]
        return json.loads(' '.join(lines))
    except:
        return None

def gorsel_tipi_sec(topic_name, baglam_id):
    """Konuya ve bağlama göre uygun görsel tipi seç"""
    topic_lower = topic_name.lower() if topic_name else ""
    
    # Konu bazlı seçim
    if any(x in topic_lower for x in ["üçgen", "dörtgen", "çember", "daire", "geometri", "açı"]):
        tipler = GORSEL_TIPLERI["geometri"]
    elif any(x in topic_lower for x in ["cebir", "denklem", "fonksiyon", "polinom"]):
        tipler = GORSEL_TIPLERI["cebir"]
    elif any(x in topic_lower for x in ["veri", "istatistik", "grafik", "tablo"]):
        tipler = GORSEL_TIPLERI["veri"]
    elif any(x in topic_lower for x in ["olasılık", "permütasyon", "kombinasyon"]):
        tipler = GORSEL_TIPLERI["olasilik"]
    else:
        # Bağlam bazlı fallback
        tipler = GORSEL_TIPLERI.get(baglam_id, GORSEL_TIPLERI["default"])
    
    return random.choice(tipler)

# ═══════════════════════════════════════════════════════════════════════════════
# GÖRSEL ÜRETİM FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════════

def gorsel_uret(gorsel_betimleme):
    """Gemini Image API ile görsel üret"""
    
    if not GORSEL_URETIM_AKTIF:
        return None
    
    tip = gorsel_betimleme.get("tip", "geometrik_sekil")
    detay = gorsel_betimleme.get("detay", "")
    gorunen_veriler = gorsel_betimleme.get("gorunen_veriler", "")
    
    full_detay = f"{detay}\n\nGörselde görünecek değerler: {gorunen_veriler}"
    prompt = IMAGE_PROMPT_TEMPLATE.format(tip=tip, detay=full_detay)
    
    for attempt in range(3):
        try:
            print(f"      🎨 Görsel üretiliyor (deneme {attempt + 1}/3)...")
            
            response = gemini.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
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
                            print(f"      ✅ Görsel üretildi ({len(image_bytes)} bytes)")
                            return image_bytes
            
            print("      ⚠️ Görsel response'da bulunamadı")
            
        except Exception as e:
            print(f"      ⚠️ Görsel hatası (deneme {attempt + 1}): {str(e)[:100]}")
            time.sleep(2)
    
    print("      ❌ Görsel üretimi başarısız")
    return None

def storage_yukle(image_data, filename):
    """Supabase Storage'a görsel yükle"""
    
    if not image_data:
        return None
    
    try:
        # image_data bytes olarak geliyor
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data
        
        upload_url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{filename}"
        
        response = requests.post(
            upload_url,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "image/png"
            },
            data=image_bytes,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{filename}"
            print(f"      ✅ Görsel yüklendi: {filename}")
            return public_url
        else:
            print(f"      ⚠️ Yükleme hatası: {response.status_code} - {response.text[:100]}")
            return None
            
    except Exception as e:
        print(f"      ⚠️ Storage hatası: {str(e)[:100]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# VERİTABANI FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════════

def curriculum_getir():
    """Matematik ve Geometri kazanımlarını getir - sınıf filtresine göre"""
    try:
        # Temel sorgular
        mat_query = supabase.table('curriculum').select('*').eq('lesson_name', 'Matematik')
        geo_query = supabase.table('curriculum').select('*').eq('lesson_name', 'Geometri')
        
        # Sınıf filtresi varsa uygula
        if SINIF_FILTRE:
            mat_query = mat_query.eq('grade_level', SINIF_FILTRE)
            geo_query = geo_query.eq('grade_level', SINIF_FILTRE)
            print(f"📌 Sınıf filtresi aktif: {SINIF_FILTRE}. sınıf")
        else:
            mat_query = mat_query.gte('grade_level', 3).lte('grade_level', 12)
            geo_query = geo_query.gte('grade_level', 3).lte('grade_level', 12)
        
        matematik = mat_query.execute()
        geometri = geo_query.execute()
        
        sonuc = []
        if matematik.data:
            sonuc.extend(matematik.data)
        if geometri.data:
            sonuc.extend(geometri.data)
        return sonuc
    except Exception as e:
        print(f"❌ Curriculum hatası: {e}")
        return []

def mevcut_soru_sayisi(curriculum_id):
    """Kazanım için mevcut soru sayısı - devre dışı, her zaman 0 döner"""
    return 0  # Her zaman yeni soru üret

def soru_kaydet(soru, curriculum_row, puan, image_url=None):
    """Soruyu veritabanına kaydet - question_bank tablosuna uygun"""
    try:
        senaryo = soru.get('senaryo', '')
        soru_metni = soru.get('soru_metni', '')
        tam_metin = f"{senaryo}\n\n{soru_metni}"
        
        secenekler = soru.get('secenekler', {})
        cozum = soru.get('cozum_adimlari', [])
        sinif = curriculum_row.get('grade_level', 8)
        
        # topic_group belirle
        if sinif <= 4:
            topic_group = "ILKOKUL"
        elif sinif <= 8:
            topic_group = "LGS"
        elif sinif <= 10:
            topic_group = "TYT"
        else:
            topic_group = "AYT"
        
        kayit = {
            'original_text': tam_metin,
            'scenario_text': senaryo,
            'options': secenekler if isinstance(secenekler, dict) else json.loads(secenekler) if isinstance(secenekler, str) else {},
            'correct_answer': soru.get('dogru_cevap', 'A'),
            'solution_text': '\n'.join(cozum) if isinstance(cozum, list) else str(cozum),
            'solution_detailed': soru.get('solution_detailed', ''),
            'difficulty': soru.get('zorluk_puan', 3),
            'subject': curriculum_row.get('lesson_name', 'Matematik'),
            'grade_level': sinif,
            'topic': f"{curriculum_row.get('topic_name', '')} -> {curriculum_row.get('sub_topic', '')}".strip(' ->'),
            'topic_group': topic_group,
            'kazanim_id': curriculum_row.get('id'),
            'question_type': 'coktan_secmeli',
            'bloom_level': soru.get('bloom_seviye', 'uygulama'),
            'life_skill_category': soru.get('baglam_adi', ''),
            'is_active': True,
            'verified': False
        }
        
        # Görsel URL varsa ekle
        if image_url:
            kayit['image_url'] = image_url
        
        result = supabase.table('question_bank').insert(kayit).execute()
        return result.data[0].get('id') if result.data else None
    except Exception as e:
        print(f"   ❌ Kayıt hatası: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI SORU ÜRETİMİ (GÖRSEL BETİMLEME DAHİL)
# ═══════════════════════════════════════════════════════════════════════════════

def gemini_soru_uret(curriculum_row, bloom_seviye, baglam, geri_bildirim=None, gorsel_gerekli=False):
    """Gemini ile soru üret - Görsel betimleme dahil"""
    
    sinif = curriculum_row.get('grade_level', 8)
    topic = curriculum_row.get('topic_name', '')
    sub_topic = curriculum_row.get('sub_topic', '')
    ayar = SINIF_AYARLARI.get(sinif, SINIF_AYARLARI[8])
    
    min_kelime, max_kelime = ayar['kelime']
    secenek_sayisi = ayar['secenek']
    
    isim = random.choice(ISIMLER)
    ornek = random.choice(baglam['ornekler'])
    
    geri_bildirim_text = ""
    if geri_bildirim:
        geri_bildirim_text = f"\n\n⚠️ ÖNCEKİ HATA: {geri_bildirim}\nBu hatayı düzelt!"
    
    # Görsel tipi seç
    gorsel_tipi = gorsel_tipi_sec(topic, baglam['id'])
    
    # Görsel betimleme talimatı
    gorsel_talimat = ""
    if gorsel_gerekli:
        gorsel_talimat = f'''

ADIM 4 - GÖRSEL BETİMLEME (ÇOK ÖNEMLİ!):
Soru için profesyonel bir eğitim görseli betimle.
Görsel tipi: {gorsel_tipi}

⚠️ KRİTİK KURALLAR - ÇÖZÜM İPUCU VERMEME:
- Görselde SADECE senaryoda VERİLEN bilgiler olmalı
- ÇÖZÜMDE HESAPLANAN değerler ASLA görselde olmamalı
- Cevabı gösteren noktalar, işaretler, değerler YASAK
- Grafiklerde sonuç noktası (cevap koordinatı) GÖSTERİLMEMELİ
- Sadece problemin BAŞLANGIÇ durumunu göster
- Öğrenci görsele bakarak cevabı BULAMAMALI

ÖRNEK - YANLIŞ: Kargo sorusunda (20, 75) noktası göstermek (çünkü 20 kg cevaptır)
ÖRNEK - DOĞRU: Sadece 45 TL sabit ücret çizgisi ve 3 TL/kg eğimi göstermek

"gorsel_betimleme" alanında şunları yaz:
- "tip": görsel tipi ("{gorsel_tipi}")
- "detay": çizilecek şeklin detaylı açıklaması (minimum 50 kelime) - SADECE VERİLEN BİLGİLER
- "gorunen_veriler": SADECE soruda verilen sabit değerler (hesaplanan sonuçlar HARİÇ)
'''

    prompt = f'''Matematik sorusu oluştur. ÖNEMLİ: Önce çözümü yap, sonra şıkları oluştur!

KONU: {topic}
ALT KONU: {sub_topic}
SINIF: {sinif}. sınıf
KARAKTER: {isim}
BAĞLAM: {ornek}
{geri_bildirim_text}

ADIM ADIM İLERLE:

ADIM 1 - PROBLEM TASARLA:
- Sayısal değerler belirle
- Çözümü yap, DOĞRU CEVABI HESAPLA

ADIM 2 - SENARYO YAZ:
- {isim} karakteri ile {ornek} temalı hikaye ({min_kelime}-{max_kelime} kelime)

ADIM 3 - ŞIKLARI OLUŞTUR:
- A: Doğru cevap (hesapladığın)
- B,C,D{",E" if secenek_sayisi == 5 else ""}: Yaygın hatalardan türetilmiş çeldiriciler
{gorsel_talimat}

KRİTİK: Doğru cevap MUTLAKA şıklarda olmalı! Çözümdeki sonuç = Doğru şık

JSON:
{{"senaryo":"hikaye", "soru_metni":"soru", "secenekler":{{"A":"doğru","B":"çeldirici1","C":"çeldirici2","D":"çeldirici3"{', "E":"çeldirici4"' if secenek_sayisi == 5 else ''}}}, "dogru_cevap":"A", "cozum":"Adım adım çözüm"{', "gorsel_betimleme":{{"tip":"...", "detay":"...", "gorunen_veriler":"..."}}' if gorsel_gerekli else ''}}}'''

    try:
        response = gemini.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=8096
            )
        )
        
        raw_text = response.text if response.text else ""
        
        if not raw_text:
            return None
        
        soru = json_parse(raw_text)
        
        if soru:
            soru['sinif'] = sinif
            soru['curriculum_id'] = curriculum_row.get('id')
            soru['topic_name'] = topic
            soru['sub_topic'] = sub_topic
            soru['bloom_seviye'] = bloom_seviye
            soru['baglam_adi'] = baglam['ad']
            soru['zorluk_puan'] = {"hatırlama": 1, "anlama": 2, "uygulama": 3, "analiz": 4, "değerlendirme": 5, "yaratma": 6}.get(bloom_seviye, 3)
            
            # Eksik alanları tamamla
            if 'secenekler' not in soru or not soru['secenekler']:
                soru['secenekler'] = {"A": "?", "B": "?", "C": "?", "D": "?"}
            if 'dogru_cevap' not in soru:
                soru['dogru_cevap'] = "A"
            if 'soru_metni' not in soru:
                soru['soru_metni'] = "Sonuç kaçtır?"
            if 'cozum_adimlari' not in soru:
                soru['cozum_adimlari'] = [soru.get('cozum', 'Çözüm')]
            if 'solution_detailed' not in soru:
                soru['solution_detailed'] = soru.get('cozum', soru.get('senaryo', ''))
            
            return soru
        
        return None
        
    except Exception as e:
        print(f"      ⚠️ Gemini hatası: {str(e)[:100]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DOĞRULAMA (DeepSeek veya Gemini)
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_dogrula(soru):
    """DeepSeek ile doğrula"""
    if not DEEPSEEK_AKTIF:
        return None  # Fallback'e geç
    
    try:
        prompt = f'''Bu matematik sorusunu değerlendir (100 üzerinden puan ver):

{json.dumps(soru, ensure_ascii=False, indent=2)}

JSON yanıt:
{{"gecerli": true/false, "puan": 0-100, "geri_bildirim": "varsa sorun"}}'''

        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=500
        )
        
        result = json_parse(response.choices[0].message.content)
        return result if result else None
        
    except Exception as e:
        print(f"      ⚠️ DeepSeek doğrulama hatası: {str(e)[:50]}")
        return None

def gemini_dogrula(soru):
    """Gemini ile doğrula (fallback) - Matematiksel tutarlılık kontrolü"""
    try:
        cozum = soru.get('cozum', soru.get('solution_detailed', ''))
        secenekler = soru.get('secenekler', {})
        dogru_cevap = soru.get('dogru_cevap', 'A')
        dogru_sik_degeri = secenekler.get(dogru_cevap, '')
        
        prompt = f'''Bu matematik sorusunu KONTROL ET:

ÇÖZÜM: {cozum}

ŞIKLAR: {json.dumps(secenekler, ensure_ascii=False)}

DOĞRU CEVAP: {dogru_cevap} = {dogru_sik_degeri}

KONTROL:
1. Çözümdeki sonuç ile "{dogru_cevap}" şıkkındaki değer ({dogru_sik_degeri}) AYNI MI?
2. Matematiksel işlemler doğru mu?
3. Diğer şıklar mantıklı çeldiriciler mi?

JSON yanıt:
{{"gecerli": true/false, "puan": 0-100, "geri_bildirim": "Eğer çözüm sonucu şıkla uyuşmuyorsa veya hata varsa açıkla, yoksa null"}}'''

        response = gemini.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2500
            )
        )
        
        result = json_parse(response.text)
        return result if result else {"gecerli": True, "puan": 70, "geri_bildirim": None}
        
    except Exception as e:
        print(f"      ⚠️ Gemini doğrulama hatası: {str(e)[:50]}")
        return {"gecerli": True, "puan": 70, "geri_bildirim": None}

def soru_dogrula(soru):
    """Soruyu doğrula - önce DeepSeek, yoksa Gemini"""
    # Önce DeepSeek dene
    result = deepseek_dogrula(soru)
    if result:
        return result
    
    # DeepSeek yoksa Gemini kullan
    return gemini_dogrula(soru)

# ═══════════════════════════════════════════════════════════════════════════════
# SORU ÜRETİM PIPELINE (GÖRSEL DAHİL)
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret(curriculum_row, bloom_seviye, baglam):
    """Tek soru üret - görsel dahil"""
    
    MAX_DENEME = 3
    geri_bildirim = None
    
    # Görsel gerekli mi?
    sinif = curriculum_row.get('grade_level', 8)
    ayar = SINIF_AYARLARI.get(sinif, SINIF_AYARLARI[8])
    gorsel_oran = ayar.get('gorsel_oran', 0.5)
    gorsel_gerekli = GORSEL_URETIM_AKTIF and (random.random() < gorsel_oran)
    
    if gorsel_gerekli:
        print(f"      🎨 Görsel ÜRETİLECEK")
    
    for deneme in range(MAX_DENEME):
        time.sleep(0.5)
        
        soru = gemini_soru_uret(curriculum_row, bloom_seviye, baglam, geri_bildirim, gorsel_gerekli)
        
        if not soru:
            print(f"      ⚠️ Soru üretilemedi (Deneme {deneme+1})")
            continue
        
        if len(soru.get('senaryo', '')) < 30:
            print(f"      ⚠️ Senaryo çok kısa (Deneme {deneme+1})")
            geri_bildirim = "Senaryo çok kısa, en az 80 kelime olmalı"
            continue
        
        dogrulama = soru_dogrula(soru)
        puan = dogrulama.get('puan', 75)
        
        if dogrulama.get('gecerli', True) and puan >= 50:
            # Görsel üret (eğer betimleme varsa)
            image_url = None
            if gorsel_gerekli and soru.get('gorsel_betimleme'):
                image_data = gorsel_uret(soru['gorsel_betimleme'])
                if image_data:
                    # Benzersiz dosya adı oluştur
                    filename = f"pisa_{sinif}_{uuid.uuid4().hex[:8]}_{int(time.time())}.png"
                    image_url = storage_yukle(image_data, filename)
            
            return soru, puan, image_url
        else:
            geri_bildirim = dogrulama.get('geri_bildirim')
            print(f"      ⚠️ Puan: {puan}/100 (Deneme {deneme+1})")
    
    return None, 0, None

# ═══════════════════════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════════════════════

def toplu_uret():
    """Tüm kazanımlar için soru üret"""
    
    curriculum = curriculum_getir()
    if not curriculum:
        print("❌ Curriculum bulunamadı!")
        return 0
    
    sinif_dagilimi = {}
    for c in curriculum:
        sinif = c.get('grade_level', 0)
        sinif_dagilimi[sinif] = sinif_dagilimi.get(sinif, 0) + 1
    
    print(f"\n✅ {len(curriculum)} Matematik/Geometri kazanımı bulundu")
    print("   📊 Sınıf Dağılımı:")
    for sinif in sorted(sinif_dagilimi.keys()):
        print(f"      {sinif}. Sınıf: {sinif_dagilimi[sinif]} kazanım")
    
    # Eksik soru olanları seç
    secilen = []
    for kaz in curriculum:
        mevcut = mevcut_soru_sayisi(kaz.get('id'))
        if mevcut < SORU_PER_KAZANIM:
            kaz['_mevcut'] = mevcut
            secilen.append(kaz)
    
    if not secilen:
        print("✅ Tüm kazanımlarda yeterli soru var!")
        return 0
    
    random.shuffle(secilen)
    secilen = secilen[:MAX_KAZANIM]
    
    print(f"\n{'='*70}")
    print(f"🎯 BAĞLAM TEMELLİ SORU ÜRETİM V6 - GÖRSEL DESTEKLİ")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Sınıf Filtresi: {f'{SINIF_FILTRE}. sınıf' if SINIF_FILTRE else 'Tüm sınıflar (3-12)'}")
    print(f"   İşlenecek: {len(secilen)} kazanım")
    print(f"   Kazanım başına: {SORU_PER_KAZANIM} soru")
    print(f"   DeepSeek: {'✅ AKTİF' if DEEPSEEK_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"   Görsel Üretim: {'✅ AKTİF' if GORSEL_URETIM_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"{'='*70}\n")
    
    basarili = 0
    gorselli = 0
    toplam_puan = 0
    baslangic = time.time()
    
    for idx, kaz in enumerate(secilen):
        sinif = kaz.get('grade_level', 8)
        topic = kaz.get('topic_name', '')
        sub_topic = kaz.get('sub_topic', '')
        kaz_id = kaz.get('id')
        mevcut = kaz.get('_mevcut', 0)
        ayar = SINIF_AYARLARI.get(sinif, SINIF_AYARLARI[8])
        
        print(f"[{idx+1}/{len(secilen)}] Kazanım ID: {kaz_id}")
        print(f"   📚 {topic}" + (f" - {sub_topic}" if sub_topic else ""))
        print(f"   📊 {sinif}. Sınıf | Mevcut: {mevcut}/{SORU_PER_KAZANIM}")
        
        bloom_listesi = ayar['bloom'][:SORU_PER_KAZANIM - mevcut]
        
        for soru_idx, bloom in enumerate(bloom_listesi):
            baglam = random.choice(BAGLAMLAR)
            
            print(f"\n   Soru {mevcut + soru_idx + 1}/{SORU_PER_KAZANIM}:")
            print(f"      Bloom: {bloom} | Bağlam: {baglam['ad']}")
            
            soru, puan, image_url = tek_soru_uret(kaz, bloom, baglam)
            
            if soru:
                soru_id = soru_kaydet(soru, kaz, puan, image_url)
                if soru_id:
                    basarili += 1
                    toplam_puan += puan
                    if image_url:
                        gorselli += 1
                        print(f"      ✅ Başarılı! ID: {soru_id} | Puan: {puan}/100 | 🖼️ GÖRSELLİ")
                    else:
                        print(f"      ✅ Başarılı! ID: {soru_id} | Puan: {puan}/100")
                else:
                    print(f"      ❌ Kayıt başarısız")
            else:
                print(f"      ❌ Üretim başarısız")
            
            time.sleep(BEKLEME)
        
        print()
    
    sure = time.time() - baslangic
    ort_puan = toplam_puan / basarili if basarili > 0 else 0
    
    print(f"{'='*70}")
    print(f"📊 SONUÇ RAPORU")
    print(f"{'='*70}")
    print(f"   ✅ Toplam üretilen: {basarili} soru")
    print(f"   🖼️ Görselli soru: {gorselli}")
    print(f"   📈 Ortalama Kalite: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"{'='*70}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🎯 BAĞLAM TEMELLİ SORU ÜRETİCİ BOT V6 - GÖRSEL DESTEKLİ")
    print("   📚 12 Farklı Bağlam Türü")
    print("   🧠 Bloom Taksonomisi")
    print("   ✨ Gemini 2.5 Flash + Gemini Image")
    print("   🖼️ Otomatik Görsel Üretimi")
    if SINIF_FILTRE:
        print(f"   🎯 Hedef Sınıf: {SINIF_FILTRE}. sınıf")
    print("="*70 + "\n")
    
    print("🔍 Gemini API test ediliyor...")
    try:
        response = gemini.models.generate_content(
            model='gemini-2.5-flash',
            contents='2+2=?'
        )
        print(f"✅ Gemini çalışıyor: {response.text.strip()[:20]}")
    except Exception as e:
        print(f"❌ Gemini HATASI: {e}")
        return
    
    basarili = toplu_uret()
    
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} bağlam temelli soru üretildi.")

if __name__ == "__main__":
    main()
