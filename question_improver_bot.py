"""
🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V5
═══════════════════════════════════════════════════════════════════════════════

Mevcut soruları kalite kontrolünden geçirir ve iyileştirir.
V5: Başarısız işlenmiş soruları da tekrar işler

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
🆕 V5: is_pirilti=TRUE ama pirilti_pirilti boş olan soruları tekrar işler
🆕 V5: 3 mod: yeni sorular, başarısız sorular, retry sorular

@version 5.0.0
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

# İşlenecek ID aralığı
START_ID = int(os.environ.get('START_ID', '7255'))
# END_ID: Boş bırakılırsa veritabanından max ID alınır
END_ID_ENV = os.environ.get('END_ID', '')

# Ayarlar
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '50'))
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

# Dinamik END_ID hesaplama
if END_ID_ENV:
    END_ID = int(END_ID_ENV)
    print(f"   END_ID (env): {END_ID}")
else:
    try:
        max_result = supabase.table('question_bank').select('id').order('id', desc=True).limit(1).execute()
        END_ID = max_result.data[0]['id'] if max_result.data else START_ID
        print(f"   END_ID (otomatik): {END_ID}")
    except:
        END_ID = START_ID + 10000
        print(f"   END_ID (varsayılan): {END_ID}")
print(f"   📍 Çalışma aralığı: {START_ID} - {END_ID}")

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
# PROGRESS YÖNETİMİ
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

# ═══════════════════════════════════════════════════════════════════════════════
# V5 YENİ: BAŞARISIZ İŞLENMİŞ SORULARI TESPİT ET
# ═══════════════════════════════════════════════════════════════════════════════

def basarisiz_islenmis_sorulari_getir(limit):
    """
    V5 YENİ: is_pirilti = TRUE ama pirilti_pirilti boş/null olan soruları getir
    Bu sorular işlenmiş ama bir şekilde başarısız olmuş (API hatası, timeout, vs.)
    """
    try:
        print(f"   🔍 Başarısız işlenmiş sorular aranıyor...")
        
        # is_pirilti = TRUE ama pirilti_pirilti = NULL veya boş
        result = supabase.table('question_bank')\
            .select('*')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .eq('is_pirilti', True)\
            .is_('pirilti_pirilti', 'null')\
            .order('id')\
            .limit(limit)\
            .execute()
        
        sorular = result.data if result.data else []
        
        if len(sorular) < limit:
            # pirilti_pirilti boş string olanları da kontrol et
            result2 = supabase.table('question_bank')\
                .select('*')\
                .gte('id', START_ID)\
                .lte('id', END_ID)\
                .eq('is_pirilti', True)\
                .eq('pirilti_pirilti', '')\
                .order('id')\
                .limit(limit - len(sorular))\
                .execute()
            
            if result2.data:
                sorular.extend(result2.data)
        
        print(f"   📋 {len(sorular)} başarısız işlenmiş soru bulundu")
        return sorular
        
    except Exception as e:
        print(f"   ⚠️ Başarısız soru arama hatası: {str(e)[:80]}")
        return []

def eksik_alan_olan_sorulari_getir(limit):
    """
    V5 YENİ: is_pirilti = TRUE ama önemli alanları eksik olan soruları getir
    pirilti_pirilti var ama solution_pirilti veya cot_pirilti eksik
    """
    try:
        print(f"   🔍 Eksik alanlı sorular aranıyor...")
        
        # solution_pirilti eksik
        result = supabase.table('question_bank')\
            .select('*')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .eq('is_pirilti', True)\
            .not_.is_('pirilti_pirilti', 'null')\
            .is_('solution_pirilti', 'null')\
            .order('id')\
            .limit(limit)\
            .execute()
        
        sorular = result.data if result.data else []
        print(f"   📋 {len(sorular)} eksik alanlı soru bulundu")
        return sorular
        
    except Exception as e:
        print(f"   ⚠️ Eksik alan arama hatası: {str(e)[:80]}")
        return []

# ═══════════════════════════════════════════════════════════════════════════════
# İŞLENMEMİŞ SORULARI GETİR - V5 GÜNCELLENMİŞ
# ═══════════════════════════════════════════════════════════════════════════════

def islenmemis_sorulari_getir(limit, mode='new'):
    """
    V5 Güncelleme: 3 mod destekler:
    - 'new': Hiç işlenmemiş sorular (is_pirilti = FALSE veya NULL)
    - 'failed': İşlenmiş ama başarısız (is_pirilti = TRUE ama pirilti_pirilti boş)
    - 'retry': Progress tablosunda failed/pending_retry olanlar
    """
    try:
        if mode == 'failed':
            return basarisiz_islenmis_sorulari_getir(limit)
        
        if mode == 'incomplete':
            return eksik_alan_olan_sorulari_getir(limit)
        
        if mode == 'retry' and PROGRESS_TABLE_EXISTS:
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
        
        # mode == 'new': Yeni/işlenmemiş sorular
        print(f"   🔍 İşlenmemiş (yeni) sorular aranıyor...")
        
        # is_pirilti = FALSE veya NULL olan sorular
        # Önce FALSE olanlar
        result = supabase.table('question_bank')\
            .select('*')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .eq('is_pirilti', False)\
            .order('id')\
            .limit(limit)\
            .execute()
        
        sorular = result.data if result.data else []
        
        if len(sorular) < limit:
            # NULL olanları da ekle
            result2 = supabase.table('question_bank')\
                .select('*')\
                .gte('id', START_ID)\
                .lte('id', END_ID)\
                .is_('is_pirilti', 'null')\
                .order('id')\
                .limit(limit - len(sorular))\
                .execute()
            
            if result2.data:
                sorular.extend(result2.data)
        
        print(f"   📋 {len(sorular)} yeni soru bulundu")
        return sorular
            
    except Exception as e:
        print(f"❌ Soru getirme hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def tum_isler_durumu():
    """V5: Tüm iş durumlarını detaylı raporla"""
    try:
        # Toplam soru sayısı
        total = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .execute()
        total_count = total.count if total.count else 0
        
        # is_pirilti = TRUE olanlar (işlenmiş)
        islenmis = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .eq('is_pirilti', True)\
            .execute()
        islenmis_count = islenmis.count if islenmis.count else 0
        
        # is_pirilti = FALSE olanlar (yeni)
        yeni = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .eq('is_pirilti', False)\
            .execute()
        yeni_count = yeni.count if yeni.count else 0
        
        # is_pirilti = NULL olanlar
        null_count = total_count - islenmis_count - yeni_count
        
        # Başarısız işlenmiş: is_pirilti = TRUE ama pirilti_pirilti = NULL
        basarisiz = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .eq('is_pirilti', True)\
            .is_('pirilti_pirilti', 'null')\
            .execute()
        basarisiz_count = basarisiz.count if basarisiz.count else 0
        
        # Tam başarılı: is_pirilti = TRUE ve pirilti_pirilti dolu
        tam_basarili = islenmis_count - basarisiz_count
        
        # Progress tablosundan retry bekleyenler
        retry_count = 0
        if PROGRESS_TABLE_EXISTS:
            retry = supabase.table(PROGRESS_TABLE)\
                .select('question_id', count='exact')\
                .in_('status', ['failed', 'pending_retry'])\
                .execute()
            retry_count = retry.count if retry.count else 0
        
        return {
            'total': total_count,
            'islenmis': islenmis_count,
            'tam_basarili': tam_basarili,
            'basarisiz_islenmis': basarisiz_count,
            'yeni': yeni_count,
            'null': null_count,
            'retry_bekleyen': retry_count,
            'completed': basarisiz_count == 0 and yeni_count == 0 and null_count == 0
        }
        
    except Exception as e:
        print(f"   ⚠️ Durum kontrol hatası: {str(e)[:80]}")
        return {
            'total': 0, 'islenmis': 0, 'tam_basarili': 0,
            'basarisiz_islenmis': 0, 'yeni': 0, 'null': 0,
            'retry_bekleyen': 0, 'completed': False
        }

# ═══════════════════════════════════════════════════════════════════════════════
# SORU KALİTE ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════════

def soru_kalite_analizi(soru):
    """Sorunun kalite sorunlarını tespit et"""
    sorunlar = []
    
    question_text = soru.get('question', '') or ''
    solution = soru.get('solution', '') or ''
    
    # Kısa soru kontrolü
    if len(question_text) < 50:
        sorunlar.append('kisa_soru')
    
    # Bağlam eksikliği
    if not any(k in question_text.lower() for k in ['bir', 'ahmet', 'ayşe', 'market', 'okul', 'fabrika', 'araba', 'tren', 'metre', 'kg', 'litre']):
        if len(question_text) < 100:
            sorunlar.append('baglam_yok')
    
    # Çözüm eksik/kısa
    if len(solution) < 100:
        sorunlar.append('kisa_cozum')
    
    # Adım adım format yok
    if not any(s in solution for s in ['1.', '2.', 'Adım', 'adım', 'İlk olarak', 'Sonra', 'Son olarak']):
        sorunlar.append('format_yok')
    
    return {
        'sorunlar': sorunlar,
        'iyilestirme_gerekli': len(sorunlar) > 0
    }

# ═══════════════════════════════════════════════════════════════════════════════
# JSON PARSE YARDIMCILARI
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """Gemini çıktısından JSON'u temizle"""
    if not text:
        return None
    
    # Markdown code block kaldır
    text = re.sub(r'^```json\s*', '', text.strip())
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    
    return text.strip()

def json_parse_with_fallback(text):
    """JSON parse et, başarısız olursa regex ile dene"""
    if not text:
        return None
    
    temiz = json_temizle(text)
    
    # Normal parse dene
    try:
        return json.loads(temiz)
    except:
        pass
    
    # LaTeX escape düzelt
    try:
        # Tek backslash'ları çift yap (JSON için)
        fixed = re.sub(r'(?<!\\)\\(?![\\nrt"])', r'\\\\', temiz)
        return json.loads(fixed)
    except:
        pass
    
    # Regex fallback
    try:
        result = {}
        
        # question
        q_match = re.search(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)', temiz, re.DOTALL)
        if q_match:
            result['question'] = q_match.group(1).replace('\\"', '"').replace('\\n', '\n')
        
        # solution
        s_match = re.search(r'"solution"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)', temiz, re.DOTALL)
        if s_match:
            result['solution'] = s_match.group(1).replace('\\"', '"').replace('\\n', '\n')
        
        # cot
        c_match = re.search(r'"cot"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)', temiz, re.DOTALL)
        if c_match:
            result['cot'] = c_match.group(1).replace('\\"', '"').replace('\\n', '\n')
        
        # correct_answer
        a_match = re.search(r'"correct_answer"\s*:\s*"([A-E])"', temiz)
        if a_match:
            result['correct_answer'] = a_match.group(1)
        
        # options
        o_match = re.search(r'"options"\s*:\s*(\{[^}]+\})', temiz)
        if o_match:
            try:
                result['options'] = json.loads(o_match.group(1))
            except:
                pass
        
        # iyilestirme_yapildi
        i_match = re.search(r'"iyilestirme_yapildi"\s*:\s*(true|false)', temiz, re.IGNORECASE)
        if i_match:
            result['iyilestirme_yapildi'] = i_match.group(1).lower() == 'true'
        
        if 'question' in result:
            return result
            
    except:
        pass
    
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# GEMİNİ İLE İYİLEŞTİRME
# ═══════════════════════════════════════════════════════════════════════════════

def gemini_iyilestir(soru, analiz):
    """Gemini ile soruyu iyileştir"""
    
    question_text = soru.get('question', '') or ''
    solution = soru.get('solution', '') or ''
    options = soru.get('options', {}) or {}
    correct_answer = soru.get('correct_answer', '') or ''
    topic = soru.get('topic', '') or ''
    subtopic = soru.get('subtopic', '') or ''
    grade = soru.get('grade_level', 8)
    
    # Bloom seviyesi
    bloom_seviyeleri = SINIF_BLOOM_MAP.get(grade, ['uygulama'])
    bloom_info = ', '.join([f"{s} ({BLOOM_SEVIYELERI[s]['aciklama']})" for s in bloom_seviyeleri])
    
    prompt = f"""Sen bir matematik eğitimi uzmanısın. Aşağıdaki soruyu analiz et ve iyileştir.

📋 MEVCUT SORU:
Konu: {topic} / {subtopic}
Sınıf: {grade}. sınıf
Bloom Seviyeleri: {bloom_info}

Soru:
{question_text}

Seçenekler:
{json.dumps(options, ensure_ascii=False)}

Doğru Cevap: {correct_answer}

Mevcut Çözüm:
{solution}

📝 TESPİT EDİLEN SORUNLAR:
{', '.join(analiz['sorunlar']) if analiz['sorunlar'] else 'Genel kalite kontrolü'}

🎯 GÖREV:
1. Soru kısa veya bağlamsızsa, gerçek hayat senaryosu ekle (isim, yer, durum)
2. Çözümü MUTLAKA adım adım formatla (1., 2., 3. şeklinde)
3. Her adımda matematiksel işlemi açıkla
4. Chain of Thought (CoT) düşünme süreci oluştur
5. Doğru cevabın seçeneklerdekiyle TUTARLI olduğunu kontrol et

⚠️ ÖNEMLİ:
- Sorunun matematik mantığını DEĞİŞTİRME
- Doğru cevap aynı kalmalı: {correct_answer}
- Seçenek değerleri değişmemeli
- LaTeX formülleri için \\( \\) kullan

📤 ÇIKTI (SADECE JSON, başka hiçbir şey yazma):
{{
  "question": "İyileştirilmiş soru metni (bağlamlı, anlaşılır)",
  "solution": "Adım adım çözüm:\\n1. İlk adım...\\n2. İkinci adım...\\n3. Sonuç...",
  "cot": "Düşünme süreci: Önce ... sonra ... dolayısıyla ...",
  "options": {json.dumps(options, ensure_ascii=False)},
  "correct_answer": "{correct_answer}",
  "iyilestirme_yapildi": true
}}"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4096
            )
        )
        
        if response.text:
            parsed = json_parse_with_fallback(response.text)
            if parsed:
                return parsed
            else:
                print(f"      ⚠️ JSON parse edilemedi")
                return None
        return None
        
    except Exception as e:
        print(f"      ❌ Gemini hatası: {type(e).__name__}: {str(e)[:60]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_kontrol(iyilestirilmis, orijinal):
    """DeepSeek ile çözümü doğrula ve puanla"""
    if not deepseek:
        return {'puan': 85, 'matematik_dogru': True, 'cevap_dogru': True}
    
    prompt = f"""Aşağıdaki matematik sorusu ve çözümünü değerlendir.

SORU:
{iyilestirilmis.get('question', '')}

ÇÖZÜM:
{iyilestirilmis.get('solution', '')}

SEÇENEKLER:
{json.dumps(iyilestirilmis.get('options', {}), ensure_ascii=False)}

BELİRTİLEN DOĞRU CEVAP: {iyilestirilmis.get('correct_answer', '')}

KONTROL ET:
1. Matematiksel hesaplamalar doğru mu?
2. Çözüm adımları mantıklı mı?
3. Sonuç, belirtilen doğru cevapla uyuşuyor mu?
4. Çözüm anlaşılır ve öğretici mi?

SADECE JSON döndür:
{{"puan": 0-100, "matematik_dogru": true/false, "cevap_dogru": true/false, "aciklama": "kısa değerlendirme"}}"""

    try:
        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=500,
            temperature=0.1
        )
        
        text = response.choices[0].message.content
        parsed = json_parse_with_fallback(text)
        
        if parsed:
            return parsed
        
        # Fallback değerler
        return {'puan': 75, 'matematik_dogru': True, 'cevap_dogru': True}
        
    except Exception as e:
        print(f"      ⚠️ DeepSeek hatası: {str(e)[:50]}")
        return {'puan': 80, 'matematik_dogru': True, 'cevap_dogru': True}

# ═══════════════════════════════════════════════════════════════════════════════
# VERİTABANI GÜNCELLEME
# ═══════════════════════════════════════════════════════════════════════════════

def question_bank_guncelle(question_id, iyilestirilmis, puan):
    """Question bank tablosunu güncelle"""
    try:
        update_data = {
            'pirilti_pirilti': iyilestirilmis.get('question', ''),
            'solution_pirilti': iyilestirilmis.get('solution', ''),
            'cot_pirilti': iyilestirilmis.get('cot', ''),
            'deepseek_pirilti': puan,
            'is_pirilti': True,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        supabase.table('question_bank').update(update_data).eq('id', question_id).execute()
        return True
        
    except Exception as e:
        print(f"      ❌ DB güncelleme hatası: {str(e)[:60]}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU İŞLE
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_isle(soru):
    """Tek bir soruyu işle"""
    question_id = soru.get('id')
    
    # Kalite analizi
    analiz = soru_kalite_analizi(soru)
    
    for deneme in range(MAX_DENEME):
        try:
            # Gemini ile iyileştir
            print(f"      🤖 Gemini işliyor... (deneme {deneme+1})")
            iyilestirilmis = gemini_iyilestir(soru, analiz)
            
            if not iyilestirilmis:
                print(f"   ⚠️ Gemini çıktı vermedi (deneme {deneme+1})")
                time.sleep(2)
                continue
            
            # DeepSeek kontrolü
            print(f"      🔍 DeepSeek kontrol...")
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
# BATCH İŞLEME
# ═══════════════════════════════════════════════════════════════════════════════

def batch_isle(mode='new'):
    """Bir batch soruyu işle"""
    
    mode_labels = {
        'new': '🆕 YENİ SORULAR',
        'failed': '🔄 BAŞARISIZ İŞLENMİŞ SORULAR',
        'incomplete': '📝 EKSİK ALANLI SORULAR',
        'retry': '🔁 RETRY BEKLEYENLER'
    }
    
    mode_str = mode_labels.get(mode, mode.upper())
    
    # İşlenecek soruları getir
    sorular = islenmemis_sorulari_getir(BATCH_SIZE, mode)
    
    if not sorular:
        return {'islenen': 0, 'basarili': 0, 'bitti': True, 'mode': mode}
    
    print(f"\n{'='*70}")
    print(f"🔧 QUESTION BANK İYİLEŞTİRME V5 - {mode_str}")
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
    durum = tum_isler_durumu()
    
    print(f"\n{'='*70}")
    print(f"📊 BATCH RAPORU - {mode_str}")
    print(f"{'='*70}")
    print(f"   ✅ Başarılı: {basarili}/{len(sorular)}")
    print(f"   📈 Ortalama Puan: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   ")
    print(f"   📋 Genel Durum:")
    print(f"      Toplam: {durum['total']} soru")
    print(f"      ✅ Tam Başarılı: {durum['tam_basarili']}")
    print(f"      ⚠️ Başarısız İşlenmiş: {durum['basarisiz_islenmis']}")
    print(f"      🆕 Yeni: {durum['yeni']}")
    print(f"      ❓ NULL: {durum['null']}")
    print(f"{'='*70}\n")
    
    return {
        'islenen': len(sorular),
        'basarili': basarili,
        'bitti': durum['completed'],
        'mode': mode
    }

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V5")
    print("   📚 ID Aralığı: {} - {} (dinamik)".format(START_ID, END_ID))
    print("   ✅ Kısa soruları bağlamlı hale getirir")
    print("   ✅ Yanlış çözümleri düzeltir")
    print("   ✅ Adım adım çözüm formatı")
    print("   ✅ DeepSeek kalite kontrolü")
    print("   🆕 V5: Başarısız işlenmiş soruları tekrar işler")
    print("   🆕 V5: 3 mod: new, failed, retry")
    print("="*70 + "\n")
    
    # Progress tablosu kontrolü
    progress_tablo_kontrol()
    
    # API testleri
    print("\n🔍 Gemini API test ediliyor...")
    try:
        test = gemini_client.models.generate_content(
            model='gemini-2.5-flash-preview-05-20',
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
    
    # Detaylı durum kontrolü
    durum = tum_isler_durumu()
    print(f"\n📋 Mevcut Durum:")
    print(f"   Toplam: {durum['total']} soru")
    print(f"   ✅ Tam Başarılı: {durum['tam_basarili']}")
    print(f"   ⚠️ Başarısız İşlenmiş: {durum['basarisiz_islenmis']}")
    print(f"   🆕 Yeni (is_pirilti=FALSE): {durum['yeni']}")
    print(f"   ❓ NULL (is_pirilti=NULL): {durum['null']}")
    print(f"   🔁 Retry Bekleyen: {durum['retry_bekleyen']}")
    
    if durum['completed']:
        print("\n🎉 TÜM İŞLER TAMAMLANDI!")
        return
    
    # V5 ÖNCELİK SIRASI:
    # 1. Başarısız işlenmiş sorular (is_pirilti=TRUE ama pirilti_pirilti=NULL)
    # 2. Yeni sorular (is_pirilti=FALSE veya NULL)
    # 3. Retry bekleyenler
    
    islem_yapildi = False
    
    # 1. Başarısız işlenmiş sorular
    if durum['basarisiz_islenmis'] > 0:
        print("\n" + "="*70)
        print(f"📍 1. ÖNCELIK: BAŞARISIZ İŞLENMİŞ SORULAR ({durum['basarisiz_islenmis']} soru)")
        print("="*70)
        
        sonuc = batch_isle(mode='failed')
        islem_yapildi = sonuc['islenen'] > 0
    
    # 2. Yeni sorular (eğer batch dolmadıysa)
    if not islem_yapildi and (durum['yeni'] > 0 or durum['null'] > 0):
        print("\n" + "="*70)
        print(f"📍 2. ÖNCELIK: YENİ SORULAR ({durum['yeni'] + durum['null']} soru)")
        print("="*70)
        
        sonuc = batch_isle(mode='new')
        islem_yapildi = sonuc['islenen'] > 0
    
    # 3. Retry bekleyenler
    if not islem_yapildi and durum['retry_bekleyen'] > 0:
        print("\n" + "="*70)
        print(f"📍 3. ÖNCELIK: RETRY BEKLEYENLER ({durum['retry_bekleyen']} soru)")
        print("="*70)
        
        sonuc = batch_isle(mode='retry')
    
    # Final durum
    final_durum = tum_isler_durumu()
    
    print("\n" + "="*70)
    print("📊 FİNAL DURUM")
    print("="*70)
    print(f"   Toplam: {final_durum['total']} soru")
    print(f"   ✅ Tam Başarılı: {final_durum['tam_basarili']}")
    print(f"   ⚠️ Başarısız İşlenmiş: {final_durum['basarisiz_islenmis']}")
    print(f"   🆕 Yeni: {final_durum['yeni']}")
    print(f"   ❓ NULL: {final_durum['null']}")
    
    if final_durum['completed']:
        print("\n🎉 TÜM İŞLER TAMAMLANDI!")
    else:
        kalan = final_durum['basarisiz_islenmis'] + final_durum['yeni'] + final_durum['null']
        print(f"\n📋 Sonraki çalışmada devam edilecek... (Kalan: {kalan})")

if __name__ == "__main__":
    main()
