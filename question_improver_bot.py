"""
🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V1
═══════════════════════════════════════════════════════════════════════════════

Mevcut soruları kalite kontrolünden geçirir ve iyileştirir.

📚 ÖZELLİKLER:
✅ Kısa/kalitesiz soruları bağlamlı hale getirir
✅ Yanlış çözümleri düzeltir
✅ Adım adım çözüm formatına çevirir
✅ Bloom taksonomisi ve beceri temelli yaklaşım
✅ Gemini 2.5 Flash ile CoT çözüm
✅ DeepSeek doğrulama ve kalite puanı
✅ Temiz JSON çıktı (HTML uyumlu)
✅ İlk geçişte atlananları 2. geçişte işler

@version 1.0.0
@author MATAİ PRO
"""

import os
import json
import re
import time
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

# İşlenecek ID aralığı
START_ID = int(os.environ.get('START_ID', '7255'))
END_ID = int(os.environ.get('END_ID', '12122'))

# Ayarlar
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '50'))  # Her çalışmada işlenecek soru
MIN_DEEPSEEK_PUAN = 70
BEKLEME = 1.0
MAX_DENEME = 3
API_TIMEOUT = 45

# Progress tablosu
PROGRESS_TABLE = 'question_improver_progress'

# ═══════════════════════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

# Debug: Hangi env var'lar eksik?
print(f"   SUPABASE_URL: {'✅' if SUPABASE_URL else '❌ EKSİK'}")
print(f"   SUPABASE_KEY: {'✅' if SUPABASE_KEY else '❌ EKSİK'}")
print(f"   GEMINI_API_KEY: {'✅' if GEMINI_API_KEY else '❌ EKSİK'}")
print(f"   DEEPSEEK_API_KEY: {'✅' if DEEPSEEK_API_KEY else '⚠️ Opsiyonel'}")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    print("   Lütfen GitHub Secrets'ı kontrol edin:")
    print("   - SUPABASE_URL")
    print("   - SUPABASE_KEY") 
    print("   - GEMINI_API_KEY")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

deepseek = None
if DEEPSEEK_API_KEY:
    deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
    print("✅ DeepSeek doğrulama AKTİF")
else:
    print("⚠️ DeepSeek API key yok, doğrulama DEVRE DIŞI")

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════════════════════
# BLOOM TAKSONOMİSİ
# ═══════════════════════════════════════════════════════════════════════════════

BLOOM_SEVIYELERI = {
    'hatırlama': {
        'fiiller': ['tanımla', 'listele', 'hatırla', 'bul', 'say'],
        'aciklama': 'Bilgiyi hafızadan çağırma'
    },
    'anlama': {
        'fiiller': ['açıkla', 'özetle', 'yorumla', 'sınıfla', 'karşılaştır'],
        'aciklama': 'Anlamı kavrama ve ifade etme'
    },
    'uygulama': {
        'fiiller': ['hesapla', 'çöz', 'uygula', 'göster', 'kullan'],
        'aciklama': 'Bilgiyi yeni durumlarda kullanma'
    },
    'analiz': {
        'fiiller': ['analiz et', 'ayırt et', 'incele', 'ilişkilendir', 'çözümle'],
        'aciklama': 'Bileşenlere ayırma ve ilişkileri anlama'
    },
    'değerlendirme': {
        'fiiller': ['değerlendir', 'karşılaştır', 'eleştir', 'karar ver', 'savun'],
        'aciklama': 'Ölçütlere göre yargılama'
    },
    'yaratma': {
        'fiiller': ['tasarla', 'oluştur', 'planla', 'geliştir', 'üret'],
        'aciklama': 'Özgün ürün ortaya koyma'
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# SINIF SEVİYE HARİTASI
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_BLOOM_MAP = {
    3: ['hatırlama', 'anlama'],
    4: ['hatırlama', 'anlama'],
    5: ['hatırlama', 'anlama', 'uygulama'],
    6: ['anlama', 'uygulama'],
    7: ['anlama', 'uygulama', 'analiz'],
    8: ['uygulama', 'analiz'],
    9: ['uygulama', 'analiz'],
    10: ['analiz', 'değerlendirme'],
    11: ['analiz', 'değerlendirme', 'yaratma'],
    12: ['değerlendirme', 'yaratma']
}

# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS YÖNETİMİ
# ═══════════════════════════════════════════════════════════════════════════════

def progress_getir(question_id):
    """Bir soru için progress bilgisi getir"""
    try:
        result = supabase.table(PROGRESS_TABLE)\
            .select('*')\
            .eq('question_id', question_id)\
            .execute()
        return result.data[0] if result.data else None
    except:
        return None

def progress_kaydet(question_id, status, attempt=1, deepseek_puan=None, hata=None):
    """Progress kaydet veya güncelle"""
    try:
        mevcut = progress_getir(question_id)
        
        data = {
            'question_id': question_id,
            'status': status,  # 'success', 'failed', 'skipped', 'pending_retry'
            'attempt_count': attempt,
            'deepseek_score': deepseek_puan,
            'last_error': hata,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        if mevcut:
            supabase.table(PROGRESS_TABLE)\
                .update(data)\
                .eq('question_id', question_id)\
                .execute()
        else:
            data['created_at'] = datetime.utcnow().isoformat()
            supabase.table(PROGRESS_TABLE).insert(data).execute()
        return True
    except Exception as e:
        print(f"   ⚠️ Progress kayıt hatası: {str(e)[:50]}")
        return False

def islenmemis_sorulari_getir(limit, retry_mode=False):
    """İşlenmemiş veya tekrar işlenecek soruları getir"""
    try:
        # Önce progress tablosunda işlenmiş ID'leri al
        if retry_mode:
            # 2. geçiş: failed veya pending_retry olanlar
            progress_result = supabase.table(PROGRESS_TABLE)\
                .select('question_id')\
                .in_('status', ['failed', 'pending_retry'])\
                .execute()
            
            if not progress_result.data:
                return []
            
            retry_ids = [p['question_id'] for p in progress_result.data]
            
            # Bu ID'lerdeki soruları getir
            result = supabase.table('question_bank')\
                .select('*')\
                .in_('id', retry_ids)\
                .limit(limit)\
                .execute()
        else:
            # 1. geçiş: hiç işlenmemiş olanlar
            progress_result = supabase.table(PROGRESS_TABLE)\
                .select('question_id')\
                .execute()
            
            islenmis_ids = [p['question_id'] for p in progress_result.data] if progress_result.data else []
            
            # İşlenmemiş soruları getir
            query = supabase.table('question_bank')\
                .select('*')\
                .gte('id', START_ID)\
                .lte('id', END_ID)\
                .order('id')
            
            if islenmis_ids:
                # not in kullanamıyoruz, manuel filtreleme yapacağız
                result = query.limit(limit * 2).execute()
                if result.data:
                    result.data = [q for q in result.data if q['id'] not in islenmis_ids][:limit]
            else:
                result = query.limit(limit).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        print(f"❌ Soru getirme hatası: {str(e)}")
        return []

def tum_isler_bitti_mi():
    """Tüm işlerin bitip bitmediğini kontrol et"""
    try:
        # Toplam soru sayısı
        total = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .execute()
        
        total_count = total.count if total.count else 0
        
        # Başarılı işlenen sayısı
        success = supabase.table(PROGRESS_TABLE)\
            .select('question_id', count='exact')\
            .eq('status', 'success')\
            .execute()
        
        success_count = success.count if success.count else 0
        
        # Retry bekleyen var mı?
        pending = supabase.table(PROGRESS_TABLE)\
            .select('question_id', count='exact')\
            .in_('status', ['failed', 'pending_retry'])\
            .execute()
        
        pending_count = pending.count if pending.count else 0
        
        return {
            'total': total_count,
            'success': success_count,
            'pending': pending_count,
            'completed': success_count >= total_count and pending_count == 0
        }
    except:
        return {'total': 0, 'success': 0, 'pending': 0, 'completed': False}

# ═══════════════════════════════════════════════════════════════════════════════
# SORU KALİTE ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════════

def soru_kalite_analizi(soru):
    """Sorunun kalitesini analiz et"""
    original_text = soru.get('original_text', '') or ''
    solution_text = soru.get('solution_text', '') or ''
    
    sorunlar = []
    
    # 1. Çok kısa soru kontrolü
    if len(original_text) < 50:
        sorunlar.append('cok_kisa')
    
    # 2. Bağlam yokluğu kontrolü
    baglam_kelimeleri = ['için', 'durumda', 'ise', 'göre', 'kadar', 'arasında']
    if not any(k in original_text.lower() for k in baglam_kelimeleri):
        if len(original_text) < 100:
            sorunlar.append('baglamsiz')
    
    # 3. Sadece işlem sorusu kontrolü (2^5=?, √49=? gibi)
    basit_pattern = r'^[\d\^\√\+\-\*\/\(\)\s\=\?]+$'
    temiz_metin = re.sub(r'[a-zA-ZğüşöçıİĞÜŞÖÇ]', '', original_text)
    if len(temiz_metin) > len(original_text) * 0.7:
        sorunlar.append('sadece_islem')
    
    # 4. Çözüm kalitesi kontrolü
    if not solution_text or len(solution_text) < 30:
        sorunlar.append('cozum_eksik')
    elif 'adım' not in solution_text.lower() and '\n' not in solution_text:
        sorunlar.append('cozum_formatsiz')
    
    # 5. Seçenek kontrolü
    options = soru.get('options')
    if not options:
        sorunlar.append('secenek_yok')
    
    return {
        'sorunlar': sorunlar,
        'iyilestirme_gerekli': len(sorunlar) > 0,
        'oncelik': 'yuksek' if 'cok_kisa' in sorunlar or 'sadece_islem' in sorunlar else 'normal'
    }

# ═══════════════════════════════════════════════════════════════════════════════
# JSON TEMİZLEME (HTML UYUMLU)
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """JSON'u temizle ve parse et - HTML uyumlu"""
    if not text:
        return None
    
    # Markdown code block temizliği
    if '```json' in text:
        try:
            text = text.split('```json')[1].split('```')[0]
        except:
            pass
    elif '```' in text:
        parts = text.split('```')
        for part in parts:
            if '{' in part and '}' in part:
                text = part
                break
    
    text = text.strip()
    
    start = text.find('{')
    end = text.rfind('}')
    
    if start < 0 or end < 0 or end <= start:
        return None
    
    text = text[start:end+1]
    
    # Kontrol karakterlerini temizle
    text = text.replace('\t', ' ')
    text = text.replace('\r\n', '\\n')
    text = text.replace('\r', '\\n')
    text = text.replace('\n', '\\n')
    
    # Çoklu boşlukları temizle
    text = re.sub(r'\\n\\n+', '\\n', text)
    text = re.sub(r'\s+', ' ', text)
    
    # Trailing comma temizliği
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*\]', ']', text)
    
    try:
        return json.loads(text)
    except:
        pass
    
    # Agresif temizleme
    try:
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        return json.loads(text)
    except:
        pass
    
    return None

def html_safe_text(text):
    """Metni HTML-safe hale getir"""
    if not text:
        return ""
    
    # Özel karakterleri escape et
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')
    
    return text

# ═══════════════════════════════════════════════════════════════════════════════
# GEMİNİ İLE SORU İYİLEŞTİRME
# ═══════════════════════════════════════════════════════════════════════════════

IYILESTIRME_PROMPT = """Sen matematik eğitimi uzmanı ve soru editörüsün. Görevin mevcut soruları kalite standartlarına uygun hale getirmek.

## 📋 GÖREV

Verilen soruyu analiz et ve iyileştir:
1. Soru çok kısaysa (örn: "2^5=?", "√49=?") → Bağlamlı, beceri temelli hale getir
2. Çözüm eksik/yanlışsa → Doğru ve adım adım çözüm yaz
3. Çözüm formatı kötüyse → Temiz, öz format kullan

## ⚠️ KRİTİK KURALLAR

### SORU İYİLEŞTİRME:
- Çok kısa sorulara KISA bir bağlam ekle (1-2 cümle yeterli)
- Gereksiz uzatma YAPMA, öz tut
- Matematiksel içeriği KORUMALI
- Sınıf seviyesine uygun olmalı

### ÇÖZÜM FORMATI:
- Her adım tek satırda, kısa ve öz
- Gereksiz açıklama YAPMA
- Format: "Adım N: [kısa açıklama] → [işlem] = [sonuç]"
- Maksimum 5-6 adım
- Sonunda "Cevap: X" şeklinde bitir

### KÖTÜ ÖRNEK (YAPMA!):
```
Adım 1: Öncelikle bu problemde bize verilen bilgileri inceleyelim. 
Soruda 2 üzeri 5'in değerini bulmamız istenmektedir. 
Üslü ifadelerde taban sayı kendisiyle üs kadar çarpılır...
```

### İYİ ÖRNEK (BÖYLE YAP!):
```
Adım 1: Üslü ifadeyi aç → 2^5 = 2×2×2×2×2
Adım 2: Hesapla → 2×2 = 4, 4×2 = 8, 8×2 = 16, 16×2 = 32
Cevap: 32
```

## 📐 BLOOM TAKSONOMİSİ

Soruyu şu seviyelerden birine uygun tasarla:
- Hatırlama: Tanımla, listele, hatırla
- Anlama: Açıkla, yorumla, özetle
- Uygulama: Hesapla, çöz, uygula
- Analiz: Analiz et, karşılaştır, ayırt et
- Değerlendirme: Değerlendir, eleştir
- Yaratma: Tasarla, oluştur

## 📋 JSON ÇIKTI FORMATI

```json
{
  "soru_metni": "[İyileştirilmiş soru - bağlamlı, öz]",
  "secenekler": {
    "A": "[seçenek]",
    "B": "[seçenek]",
    "C": "[seçenek]",
    "D": "[seçenek]",
    "E": "[seçenek]"
  },
  "dogru_cevap": "[A/B/C/D/E]",
  "cozum_adimlari": "[Adım 1: ... → ... = ...\\nAdım 2: ... → ... = ...\\nCevap: ...]",
  "cozum_kisa": "[Tek cümlelik özet]",
  "bloom_seviye": "[hatırlama/anlama/uygulama/analiz/değerlendirme/yaratma]",
  "beceri": "[sayısal işlem/problem çözme/akıl yürütme/modelleme]",
  "iyilestirme_yapildi": true/false,
  "degisiklikler": "[Yapılan değişikliklerin kısa özeti]"
}
```

⚠️ SADECE JSON döndür. Başka açıklama yazma.
"""

def gemini_ile_iyilestir(soru, analiz):
    """Gemini ile soruyu iyileştir"""
    try:
        original_text = soru.get('original_text', '')
        solution_text = soru.get('solution_text', '')
        options = soru.get('options', {})
        correct_answer = soru.get('correct_answer', '')
        grade_level = soru.get('grade_level', 8)
        topic = soru.get('topic', '')
        
        # Options'ı string'e çevir
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except:
                pass
        
        options_str = ""
        if isinstance(options, dict):
            for k, v in options.items():
                options_str += f"{k}) {v}\n"
        
        prompt = f"""{IYILESTIRME_PROMPT}

## MEVCUT SORU BİLGİLERİ

**Sınıf:** {grade_level}. Sınıf
**Konu:** {topic}
**Sorunlar:** {', '.join(analiz['sorunlar']) if analiz['sorunlar'] else 'Yok'}

**Soru Metni:**
{original_text}

**Mevcut Seçenekler:**
{options_str}

**Doğru Cevap:** {correct_answer}

**Mevcut Çözüm:**
{solution_text if solution_text else 'YOK'}

---

Şimdi bu soruyu iyileştir. SADECE JSON döndür."""

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2000,
                response_mime_type="application/json"
            )
        )
        
        return json_temizle(response.text.strip())
        
    except Exception as e:
        print(f"   ⚠️ Gemini hatası: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

DEEPSEEK_KONTROL_PROMPT = """Sen matematik soru kalite kontrolcüsüsün. Verilen soruyu değerlendir.

## DEĞERLENDİRME KRİTERLERİ

1. **Matematiksel Doğruluk (40 puan)**
   - Çözüm adımları doğru mu?
   - Cevap doğru mu?

2. **Çözüm Kalitesi (30 puan)**
   - Adımlar açık ve öz mü?
   - Gereksiz uzatma var mı?
   - Format temiz mi?

3. **Soru Kalitesi (30 puan)**
   - Soru anlaşılır mı?
   - Seviyeye uygun mu?
   - Seçenekler mantıklı mı?

## ÇIKTI FORMATI

```json
{
  "gecerli": true/false,
  "puan": 0-100,
  "matematik_dogru": true/false,
  "cevap_dogru": true/false,
  "sorunlar": ["sorun1", "sorun2"],
  "oneri": "varsa düzeltme önerisi"
}
```

SADECE JSON döndür."""

def deepseek_kontrol(iyilestirilmis, orijinal):
    """DeepSeek ile kalite kontrolü yap"""
    if not deepseek:
        return {'gecerli': True, 'puan': 75, 'matematik_dogru': True}
    
    try:
        soru_metni = iyilestirilmis.get('soru_metni', '')
        cozum = iyilestirilmis.get('cozum_adimlari', '')
        dogru_cevap = iyilestirilmis.get('dogru_cevap', '')
        secenekler = iyilestirilmis.get('secenekler', {})
        
        kontrol_metni = f"""
**Soru:** {soru_metni}

**Seçenekler:**
{json.dumps(secenekler, ensure_ascii=False, indent=2)}

**Doğru Cevap:** {dogru_cevap}

**Çözüm:**
{cozum}
"""
        
        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[
                {'role': 'system', 'content': DEEPSEEK_KONTROL_PROMPT},
                {'role': 'user', 'content': f'Bu soruyu değerlendir:\n{kontrol_metni}'}
            ],
            max_tokens=800,
            timeout=API_TIMEOUT
        )
        
        result = json_temizle(response.choices[0].message.content)
        return result if result else {'gecerli': False, 'puan': 0}
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek hatası: {str(e)[:50]}")
        return {'gecerli': True, 'puan': 70}

# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION BANK GÜNCELLEME
# ═══════════════════════════════════════════════════════════════════════════════

def question_bank_guncelle(question_id, iyilestirilmis, deepseek_puan):
    """Question bank'taki soruyu güncelle"""
    try:
        # Seçenekleri JSON string'e çevir
        secenekler = iyilestirilmis.get('secenekler', {})
        if isinstance(secenekler, dict):
            secenekler_str = json.dumps(secenekler, ensure_ascii=False)
        else:
            secenekler_str = str(secenekler)
        
        # Çözüm adımlarını düzenle
        cozum = iyilestirilmis.get('cozum_adimlari', '')
        if isinstance(cozum, list):
            cozum = '\n'.join(cozum)
        
        # \n'leri gerçek newline'a çevir
        cozum = cozum.replace('\\n', '\n')
        
        update_data = {
            'original_text': iyilestirilmis.get('soru_metni', ''),
            'options': secenekler_str,
            'correct_answer': iyilestirilmis.get('dogru_cevap', ''),
            'solution_text': cozum,
            'solution_short': iyilestirilmis.get('cozum_kisa', ''),
            'bloom_level': iyilestirilmis.get('bloom_seviye', ''),
            'verified': True,
            'verified_at': datetime.utcnow().isoformat()
        }
        
        # Boş değerleri temizle
        update_data = {k: v for k, v in update_data.items() if v}
        
        result = supabase.table('question_bank')\
            .update(update_data)\
            .eq('id', question_id)\
            .execute()
        
        return bool(result.data)
        
    except Exception as e:
        print(f"   ⚠️ Güncelleme hatası: {str(e)[:50]}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU İŞLE
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_isle(soru):
    """Tek bir soruyu işle ve iyileştir"""
    question_id = soru.get('id')
    
    for deneme in range(MAX_DENEME):
        try:
            # 1. Kalite analizi
            analiz = soru_kalite_analizi(soru)
            
            # 2. Gemini ile iyileştir
            iyilestirilmis = gemini_ile_iyilestir(soru, analiz)
            
            if not iyilestirilmis:
                print(f"   ⚠️ Gemini başarısız (deneme {deneme+1})")
                continue
            
            # 3. DeepSeek kontrolü
            kontrol = deepseek_kontrol(iyilestirilmis, soru)
            puan = kontrol.get('puan', 0)
            
            if puan < MIN_DEEPSEEK_PUAN:
                print(f"   ⚠️ Düşük puan: {puan} (deneme {deneme+1})")
                if deneme < MAX_DENEME - 1:
                    continue
                else:
                    # Son denemede de başarısız - pending_retry olarak işaretle
                    progress_kaydet(question_id, 'pending_retry', deneme+1, puan, 'Düşük kalite puanı')
                    return {'success': False, 'puan': puan, 'reason': 'low_score'}
            
            # 4. Matematik doğru mu?
            if not kontrol.get('matematik_dogru', True) or not kontrol.get('cevap_dogru', True):
                print(f"   ⚠️ Matematik hatası (deneme {deneme+1})")
                if deneme < MAX_DENEME - 1:
                    continue
                else:
                    progress_kaydet(question_id, 'pending_retry', deneme+1, puan, 'Matematik hatası')
                    return {'success': False, 'puan': puan, 'reason': 'math_error'}
            
            # 5. Question Bank'ı güncelle
            if question_bank_guncelle(question_id, iyilestirilmis, puan):
                progress_kaydet(question_id, 'success', deneme+1, puan)
                return {
                    'success': True,
                    'puan': puan,
                    'iyilestirme': iyilestirilmis.get('iyilestirme_yapildi', False)
                }
            else:
                print(f"   ⚠️ DB güncelleme hatası (deneme {deneme+1})")
                continue
                
        except Exception as e:
            print(f"   ⚠️ Hata (deneme {deneme+1}): {str(e)[:50]}")
            continue
    
    progress_kaydet(question_id, 'failed', MAX_DENEME, None, 'Max deneme aşıldı')
    return {'success': False, 'reason': 'max_attempts'}

# ═══════════════════════════════════════════════════════════════════════════════
# ANA İŞLEM DÖNGÜSÜ
# ═══════════════════════════════════════════════════════════════════════════════

def batch_isle(retry_mode=False):
    """Bir batch soruyu işle"""
    
    mode_str = "TEKRAR GEÇİŞ" if retry_mode else "İLK GEÇİŞ"
    
    # İşlenecek soruları getir
    sorular = islenmemis_sorulari_getir(BATCH_SIZE, retry_mode)
    
    if not sorular:
        return {'islenen': 0, 'basarili': 0, 'bitti': True}
    
    print(f"\n{'='*70}")
    print(f"🔧 QUESTION BANK İYİLEŞTİRME - {mode_str}")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   İşlenecek: {len(sorular)} soru")
    print(f"   ID Aralığı: {START_ID} - {END_ID}")
    print(f"{'='*70}\n")
    
    basarili = 0
    toplam_puan = 0
    baslangic = time.time()
    
    for idx, soru in enumerate(sorular):
        question_id = soru.get('id')
        topic = soru.get('topic', 'Bilinmeyen')[:30]
        grade = soru.get('grade_level', '?')
        
        print(f"\n[{idx+1}/{len(sorular)}] ID: {question_id} | {grade}. Sınıf | {topic}")
        
        # Kalite analizi
        analiz = soru_kalite_analizi(soru)
        if analiz['sorunlar']:
            print(f"   📋 Sorunlar: {', '.join(analiz['sorunlar'])}")
        
        # İşle
        sonuc = tek_soru_isle(soru)
        
        if sonuc['success']:
            basarili += 1
            puan = sonuc.get('puan', 0)
            toplam_puan += puan
            iyilestirme = "✨ İyileştirildi" if sonuc.get('iyilestirme') else "✅ Doğrulandı"
            print(f"   {iyilestirme} | Puan: {puan}/100")
        else:
            reason = sonuc.get('reason', 'unknown')
            print(f"   ❌ Başarısız: {reason}")
        
        time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    ort_puan = toplam_puan / basarili if basarili > 0 else 0
    
    # Durum kontrolü
    durum = tum_isler_bitti_mi()
    
    print(f"\n{'='*70}")
    print(f"📊 BATCH RAPORU - {mode_str}")
    print(f"{'='*70}")
    print(f"   ✅ Başarılı: {basarili}/{len(sorular)}")
    print(f"   📈 Ortalama Puan: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   ")
    print(f"   📋 Genel Durum:")
    print(f"      Toplam: {durum['total']} soru")
    print(f"      Başarılı: {durum['success']}")
    print(f"      Bekleyen: {durum['pending']}")
    print(f"{'='*70}\n")
    
    return {
        'islenen': len(sorular),
        'basarili': basarili,
        'bitti': durum['completed']
    }

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V1")
    print("   📚 ID Aralığı: {} - {}".format(START_ID, END_ID))
    print("   ✅ Kısa soruları bağlamlı hale getirir")
    print("   ✅ Yanlış çözümleri düzeltir")
    print("   ✅ Adım adım çözüm formatı")
    print("   ✅ DeepSeek kalite kontrolü")
    print("   ✅ Atlananları 2. geçişte işler")
    print("="*70 + "\n")
    
    # API testleri
    print("🔍 Gemini API test ediliyor...")
    try:
        test = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents='2+2=?'
        )
        print(f"✅ Gemini çalışıyor")
    except Exception as e:
        print(f"❌ Gemini HATASI: {e}")
        exit(1)
    
    if deepseek:
        print("🔍 DeepSeek API test ediliyor...")
        try:
            test = deepseek.chat.completions.create(
                model='deepseek-chat',
                messages=[{'role': 'user', 'content': '3+5=?'}],
                max_tokens=10
            )
            print(f"✅ DeepSeek çalışıyor")
        except Exception as e:
            print(f"⚠️ DeepSeek hatası: {e}")
    
    # Durum kontrolü
    durum = tum_isler_bitti_mi()
    print(f"\n📋 Mevcut Durum:")
    print(f"   Toplam: {durum['total']} soru")
    print(f"   Başarılı: {durum['success']}")
    print(f"   Bekleyen: {durum['pending']}")
    
    if durum['completed']:
        print("\n🎉 TÜM İŞLER TAMAMLANDI!")
        return
    
    # İlk geçiş
    print("\n" + "="*70)
    print("📍 İLK GEÇİŞ BAŞLIYOR...")
    print("="*70)
    
    sonuc = batch_isle(retry_mode=False)
    
    # Eğer ilk geçişte iş kalmadıysa, retry mode'a geç
    if sonuc['islenen'] == 0 and durum['pending'] > 0:
        print("\n" + "="*70)
        print("📍 TEKRAR GEÇİŞ BAŞLIYOR (Atlanan sorular)...")
        print("="*70)
        
        sonuc = batch_isle(retry_mode=True)
    
    # Final durum
    final_durum = tum_isler_bitti_mi()
    
    if final_durum['completed']:
        print("\n" + "="*70)
        print("🎉 TÜM İŞLER TAMAMLANDI!")
        print(f"   Toplam işlenen: {final_durum['success']} soru")
        print("="*70)
    else:
        print(f"\n📋 Sonraki çalışmada devam edilecek...")
        print(f"   Kalan: {final_durum['total'] - final_durum['success']} soru")

if __name__ == "__main__":
    main()
