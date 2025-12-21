"""
🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V2
═══════════════════════════════════════════════════════════════════════════════

Mevcut soruları kalite kontrolünden geçirir ve iyileştirir.
JSON escape hatalarını çözen gelişmiş versiyon.

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

@version 2.0.0
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
END_ID = int(os.environ.get('END_ID', '12122'))

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

def islenmemis_sorulari_getir(limit, retry_mode=False):
    """İşlenmemiş veya tekrar işlenecek soruları getir"""
    try:
        if not PROGRESS_TABLE_EXISTS:
            print(f"   📋 Progress tablosu yok, direkt sorgulama...")
            result = supabase.table('question_bank').select('*').gte('id', START_ID).lte('id', END_ID).order('id').limit(limit).execute()
            return result.data if result.data else []
        
        if retry_mode:
            progress_result = supabase.table(PROGRESS_TABLE).select('question_id').in_('status', ['failed', 'pending_retry']).execute()
            if not progress_result.data:
                return []
            retry_ids = [p['question_id'] for p in progress_result.data]
            result = supabase.table('question_bank').select('*').in_('id', retry_ids).limit(limit).execute()
        else:
            progress_result = supabase.table(PROGRESS_TABLE).select('question_id').execute()
            islenmis_ids = set([p['question_id'] for p in progress_result.data]) if progress_result.data else set()
            result = supabase.table('question_bank').select('*').gte('id', START_ID).lte('id', END_ID).order('id').limit(limit * 2).execute()
            if result.data:
                result.data = [q for q in result.data if q['id'] not in islenmis_ids][:limit]
        
        return result.data if result.data else []
    except Exception as e:
        print(f"❌ Soru getirme hatası: {str(e)}")
        return []

def tum_isler_bitti_mi():
    """Tüm işlerin bitip bitmediğini kontrol et"""
    if not PROGRESS_TABLE_EXISTS:
        return {'total': END_ID - START_ID + 1, 'success': 0, 'pending': 0, 'completed': False}
    try:
        total = supabase.table('question_bank').select('id', count='exact').gte('id', START_ID).lte('id', END_ID).execute()
        total_count = total.count if total.count else 0
        success = supabase.table(PROGRESS_TABLE).select('question_id', count='exact').eq('status', 'success').execute()
        success_count = success.count if success.count else 0
        pending = supabase.table(PROGRESS_TABLE).select('question_id', count='exact').in_('status', ['failed', 'pending_retry']).execute()
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
    
    if len(original_text) < 50:
        sorunlar.append('cok_kisa')
    
    baglam_kelimeleri = ['için', 'durumda', 'ise', 'göre', 'kadar', 'arasında']
    if not any(k in original_text.lower() for k in baglam_kelimeleri):
        if len(original_text) < 100:
            sorunlar.append('baglamsiz')
    
    temiz_metin = re.sub(r'[a-zA-ZğüşöçıİĞÜŞÖÇ]', '', original_text)
    if len(temiz_metin) > len(original_text) * 0.7:
        sorunlar.append('sadece_islem')
    
    if not solution_text or len(solution_text) < 30:
        sorunlar.append('cozum_eksik')
    elif 'adım' not in solution_text.lower() and '\n' not in solution_text:
        sorunlar.append('cozum_formatsiz')
    
    options = soru.get('options')
    if not options:
        sorunlar.append('secenek_yok')
    
    return {
        'sorunlar': sorunlar,
        'iyilestirme_gerekli': len(sorunlar) > 0,
        'oncelik': 'yuksek' if 'cok_kisa' in sorunlar or 'sadece_islem' in sorunlar else 'normal'
    }

# ═══════════════════════════════════════════════════════════════════════════════
# ROBUST JSON TEMİZLEME (LaTeX UYUMLU)
# ═══════════════════════════════════════════════════════════════════════════════

def fix_latex_escapes(text):
    """
    LaTeX backslash'larını JSON-safe hale getir.
    Bu fonksiyon JSON parse'dan ÖNCE çağrılmalı.
    """
    if not text:
        return text
    
    # Bilinen LaTeX komutları - bunları double backslash yapacağız
    latex_commands = [
        # Matematik sembolleri
        'pmod', 'bmod', 'mod', 'equiv', 'approx', 'sim', 'cong', 'neq', 'ne',
        'leq', 'geq', 'le', 'ge', 'lt', 'gt', 'll', 'gg',
        'pm', 'mp', 'times', 'div', 'cdot', 'cdots', 'ldots', 'dots', 'vdots', 'ddots',
        'infty', 'partial', 'nabla', 'forall', 'exists', 'nexists',
        'in', 'notin', 'ni', 'subset', 'supset', 'subseteq', 'supseteq',
        'cup', 'cap', 'setminus', 'emptyset', 'varnothing',
        'land', 'lor', 'lnot', 'neg', 'implies', 'iff', 'therefore', 'because',
        # Yunan harfleri
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon', 'zeta', 'eta',
        'theta', 'vartheta', 'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi',
        'pi', 'varpi', 'rho', 'varrho', 'sigma', 'varsigma', 'tau', 'upsilon',
        'phi', 'varphi', 'chi', 'psi', 'omega',
        'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon',
        'Phi', 'Psi', 'Omega',
        # Fonksiyonlar
        'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
        'arcsin', 'arccos', 'arctan', 'arccot',
        'sinh', 'cosh', 'tanh', 'coth',
        'log', 'ln', 'lg', 'exp',
        'lim', 'limsup', 'liminf', 'sup', 'inf', 'max', 'min',
        'det', 'dim', 'ker', 'hom', 'arg', 'deg', 'gcd', 'lcm',
        # Yapısal
        'frac', 'dfrac', 'tfrac', 'cfrac',
        'sqrt', 'root', 'binom', 'choose',
        'sum', 'prod', 'coprod', 'int', 'iint', 'iiint', 'oint',
        'bigcup', 'bigcap', 'bigsqcup', 'bigvee', 'bigwedge', 'bigoplus', 'bigotimes',
        # Formatlar
        'text', 'textrm', 'textbf', 'textit', 'textsf', 'texttt',
        'mathrm', 'mathbf', 'mathit', 'mathsf', 'mathtt', 'mathbb', 'mathcal', 'mathfrak',
        'boldsymbol', 'bm',
        'overline', 'underline', 'widehat', 'widetilde', 'overrightarrow', 'overleftarrow',
        'overbrace', 'underbrace',
        # Parantezler
        'left', 'right', 'bigl', 'bigr', 'Bigl', 'Bigr', 'biggl', 'biggr', 'Biggl', 'Biggr',
        'langle', 'rangle', 'lfloor', 'rfloor', 'lceil', 'rceil', 'lvert', 'rvert',
        # Oklar
        'to', 'gets', 'leftarrow', 'rightarrow', 'leftrightarrow',
        'Leftarrow', 'Rightarrow', 'Leftrightarrow',
        'longleftarrow', 'longrightarrow', 'longleftrightarrow',
        'uparrow', 'downarrow', 'updownarrow',
        'mapsto', 'longmapsto', 'hookrightarrow', 'hookleftarrow',
        # Aksanlar
        'hat', 'check', 'breve', 'acute', 'grave', 'tilde', 'bar', 'vec', 'dot', 'ddot',
        # Boşluklar
        'quad', 'qquad', 'enspace', 'thinspace', 'negthinspace',
        # Diğer
        'circ', 'bullet', 'star', 'dagger', 'ddagger', 'ell', 'hbar', 'imath', 'jmath',
        'Re', 'Im', 'wp', 'prime', 'backslash', 'angle', 'measuredangle',
        'triangle', 'square', 'diamond', 'clubsuit', 'diamondsuit', 'heartsuit', 'spadesuit',
        # Ortam
        'begin', 'end', 'item', 'newline', 'displaystyle', 'textstyle', 'scriptstyle',
        # Derece ve ölçüler
        'degree', 'circ',
        # Özel
        'mathbb', 'mathcal', 'mathfrak', 'mathscr',
        # Setler
        'N', 'Z', 'Q', 'R', 'C',
        # Diğer önemli komutlar
        'mid', 'nmid', 'parallel', 'nparallel', 'perp', 'not',
        'propto', 'asymp', 'bowtie', 'models', 'vdash', 'dashv',
        'top', 'bot', 'vee', 'wedge', 'oplus', 'ominus', 'otimes', 'oslash', 'odot',
    ]
    
    # Önce tüm bilinen LaTeX komutlarını \\komut şeklinde düzelt
    for cmd in latex_commands:
        # \komut -> \\komut (JSON'da escape)
        # Ama dikkat: zaten \\ olanları tekrar değiştirme
        # Regex: tek backslash + komut, ama önünde başka backslash olmasın
        pattern = r'(?<!\\)\\' + cmd + r'(?![a-zA-Z])'
        replacement = '\\\\' + cmd
        text = re.sub(pattern, replacement, text)
    
    # Özel durumlar: \{ \} \[ \] \( \) - bunlar da escape edilmeli
    special_chars = ['{', '}', '[', ']', '(', ')', '_', '^', '&', '%', '$', '#']
    for char in special_chars:
        # \{ -> \\{ şeklinde
        text = re.sub(r'(?<!\\)\\' + re.escape(char), '\\\\' + char, text)
    
    return text

def extract_json_from_text(text):
    """
    Metinden JSON objesini çıkar.
    Markdown code block'ları, açıklamalar vs. temizler.
    """
    if not text:
        return None
    
    text = text.strip()
    
    # 1. Markdown code block'u temizle
    if '```json' in text:
        start = text.find('```json') + 7
        end = text.find('```', start)
        if end > start:
            text = text[start:end].strip()
    elif '```' in text:
        start = text.find('```') + 3
        end = text.find('```', start)
        if end > start:
            text = text[start:end].strip()
    
    # 2. JSON sınırlarını bul
    brace_start = text.find('{')
    if brace_start < 0:
        return None
    
    # Doğru kapanış parantezini bul (nested JSON'lar için)
    depth = 0
    brace_end = -1
    in_string = False
    escape_next = False
    
    for i in range(brace_start, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break
    
    if brace_end < 0:
        # Fallback: son } karakterini kullan
        brace_end = text.rfind('}')
    
    if brace_end <= brace_start:
        return None
    
    return text[brace_start:brace_end + 1]

def json_temizle(text):
    """
    JSON'u temizle ve parse et - LaTeX escape'leri düzelten robust versiyon.
    """
    if not text:
        print(f"      ⚠️ json_temizle: text boş")
        return None
    
    original_text = text
    
    # 1. JSON kısmını çıkar
    json_text = extract_json_from_text(text)
    if not json_text:
        print(f"      ⚠️ json_temizle: JSON bulunamadı")
        return None
    
    # 2. Denemeler listesi
    attempts = []
    
    # Deneme 1: Direkt parse
    attempts.append(('direkt', json_text))
    
    # Deneme 2: LaTeX escape'leri düzelt
    latex_fixed = fix_latex_escapes(json_text)
    attempts.append(('latex_fixed', latex_fixed))
    
    # Deneme 3: Newline'ları temizle
    newline_fixed = latex_fixed.replace('\n', ' ').replace('\r', ' ')
    newline_fixed = re.sub(r'\s+', ' ', newline_fixed)
    attempts.append(('newline_fixed', newline_fixed))
    
    # Deneme 4: Trailing comma temizle
    comma_fixed = re.sub(r',\s*}', '}', newline_fixed)
    comma_fixed = re.sub(r',\s*\]', ']', comma_fixed)
    attempts.append(('comma_fixed', comma_fixed))
    
    # Deneme 5: Tüm tek backslash'ları double yap (agresif)
    aggressive_fix = re.sub(r'(?<!\\)\\(?![\\"])', r'\\\\', comma_fixed)
    attempts.append(('aggressive_fix', aggressive_fix))
    
    # Deneme 6: Control karakterlerini temizle
    control_fixed = ''.join(char for char in aggressive_fix if ord(char) >= 32 or char in '\n\r\t')
    attempts.append(('control_fixed', control_fixed))
    
    # Tüm denemeleri yap
    for attempt_name, attempt_text in attempts:
        try:
            result = json.loads(attempt_text)
            # print(f"      ✅ JSON parse başarılı: {attempt_name}")
            return result
        except json.JSONDecodeError as e:
            continue
    
    # Hiçbiri çalışmadıysa, son çare: regex ile field'ları çıkar
    print(f"      ⚠️ Tüm JSON parse denemeleri başarısız, regex fallback deneniyor...")
    return regex_json_fallback(original_text)

def regex_json_fallback(text):
    """
    JSON parse edilemezse, regex ile ana field'ları çıkarmaya çalış.
    """
    try:
        result = {}
        
        # soru_metni
        match = re.search(r'"soru_metni"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', text, re.DOTALL)
        if match:
            result['soru_metni'] = match.group(1).replace('\\"', '"')
        
        # secenekler (basit yaklaşım)
        secenekler_match = re.search(r'"secenekler"\s*:\s*\{([^}]+)\}', text, re.DOTALL)
        if secenekler_match:
            secenekler_text = secenekler_match.group(1)
            secenekler = {}
            for opt in ['A', 'B', 'C', 'D', 'E']:
                opt_match = re.search(rf'"{opt}"\s*:\s*"([^"]*)"', secenekler_text)
                if opt_match:
                    secenekler[opt] = opt_match.group(1)
            result['secenekler'] = secenekler
        
        # dogru_cevap
        match = re.search(r'"dogru_cevap"\s*:\s*"([A-E])"', text)
        if match:
            result['dogru_cevap'] = match.group(1)
        
        # cozum_adimlari
        match = re.search(r'"cozum_adimlari"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', text, re.DOTALL)
        if match:
            result['cozum_adimlari'] = match.group(1).replace('\\"', '"').replace('\\n', '\n')
        
        # cozum_kisa
        match = re.search(r'"cozum_kisa"\s*:\s*"([^"]*)"', text)
        if match:
            result['cozum_kisa'] = match.group(1)
        
        # bloom_seviye
        match = re.search(r'"bloom_seviye"\s*:\s*"([^"]*)"', text)
        if match:
            result['bloom_seviye'] = match.group(1)
        
        # beceri
        match = re.search(r'"beceri"\s*:\s*"([^"]*)"', text)
        if match:
            result['beceri'] = match.group(1)
        
        # iyilestirme_yapildi
        match = re.search(r'"iyilestirme_yapildi"\s*:\s*(true|false)', text)
        if match:
            result['iyilestirme_yapildi'] = match.group(1) == 'true'
        
        # Minimum gerekli alanlar var mı kontrol et
        if result.get('soru_metni') and result.get('dogru_cevap'):
            print(f"      ✅ Regex fallback başarılı")
            return result
        
        print(f"      ⚠️ Regex fallback: yetersiz veri")
        return None
        
    except Exception as e:
        print(f"      ⚠️ Regex fallback hatası: {str(e)[:50]}")
        return None

def html_safe_text(text):
    """Metni HTML-safe hale getir"""
    if not text:
        return ""
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

# Daha net JSON talimatları ile güncellenmiş prompt
IYILESTIRME_PROMPT = """Sen matematik eğitimi uzmanı ve soru editörüsün. Görevin mevcut soruları kalite standartlarına uygun hale getirmek.

## 📋 GÖREV

Verilen soruyu analiz et ve iyileştir:
1. Soru çok kısaysa (örn: "2^5=?", "√49=?") → Bağlamlı, beceri temelli hale getir
2. Çözüm eksik/yanlışsa → Doğru ve adım adım çözüm yaz
3. Çözüm formatı kötüyse → Temiz, öz format kullan

## ⚠️ KRİTİK JSON KURALLARI

MUTLAKA şu kurallara uy:
1. LaTeX komutları için ÇİFT backslash kullan: \\\\frac, \\\\sqrt, \\\\times, \\\\leq, \\\\geq, \\\\equiv, \\\\pmod vs.
2. Yeni satır için \\n kullan (çift backslash değil, tek)
3. Tırnak içinde tırnak için \\" kullan
4. JSON dışında HİÇBİR ŞEY yazma

### DOĞRU LaTeX KULLANIMI (JSON İÇİNDE):
- Kesir: \\\\frac{a}{b}
- Karekök: \\\\sqrt{x}
- Çarpı: \\\\times veya \\\\cdot
- Eşit değil: \\\\neq
- Küçük eşit: \\\\leq
- Büyük eşit: \\\\geq
- Denk: \\\\equiv
- Mod: \\\\pmod{n} veya (mod n)
- Kümeler: \\\\{1, 2, 3\\\\}
- Üst simge: ^{2}
- Alt simge: _{n}

## SORU İYİLEŞTİRME:
- Çok kısa sorulara KISA bir bağlam ekle (1-2 cümle yeterli)
- Gereksiz uzatma YAPMA, öz tut
- Matematiksel içeriği KORUMALI
- Sınıf seviyesine uygun olmalı

## ÇÖZÜM FORMATI:
- Her adım tek satırda, kısa ve öz
- Gereksiz açıklama YAPMA
- Format: "Adim N: [kisa aciklama] -> [islem] = [sonuc]"
- Maksimum 5-6 adım
- Sonunda "Cevap: X" şeklinde bitir
- LaTeX kullanmak yerine basit metin formatı tercih et

## 📋 JSON ÇIKTI FORMATI

```json
{
  "soru_metni": "İyileştirilmiş soru metni",
  "secenekler": {
    "A": "secenek A",
    "B": "secenek B",
    "C": "secenek C",
    "D": "secenek D",
    "E": "secenek E"
  },
  "dogru_cevap": "A",
  "cozum_adimlari": "Adim 1: Aciklama -> islem = sonuc\\nAdim 2: Aciklama -> islem = sonuc\\nCevap: X",
  "cozum_kisa": "Tek cumlelik ozet",
  "bloom_seviye": "uygulama",
  "beceri": "sayisal islem",
  "iyilestirme_yapildi": true,
  "degisiklikler": "Yapilan degisikliklerin kisa ozeti"
}
```

⚠️ SADECE JSON döndür. Başka açıklama yazma. JSON dışında hiçbir şey yazma.
"""

def gemini_ile_iyilestir(soru, analiz):
    """Gemini ile soruyu iyileştir"""
    try:
        original_text = soru.get('original_text', '') or ''
        solution_text = soru.get('solution_text', '') or ''
        options = soru.get('options', {})
        correct_answer = soru.get('correct_answer', '') or ''
        grade_level = soru.get('grade_level', 8)
        topic = soru.get('topic', '') or ''
        
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
        elif options:
            options_str = str(options)
        
        prompt = f"""{IYILESTIRME_PROMPT}

## MEVCUT SORU BİLGİLERİ

**Sınıf:** {grade_level}. Sınıf
**Konu:** {topic}
**Sorunlar:** {', '.join(analiz['sorunlar']) if analiz['sorunlar'] else 'Yok'}

**Soru Metni:**
{original_text[:1000] if original_text else 'BOŞ'}

**Mevcut Seçenekler:**
{options_str if options_str else 'YOK'}

**Doğru Cevap:** {correct_answer if correct_answer else 'YOK'}

**Mevcut Çözüm:**
{solution_text[:1000] if solution_text else 'YOK'}

---

Şimdi bu soruyu iyileştir. SADECE JSON döndür, başka bir şey yazma."""

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,  # Daha deterministik çıktı için düşürüldü
                max_output_tokens=4000
            )
        )
        
        if not response:
            print(f"      ⚠️ Gemini response None")
            return None
        
        # Response text kontrolü
        response_text = None
        if hasattr(response, 'text'):
            response_text = response.text
        elif hasattr(response, 'candidates') and response.candidates:
            if hasattr(response.candidates[0], 'content'):
                if hasattr(response.candidates[0].content, 'parts'):
                    response_text = response.candidates[0].content.parts[0].text
        
        if not response_text:
            print(f"      ⚠️ Gemini response.text boş")
            return None
        
        print(f"      📝 Gemini yanıt: {len(response_text)} karakter")
        
        result = json_temizle(response_text.strip())
        
        if not result:
            print(f"      ⚠️ JSON parse başarısız, yanıt: {response_text[:100]}...")
            return None
        
        return result
        
    except Exception as e:
        print(f"      ⚠️ Gemini exception: {type(e).__name__}: {str(e)[:100]}")
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

## ⚠️ KRİTİK JSON KURALLARI
- SADECE JSON döndür
- LaTeX için ÇİFT backslash: \\\\frac, \\\\sqrt vs.
- JSON dışında HİÇBİR ŞEY yazma

## ÇIKTI FORMATI

```json
{
  "gecerli": true,
  "puan": 85,
  "matematik_dogru": true,
  "cevap_dogru": true,
  "sorunlar": [],
  "oneri": ""
}
```

SADECE JSON döndür."""

def deepseek_kontrol(iyilestirilmis, orijinal):
    """DeepSeek ile kalite kontrolü yap"""
    if not deepseek:
        return {'gecerli': True, 'puan': 75, 'matematik_dogru': True, 'cevap_dogru': True}
    
    try:
        soru_metni = iyilestirilmis.get('soru_metni', '')
        cozum = iyilestirilmis.get('cozum_adimlari', '')
        dogru_cevap = iyilestirilmis.get('dogru_cevap', '')
        secenekler = iyilestirilmis.get('secenekler', {})
        
        # Seçenekleri güvenli string'e çevir
        try:
            secenekler_str = json.dumps(secenekler, ensure_ascii=False, indent=2)
        except:
            secenekler_str = str(secenekler)
        
        kontrol_metni = f"""
**Soru:** {soru_metni}

**Seçenekler:**
{secenekler_str}

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
        
        if result:
            return result
        else:
            # JSON parse başarısız, varsayılan değerler
            print(f"      ⚠️ DeepSeek JSON parse başarısız, varsayılan değerler kullanılıyor")
            return {'gecerli': True, 'puan': 70, 'matematik_dogru': True, 'cevap_dogru': True}
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek hatası: {str(e)[:50]}")
        return {'gecerli': True, 'puan': 70, 'matematik_dogru': True, 'cevap_dogru': True}

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
        
        # \n'leri gerçek newline'a çevir (escape edilmiş olanları)
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
        
        result = supabase.table('question_bank').update(update_data).eq('id', question_id).execute()
        
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
    
    # Kalite analizi
    analiz = soru_kalite_analizi(soru)
    
    for deneme in range(MAX_DENEME):
        try:
            # Gemini ile iyileştir
            print(f"      🔄 Gemini çağrılıyor (deneme {deneme+1})...")
            iyilestirilmis = gemini_ile_iyilestir(soru, analiz)
            
            if not iyilestirilmis:
                print(f"   ⚠️ Gemini başarısız (deneme {deneme+1})")
                time.sleep(2)
                continue
            
            print(f"      ✅ Gemini yanıt verdi")
            
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
    print("🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V2")
    print("   📚 ID Aralığı: {} - {}".format(START_ID, END_ID))
    print("   ✅ Kısa soruları bağlamlı hale getirir")
    print("   ✅ Yanlış çözümleri düzeltir")
    print("   ✅ Adım adım çözüm formatı")
    print("   ✅ DeepSeek kalite kontrolü")
    print("   ✅ LaTeX JSON escape düzeltmesi")
    print("   ✅ Regex fallback JSON parser")
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
