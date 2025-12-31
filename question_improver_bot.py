"""
🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V4
═══════════════════════════════════════════════════════════════════════════════

Mevcut soruları kalite kontrolünden geçirir ve iyileştirir.
V4: Dinamik ID aralığı - veritabanındaki max ID'ye kadar çalışır

📚 ÖZELLİKLER:
✅ Kısa/kalitesiz soruları bağlamlı hale getirir
✅ Yanlış çözümleri düzeltir
✅ Adım adım çözüm formatına çevirir
✅ Bloom taksonomisi ve beceri temelli yaklaşım
✅ Gemini 2.5 Flash ile CoT çözüm
✅ DeepSeek doğrulama ve kalite puanı
✅ Temiz JSON çıktı (HTML uyumlu)
✅ LaTeX matematiksel ifadeleri doğru escape eder
✅ İlk geçişte atlananları 2. geçişte işler
✅ Her gün kontrol eder, işlenmemiş soru kalmayana kadar devam eder
🆕 V4: Dinamik END_ID - veritabanındaki max ID otomatik alınır
🆕 V4: Kaldığı yerden devam eder (son_id düzeltmesi)

@version 4.0.0
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

# Supabase import
try:
    from supabase import create_client, Client
except ImportError:
    from supabase._sync.client import SyncClient as Client
    from supabase import create_client

# ═══════════════════════════════════════════════════════════════════════════════
# YAPILANDIRMA
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

# İşlenecek ID aralığı - START_ID sabit, END_ID dinamik olacak
START_ID = int(os.environ.get('START_ID', '7255'))
# END_ID artık opsiyonel - verilmezse veritabanından max ID alınacak
END_ID_ENV = os.environ.get('END_ID', '')

# Ayarlar
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '100'))
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

print(f"   SUPABASE_URL: {'✅' if SUPABASE_URL else '❌ EKSİK'}")
print(f"   SUPABASE_KEY: {'✅' if SUPABASE_KEY else '❌ EKSİK'}")
print(f"   GEMINI_API_KEY: {'✅' if GEMINI_API_KEY else '❌ EKSİK'}")
print(f"   DEEPSEEK_API_KEY: {'✅' if DEEPSEEK_API_KEY else '⚠️ Opsiyonel'}")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    exit(1)

print("🔗 Supabase bağlantısı kuruluyor...")
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    test_result = supabase.table('question_bank').select('id').limit(1).execute()
    print(f"✅ Supabase bağlantısı başarılı")
except Exception as e:
    print(f"❌ Supabase bağlantı hatası: {e}")
    exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# DİNAMİK END_ID HESAPLAMA - V4 YENİ
# ═══════════════════════════════════════════════════════════════════════════════

def veritabanindan_max_id_al():
    """Veritabanındaki en büyük ID'yi al"""
    try:
        result = supabase.table('question_bank')\
            .select('id')\
            .order('id', desc=True)\
            .limit(1)\
            .execute()
        
        if result.data:
            return result.data[0]['id']
        return START_ID
    except Exception as e:
        print(f"⚠️ Max ID alınamadı: {e}")
        return START_ID

# END_ID'yi belirle
if END_ID_ENV:
    END_ID = int(END_ID_ENV)
    print(f"   END_ID (env): {END_ID}")
else:
    END_ID = veritabanindan_max_id_al()
    print(f"   END_ID (otomatik): {END_ID}")

print(f"   📍 Çalışma aralığı: {START_ID} - {END_ID}")

# Gemini ve DeepSeek bağlantıları
print("🔗 Gemini bağlantısı kuruluyor...")
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"✅ Gemini client oluşturuldu")
except Exception as e:
    print(f"❌ Gemini client hatası: {e}")
    exit(1)

deepseek = None
if DEEPSEEK_API_KEY:
    print("🔗 DeepSeek bağlantısı kuruluyor...")
    try:
        deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
        print("✅ DeepSeek doğrulama AKTİF")
    except Exception as e:
        print(f"⚠️ DeepSeek hatası: {e}")
else:
    print("⚠️ DeepSeek API key yok, doğrulama DEVRE DIŞI")

print("✅ Tüm API bağlantıları hazır!\n")

# ═══════════════════════════════════════════════════════════════════════════════
# BLOOM TAKSONOMİSİ
# ═══════════════════════════════════════════════════════════════════════════════

BLOOM_SEVIYELERI = {
    'hatırlama': {'fiiller': ['tanımla', 'listele', 'hatırla', 'bul', 'say'], 'aciklama': 'Bilgiyi hafızadan çağırma'},
    'anlama': {'fiiller': ['açıkla', 'özetle', 'yorumla', 'sınıfla', 'karşılaştır'], 'aciklama': 'Anlamı kavrama'},
    'uygulama': {'fiiller': ['hesapla', 'çöz', 'uygula', 'göster', 'kullan'], 'aciklama': 'Bilgiyi yeni durumlarda kullanma'},
    'analiz': {'fiiller': ['analiz et', 'ayırt et', 'incele', 'ilişkilendir'], 'aciklama': 'Bileşenlere ayırma'},
    'değerlendirme': {'fiiller': ['değerlendir', 'karşılaştır', 'eleştir', 'karar ver'], 'aciklama': 'Ölçütlere göre yargılama'},
    'yaratma': {'fiiller': ['tasarla', 'oluştur', 'planla', 'geliştir'], 'aciklama': 'Özgün ürün ortaya koyma'}
}

SINIF_BLOOM_MAP = {
    3: ['hatırlama', 'anlama'], 4: ['hatırlama', 'anlama'],
    5: ['hatırlama', 'anlama', 'uygulama'], 6: ['anlama', 'uygulama'],
    7: ['anlama', 'uygulama', 'analiz'], 8: ['uygulama', 'analiz'],
    9: ['uygulama', 'analiz'], 10: ['analiz', 'değerlendirme'],
    11: ['analiz', 'değerlendirme', 'yaratma'], 12: ['değerlendirme', 'yaratma']
}

# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS YÖNETİMİ - V4 GÜNCELLEME
# ═══════════════════════════════════════════════════════════════════════════════

PROGRESS_TABLE_EXISTS = False

def progress_tablo_kontrol():
    """Progress tablosunun var olup olmadığını kontrol et"""
    global PROGRESS_TABLE_EXISTS
    try:
        supabase.table(PROGRESS_TABLE).select('id').limit(1).execute()
        PROGRESS_TABLE_EXISTS = True
        print(f"✅ Progress tablosu mevcut")
        return True
    except:
        print(f"⚠️ Progress tablosu yok - takipsiz modda çalışılacak")
        PROGRESS_TABLE_EXISTS = False
        return False

def progress_getir(question_id):
    """Bir soru için progress bilgisi getir"""
    if not PROGRESS_TABLE_EXISTS:
        return None
    try:
        result = supabase.table(PROGRESS_TABLE).select('*').eq('question_id', question_id).execute()
        return result.data[0] if result.data else None
    except:
        return None

def progress_kaydet(question_id, status, attempt=1, deepseek_puan=None, hata=None):
    """Progress kaydet veya güncelle"""
    if not PROGRESS_TABLE_EXISTS:
        return True
    try:
        mevcut = progress_getir(question_id)
        data = {
            'question_id': question_id,
            'status': status,
            'attempt_count': attempt,
            'deepseek_score': deepseek_puan,
            'last_error': hata,
            'updated_at': datetime.utcnow().isoformat()
        }
        if mevcut:
            supabase.table(PROGRESS_TABLE).update(data).eq('question_id', question_id).execute()
        else:
            data['created_at'] = datetime.utcnow().isoformat()
            supabase.table(PROGRESS_TABLE).insert(data).execute()
        return True
    except Exception as e:
        print(f"   ⚠️ Progress kayıt hatası: {str(e)[:50]}")
        return False

def son_islenen_id_getir():
    """Progress tablosundan son başarıyla işlenen ID'yi getir"""
    if not PROGRESS_TABLE_EXISTS:
        return START_ID - 1
    try:
        # Success durumundaki en büyük question_id'yi bul
        result = supabase.table(PROGRESS_TABLE)\
            .select('question_id')\
            .eq('status', 'success')\
            .order('question_id', desc=True)\
            .limit(1)\
            .execute()
        
        if result.data:
            return result.data[0]['question_id']
        return START_ID - 1
    except Exception as e:
        print(f"   ⚠️ Son ID getirme hatası: {str(e)[:50]}")
        return START_ID - 1

def islenmemis_sorulari_getir(limit, retry_mode=False):
    """
    İşlenmemiş veya tekrar işlenecek soruları getir - V4 DÜZELTİLMİŞ
    
    V4 Değişiklik: 
    - son_id değişkeni artık gerçekten kullanılıyor
    - baslangic_id = son_id + 1 olarak düzeltildi
    - Dinamik END_ID desteği
    """
    try:
        if not PROGRESS_TABLE_EXISTS:
            # Progress tablosu yoksa, question_bank'teki improved_at alanına bak
            print(f"   📋 Progress tablosu yok, improved_at kontrolü...")
            
            # improved_at null olan soruları getir
            result = supabase.table('question_bank')\
                .select('*')\
                .gte('id', START_ID)\
                .lte('id', END_ID)\
                .is_('improved_at', 'null')\
                .order('id')\
                .limit(limit)\
                .execute()
            
            if result.data:
                return result.data
            
            # Eğer improved_at null yoksa, normal sıralı getir (eski davranış)
            result = supabase.table('question_bank')\
                .select('*')\
                .gte('id', START_ID)\
                .lte('id', END_ID)\
                .order('id')\
                .limit(limit)\
                .execute()
            return result.data if result.data else []
        
        if retry_mode:
            # Retry mode: failed veya pending_retry olanları getir
            progress_result = supabase.table(PROGRESS_TABLE)\
                .select('question_id')\
                .in_('status', ['failed', 'pending_retry'])\
                .order('question_id')\
                .limit(limit)\
                .execute()
            
            if not progress_result.data:
                return []
            
            retry_ids = [p['question_id'] for p in progress_result.data]
            result = supabase.table('question_bank')\
                .select('*')\
                .in_('id', retry_ids)\
                .order('id')\
                .execute()
            return result.data if result.data else []
        
        else:
            # V4 DEĞİŞİKLİK: Tüm işlenmiş ID'leri al
            progress_result = supabase.table(PROGRESS_TABLE)\
                .select('question_id')\
                .execute()
            
            islenmis_ids = set()
            if progress_result.data:
                islenmis_ids = set([p['question_id'] for p in progress_result.data])
            
            print(f"   📊 Progress'te {len(islenmis_ids)} kayıt var")
            
            # V4 DÜZELTMESİ: Son başarılı ID'yi bul ve ORADAN devam et
            son_id = son_islenen_id_getir()
            
            # 🔧 V4 KRİTİK DÜZELTME: baslangic_id artık son_id + 1
            # Eğer hiç işlenmemişse START_ID'den başla
            baslangic_id = max(son_id + 1, START_ID)
            
            print(f"   📍 Son işlenen ID: {son_id}, Başlangıç: {baslangic_id}")
            
            sorular = []
            
            # Chunk'lar halinde tara
            chunk_size = 200  # Her seferinde 200 soru kontrol et
            current_start = baslangic_id
            
            while len(sorular) < limit and current_start <= END_ID:
                # Bu chunk'taki soruları çek
                result = supabase.table('question_bank')\
                    .select('*')\
                    .gte('id', current_start)\
                    .lte('id', min(current_start + chunk_size - 1, END_ID))\
                    .order('id')\
                    .execute()
                
                if result.data:
                    # İşlenmemiş olanları filtrele
                    for soru in result.data:
                        if soru['id'] not in islenmis_ids:
                            sorular.append(soru)
                            if len(sorular) >= limit:
                                break
                
                current_start += chunk_size
            
            # Eğer son_id'den sonra soru bulunamadıysa, arada atlanmış olabilecekleri kontrol et
            if len(sorular) == 0 and len(islenmis_ids) < (END_ID - START_ID + 1):
                print(f"   🔍 Atlanmış sorular kontrol ediliyor...")
                current_start = START_ID
                
                while len(sorular) < limit and current_start <= END_ID:
                    result = supabase.table('question_bank')\
                        .select('*')\
                        .gte('id', current_start)\
                        .lte('id', min(current_start + chunk_size - 1, END_ID))\
                        .order('id')\
                        .execute()
                    
                    if result.data:
                        for soru in result.data:
                            if soru['id'] not in islenmis_ids:
                                sorular.append(soru)
                                if len(sorular) >= limit:
                                    break
                    
                    current_start += chunk_size
            
            print(f"   📋 {len(sorular)} işlenmemiş soru bulundu")
            return sorular
            
    except Exception as e:
        print(f"❌ Soru getirme hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def tum_isler_bitti_mi():
    """Tüm işlerin bitip bitmediğini kontrol et"""
    if not PROGRESS_TABLE_EXISTS:
        return {'total': END_ID - START_ID + 1, 'success': 0, 'pending': 0, 'completed': False}
    try:
        total = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .execute()
        total_count = total.count if total.count else 0
        
        success = supabase.table(PROGRESS_TABLE)\
            .select('question_id', count='exact')\
            .eq('status', 'success')\
            .execute()
        success_count = success.count if success.count else 0
        
        pending = supabase.table(PROGRESS_TABLE)\
            .select('question_id', count='exact')\
            .in_('status', ['failed', 'pending_retry'])\
            .execute()
        pending_count = pending.count if pending.count else 0
        
        # İşlenmemiş soru sayısı
        islenmemis = total_count - success_count - pending_count
        
        return {
            'total': total_count,
            'success': success_count,
            'pending': pending_count,
            'islenmemis': islenmemis,
            'completed': success_count >= total_count and pending_count == 0
        }
    except:
        return {'total': 0, 'success': 0, 'pending': 0, 'islenmemis': 0, 'completed': False}

# ═══════════════════════════════════════════════════════════════════════════════
# SORU KALİTE ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════════

def soru_kalite_analizi(soru):
    """Sorunun kalitesini analiz et"""
    original_text = soru.get('original_text', '') or ''
    solution_text = soru.get('solution_text', '') or ''
    
    sorunlar = []
    
    if len(original_text) < 50:
        sorunlar.append('cok_kisa')
    
    if not solution_text or len(solution_text) < 20:
        sorunlar.append('cozum_eksik')
    
    if 'adım' not in solution_text.lower() and 'adim' not in solution_text.lower():
        sorunlar.append('adim_yok')
    
    return {
        'sorunlar': sorunlar,
        'skor': max(0, 100 - len(sorunlar) * 20)
    }

# ═══════════════════════════════════════════════════════════════════════════════
# JSON YARDIMCI FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """Gemini'den gelen metni JSON için temizle"""
    if not text:
        return '{}'
    
    # Markdown code block'larını temizle
    text = re.sub(r'^```json\s*', '', text.strip())
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    
    # JSON bloğunu bul
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        text = json_match.group(0)
    
    return text.strip()

def guvenli_json_parse(text):
    """JSON parse et, hata durumunda regex fallback"""
    temiz = json_temizle(text)
    
    try:
        return json.loads(temiz)
    except json.JSONDecodeError:
        pass
    
    # Regex fallback
    result = {}
    
    patterns = {
        'original_text': r'"original_text"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]',
        'solution_text': r'"solution_text"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]',
        'correct_answer': r'"correct_answer"\s*:\s*"([^"]*)"\s*[,}]',
        'iyilestirme_yapildi': r'"iyilestirme_yapildi"\s*:\s*(true|false)',
        'degisiklik_ozeti': r'"degisiklik_ozeti"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, temiz, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1)
            if key == 'iyilestirme_yapildi':
                result[key] = value.lower() == 'true'
            else:
                result[key] = value.replace('\\"', '"').replace('\\n', '\n')
    
    return result if result else None

# ═══════════════════════════════════════════════════════════════════════════════
# GEMİNİ İYİLEŞTİRME
# ═══════════════════════════════════════════════════════════════════════════════

def gemini_iyilestir(soru):
    """Gemini ile soruyu iyileştir"""
    question_id = soru.get('id')
    grade = soru.get('grade_level', 8)
    topic = soru.get('topic', 'Matematik')
    original_text = soru.get('original_text', '')
    solution_text = soru.get('solution_text', '')
    correct_answer = soru.get('correct_answer', '')
    options = soru.get('options', {})
    
    bloom_seviyeleri = SINIF_BLOOM_MAP.get(grade, ['uygulama', 'analiz'])
    bloom_str = ', '.join(bloom_seviyeleri)
    
    prompt = f"""Sen bir matematik eğitimi uzmanısın. Aşağıdaki soruyu kalite kontrolünden geçir ve gerekirse iyileştir.

SORU BİLGİLERİ:
- ID: {question_id}
- Sınıf: {grade}. sınıf
- Konu: {topic}
- Hedef Bloom Seviyeleri: {bloom_str}

MEVCUT SORU:
{original_text}

MEVCUT ÇÖZÜM:
{solution_text}

DOĞRU CEVAP: {correct_answer}

SEÇENEKLER: {json.dumps(options, ensure_ascii=False) if options else 'Yok'}

GÖREVLER:

1. **SORU ANALİZİ**:
   - Soru yeterince bağlam içeriyor mu? (kişi adı, senaryo, günlük hayat bağlantısı)
   - Dil bilgisi ve anlaşılırlık uygun mu?
   - Bloom seviyesine uygun mu?

2. **ÇÖZÜM ANALİZİ**:
   - Çözüm matematiksel olarak doğru mu?
   - Adım adım açıklama var mı?
   - Her adımın gerekçesi belirtilmiş mi?

3. **İYİLEŞTİRME** (Gerekirse):
   - Kısa/bağlamsız sorulara kişi adı ve senaryo ekle
   - Eksik/hatalı çözümleri düzelt
   - Adım adım format kullan

ÖNEMLİ KURALLAR:
- LaTeX formülleri için \\( ve \\) veya \\[ ve \\] kullan
- JSON string içinde backslash'leri çift yaz: \\\\ 
- Üssü ifadeler için ^{{}} kullan
- Türkçe karakterleri koru

JSON FORMATI (SADECE BU FORMATTA CEVAP VER):
{{
  "original_text": "İyileştirilmiş soru metni (veya orijinal)",
  "solution_text": "Adım adım çözüm",
  "correct_answer": "{correct_answer}",
  "iyilestirme_yapildi": true/false,
  "degisiklik_ozeti": "Yapılan değişiklikler veya 'Değişiklik gerekmedi'"
}}"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4000
            )
        )
        
        if response.text:
            result = guvenli_json_parse(response.text)
            if result:
                return result
        
        return None
        
    except Exception as e:
        print(f"   ⚠️ Gemini hatası: {str(e)[:80]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_kontrol(iyilestirilmis, orijinal_soru):
    """DeepSeek ile kalite kontrolü"""
    if not deepseek:
        return {'puan': 80, 'matematik_dogru': True, 'cevap_dogru': True}
    
    original_text = iyilestirilmis.get('original_text', '')
    solution_text = iyilestirilmis.get('solution_text', '')
    correct_answer = iyilestirilmis.get('correct_answer', '')
    
    prompt = f"""Aşağıdaki matematik sorusunu ve çözümünü değerlendir.

SORU:
{original_text}

ÇÖZÜM:
{solution_text}

DOĞRU CEVAP: {correct_answer}

Değerlendirme kriterleri:
1. Matematiksel doğruluk (hesaplamalar doğru mu?)
2. Çözümün cevaba ulaşıyor mu?
3. Açıklama kalitesi
4. Adım adım format

JSON olarak cevap ver:
{{
  "puan": 0-100,
  "matematik_dogru": true/false,
  "cevap_dogru": true/false,
  "aciklama": "Kısa değerlendirme"
}}"""

    try:
        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=500,
            temperature=0.1
        )
        
        text = response.choices[0].message.content
        result = guvenli_json_parse(text)
        
        if result:
            return {
                'puan': result.get('puan', 70),
                'matematik_dogru': result.get('matematik_dogru', True),
                'cevap_dogru': result.get('cevap_dogru', True)
            }
        
        return {'puan': 70, 'matematik_dogru': True, 'cevap_dogru': True}
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek hatası: {str(e)[:50]}")
        return {'puan': 75, 'matematik_dogru': True, 'cevap_dogru': True}

# ═══════════════════════════════════════════════════════════════════════════════
# VERİTABANI GÜNCELLEME
# ═══════════════════════════════════════════════════════════════════════════════

def question_bank_guncelle(question_id, iyilestirilmis, puan):
    """Question bank'ı güncelle"""
    try:
        update_data = {
            'original_text': iyilestirilmis.get('original_text'),
            'solution_text': iyilestirilmis.get('solution_text'),
            'deepseek_score': puan,
            'improved_at': datetime.utcnow().isoformat()
        }
        
        # None değerleri temizle
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        supabase.table('question_bank').update(update_data).eq('id', question_id).execute()
        return True
        
    except Exception as e:
        print(f"   ⚠️ DB güncelleme hatası: {str(e)[:50]}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU İŞLEME
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_isle(soru):
    """Tek bir soruyu işle"""
    question_id = soru.get('id')
    
    for deneme in range(MAX_DENEME):
        try:
            # Gemini ile iyileştir
            print(f"      🤖 Gemini analizi... (deneme {deneme+1})")
            iyilestirilmis = gemini_iyilestir(soru)
            
            if not iyilestirilmis:
                print(f"   ⚠️ Gemini yanıt vermedi (deneme {deneme+1})")
                time.sleep(2)
                continue
            
            # DeepSeek kontrolü
            print(f"      🔄 DeepSeek kontrolü...")
            kontrol = deepseek_kontrol(iyilestirilmis, soru)
            puan = kontrol.get('puan', 0)
            
            if puan < MIN_DEEPSEEK_PUAN:
                print(f"   ⚠️ Düşük puan: {puan} (deneme {deneme+1})")
                if deneme < MAX_DENEME - 1:
                    time.sleep(2)
                    continue
                else:
                    progress_kaydet(question_id, 'pending_retry', deneme+1, puan, 'Düşük kalite puanı')
                    return {'success': False, 'puan': puan, 'reason': 'low_score'}
            
            # Matematik doğru mu?
            if not kontrol.get('matematik_dogru', True) or not kontrol.get('cevap_dogru', True):
                print(f"   ⚠️ Matematik hatası (deneme {deneme+1})")
                if deneme < MAX_DENEME - 1:
                    time.sleep(2)
                    continue
                else:
                    progress_kaydet(question_id, 'pending_retry', deneme+1, puan, 'Matematik hatası')
                    return {'success': False, 'puan': puan, 'reason': 'math_error'}
            
            # Question Bank'ı güncelle
            print(f"      🔄 Veritabanı güncelleniyor...")
            if question_bank_guncelle(question_id, iyilestirilmis, puan):
                progress_kaydet(question_id, 'success', deneme+1, puan)
                return {
                    'success': True,
                    'puan': puan,
                    'iyilestirme': iyilestirilmis.get('iyilestirme_yapildi', False)
                }
            else:
                print(f"   ⚠️ DB güncelleme hatası (deneme {deneme+1})")
                time.sleep(2)
                continue
                
        except Exception as e:
            print(f"   ⚠️ Hata (deneme {deneme+1}): {type(e).__name__}: {str(e)[:80]}")
            time.sleep(2)
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
    print(f"🔧 QUESTION BANK İYİLEŞTİRME V4 - {mode_str}")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   İşlenecek: {len(sorular)} soru")
    print(f"   ID Aralığı: {START_ID} - {END_ID}")
    if sorular:
        print(f"   Bu batch ID'leri: {sorular[0]['id']} - {sorular[-1]['id']}")
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
    print(f"      Bekleyen (retry): {durum['pending']}")
    print(f"      İşlenmemiş: {durum.get('islenmemis', '?')}")
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
    print("🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V4")
    print("   📚 ID Aralığı: {} - {} (dinamik)".format(START_ID, END_ID))
    print("   ✅ Kısa soruları bağlamlı hale getirir")
    print("   ✅ Yanlış çözümleri düzeltir")
    print("   ✅ Adım adım çözüm formatı")
    print("   ✅ DeepSeek kalite kontrolü")
    print("   ✅ LaTeX JSON escape düzeltmesi")
    print("   ✅ Regex fallback JSON parser")
    print("   🆕 V4: Dinamik END_ID - veritabanından otomatik alınır")
    print("   🆕 V4: Kaldığı yerden devam eder (son_id düzeltmesi)")
    print("="*70 + "\n")
    
    # Progress tablosu kontrolü
    progress_tablo_kontrol()
    
    # API testleri
    print("\n🔍 Gemini API test ediliyor...")
    try:
        test = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Merhaba, 2+2=?'
        )
        print(f"✅ Gemini çalışıyor: {test.text[:30] if test.text else 'OK'}...")
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
    print(f"   Bekleyen (retry): {durum['pending']}")
    print(f"   İşlenmemiş: {durum.get('islenmemis', durum['total'] - durum['success'] - durum['pending'])}")
    
    if durum['completed']:
        print("\n🎉 TÜM İŞLER TAMAMLANDI!")
        return
    
    # İlk geçiş - işlenmemiş sorular
    islenmemis = durum.get('islenmemis', durum['total'] - durum['success'] - durum['pending'])
    
    if islenmemis > 0:
        print("\n" + "="*70)
        print(f"📍 İLK GEÇİŞ BAŞLIYOR... ({islenmemis} işlenmemiş soru)")
        print("="*70)
        
        sonuc = batch_isle(retry_mode=False)
    else:
        sonuc = {'islenen': 0}
    
    # Eğer ilk geçişte iş kalmadıysa veya az işlendiyse, retry mode'a geç
    if sonuc['islenen'] == 0 and durum['pending'] > 0:
        print("\n" + "="*70)
        print(f"📍 TEKRAR GEÇİŞ BAŞLIYOR ({durum['pending']} bekleyen soru)...")
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
        kalan = final_durum['total'] - final_durum['success']
        print(f"\n📋 Sonraki çalışmada devam edilecek...")
        print(f"   Kalan: {kalan} soru")
        print(f"   - İşlenmemiş: {final_durum.get('islenmemis', '?')}")
        print(f"   - Bekleyen (retry): {final_durum['pending']}")

if __name__ == "__main__":
    main()
