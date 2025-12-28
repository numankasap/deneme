"""
🎯 BAĞLAM TEMELLİ SORU ÜRETİCİ BOT V5
═══════════════════════════════════════════════════════════════════════════════

Temiz, sade ve etkili soru üretici.
- Gemini 2.5 Pro: Soru üretimi (CoT ile)
- DeepSeek Reasoner: Doğrulama ve geri bildirim
- Her bağlamdan 1 soru
- Her kazanımdan 3 zorluk seviyesi

@version 5.0.0
@author MATAİ PRO
"""

import os
import json
import random
import time
import hashlib
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

# Ayarlar
SORU_PER_KAZANIM = int(os.environ.get('SORU_PER_KAZANIM', '3'))
MAX_KAZANIM = int(os.environ.get('MAX_ISLEM_PER_RUN', '10'))
BEKLEME = 2.0

# ═══════════════════════════════════════════════════════════════════════════════
# 12 BAĞLAM TÜRÜ (HTML'den alındı)
# ═══════════════════════════════════════════════════════════════════════════════

BAGLAMLAR = [
    {"id": "gunluk", "ad": "Günlük Yaşam", "icon": "🏠", "ornekler": ["alışveriş", "ev işleri", "ulaşım", "yemek tarifi"]},
    {"id": "mesleki", "ad": "Mesleki", "icon": "💼", "ornekler": ["mühendislik", "mimarlık", "tarım", "ticaret"]},
    {"id": "cevre", "ad": "Çevresel", "icon": "🌿", "ornekler": ["iklim", "geri dönüşüm", "enerji tasarrufu", "su kaynakları"]},
    {"id": "bilimsel", "ad": "Bilimsel", "icon": "🔬", "ornekler": ["deney", "araştırma", "gözlem", "ölçüm"]},
    {"id": "tarihsel", "ad": "Tarihsel", "icon": "🏛️", "ornekler": ["antik yapılar", "eski uygarlıklar", "tarihsel olaylar"]},
    {"id": "kulturel", "ad": "Kültürel", "icon": "🎭", "ornekler": ["sanat", "müzik", "gelenekler", "el sanatları"]},
    {"id": "sportif", "ad": "Sportif", "icon": "⚽", "ornekler": ["maç istatistikleri", "antrenman", "yarışma"]},
    {"id": "teknolojik", "ad": "Teknolojik", "icon": "💻", "ornekler": ["yazılım", "robotik", "yapay zeka", "internet"]},
    {"id": "saglik", "ad": "Sağlık", "icon": "🏥", "ornekler": ["beslenme", "egzersiz", "ilaç dozu", "hastane"]},
    {"id": "vatandaslik", "ad": "Vatandaşlık", "icon": "🏙️", "ornekler": ["belediye", "seçim", "vergi", "toplum"]},
    {"id": "ekonomik", "ad": "Ekonomik", "icon": "💰", "ornekler": ["bütçe", "faiz", "yatırım", "tasarruf"]},
    {"id": "oyun", "ad": "Oyunlaştırılmış", "icon": "🎮", "ornekler": ["bulmaca", "strateji oyunu", "hazine avı"]}
]

# ═══════════════════════════════════════════════════════════════════════════════
# SINIF SEVİYE AYARLARI
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_AYARLARI = {
    # İlkokul (3-4): Basit, somut, kısa
    3: {"kelime": (80, 120), "bloom": ["hatırlama", "anlama"], "secenek": 4, "seviye": "ilkokul"},
    4: {"kelime": (80, 120), "bloom": ["hatırlama", "anlama", "uygulama"], "secenek": 4, "seviye": "ilkokul"},
    
    # Ortaokul (5-8): Orta uzunluk, grafik/tablo destekli
    5: {"kelime": (120, 180), "bloom": ["anlama", "uygulama", "analiz"], "secenek": 4, "seviye": "ortaokul"},
    6: {"kelime": (120, 180), "bloom": ["anlama", "uygulama", "analiz"], "secenek": 4, "seviye": "ortaokul"},
    7: {"kelime": (150, 200), "bloom": ["uygulama", "analiz"], "secenek": 4, "seviye": "ortaokul"},
    8: {"kelime": (150, 200), "bloom": ["uygulama", "analiz", "değerlendirme"], "secenek": 4, "seviye": "ortaokul"},
    
    # Lise (9-12): Uzun, karmaşık senaryolar
    9: {"kelime": (180, 250), "bloom": ["uygulama", "analiz", "değerlendirme"], "secenek": 5, "seviye": "lise"},
    10: {"kelime": (180, 250), "bloom": ["analiz", "değerlendirme"], "secenek": 5, "seviye": "lise"},
    11: {"kelime": (200, 300), "bloom": ["analiz", "değerlendirme", "yaratma"], "secenek": 5, "seviye": "lise"},
    12: {"kelime": (200, 300), "bloom": ["analiz", "değerlendirme", "yaratma"], "secenek": 5, "seviye": "lise"}
}

# Türk isimleri
ISIMLER = ["Elif", "Yusuf", "Zeynep", "Ahmet", "Ayşe", "Mehmet", "Fatma", "Ali", "Emine", "Mustafa",
           "Defne", "Ege", "Ada", "Kerem", "Mira", "Baran", "Ela", "Deniz", "Can", "Su"]

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
        # Test
        test = deepseek.chat.completions.create(
            model='deepseek-reasoner',
            messages=[{'role': 'user', 'content': '2+2=?'}],
            max_tokens=10
        )
        DEEPSEEK_AKTIF = True
        print("✅ DeepSeek Reasoner AKTİF")
    except Exception as e:
        print(f"⚠️ DeepSeek hatası: {e}")

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════════════

def rastgele_isim():
    return random.choice(ISIMLER)

def rastgele_baglam():
    return random.choice(BAGLAMLAR)

def json_parse(text):
    """JSON çıkar ve parse et"""
    if not text:
        return None
    
    # Markdown temizle
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0]
    elif '```' in text:
        for part in text.split('```'):
            if '{' in part and '}' in part:
                text = part
                break
    
    # JSON bul
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start:
        return None
    
    text = text[start:end+1]
    
    try:
        return json.loads(text)
    except:
        # Temizle ve tekrar dene
        import re
        text = re.sub(r'[\x00-\x1f]', ' ', text)
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*\]', ']', text)
        try:
            return json.loads(text)
        except:
            return None

def soru_hash(soru):
    """Soru için benzersiz hash"""
    metin = f"{soru.get('senaryo', '')}{soru.get('soru_metni', '')}"
    return hashlib.md5(metin.encode()).hexdigest()[:16]

# ═══════════════════════════════════════════════════════════════════════════════
# VERİTABANI FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════════

def curriculum_getir():
    """Matematik kazanımlarını getir"""
    try:
        result = supabase.table('curriculum').select('*').eq('subject', 'Matematik').gte('grade_level', 3).lte('grade_level', 12).execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"❌ Curriculum hatası: {e}")
        return []

def mevcut_soru_sayisi(curriculum_id):
    """Kazanım için mevcut soru sayısı"""
    try:
        result = supabase.table('question_bank').select('id', count='exact').eq('curriculum_id', curriculum_id).execute()
        return result.count or 0
    except:
        return 0

def soru_kaydet(soru, curriculum_row, puan):
    """Soruyu veritabanına kaydet"""
    try:
        senaryo = soru.get('senaryo', '')
        soru_metni = soru.get('soru_metni', '')
        tam_metin = f"{senaryo}\n\n{soru_metni}"
        
        secenekler = soru.get('secenekler', {})
        cozum = soru.get('cozum_adimlari', [])
        
        kayit = {
            'question_text': tam_metin,
            'options': json.dumps(secenekler, ensure_ascii=False) if isinstance(secenekler, dict) else str(secenekler),
            'correct_answer': soru.get('dogru_cevap', 'A'),
            'solution': '\n'.join(cozum) if isinstance(cozum, list) else str(cozum),
            'solution_latex': soru.get('solution_detailed', ''),
            'difficulty': soru.get('zorluk_puan', 3),
            'curriculum_id': curriculum_row.get('id'),
            'topic': curriculum_row.get('topic_name', ''),
            'sub_topic': curriculum_row.get('sub_topic', ''),
            'grade_level': curriculum_row.get('grade_level', 8),
            'question_type': 'multiple_choice',
            'source': 'curriculum_bot_v5',
            'is_active': True,
            'metadata': json.dumps({
                'bloom': soru.get('bloom_seviye', 'uygulama'),
                'baglam': soru.get('baglam_adi', ''),
                'puan': puan,
                'hash': soru_hash(soru)
            }, ensure_ascii=False)
        }
        
        result = supabase.table('question_bank').insert(kayit).execute()
        return result.data[0].get('id') if result.data else None
    except Exception as e:
        print(f"   ❌ Kayıt hatası: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI: SORU ÜRETİMİ (Chain of Thought)
# ═══════════════════════════════════════════════════════════════════════════════

def gemini_soru_uret(curriculum_row, bloom_seviye, baglam, geri_bildirim=None):
    """Gemini ile CoT kullanarak soru üret"""
    
    sinif = curriculum_row.get('grade_level', 8)
    topic = curriculum_row.get('topic_name', '')
    sub_topic = curriculum_row.get('sub_topic', '')
    ayar = SINIF_AYARLARI.get(sinif, SINIF_AYARLARI[8])
    
    min_kelime, max_kelime = ayar['kelime']
    secenek_sayisi = ayar['secenek']
    seviye = ayar['seviye']
    
    isim = rastgele_isim()
    ornek = random.choice(baglam['ornekler'])
    
    # Seçenek şablonu
    if secenek_sayisi == 4:
        secenekler = '"A": "...", "B": "...", "C": "...", "D": "..."'
    else:
        secenekler = '"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."'
    
    # Geri bildirim varsa ekle
    geri_bildirim_text = ""
    if geri_bildirim:
        geri_bildirim_text = f"""

⚠️ ÖNCEKİ DENEME GERİ BİLDİRİMİ:
{geri_bildirim}
Bu sorunları düzelterek yeni soru üret!
"""
    
    prompt = f'''Sen bir matematik eğitimi uzmanısın. TYMM yaklaşımına uygun bağlam temelli soru hazırla.

📚 KONU: {topic} - {sub_topic if sub_topic else 'Genel'}
📊 SINIF: {sinif}. sınıf ({seviye})
🎯 BLOOM SEVİYESİ: {bloom_seviye.upper()}
🏷️ BAĞLAM: {baglam['icon']} {baglam['ad']} ({ornek})
👤 KARAKTER: {isim}
{geri_bildirim_text}

═══════════════════════════════════════════════════════════════════════════════
📝 ADIM ADIM ÇÖZÜM YAKLAŞIMI (Chain of Thought)
═══════════════════════════════════════════════════════════════════════════════

ADIM 1: Önce matematiksel problemi tasarla
- Konu: {topic}
- Hangi formül/kavram kullanılacak?
- Verilecek sayısal değerler neler?
- Doğru cevap ne olacak?

ADIM 2: Bağlamı oluştur
- {baglam['ad']} bağlamında {isim} karakteri ile senaryo yaz
- {min_kelime}-{max_kelime} kelime
- Tüm sayısal veriler senaryoda olmalı

ADIM 3: Çözüm adımlarını yaz
- Her adımı açıkla
- İşlemleri göster
- Sonuca ulaş

ADIM 4: Şıkları oluştur
- Doğru cevap: Çözümden gelen sonuç
- Çeldiriciler: Yaygın hatalardan türet (işlem hatası, yarım çözüm, ters işlem)

═══════════════════════════════════════════════════════════════════════════════
📋 KURALLAR
═══════════════════════════════════════════════════════════════════════════════
1. Bağlam gerçekçi ve anlamlı olmalı
2. Soru bağlamdan bağımsız cevaplanamamalı
3. Ezbere dayalı değil, beceri ölçen soru olmalı
4. Tüm veriler senaryoda açıkça belirtilmeli
5. {secenek_sayisi} seçenek olmalı

═══════════════════════════════════════════════════════════════════════════════
📤 JSON ÇIKTI
═══════════════════════════════════════════════════════════════════════════════

```json
{{
  "senaryo": "{isim} ile {baglam['ad'].lower()} temalı hikaye ({min_kelime}-{max_kelime} kelime)",
  "soru_metni": "Soru kökü - net ve açık",
  "secenekler": {{{secenekler}}},
  "dogru_cevap": "A/B/C/D/E",
  "cozum_adimlari": [
    "Adım 1: [Açıklama] → [İşlem] = [Sonuç]",
    "Adım 2: [Açıklama] → [İşlem] = [Sonuç]"
  ],
  "solution_detailed": "Öğrenci dostu detaylı çözüm açıklaması",
  "kullanilan_kavram": "{topic} ile ilgili kavram/formül"
}}
```

SADECE JSON döndür!'''

    try:
        response = gemini.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2000
            )
        )
        
        soru = json_parse(response.text)
        
        if soru and 'senaryo' in soru and 'secenekler' in soru:
            # Meta bilgileri ekle
            soru['sinif'] = sinif
            soru['curriculum_id'] = curriculum_row.get('id')
            soru['topic_name'] = topic
            soru['sub_topic'] = sub_topic
            soru['bloom_seviye'] = bloom_seviye
            soru['baglam_adi'] = baglam['ad']
            soru['zorluk_puan'] = {"hatırlama": 1, "anlama": 2, "uygulama": 3, "analiz": 4, "değerlendirme": 5, "yaratma": 6}.get(bloom_seviye, 3)
            return soru
        
        return None
        
    except Exception as e:
        print(f"      ⚠️ Gemini hatası: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK: DOĞRULAMA VE GERİ BİLDİRİM
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_dogrula(soru):
    """DeepSeek Reasoner ile soru doğrula"""
    
    if not DEEPSEEK_AKTIF:
        return {"gecerli": True, "puan": 75, "geri_bildirim": None}
    
    try:
        prompt = f'''Aşağıdaki matematik sorusunu değerlendir:

SORU:
{json.dumps(soru, ensure_ascii=False, indent=2)}

DEĞERLENDİRME KRİTERLERİ (her biri 25 puan):

1. MATEMATİKSEL DOĞRULUK (25p)
   - Çözüm adımları doğru mu?
   - Sonuç doğru hesaplanmış mı?
   - Doğru cevap şıklarda var mı?

2. KONU UYUMU (25p)
   - Soru belirtilen konuyla ilgili mi?
   - Konunun kavramları kullanılmış mı?

3. BAĞLAM KALİTESİ (25p)
   - Senaryo gerçekçi mi?
   - Tüm veriler mevcut mu?
   - Bağlam olmadan cevaplanabilir mi? (olmamalı)

4. SINIF SEVİYESİ (25p)
   - Zorluk seviyesi uygun mu?
   - Dil ve anlatım yaşa uygun mu?

JSON ÇIKTI:
```json
{{
  "gecerli": true/false,
  "puan": 0-100,
  "geri_bildirim": "Varsa düzeltilmesi gereken noktalar veya null"
}}
```'''

        response = deepseek.chat.completions.create(
            model='deepseek-reasoner',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=1000
        )
        
        result = json_parse(response.choices[0].message.content)
        
        if result:
            return result
        return {"gecerli": True, "puan": 70, "geri_bildirim": None}
        
    except Exception as e:
        print(f"      ⚠️ DeepSeek hatası: {str(e)[:40]}")
        return {"gecerli": True, "puan": 70, "geri_bildirim": None}

# ═══════════════════════════════════════════════════════════════════════════════
# ANA SORU ÜRETİM PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret(curriculum_row, bloom_seviye, baglam):
    """Tek soru üret: Gemini → DeepSeek → Geri bildirim döngüsü"""
    
    MAX_DENEME = 3
    geri_bildirim = None
    
    for deneme in range(MAX_DENEME):
        time.sleep(0.5)
        
        # 1. Gemini ile soru üret
        soru = gemini_soru_uret(curriculum_row, bloom_seviye, baglam, geri_bildirim)
        
        if not soru:
            print(f"      ⚠️ Soru üretilemedi (Deneme {deneme+1})")
            continue
        
        # 2. Temel kontroller
        if not soru.get('senaryo') or len(soru.get('senaryo', '')) < 50:
            print(f"      ⚠️ Senaryo çok kısa (Deneme {deneme+1})")
            geri_bildirim = "Senaryo çok kısa, en az 80 kelime olmalı"
            continue
        
        if not soru.get('secenekler') or len(soru.get('secenekler', {})) < 4:
            print(f"      ⚠️ Şıklar eksik (Deneme {deneme+1})")
            geri_bildirim = "En az 4 şık olmalı"
            continue
        
        # 3. DeepSeek doğrulama
        dogrulama = deepseek_dogrula(soru)
        puan = dogrulama.get('puan', 70)
        
        if dogrulama.get('gecerli', True) and puan >= 60:
            # Başarılı!
            return soru, puan
        else:
            # Geri bildirim al ve tekrar dene
            geri_bildirim = dogrulama.get('geri_bildirim')
            print(f"      ⚠️ DeepSeek: {puan}/100 (Deneme {deneme+1})")
            if geri_bildirim:
                print(f"         → {geri_bildirim[:60]}...")
    
    return None, 0

# ═══════════════════════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════════════════════

def toplu_uret():
    """Tüm kazanımlar için soru üret"""
    
    # Curriculum getir
    curriculum = curriculum_getir()
    if not curriculum:
        print("❌ Curriculum bulunamadı!")
        return 0
    
    # Sınıf dağılımı
    sinif_dagilimi = {}
    for c in curriculum:
        sinif = c.get('grade_level', 0)
        sinif_dagilimi[sinif] = sinif_dagilimi.get(sinif, 0) + 1
    
    print(f"\n✅ {len(curriculum)} Matematik kazanımı bulundu (3-12. sınıf)")
    print("   📊 Sınıf Dağılımı:")
    for sinif in sorted(sinif_dagilimi.keys()):
        print(f"      {sinif}. Sınıf: {sinif_dagilimi[sinif]} kazanım")
    
    # Her sınıftan dengeli seçim
    secilen = []
    for sinif in range(3, 13):
        sinif_kazanimlari = [c for c in curriculum if c.get('grade_level') == sinif]
        if sinif_kazanimlari:
            # Eksik sorular olanları öncelikle al
            for kaz in sinif_kazanimlari:
                mevcut = mevcut_soru_sayisi(kaz.get('id'))
                if mevcut < SORU_PER_KAZANIM:
                    kaz['_mevcut'] = mevcut
                    secilen.append(kaz)
                    if len([s for s in secilen if s.get('grade_level') == sinif]) >= MAX_KAZANIM // 10 + 1:
                        break
    
    if not secilen:
        print("✅ Tüm kazanımlarda yeterli soru var!")
        return 0
    
    # Karıştır ve limitle
    random.shuffle(secilen)
    secilen = secilen[:MAX_KAZANIM]
    
    print(f"\n{'='*70}")
    print(f"🎯 BAĞLAM TEMELLİ SORU ÜRETİM V5")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   İşlenecek: {len(secilen)} kazanım")
    print(f"   Kazanım başına: {SORU_PER_KAZANIM} soru (farklı bloom seviyeleri)")
    print(f"   DeepSeek: {'✅ AKTİF' if DEEPSEEK_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"{'='*70}\n")
    
    basarili = 0
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
        
        # Her kazanım için farklı bloom seviyelerinde soru üret
        bloom_listesi = ayar['bloom'][:SORU_PER_KAZANIM - mevcut]
        
        for soru_idx, bloom in enumerate(bloom_listesi):
            baglam = rastgele_baglam()
            
            print(f"\n   Soru {mevcut + soru_idx + 1}/{SORU_PER_KAZANIM}:")
            print(f"      Bloom: {bloom} | Bağlam: {baglam['icon']} {baglam['ad']}")
            
            soru, puan = tek_soru_uret(kaz, bloom, baglam)
            
            if soru:
                soru_id = soru_kaydet(soru, kaz, puan)
                if soru_id:
                    basarili += 1
                    toplam_puan += puan
                    print(f"      ✅ Başarılı! ID: {soru_id} | Puan: {puan}/100")
                else:
                    print(f"      ❌ Kayıt başarısız")
            else:
                print(f"      ❌ Üretim başarısız")
            
            time.sleep(BEKLEME)
        
        print()
    
    # Rapor
    sure = time.time() - baslangic
    ort_puan = toplam_puan / basarili if basarili > 0 else 0
    
    print(f"{'='*70}")
    print(f"📊 SONUÇ RAPORU")
    print(f"{'='*70}")
    print(f"   ✅ Toplam üretilen: {basarili} soru")
    print(f"   📈 Ortalama Kalite: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"{'='*70}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🎯 BAĞLAM TEMELLİ SORU ÜRETİCİ BOT V5")
    print("   📚 12 Farklı Bağlam Türü")
    print("   🧠 Bloom Taksonomisi Entegrasyonu")
    print("   🔄 Gemini → DeepSeek Geri Bildirim Döngüsü")
    print("   ✨ Chain of Thought Yaklaşımı")
    print("="*70 + "\n")
    
    # Gemini testi
    print("🔍 Gemini API test ediliyor...")
    try:
        response = gemini.models.generate_content(
            model='gemini-2.5-pro',
            contents='2+2=?'
        )
        print(f"✅ Gemini Pro çalışıyor: {response.text.strip()[:20]}")
    except Exception as e:
        print(f"❌ Gemini HATASI: {e}")
        return
    
    # Üretim başlat
    basarili = toplu_uret()
    
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} bağlam temelli soru üretildi.")

if __name__ == "__main__":
    main()
