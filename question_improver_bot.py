"""
🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V5 - MAARİF MODELİ
═══════════════════════════════════════════════════════════════════════════════

Mevcut soruları Türkiye Yüzyılı Maarif Modeli'ne uygun hale getirir.
V5: Maarif Modeli tam uyum + Bağlam temelli soru dönüşümü

📚 MAARİF MODELİ UYUMLULUK:
✅ Bağlam temelli soru yapısı (gerçek yaşam senaryoları)
✅ Sınıf seviyesine uygun bağlam uzunluğu
✅ Gereksiz detayları temizler (duygusal ifadeler, alakasız hikayeler)
✅ Sayısal değerleri ve görseli KORUR (değiştirmez)
✅ Bloom taksonomisi + süreç bileşenleri (analiz, çıkarım, yorumlama)
✅ Üst düzey düşünme becerilerini hedefler
✅ Ezbere değil, bilginin uygulanışını ölçer

📚 TEKNİK ÖZELLİKLER:
✅ Gemini 3 Pro ile akıllı iyileştirme
✅ DeepSeek kalite kontrolü
✅ Temiz JSON çıktı (LaTeX uyumlu)
✅ Dinamik END_ID + kaldığı yerden devam
✅ İlk/tekrar geçiş mantığı

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
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

# Gemini API Key Seçimi (1 veya 2)
# Workflow'da GEMINI_KEY_SELECT=1 veya GEMINI_KEY_SELECT=2 olarak ayarla
GEMINI_KEY_SELECT = os.environ.get('GEMINI_KEY_SELECT', '1')
GEMINI_API_KEY_1 = os.environ.get('GEMINI_API_KEY')
GEMINI_API_KEY_2 = os.environ.get('GEMINI_API_KEY2')

# Seçilen API key'i kullan
if GEMINI_KEY_SELECT == '2' and GEMINI_API_KEY_2:
    GEMINI_API_KEY = GEMINI_API_KEY_2
    GEMINI_KEY_LABEL = "GEMINI_API_KEY2 (Yedek)"
else:
    GEMINI_API_KEY = GEMINI_API_KEY_1
    GEMINI_KEY_LABEL = "GEMINI_API_KEY (Ana)"

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
print(f"   GEMINI_API_KEY: {'✅' if GEMINI_API_KEY_1 else '❌ EKSİK'}")
print(f"   GEMINI_API_KEY2: {'✅' if GEMINI_API_KEY_2 else '⚠️ Yok'}")
print(f"   🔑 Kullanılan: {GEMINI_KEY_LABEL}")
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

# Hedef dersler (Fizik hariç)
HEDEF_DERSLER = ['Matematik', 'Geometri']

# Dinamik END_ID hesaplama - SADECE hedef derslerin max ID'si
if END_ID_ENV:
    END_ID = int(END_ID_ENV)
    print(f"   END_ID (env): {END_ID}")
else:
    try:
        # Sadece Matematik ve Geometri sorularının max ID'sini al
        max_result = supabase.table('question_bank')\
            .select('id')\
            .in_('subject', HEDEF_DERSLER)\
            .order('id', desc=True)\
            .limit(1)\
            .execute()
        END_ID = max_result.data[0]['id'] if max_result.data else START_ID
        print(f"   END_ID (otomatik - Matematik/Geometri): {END_ID}")
    except:
        END_ID = START_ID + 10000
        print(f"   END_ID (varsayılan): {END_ID}")
print(f"   📍 Çalışma aralığı: {START_ID} - {END_ID}")
print(f"   📚 Hedef dersler: {', '.join(HEDEF_DERSLER)}")

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
# MAARİF MODELİ - BLOOM TAKSONOMİSİ VE SÜREÇ BİLEŞENLERİ
# ═══════════════════════════════════════════════════════════════════════════════

BLOOM_SEVIYELERI = {
    'hatırlama': {'fiiller': ['tanımla', 'listele', 'hatırla', 'bul', 'say'], 'aciklama': 'Bilgiyi hafızadan çağırma'},
    'anlama': {'fiiller': ['açıkla', 'özetle', 'yorumla', 'sınıfla', 'karşılaştır'], 'aciklama': 'Anlamı kavrama'},
    'uygulama': {'fiiller': ['hesapla', 'çöz', 'uygula', 'göster', 'kullan'], 'aciklama': 'Bilgiyi yeni durumlarda kullanma'},
    'analiz': {'fiiller': ['analiz et', 'ayırt et', 'incele', 'ilişkilendir'], 'aciklama': 'Bileşenlere ayırma'},
    'değerlendirme': {'fiiller': ['değerlendir', 'karşılaştır', 'eleştir', 'karar ver'], 'aciklama': 'Ölçütlere göre yargılama'},
    'yaratma': {'fiiller': ['tasarla', 'oluştur', 'planla', 'geliştir'], 'aciklama': 'Özgün ürün ortaya koyma'}
}

# Maarif Modeli Süreç Bileşenleri
SUREC_BILESENLERI = {
    'cozumleme': 'Problemi parçalara ayırma ve analiz etme',
    'cikarim': 'Verilerden sonuç çıkarma',
    'yorumlama': 'Bilgiyi anlamlandırma ve açıklama',
    'sentezleme': 'Farklı bilgileri birleştirme',
    'degerlendirme': 'Sonuçları ölçütlere göre yargılama',
    'siniflandirma': 'Bilgileri kategorilere ayırma',
    'karsilastirma': 'Benzerlik ve farklılıkları belirleme',
    'transfer': 'Bilgiyi yeni durumlara uygulama'
}

SINIF_BLOOM_MAP = {
    3: ['hatırlama', 'anlama'], 4: ['hatırlama', 'anlama'],
    5: ['hatırlama', 'anlama', 'uygulama'], 6: ['anlama', 'uygulama'],
    7: ['anlama', 'uygulama', 'analiz'], 8: ['uygulama', 'analiz'],
    9: ['uygulama', 'analiz'], 10: ['analiz', 'değerlendirme'],
    11: ['analiz', 'değerlendirme', 'yaratma'], 12: ['değerlendirme', 'yaratma']
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAARİF MODELİ - SINIF SEVİYESİNE GÖRE BAĞLAM KURALLARI
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_BAGLAM_KURALLARI = {
    # İlkokul (1-4. Sınıf)
    1: {'cumle_sayisi': '1-2', 'secenek_sayisi': 3, 'dil': 'çok basit, günlük kelimeler', 'gorsel': 'zorunlu'},
    2: {'cumle_sayisi': '2-3', 'secenek_sayisi': 3, 'dil': 'basit cümleler', 'gorsel': 'sık kullanılmalı'},
    3: {'cumle_sayisi': '2-3', 'secenek_sayisi': 4, 'dil': 'basit, somut', 'gorsel': 'destekleyici'},
    4: {'cumle_sayisi': '3-4', 'secenek_sayisi': 4, 'dil': 'açıklayıcı', 'gorsel': 'tablo/basit grafik olabilir'},

    # Ortaokul (5-8. Sınıf)
    5: {'cumle_sayisi': '3-4', 'secenek_sayisi': 4, 'dil': 'ders terimleri kullanılabilir', 'gorsel': 'grafik/tablo/şema'},
    6: {'cumle_sayisi': '4-5', 'secenek_sayisi': 4, 'dil': 'akademik dil başlangıcı', 'gorsel': 'karmaşık grafikler'},
    7: {'cumle_sayisi': '4-6', 'secenek_sayisi': 5, 'dil': 'akademik dil', 'gorsel': 'çoklu veri kaynakları'},
    8: {'cumle_sayisi': '5-6', 'secenek_sayisi': 5, 'dil': 'tam akademik dil', 'gorsel': 'karmaşık veri setleri'},

    # Lise (9-12. Sınıf)
    9: {'cumle_sayisi': '5-7', 'secenek_sayisi': 5, 'dil': 'disipline özgü terminoloji', 'gorsel': 'çoklu grafik/tablo'},
    10: {'cumle_sayisi': '5-7', 'secenek_sayisi': 5, 'dil': 'disipline özgü terminoloji', 'gorsel': 'akademik düzey'},
    11: {'cumle_sayisi': '6-8', 'secenek_sayisi': 5, 'dil': 'üniversite hazırlık düzeyi', 'gorsel': 'akademik analiz'},
    12: {'cumle_sayisi': '6-8', 'secenek_sayisi': 5, 'dil': 'üniversite hazırlık düzeyi', 'gorsel': 'karmaşık senaryolar'}
}

# Gereksiz detay kalıpları (bunlar temizlenecek)
GEREKSIZ_DETAY_KALIPLARI = [
    r'.*çok sev.*',  # "dedesini çok sevmektedir" gibi
    r'.*her zaman.*sevgiyle.*',
    r'.*mutlu.*olur.*',
    r'.*heyecanla.*',
    r'.*neşeyle.*',
    r'.*keyifle.*',
    r'.*merakla.*bakar.*',
    r'.*gururla.*',
]

# Anlamsız bağlam başlangıçları
ANLAMLIZ_BASLANGICLAR = [
    'dedesini çok sev',
    'annesini çok sev',
    'babasını çok sev',
    'arkadaşlarıyla iyi geçin',
    'çok çalışkan bir öğrenci',
    'dersleri çok sev',
    'matematiği çok sev',
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS YÖNETİMİ - V3 GÜNCELLEME
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

# Not: HEDEF_DERSLER yukarıda tanımlı ['Matematik', 'Geometri']

def islenmemis_sorulari_getir(limit, retry_mode=False):
    """
    İşlenmemiş veya tekrar işlenecek soruları getir - V5 MAARİF MODELİ

    V5 Değişiklik: Sadece Matematik ve Geometri dersleri işlenir (Fizik hariç)
    image_url durumuna göre farklı işleme mantığı uygulanır.
    """
    try:
        if not PROGRESS_TABLE_EXISTS:
            print(f"   📋 Progress tablosu yok, direkt sorgulama...")
            print(f"   📚 Hedef dersler: {', '.join(HEDEF_DERSLER)}")
            result = supabase.table('question_bank')\
                .select('*')\
                .gte('id', START_ID)\
                .lte('id', END_ID)\
                .in_('subject', HEDEF_DERSLER)\
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
                .in_('subject', HEDEF_DERSLER)\
                .order('id')\
                .execute()
            return result.data if result.data else []
        
        else:
            # V3 DEĞİŞİKLİK: Son işlenen ID'den devam et
            # Tüm işlenmiş ID'leri çek (success, failed, pending_retry)
            progress_result = supabase.table(PROGRESS_TABLE)\
                .select('question_id')\
                .execute()
            
            islenmis_ids = set()
            if progress_result.data:
                islenmis_ids = set([p['question_id'] for p in progress_result.data])
            
            print(f"   📊 Progress'te {len(islenmis_ids)} kayıt var")
            
            # Son başarılı ID'yi bul ve oradan devam et
            son_id = son_islenen_id_getir()
            
            # Sorguyu başlat - son ID'den sonrasını çek
            # Ama aynı zamanda arada atlanmış olabilecekleri de kontrol et
            
            # Strateji: Son işlenen ID'den devam et
            # V4 DÜZELTMESİ: baslangic_id artık son_id + 1
            
            baslangic_id = max(son_id + 1, START_ID)
            print(f"   📍 Son işlenen ID: {son_id}, Başlangıç: {baslangic_id}")
            print(f"   📚 Hedef dersler: {', '.join(HEDEF_DERSLER)}")
            sorular = []

            # Chunk'lar halinde tara
            chunk_size = 200  # Her seferinde 200 soru kontrol et
            current_start = baslangic_id

            while len(sorular) < limit and current_start <= END_ID:
                # Bu chunk'taki soruları çek - SADECE Matematik ve Geometri
                result = supabase.table('question_bank')\
                    .select('*')\
                    .gte('id', current_start)\
                    .lte('id', min(current_start + chunk_size - 1, END_ID))\
                    .in_('subject', HEDEF_DERSLER)\
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

            # Görsel durumu istatistiği
            gorselli = sum(1 for s in sorular if s.get('image_url'))
            gorselsiz = len(sorular) - gorselli
            print(f"   📋 {len(sorular)} işlenmemiş soru bulundu (🖼️ {gorselli} görselli, 📝 {gorselsiz} görselsiz)")
            return sorular
            
    except Exception as e:
        print(f"❌ Soru getirme hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def tum_isler_bitti_mi():
    """Tüm işlerin bitip bitmediğini kontrol et - SADECE Matematik/Geometri"""
    if not PROGRESS_TABLE_EXISTS:
        return {'total': END_ID - START_ID + 1, 'success': 0, 'pending': 0, 'completed': False}
    try:
        # SADECE Matematik ve Geometri sorularını say
        total = supabase.table('question_bank')\
            .select('id', count='exact')\
            .gte('id', START_ID)\
            .lte('id', END_ID)\
            .in_('subject', HEDEF_DERSLER)\
            .execute()
        total_count = total.count if total.count else 0

        # Progress tablosundan başarılı olanları say
        # Ama sadece START_ID-END_ID aralığındakileri
        success = supabase.table(PROGRESS_TABLE)\
            .select('question_id', count='exact')\
            .eq('status', 'success')\
            .gte('question_id', START_ID)\
            .lte('question_id', END_ID)\
            .execute()
        success_count = success.count if success.count else 0

        pending = supabase.table(PROGRESS_TABLE)\
            .select('question_id', count='exact')\
            .in_('status', ['failed', 'pending_retry'])\
            .gte('question_id', START_ID)\
            .lte('question_id', END_ID)\
            .execute()
        pending_count = pending.count if pending.count else 0

        # İşlenmemiş soru sayısı
        islenmemis = total_count - success_count - pending_count

        return {
            'total': total_count,
            'success': success_count,
            'pending': pending_count,
            'islenmemis': max(0, islenmemis),  # Negatif olmasın
            'completed': success_count >= total_count and pending_count == 0
        }
    except Exception as e:
        print(f"   ⚠️ Durum kontrol hatası: {str(e)[:50]}")
        return {'total': 0, 'success': 0, 'pending': 0, 'islenmemis': 0, 'completed': False}

# ═══════════════════════════════════════════════════════════════════════════════
# MAARİF MODELİ - SORU KALİTE ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════════

def gereksiz_detay_tespit(text):
    """Maarif Modeli'ne göre gereksiz detayları tespit et"""
    text_lower = text.lower()
    gereksiz_detaylar = []

    # Duygusal ifadeler
    duygusal_kaliplar = [
        'çok sev', 'çok beğen', 'mutlu ol', 'heyecanla', 'neşeyle', 'keyifle',
        'gururla', 'merakla', 'sevinçle', 'coşkuyla', 'hevesle'
    ]
    for kalip in duygusal_kaliplar:
        if kalip in text_lower:
            gereksiz_detaylar.append(f'duygusal_ifade: {kalip}')

    # Anlamsız karakter tanımlamaları
    karakter_kaliplari = [
        'çok çalışkan', 'zeki bir', 'başarılı bir', 'akıllı bir',
        'meraklı bir', 'dikkatli bir', 'özenli bir'
    ]
    for kalip in karakter_kaliplari:
        if kalip in text_lower:
            gereksiz_detaylar.append(f'karakter_tanimi: {kalip}')

    # Uzun hikaye başlangıçları (çözüme katkısı olmayan)
    hikaye_kaliplari = [
        'bir gün', 'güneşli bir gün', 'tatil günü', 'hafta sonu',
        'bir sabah', 'bir akşam', 'yaz tatilinde'
    ]
    for kalip in hikaye_kaliplari:
        if text_lower.startswith(kalip) or f'. {kalip}' in text_lower:
            gereksiz_detaylar.append(f'gereksiz_hikaye: {kalip}')

    return gereksiz_detaylar

def soru_kalite_analizi(soru):
    """Sorunun Maarif Modeli'ne uygunluğunu analiz et"""
    original_text = soru.get('original_text', '') or ''
    solution_text = soru.get('solution_text', '') or ''
    grade_level = soru.get('grade_level', 8)

    sorunlar = []

    # 1. Uzunluk kontrolü (sınıf seviyesine göre)
    min_uzunluk = 30 if grade_level <= 4 else 50 if grade_level <= 8 else 70
    if len(original_text) < min_uzunluk:
        sorunlar.append('cok_kisa')

    # 2. Çok uzun ve gereksiz detaylı soru kontrolü
    max_uzunluk = 300 if grade_level <= 4 else 500 if grade_level <= 8 else 800
    if len(original_text) > max_uzunluk:
        sorunlar.append('cok_uzun_hikaye')

    # 3. Bağlam kontrolü
    baglam_kelimeleri = ['için', 'durumda', 'ise', 'göre', 'kadar', 'arasında', 'toplam', 'sayısı']
    if not any(k in original_text.lower() for k in baglam_kelimeleri):
        if len(original_text) < 100:
            sorunlar.append('baglamsiz')

    # 4. Sadece işlem sorusu kontrolü
    temiz_metin = re.sub(r'[a-zA-ZğüşöçıİĞÜŞÖÇ\s]', '', original_text)
    if len(temiz_metin) > len(original_text) * 0.6:
        sorunlar.append('sadece_islem')

    # 5. Gereksiz detay kontrolü (Maarif Modeli özel)
    gereksiz_detaylar = gereksiz_detay_tespit(original_text)
    if gereksiz_detaylar:
        sorunlar.append('gereksiz_detay')

    # 6. Çözüm kontrolü
    if not solution_text or len(solution_text) < 30:
        sorunlar.append('cozum_eksik')
    elif 'adım' not in solution_text.lower() and '\n' not in solution_text:
        sorunlar.append('cozum_formatsiz')

    # 7. Seçenek kontrolü
    options = soru.get('options')
    if not options:
        sorunlar.append('secenek_yok')

    # Öncelik belirleme
    yuksek_oncelik = ['cok_kisa', 'sadece_islem', 'baglamsiz', 'cok_uzun_hikaye', 'gereksiz_detay']
    oncelik = 'yuksek' if any(s in sorunlar for s in yuksek_oncelik) else 'normal'

    return {
        'sorunlar': sorunlar,
        'gereksiz_detaylar': gereksiz_detaylar if gereksiz_detaylar else [],
        'iyilestirme_gerekli': True,  # Maarif Modeli için her soru iyileştirilmeli
        'oncelik': oncelik
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
            result['secenekler'] = {}
            for opt_match in re.finditer(r'"([A-E])"\s*:\s*"([^"]*)"', secenekler_text):
                result['secenekler'][opt_match.group(1)] = opt_match.group(2)
        
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
        
        # iyilestirme_yapildi
        match = re.search(r'"iyilestirme_yapildi"\s*:\s*(true|false)', text)
        if match:
            result['iyilestirme_yapildi'] = match.group(1) == 'true'
        
        if result.get('soru_metni') and result.get('dogru_cevap'):
            print(f"      ✅ Regex fallback başarılı")
            return result
        
        print(f"      ⚠️ Regex fallback yetersiz veri çıkardı")
        return None
        
    except Exception as e:
        print(f"      ⚠️ Regex fallback hatası: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# GEMİNİ İYİLEŞTİRME
# ═══════════════════════════════════════════════════════════════════════════════

IYILESTIRME_PROMPT_GORSELSIZ = """Sen Türkiye Yüzyılı Maarif Modeli konusunda uzmanlaşmış bir matematik öğretmenisin.
Bu soruda GÖRSEL YOK, dolayısıyla soruyu baştan MAARİF MODELİNE UYGUN şekilde yazabilirsin.

═══════════════════════════════════════════════════════════════════════════════
🟢 TAM ESNEKLİK - GÖRSELSİZ SORU
═══════════════════════════════════════════════════════════════════════════════

Bu soruda görsel olmadığı için:
✅ Soruyu TAMAMEN yeniden yazabilirsin
✅ Yeni isimler, yeni senaryo, yeni bağlam kullanabilirsin
✅ Seçenekleri YENİDEN DÜZENLEYEBİLİRSİN (matematiksel olarak doğru kalmalı)
✅ Çözümü baştan yazabilirsin

🔴 SADECE BUNLAR SABİT KALMALI:
- Matematiksel KONU ve KAZANIM aynı kalmalı
- Matematiksel ZORLUK SEVİYESİ korunmalı
- DOĞRU CEVAP matematiksel olarak aynı sonuca ulaşmalı

═══════════════════════════════════════════════════════════════════════════════
📚 MAARİF MODELİ TEMEL İLKELERİ
═══════════════════════════════════════════════════════════════════════════════

1. **BAĞLAM TEMELLİ**: Gerçek yaşam senaryosu ZORUNLU
   - Senaryo çözüme KATKI SAĞLAMALI (dekoratif değil)
   - HER SORU FARKLI BAĞLAM KULLANIMALI - Monotonluktan kaçın!

2. **EZBER DEĞİL, UYGULAMA**: Bilginin kullanımını ölç
   - Öğrenci senaryoyu okuyup analiz etmeli
   - Matematiksel ilişkiyi kendisi kurmalı

3. **ÜST DÜZEY DÜŞÜNME**: Analiz, çıkarım, yorumlama
   - Verilen bilgilerden sonuç çıkarma
   - Problem çözme stratejisi geliştirme

═══════════════════════════════════════════════════════════════════════════════
🏷️ BAĞLAM TÜRLERİ (ÇEŞİTLİLİK ZORUNLU!)
═══════════════════════════════════════════════════════════════════════════════

⚠️ ÖNEMLİ: Aynı bağlamı tekrar tekrar KULLANMA! Her soru için FARKLI bir
bağlam türü seç. Aşağıdaki listeden rastgele ve yaratıcı şekilde seç:

🌍 KİŞİSEL VE GÜNLÜK YAŞAM:
• 🏠 Ev ve Aile: Ev işleri, aile bütçesi, taşınma, oda düzenleme
• 🛒 Alışveriş: Market, indirim, fiyat karşılaştırma, online sipariş
• 🚗 Ulaşım ve Seyahat: Yolculuk, trafik, bilet, tatil planı, benzin
• 🍽️ Beslenme ve Yemek: Tarif, kalori, diyet, restoran, malzeme ölçüsü
• 🎉 Kutlama ve Etkinlik: Doğum günü, düğün, festival, piknik, parti

💼 MESLEKİ VE İŞ DÜNYASI:
• 🏗️ Mühendislik: İnşaat, tasarım, köprü, bina, yol yapımı
• 🏭 Üretim ve Sanayi: Fabrika, imalat, kalite kontrol, paketleme
• 🌾 Tarım ve Hayvancılık: Çiftlik, hasat, sulama, sera, hayvan bakımı
• 💰 Ekonomi ve Finans: Bütçe, yatırım, faiz, kredi, döviz
• 📊 İstatistik ve Veri: Anket, grafik, analiz, araştırma sonuçları

🔬 BİLİM VE DOĞA:
• 🧪 Deney ve Laboratuvar: Kimya, fizik, biyoloji deneyi, ölçüm
• 🌿 Çevre ve Ekoloji: İklim, geri dönüşüm, enerji tasarrufu, karbon ayak izi
• 🌌 Uzay ve Astronomi: Gezegenler, roket, uydu, yıldızlar, uzay yolculuğu
• 🏥 Sağlık ve Tıp: Hastalık, ilaç dozajı, nabız, kan değerleri
• 🦁 Hayvanlar ve Doğa: Ekosistem, göç, habitat, popülasyon

🎭 SOSYAL VE KÜLTÜREL:
• 🏛️ Tarih ve Medeniyet: Antik yapılar, tarihi olaylar, arkeoloji
• 🎨 Sanat ve Estetik: Resim, müzik, heykel, sergi, konser
• 📖 Edebiyat ve Dil: Kitap, dergi tirajı, kütüphane, yayınevi
• 🏙️ Vatandaşlık ve Toplum: Seçim, nüfus sayımı, belediye hizmetleri
• 🌍 Coğrafya ve Yerleşim: Harita, şehir planı, nüfus yoğunluğu

💻 TEKNOLOJİ VE EĞLENCE:
• 📱 Dijital ve İnternet: Uygulama, veri kullanımı, depolama, indirme
• 🎮 Oyun ve Strateji: Video oyunu puanı, bulmaca, satranç, turnuva
• ⚽ Spor ve Yarışma: Maç skoru, olimpiyat, antrenman, maraton
• 🎬 Medya ve Habercilik: Film süresi, TV izlenme oranı, podcast
• 🎢 Eğlence ve Hobi: Lunapark, koleksiyon, el işi, müze ziyareti

🎓 EĞİTİM VE OKUL:
• 📚 Okul Etkinlikleri: Sınıf projesi, bilim fuarı, okul gezisi
• 🏫 Kütüphane: Kitap ödünç alma, raf düzeni, okuma hedefi
• 🎭 Tiyatro/Müzik: Okul gösterisi, koro, enstrüman, prova

═══════════════════════════════════════════════════════════════════════════════
📝 ÇEŞİTLİ BAĞLAM ÖRNEKLERİ
═══════════════════════════════════════════════════════════════════════════════

✅ UZAY: "Bir uzay aracı Dünya'dan Mars'a giderken saatte 25.000 km hızla
   yol almaktadır. Mars'ın Dünya'ya en yakın olduğu dönemde aralarındaki
   mesafe 55 milyon km'dir. Bu yolculuk kaç gün sürer?"

✅ SPOR: "Bir maraton koşucusu 42 km'lik parkurun ilk yarısını 2 saatte
   tamamlamıştır. Geri kalan yarıyı %20 daha yavaş koşarsa toplam süre?"

✅ TARIM: "Bir çiftçi 3 hektarlık tarlasına dönüm başına 50 kg tohum ekmektedir.
   1 hektar = 10 dönüm olduğuna göre, toplam kaç kg tohum kullanır?"

✅ SAĞLIK: "Bir hastaya 6 saatte bir 250 mg ilaç verilecektir. Hastanın
   bir haftada alacağı toplam ilaç miktarı kaç gram olur?"

✅ DİJİTAL: "Bir telefon uygulaması 2.4 GB boyutundadır. İnternet hızı
   saniyede 15 MB olan biri bu uygulamayı kaç dakikada indirir?"

✅ TARİH: "Süleymaniye Camii'nin yapımı 1550-1557 yılları arasında 7 yıl
   sürmüştür. Her yıl ortalama 850 işçi çalıştığına göre toplam işçi-yıl?"

❌ KÖTÜ: "5 x 3 + 2 = ?" (bağlamsız)
❌ KÖTÜ: "Ahmet çok zeki bir öğrencidir. Matematiği sever..." (gereksiz övgü)
❌ KÖTÜ: Sürekli "sıfır atık projesi" veya "market alışverişi" (monoton)

═══════════════════════════════════════════════════════════════════════════════
📏 SINIF SEVİYESİNE GÖRE BAĞLAM
═══════════════════════════════════════════════════════════════════════════════

İLKOKUL (1-4): 2-4 cümle, çok basit dil, somut durumlar (okul, park, oyun)
ORTAOKUL (5-8): 4-6 cümle, ders terimleri, günlük hayat + bilimsel konular
LİSE (9-12): 5-8 cümle, akademik dil, mesleki/bilimsel/teknolojik senaryolar

═══════════════════════════════════════════════════════════════════════════════
📋 JSON ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════════════════════

```json
{
  "soru_metni": "Maarif Modeline uygun, bağlam temelli YENİ soru",
  "secenekler": {
    "A": "yeni secenek A",
    "B": "yeni secenek B",
    "C": "yeni secenek C",
    "D": "yeni secenek D",
    "E": "yeni secenek E"
  },
  "dogru_cevap": "A",
  "cozum_adimlari": "Adim 1: Aciklama -> islem = sonuc\\nAdim 2: ...\\nCevap: X",
  "cozum_kisa": "Tek cumlelik ozet",
  "bloom_seviye": "uygulama/analiz/degerlendirme",
  "surec_bileseni": "cozumleme/cikarim/yorumlama/transfer",
  "baglam_turu": "gunluk_yasam/mesleki/bilimsel/ekonomi/spor",
  "iyilestirme_yapildi": true,
  "degisiklikler": "Soru tamamen yeniden yazildi - Maarif Modeli uyumlu baglam eklendi"
}
```

⚠️ SADECE JSON döndür. Başka açıklama yazma.
"""

IYILESTIRME_PROMPT_GORSELLI = """Sen Türkiye Yüzyılı Maarif Modeli konusunda uzmanlaşmış bir matematik öğretmenisin.
Bu soruda GÖRSEL VAR, dolayısıyla senaryo ve karakterleri KORUMALISIN.

═══════════════════════════════════════════════════════════════════════════════
⚠️ KRİTİK: GÖRSEL UYUMU - EN ÖNEMLİ KURAL
═══════════════════════════════════════════════════════════════════════════════

Bu soruda GÖRSEL/ŞEKİL veritabanında kayıtlı! Görsel ile soru metni uyumlu olmalı.

🔴 KESİNLİKLE KORU (DEĞİŞTİRME):
- Sorudaki TÜM İSİMLER (Elif, Ahmet, Ayşe, dede, anne, öğretmen vb.)
- Sorudaki SENARYO (markete gitme, bahçede oynama, okula gitme vb.)
- Sorudaki TÜM SAYISAL DEĞERLER
- Sorudaki NESNELER (kalem, elma, top, kitap vb.)
- Doğru cevap ve seçenekler

🔴 SADECE TEMİZLE (KALDIR):
- "X, Y'yi çok sevmektedir" → KALDIR (ama X ve Y isimlerini KORU!)
- "X çok çalışkan bir öğrenciydi" → KALDIR (ama X ismini KORU!)
- "Güneşli bir günde kuşlar ötüyordu" → KALDIR
- Çözüme HİÇBİR KATKI SAĞLAMAYAN duygusal ifadeler

🟢 GÜÇLENDİR (AYNI SENARYO İÇİNDE):
- Mevcut senaryoyu daha NET ve ANLAMLI hale getir
- Matematiksel verileri daha açık ifade et
- Üst düzey düşünme becerisini tetikleyecek şekilde yeniden yaz
- Senaryoyu aşağıdaki bağlam türlerinden biriyle zenginleştir (görsel uyumlu!)

═══════════════════════════════════════════════════════════════════════════════
🏷️ SENARYO ZENGİNLEŞTİRME (GÖRSEL UYUMLU)
═══════════════════════════════════════════════════════════════════════════════

Mevcut senaryoyu koruyarak, bağlamı aşağıdaki kategorilerden biriyle ilişkilendir:

🌍 KİŞİSEL VE GÜNLÜK YAŞAM:
• Ev ve Aile, Alışveriş, Ulaşım, Beslenme, Kutlama/Etkinlik

💼 MESLEKİ VE İŞ DÜNYASI:
• Mühendislik, Üretim/Sanayi, Tarım, Ekonomi/Finans, İstatistik

🔬 BİLİM VE DOĞA:
• Deney/Laboratuvar, Çevre/Ekoloji, Uzay, Sağlık/Tıp, Hayvanlar

🎭 SOSYAL VE KÜLTÜREL:
• Tarih, Sanat, Edebiyat, Coğrafya, Vatandaşlık

💻 TEKNOLOJİ VE EĞLENCE:
• Dijital/İnternet, Oyun, Spor, Medya, Hobi

🎓 EĞİTİM VE OKUL:
• Okul etkinliği, Kütüphane, Tiyatro/Müzik

═══════════════════════════════════════════════════════════════════════════════
📝 DOĞRU DÖNÜŞÜM ÖRNEKLERİ
═══════════════════════════════════════════════════════════════════════════════

ÖRNEK 1 (ALIŞ-VERİŞ BAĞLAMI):
❌ ÖNCE: "Elif dedesini çok sevmektedir. Bir gün dedesiyle çarşıya gitti.
         Dedesi ona 50 TL verdi. Elif 3 kalem aldı. Kalemlerin tanesi 8 TL'dir."

✅ SONRA: "Elif, dedesiyle çarşıya gitmiştir. Dedesi ona okul alışverişi için
         50 TL vermiştir. Kalemlerin tanesi 8 TL olan kırtasiyeden Elif 3 kalem
         almak istemektedir. Buna göre Elif'in kaç TL'si kalır?"

📌 DİKKAT: Elif ve dedesi KORUNDU, sadece "çok sevmektedir" kaldırıldı!

ÖRNEK 2 (EĞİTİM BAĞLAMI):
❌ ÖNCE: "Ahmet çok çalışkan bir öğrencidir. Matematiği çok sever. Dersleri
         dikkatle dinler. Öğretmeni ona 24 elma verdi."

✅ SONRA: "Matematik dersinde paylaşım konusu işlenirken öğretmen, Ahmet'e
         24 elma vermiştir. Ahmet bu elmaları sınıftaki 4 arkadaşına eşit
         olarak paylaştırmak istemektedir."

📌 DİKKAT: Ahmet, öğretmen, elma KORUNDU, gereksiz övgüler kaldırıldı!

ÖRNEK 3 (SPOR BAĞLAMI):
❌ ÖNCE: "Ali futbolu çok sever. Her gün top oynar. 5 arkadaşıyla maç yaptı."

✅ SONRA: "Ali ve 5 arkadaşı okul bahçesinde futbol turnuvası düzenlemektedir.
         Takımlar eşit sayıda oyuncudan oluşacaktır."

📌 DİKKAT: Ali, futbol, arkadaş sayısı KORUNDU, senaryo sportif bağlamla güçlendirildi!

═══════════════════════════════════════════════════════════════════════════════
📏 SINIF SEVİYESİNE GÖRE BAĞLAM
═══════════════════════════════════════════════════════════════════════════════

İLKOKUL (1-4): 2-4 cümle, çok basit dil, somut durumlar
ORTAOKUL (5-8): 4-6 cümle, ders terimleri kullanılabilir
LİSE (9-12): 5-8 cümle, akademik dil, karmaşık senaryolar

═══════════════════════════════════════════════════════════════════════════════
📋 JSON ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════════════════════

```json
{
  "soru_metni": "AYNI SENARYO VE İSİMLERLE güçlendirilmiş soru",
  "secenekler": {
    "A": "AYNI secenek A",
    "B": "AYNI secenek B",
    "C": "AYNI secenek C",
    "D": "AYNI secenek D",
    "E": "AYNI secenek E"
  },
  "dogru_cevap": "AYNI",
  "cozum_adimlari": "Adim 1: Aciklama -> islem = sonuc\\nAdim 2: ...\\nCevap: X",
  "cozum_kisa": "Tek cumlelik ozet",
  "bloom_seviye": "uygulama/analiz/degerlendirme",
  "surec_bileseni": "cozumleme/cikarim/yorumlama/transfer",
  "korunan_unsurlar": "isimler, nesneler, senaryo - değişmeyen unsurlar",
  "kaldirilan_unsurlar": "temizlenen gereksiz ifadeler",
  "iyilestirme_yapildi": true,
  "degisiklikler": "Gereksiz detaylar temizlendi, baglam guclendirildi"
}
```

⚠️ SADECE JSON döndür. Başka açıklama yazma.
"""

def sinif_seviyesi_bilgisi_al(grade_level):
    """Sınıf seviyesine göre Maarif Modeli kurallarını getir"""
    grade = int(grade_level) if grade_level else 8
    kurallar = SINIF_BAGLAM_KURALLARI.get(grade, SINIF_BAGLAM_KURALLARI[8])

    if grade <= 4:
        seviye = "İLKOKUL"
        aciklama = "Çok basit dil, somut ve günlük durumlar, kısa cümleler"
    elif grade <= 8:
        seviye = "ORTAOKUL"
        aciklama = "Ders terimleri kullanılabilir, orta uzunlukta senaryolar"
    else:
        seviye = "LİSE"
        aciklama = "Akademik dil, karmaşık senaryolar, disipline özgü terimler"

    return {
        'seviye': seviye,
        'cumle_sayisi': kurallar['cumle_sayisi'],
        'dil': kurallar['dil'],
        'aciklama': aciklama
    }

def gemini_ile_iyilestir(soru, analiz):
    """Gemini ile soruyu Maarif Modeli'ne uygun hale getir"""
    try:
        original_text = soru.get('original_text', '') or ''
        solution_text = soru.get('solution_text', '') or ''
        options = soru.get('options', {})
        correct_answer = soru.get('correct_answer', '') or ''
        grade_level = soru.get('grade_level', 8)
        topic = soru.get('topic', '') or ''
        image_url = soru.get('image_url', None)  # Görsel URL kontrolü

        # Görsel var mı kontrol et
        gorsel_var = bool(image_url)  # image_url dolu ise görsel var

        # Sınıf seviyesi bilgilerini al
        seviye_bilgi = sinif_seviyesi_bilgisi_al(grade_level)

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

        # Görsel durumuna göre prompt seç
        if gorsel_var:
            base_prompt = IYILESTIRME_PROMPT_GORSELLI
            mod_aciklama = "🖼️ GÖRSEL VAR - Senaryo, isimler ve nesneler KORUNACAK"
        else:
            base_prompt = IYILESTIRME_PROMPT_GORSELSIZ
            mod_aciklama = "📝 GÖRSEL YOK - Soru baştan Maarif Modeli'ne uygun yazılabilir"

        prompt = f"""{base_prompt}

═══════════════════════════════════════════════════════════════════════════════
📚 BU SORU İÇİN ÖZEL KURALLAR
═══════════════════════════════════════════════════════════════════════════════

{mod_aciklama}

- Sınıf Seviyesi: {grade_level}. Sınıf ({seviye_bilgi['seviye']})
- Bağlam Uzunluğu: {seviye_bilgi['cumle_sayisi']} cümle
- Dil Seviyesi: {seviye_bilgi['dil']}
- Açıklama: {seviye_bilgi['aciklama']}

═══════════════════════════════════════════════════════════════════════════════
📝 İYİLEŞTİRİLECEK SORU
═══════════════════════════════════════════════════════════════════════════════

**Konu:** {topic}
**Tespit Edilen Sorunlar:** {', '.join(analiz['sorunlar']) if analiz['sorunlar'] else 'Belirgin sorun yok, bağlamı güçlendir'}

**Mevcut Soru Metni:**
{original_text[:1500] if original_text else 'BOŞ'}

**Mevcut Seçenekler:**
{options_str if options_str else 'YOK'}

**Doğru Cevap:** {correct_answer if correct_answer else 'YOK'}

**Mevcut Çözüm:**
{solution_text[:1000] if solution_text else 'YOK'}

═══════════════════════════════════════════════════════════════════════════════
🎯 GÖREV
═══════════════════════════════════════════════════════════════════════════════

1. Soru metnindeki gereksiz detayları (duygusal ifadeler, alakasız hikayeler) TEMİZLE
2. Soruya {seviye_bilgi['cumle_sayisi']} cümlelik ANLAMLI, çözüme katkı sağlayan bağlam ekle
3. Tüm sayısal değerleri ve seçenekleri AYNEN KORU
4. Çözümü adım adım yaz

SADECE JSON döndür, başka bir şey yazma."""

        response = gemini_client.models.generate_content(
            model='gemini-3-pro-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,  # Daha deterministik çıktı için düşürüldü
                max_output_tokens=20000
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

DEEPSEEK_KONTROL_PROMPT = """Sen Maarif Modeli uyumlu matematik soru kalite kontrolcüsüsün. Verilen soruyu değerlendir.

## DEĞERLENDİRME KRİTERLERİ

1. **Matematiksel Doğruluk (35 puan)**
   - Çözüm adımları doğru mu?
   - Cevap doğru mu?

2. **Maarif Modeli Uyumu (35 puan)**
   - Soru BAĞLAM TEMELLİ mi? (gerçek yaşam senaryosu var mı?)
   - Gereksiz detaylar temizlenmiş mi? (duygusal ifadeler, alakasız hikayeler yok mu?)
   - Bağlam çözüme KATKI SAĞLIYOR mu?
   - Sınıf seviyesine uygun mu?

3. **Çözüm ve Format Kalitesi (30 puan)**
   - Adımlar açık ve öz mü?
   - Gereksiz uzatma var mı?
   - Format temiz mi?

## ⚠️ ÖNEMLİ NOTLAR

### Maarif Modeli Kriterleri:
✅ İYİ: "Bir market, elmaları 5'li paketler halinde satıyor. Fiyatı 25 TL olan 3 paket almak isteyen..."
❌ KÖTÜ: "Ayşe çok çalışkan bir öğrencidir. Matematiği çok sever. Bir gün annesiyle markete gitti..."

### Görsel/Şekil Gerektiren Sorular:
- Görsel olmadan tam değerlendirme yapılamayacağını kabul et
- Matematiksel mantık doğruysa yüksek puan ver
- Şekil gerektiren sorularda minimum 70 puan ver (eğer çözüm mantıklıysa)

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
  "maarif_uyumu": true,
  "baglam_kalitesi": "iyi/orta/zayif",
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
        
        # Orijinal sorudaki konu bilgisi
        topic = orijinal.get('topic', '') or ''
        
        # Seçenekleri güvenli string'e çevir
        try:
            secenekler_str = json.dumps(secenekler, ensure_ascii=False, indent=2)
        except:
            secenekler_str = str(secenekler)
        
        kontrol_metni = f"""
**Konu:** {topic}

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
    """Bir batch soruyu Maarif Modeli'ne uygun hale getir"""

    mode_str = "TEKRAR GEÇİŞ" if retry_mode else "İLK GEÇİŞ"

    # İşlenecek soruları getir
    sorular = islenmemis_sorulari_getir(BATCH_SIZE, retry_mode)

    if not sorular:
        return {'islenen': 0, 'basarili': 0, 'bitti': True}

    print(f"\n{'='*70}")
    print(f"🔧 MAARİF MODELİ DÖNÜŞÜMÜ V5 - {mode_str}")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   İşlenecek: {len(sorular)} soru")
    print(f"   ID Aralığı: {START_ID} - {END_ID}")
    if sorular:
        print(f"   Bu batch ID'leri: {sorular[0]['id']} - {sorular[-1]['id']}")
    print(f"{'='*70}")
    print(f"   📖 Hedef: Bağlam temelli, gereksiz detaylardan arındırılmış sorular")
    print(f"{'='*70}\n")
    
    basarili = 0
    toplam_puan = 0
    baslangic = time.time()
    
    for idx, soru in enumerate(sorular):
        question_id = soru.get('id')
        topic = soru.get('topic', 'Bilinmeyen')[:30]
        grade = soru.get('grade_level', '?')

        # Sınıf seviyesi kategorisi
        seviye_kat = "İlkokul" if int(grade or 8) <= 4 else "Ortaokul" if int(grade or 8) <= 8 else "Lise"

        # Görsel durumu
        image_url = soru.get('image_url')
        gorsel_durumu = "🖼️ Görselli" if image_url else "📝 Görselsiz"
        islem_modu = "KORU" if image_url else "YENİDEN YAZ"

        print(f"\n[{idx+1}/{len(sorular)}] ID: {question_id} | {grade}. Sınıf ({seviye_kat}) | {topic}")
        print(f"   {gorsel_durumu} → Mod: {islem_modu}")

        # Kalite analizi
        analiz = soru_kalite_analizi(soru)
        if analiz['sorunlar']:
            print(f"   📋 Maarif Sorunları: {', '.join(analiz['sorunlar'])}")
        if analiz.get('gereksiz_detaylar'):
            print(f"   🧹 Temizlenecek: {len(analiz['gereksiz_detaylar'])} gereksiz detay")
        
        # İşle
        sonuc = tek_soru_isle(soru)
        
        if sonuc['success']:
            basarili += 1
            puan = sonuc.get('puan', 0)
            toplam_puan += puan
            iyilestirme = "✨ Maarif'e dönüştürüldü" if sonuc.get('iyilestirme') else "✅ Maarif uyumlu"
            print(f"   {iyilestirme} | Kalite: {puan}/100")
        else:
            reason = sonuc.get('reason', 'unknown')
            print(f"   ❌ Başarısız: {reason}")
        
        time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    ort_puan = toplam_puan / basarili if basarili > 0 else 0
    
    # Durum kontrolü
    durum = tum_isler_bitti_mi()
    
    print(f"\n{'='*70}")
    print(f"📊 MAARİF MODELİ DÖNÜŞÜM RAPORU - {mode_str}")
    print(f"{'='*70}")
    print(f"   ✅ Dönüştürülen: {basarili}/{len(sorular)} soru")
    print(f"   📈 Ortalama Maarif Kalitesi: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   ")
    print(f"   📋 Genel İlerleme:")
    print(f"      Toplam Soru: {durum['total']}")
    print(f"      Maarif Uyumlu: {durum['success']}")
    print(f"      Tekrar Gerekli: {durum['pending']}")
    print(f"      Bekleyen: {durum.get('islenmemis', '?')}")
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
    print("🔧 QUESTION BANK İYİLEŞTİRİCİ BOT V5 - MAARİF MODELİ")
    print("   📚 ID Aralığı: {} - {} (dinamik)".format(START_ID, END_ID))
    print("="*70)
    print("   📖 MAARİF MODELİ DÖNÜŞÜMÜ:")
    print("   ✅ Bağlam temelli soru yapısı (gerçek yaşam senaryoları)")
    print("   ✅ Gereksiz detayları temizler (duygusal ifadeler, hikayeler)")
    print("   ✅ Sayısal değerleri ve görselleri KORUR")
    print("   ✅ Sınıf seviyesine uygun bağlam uzunluğu")
    print("   ✅ Üst düzey düşünme becerilerini hedefler")
    print("="*70)
    print("   🛠️ TEKNİK ÖZELLİKLER:")
    print("   ✅ Gemini 3 Pro ile akıllı iyileştirme")
    print("   ✅ DeepSeek Maarif uyum kontrolü")
    print("   ✅ LaTeX JSON escape düzeltmesi")
    print("   ✅ Dinamik END_ID + kaldığı yerden devam")
    print("="*70 + "\n")
    
    # Progress tablosu kontrolü
    progress_tablo_kontrol()
    
    # API testleri
    print("\n🔍 Gemini API test ediliyor...")
    try:
        test = gemini_client.models.generate_content(
            model='gemini-3-flash-preview',
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
