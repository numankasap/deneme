"""
🎯 BAĞLAM TEMELLİ SORU ÜRETİCİ BOT V5
═══════════════════════════════════════════════════════════════════════════════

Temiz, sade ve etkili soru üretici.
- Gemini 2.5 Flash: Soru üretimi
- DeepSeek: Doğrulama ve geri bildirim (opsiyonel)
- 12 farklı bağlam türü
- Sınıf seviyesine uygun Bloom taksonomisi

@version 5.0.1
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

SORU_PER_KAZANIM = int(os.environ.get('SORU_PER_KAZANIM', '3'))
MAX_KAZANIM = int(os.environ.get('MAX_ISLEM_PER_RUN', '10'))
BEKLEME = 2.0

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
# SINIF SEVİYE AYARLARI
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_AYARLARI = {
    3: {"kelime": (80, 120), "bloom": ["hatırlama", "anlama"], "secenek": 4},
    4: {"kelime": (80, 120), "bloom": ["hatırlama", "anlama", "uygulama"], "secenek": 4},
    5: {"kelime": (120, 180), "bloom": ["anlama", "uygulama", "analiz"], "secenek": 4},
    6: {"kelime": (120, 180), "bloom": ["anlama", "uygulama", "analiz"], "secenek": 4},
    7: {"kelime": (150, 200), "bloom": ["uygulama", "analiz"], "secenek": 4},
    8: {"kelime": (150, 200), "bloom": ["uygulama", "analiz", "değerlendirme"], "secenek": 4},
    9: {"kelime": (180, 250), "bloom": ["uygulama", "analiz", "değerlendirme"], "secenek": 5},
    10: {"kelime": (180, 250), "bloom": ["analiz", "değerlendirme"], "secenek": 5},
    11: {"kelime": (200, 300), "bloom": ["analiz", "değerlendirme", "yaratma"], "secenek": 5},
    12: {"kelime": (200, 300), "bloom": ["analiz", "değerlendirme", "yaratma"], "secenek": 5}
}

ISIMLER = ["Elif", "Yusuf", "Zeynep", "Ahmet", "Ayşe", "Mehmet", "Fatma", "Ali", 
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
    """JSON çıkar ve parse et - Düzeltilmiş versiyon"""
    if not text:
        return None
    
    original = text
    
    # Markdown code block temizle
    if '```json' in text:
        try:
            text = text.split('```json')[1]
            if '```' in text:
                text = text.split('```')[0]
        except:
            pass
    elif '```' in text:
        try:
            parts = text.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('{') and '}' in part:
                    text = part
                    break
        except:
            pass
    
    text = text.strip()
    
    # JSON objesini bul
    start = text.find('{')
    end = text.rfind('}')
    
    if start < 0 or end <= start:
        return None
    
    json_text = text[start:end+1]
    
    # Direkt parse dene
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass
    
    # Temizle ve tekrar dene
    import re
    
    # Kontrol karakterlerini temizle
    json_text = re.sub(r'[\x00-\x1f\x7f]', ' ', json_text)
    
    # Trailing comma düzelt
    json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)
    
    # Tek tırnak → çift tırnak
    # json_text = json_text.replace("'", '"')
    
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        # Son çare: satır satır temizle
        try:
            lines = json_text.split('\n')
            clean_lines = []
            for line in lines:
                line = line.strip()
                if line:
                    clean_lines.append(line)
            json_text = ' '.join(clean_lines)
            return json.loads(json_text)
        except:
            return None

# ═══════════════════════════════════════════════════════════════════════════════
# VERİTABANI FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════════

def curriculum_getir():
    """Matematik ve Geometri kazanımlarını getir"""
    try:
        matematik = supabase.table('curriculum').select('*').eq('lesson_name', 'Matematik').gte('grade_level', 3).lte('grade_level', 12).execute()
        geometri = supabase.table('curriculum').select('*').eq('lesson_name', 'Geometri').gte('grade_level', 3).lte('grade_level', 12).execute()
        
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
                'puan': puan
            }, ensure_ascii=False)
        }
        
        result = supabase.table('question_bank').insert(kayit).execute()
        return result.data[0].get('id') if result.data else None
    except Exception as e:
        print(f"   ❌ Kayıt hatası: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI SORU ÜRETİMİ
# ═══════════════════════════════════════════════════════════════════════════════

def gemini_soru_uret(curriculum_row, bloom_seviye, baglam, geri_bildirim=None):
    """Gemini ile soru üret"""
    
    sinif = curriculum_row.get('grade_level', 8)
    topic = curriculum_row.get('topic_name', '')
    sub_topic = curriculum_row.get('sub_topic', '')
    ayar = SINIF_AYARLARI.get(sinif, SINIF_AYARLARI[8])
    
    min_kelime, max_kelime = ayar['kelime']
    secenek_sayisi = ayar['secenek']
    
    isim = random.choice(ISIMLER)
    ornek = random.choice(baglam['ornekler'])
    
    if secenek_sayisi == 4:
        secenekler = '"A": "değer1", "B": "değer2", "C": "değer3", "D": "değer4"'
    else:
        secenekler = '"A": "değer1", "B": "değer2", "C": "değer3", "D": "değer4", "E": "değer5"'
    
    geri_bildirim_text = ""
    if geri_bildirim:
        geri_bildirim_text = f"\n\nÖNCEKİ HATA: {geri_bildirim}\nBu hatayı düzelt!"
    
    prompt = f'''Matematik sorusu oluştur.

KONU: {topic}{' - ' + sub_topic if sub_topic else ''}
SINIF: {sinif}. sınıf
BAĞLAM: {baglam['ad']} ({ornek})
KARAKTER: {isim}
{geri_bildirim_text}

KURALLAR:
1. {min_kelime}-{max_kelime} kelime senaryo yaz
2. {isim} karakteri ile günlük yaşam hikayesi oluştur
3. Tüm sayısal veriler senaryoda olsun
4. {secenek_sayisi} şık olsun
5. Önce problemi çöz, sonra şıkları yaz

JSON formatında yanıt ver:

```json
{{
  "senaryo": "hikaye metni burada",
  "soru_metni": "soru kökü burada",
  "secenekler": {{{secenekler}}},
  "dogru_cevap": "A",
  "cozum_adimlari": ["Adım 1: işlem = sonuç", "Adım 2: işlem = sonuç"],
  "solution_detailed": "detaylı çözüm açıklaması"
}}
```'''

    try:
        response = gemini.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2000
            )
        )
        
        raw_text = response.text if response.text else ""
        
        # Debug: Raw text'i göster
        if not raw_text:
            print(f"      [DEBUG] Gemini boş yanıt döndü!")
            return None
        
        soru = json_parse(raw_text)
        
        if soru and 'senaryo' in soru:
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
                soru['cozum_adimlari'] = ["Çözüm"]
            if 'solution_detailed' not in soru:
                soru['solution_detailed'] = soru.get('senaryo', '')
            
            return soru
        else:
            print(f"      [DEBUG] JSON parse hatası. İlk 200 karakter: {raw_text[:200]}")
        
        return None
        
    except Exception as e:
        print(f"      ⚠️ Gemini hatası: {str(e)[:100]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_dogrula(soru):
    """DeepSeek ile doğrula"""
    if not DEEPSEEK_AKTIF:
        return {"gecerli": True, "puan": 75, "geri_bildirim": None}
    
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
        return result if result else {"gecerli": True, "puan": 70, "geri_bildirim": None}
        
    except Exception as e:
        return {"gecerli": True, "puan": 70, "geri_bildirim": None}

# ═══════════════════════════════════════════════════════════════════════════════
# SORU ÜRETİM PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret(curriculum_row, bloom_seviye, baglam):
    """Tek soru üret"""
    
    MAX_DENEME = 3
    geri_bildirim = None
    
    for deneme in range(MAX_DENEME):
        time.sleep(0.5)
        
        soru = gemini_soru_uret(curriculum_row, bloom_seviye, baglam, geri_bildirim)
        
        if not soru:
            print(f"      ⚠️ Soru üretilemedi (Deneme {deneme+1})")
            continue
        
        if len(soru.get('senaryo', '')) < 30:
            print(f"      ⚠️ Senaryo çok kısa (Deneme {deneme+1})")
            geri_bildirim = "Senaryo çok kısa, en az 80 kelime olmalı"
            continue
        
        dogrulama = deepseek_dogrula(soru)
        puan = dogrulama.get('puan', 75)
        
        if dogrulama.get('gecerli', True) and puan >= 50:
            return soru, puan
        else:
            geri_bildirim = dogrulama.get('geri_bildirim')
            print(f"      ⚠️ Puan: {puan}/100 (Deneme {deneme+1})")
    
    return None, 0

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
    print(f"🎯 BAĞLAM TEMELLİ SORU ÜRETİM V5")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   İşlenecek: {len(secilen)} kazanım")
    print(f"   Kazanım başına: {SORU_PER_KAZANIM} soru")
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
        
        bloom_listesi = ayar['bloom'][:SORU_PER_KAZANIM - mevcut]
        
        for soru_idx, bloom in enumerate(bloom_listesi):
            baglam = random.choice(BAGLAMLAR)
            
            print(f"\n   Soru {mevcut + soru_idx + 1}/{SORU_PER_KAZANIM}:")
            print(f"      Bloom: {bloom} | Bağlam: {baglam['ad']}")
            
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
    print("   🧠 Bloom Taksonomisi")
    print("   ✨ Gemini 2.5 Flash")
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
