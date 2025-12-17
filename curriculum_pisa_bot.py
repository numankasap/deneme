"""
🎯 CURRICULUM PISA SORU ÜRETİCİ BOT V1
═══════════════════════════════════════════════════════════════════════════════

Curriculum tablosundaki her kazanımdan PISA tarzı sorular üretir.
Sorular question_bank tablosuna kaydedilir.

📚 ÖZELLİKLER:
✅ PISA 2022 standartlarında soru üretimi
✅ Curriculum tablosundan otomatik kazanım çekme
✅ Chain of Thought (CoT) ile kaliteli çözüm
✅ DeepSeek doğrulama sistemi
✅ Bloom taksonomisi entegrasyonu
✅ Tekrar önleyici sistem

@version 1.0.0
@author MATAİ PRO
"""

import os
import json
import random
import time
import hashlib
import re
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
SORU_PER_KAZANIM = int(os.environ.get('SORU_PER_KAZANIM', '2'))  # Her kazanımdan kaç soru
MAX_ISLEM_PER_RUN = int(os.environ.get('MAX_ISLEM_PER_RUN', '50'))  # Her çalışmada max işlenecek kazanım
DEEPSEEK_DOGRULAMA = bool(DEEPSEEK_API_KEY)
COT_AKTIF = True
BEKLEME = 1.5
MAX_DENEME = 4
MIN_DEEPSEEK_PUAN = 65
API_TIMEOUT = 30

# Progress tablosu adı
PROGRESS_TABLE = 'curriculum_pisa_progress'

# ═══════════════════════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Yeni Google GenAI client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

deepseek = None
if DEEPSEEK_API_KEY:
    deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
    print("✅ DeepSeek doğrulama AKTİF")
else:
    print("⚠️ DeepSeek API key yok, doğrulama DEVRE DIŞI")

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════════════════════
# PISA 2022 İÇERİK KATEGORİLERİ (OECD Resmi Çerçeve)
# ═══════════════════════════════════════════════════════════════════════════════

PISA_ICERIK_KATEGORILERI = {
    'nicelik': {
        'ad': 'Nicelik (Quantity)',
        'aciklama': 'Sayı duyusu, büyüklükler, birimler, göstergeler, ölçüm, zihinsel hesaplama',
        'konular': ['Sayılar', 'Doğal Sayılar', 'Tam Sayılar', 'Kesirler', 'Ondalık', 'Oran', 'Orantı', 'Yüzde', 'Çarpanlar', 'Katlar', 'Üslü', 'Karekök', 'Bölünebilme']
    },
    'uzay_sekil': {
        'ad': 'Uzay ve Şekil (Space and Shape)',
        'aciklama': 'Görsel-uzamsal akıl yürütme, geometrik örüntüler, dönüşümler, perspektif',
        'konular': ['Geometri', 'Üçgen', 'Dörtgen', 'Çokgen', 'Çember', 'Daire', 'Alan', 'Çevre', 'Hacim', 'Prizma', 'Silindir', 'Piramit', 'Koni', 'Küre', 'Açı', 'Dönüşüm', 'Öteleme', 'Yansıma', 'Benzerlik', 'Eşlik', 'Analitik']
    },
    'degisim_iliskiler': {
        'ad': 'Değişim ve İlişkiler (Change and Relationships)',
        'aciklama': 'Fonksiyonel ilişkiler, cebirsel ifadeler, denklemler, değişim oranları',
        'konular': ['Cebir', 'Denklem', 'Eşitsizlik', 'Fonksiyon', 'Grafik', 'Doğrusal', 'Polinom', 'Özdeşlik', 'Çarpanlara', 'İkinci Derece', 'Logaritma', 'Üstel', 'Trigonometri', 'Limit', 'Türev', 'İntegral']
    },
    'belirsizlik_veri': {
        'ad': 'Belirsizlik ve Veri (Uncertainty and Data)',
        'aciklama': 'Olasılık, istatistik, veri yorumlama, örnekleme, belirsizlik',
        'konular': ['Veri', 'İstatistik', 'Olasılık', 'Grafik', 'Tablo', 'Ortalama', 'Medyan', 'Mod', 'Standart Sapma', 'Permütasyon', 'Kombinasyon', 'Sayma', 'Histogram']
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# PISA 2022 BAĞLAM KATEGORİLERİ (Otantik Senaryolar)
# ═══════════════════════════════════════════════════════════════════════════════

PISA_BAGLAM_KATEGORILERI = {
    'kisisel': {
        'ad': 'Kişisel (Personal)',
        'aciklama': 'Bireyin, ailesinin veya arkadaş grubunun günlük aktiviteleri',
        'temalar': [
            {'tema': 'yemek_hazirlama', 'aciklama': 'Tarif ayarlama, porsiyon hesaplama, malzeme oranları'},
            {'tema': 'alisveris', 'aciklama': 'İndirim hesaplama, fiyat karşılaştırma, bütçe yönetimi'},
            {'tema': 'oyun_strateji', 'aciklama': 'Kart oyunu, masa oyunu stratejileri ve puan hesaplama'},
            {'tema': 'kisisel_saglik', 'aciklama': 'Kalori hesaplama, egzersiz planı, uyku düzeni'},
            {'tema': 'spor_aktivite', 'aciklama': 'Koşu, bisiklet, yüzme performans takibi'},
            {'tema': 'seyahat_planlama', 'aciklama': 'Rota hesaplama, zaman planlaması, yakıt/şarj'},
            {'tema': 'kisisel_finans', 'aciklama': 'Harçlık yönetimi, birikim planı, harcama takibi'},
            {'tema': 'hobi_koleksiyon', 'aciklama': 'Kart koleksiyonu, pul, müzik albümü düzenleme'},
            {'tema': 'dijital_icerik', 'aciklama': 'Video süresi, dosya boyutu, indirme zamanı'},
            {'tema': 'ev_duzenleme', 'aciklama': 'Mobilya yerleşimi, oda boyama, bahçe düzenleme'}
        ]
    },
    'mesleki': {
        'ad': 'Mesleki (Occupational)',
        'aciklama': 'İş dünyası senaryoları',
        'temalar': [
            {'tema': 'insaat_olcum', 'aciklama': 'Malzeme hesaplama, alan ölçümü, maliyet tahmini'},
            {'tema': 'magaza_yonetimi', 'aciklama': 'Stok takibi, satış analizi, fiyatlandırma'},
            {'tema': 'tasarim_planlama', 'aciklama': 'Grafik tasarım ölçüleri, baskı hesaplamaları'},
            {'tema': 'etkinlik_organizasyonu', 'aciklama': 'Koltuk düzeni, bilet satışı, bütçe'},
            {'tema': 'kafe_restoran', 'aciklama': 'Menü fiyatlandırma, porsiyon hesabı, sipariş'},
            {'tema': 'tasimacilik', 'aciklama': 'Rota optimizasyonu, yakıt hesabı, zaman planı'},
            {'tema': 'tarim_bahcecilik', 'aciklama': 'Ekim planı, sulama hesabı, hasat tahmini'},
            {'tema': 'atolye_uretim', 'aciklama': 'Malzeme kesimi, fire hesabı, üretim planı'}
        ]
    },
    'toplumsal': {
        'ad': 'Toplumsal (Societal)',
        'aciklama': 'Yerel, ulusal veya küresel topluluk perspektifi',
        'temalar': [
            {'tema': 'toplu_tasima', 'aciklama': 'Otobüs/metro saatleri, aktarma, rota planlama'},
            {'tema': 'cevre_surdurulebilirlik', 'aciklama': 'Geri dönüşüm oranları, karbon ayak izi, su tasarrufu'},
            {'tema': 'nufus_demografi', 'aciklama': 'Nüfus dağılımı, yaş grupları, göç verileri'},
            {'tema': 'saglik_toplum', 'aciklama': 'Aşılama oranları, salgın verileri, sağlık istatistikleri'},
            {'tema': 'egitim_istatistik', 'aciklama': 'Okul başarı oranları, mezuniyet verileri'},
            {'tema': 'sehir_planlama', 'aciklama': 'Park alanı, yol ağı, altyapı planlaması'}
        ]
    },
    'bilimsel': {
        'ad': 'Bilimsel (Scientific)',
        'aciklama': 'Matematiğin doğa bilimleri ve teknolojiye uygulanması',
        'temalar': [
            {'tema': 'hava_durumu', 'aciklama': 'Sıcaklık değişimi, yağış miktarı, tahmin doğruluğu'},
            {'tema': 'ekoloji_doga', 'aciklama': 'Hayvan popülasyonu, habitat alanı, besin zinciri'},
            {'tema': 'astronomi_uzay', 'aciklama': 'Gezegen mesafeleri, yörünge hesabı, ışık yılı'},
            {'tema': 'fizik_hareket', 'aciklama': 'Hız, ivme, düşme, sarkaç hareketi'},
            {'tema': 'kimya_karisim', 'aciklama': 'Çözelti konsantrasyonu, karışım oranları'},
            {'tema': 'biyoloji_buyume', 'aciklama': 'Hücre bölünmesi, popülasyon artışı, genetik'},
            {'tema': 'teknoloji_veri', 'aciklama': 'Veri aktarım hızı, depolama kapasitesi, şarj süresi'},
            {'tema': 'muhendislik_tasarim', 'aciklama': 'Köprü dayanımı, yapı mekaniği, optimizasyon'}
        ]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# PISA 2022 YETERLİK SEVİYELERİ
# ═══════════════════════════════════════════════════════════════════════════════

PISA_YETERLIK_SEVIYELERI = {
    1: {
        'ad': 'Seviye 1 (Temel)',
        'puan_araligi': '358-420',
        'tanimlayicilar': [
            'Doğrudan verilen bilgiyi bulma',
            'Basit, rutin prosedürleri uygulama',
            'Tek adımlı işlemler yapma'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '1-2',
            'veri_sunumu': 'Doğrudan ve açık',
            'hesaplama': 'Basit dört işlem'
        }
    },
    2: {
        'ad': 'Seviye 2 (Temel Yeterlik)',
        'puan_araligi': '420-482',
        'tanimlayicilar': [
            'Basit çıkarımlar yapma',
            'İki adımlı prosedürler uygulama',
            'Temel grafik ve tablo okuma'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '2-3',
            'veri_sunumu': 'Tablo veya basit grafik',
            'hesaplama': 'Oran, yüzde, basit kesir'
        }
    },
    3: {
        'ad': 'Seviye 3 (Orta)',
        'puan_araligi': '482-545',
        'tanimlayicilar': [
            'Ardışık karar verme gerektiren stratejiler',
            'Birden fazla bilgiyi sentezleme',
            'Basit modeller oluşturma ve kullanma'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '3-4',
            'veri_sunumu': 'Çoklu kaynak veya tablo',
            'hesaplama': 'Çok adımlı, ara sonuçlar'
        }
    },
    4: {
        'ad': 'Seviye 4 (İleri)',
        'puan_araligi': '545-607',
        'tanimlayicilar': [
            'Karmaşık somut durumlar için modeller kullanma',
            'Varsayımları belirleme ve değerlendirme',
            'Farklı temsilleri bütünleştirme'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '4-5',
            'veri_sunumu': 'Çoklu temsil, grafik+tablo',
            'hesaplama': 'Model kurma, denklem'
        }
    },
    5: {
        'ad': 'Seviye 5 (Üstün)',
        'puan_araligi': '607-669',
        'tanimlayicilar': [
            'Karmaşık durumlar için model geliştirme',
            'Sistematik problem çözme stratejileri',
            'Çoklu çözüm yollarını değerlendirme'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '5-6',
            'veri_sunumu': 'Karmaşık, çoklu kaynak',
            'hesaplama': 'Üst düzey modelleme'
        }
    },
    6: {
        'ad': 'Seviye 6 (Uzman)',
        'puan_araligi': '669+',
        'tanimlayicilar': [
            'Özgün stratejiler ve yaklaşımlar geliştirme',
            'Soyut, standart dışı problemlerde çalışma',
            'Yaratıcı matematiksel düşünme'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '6+',
            'veri_sunumu': 'Soyut, çok katmanlı',
            'hesaplama': 'Genelleme, ispat benzeri'
        }
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# SINIF - SEVİYE EŞLEŞTİRME
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_PISA_MAP = {
    3: {'seviyeleri': [1], 'bloom': ['hatırlama', 'anlama']},
    4: {'seviyeleri': [1, 2], 'bloom': ['hatırlama', 'anlama']},
    5: {'seviyeleri': [1, 2], 'bloom': ['hatırlama', 'anlama']},
    6: {'seviyeleri': [1, 2, 3], 'bloom': ['hatırlama', 'anlama', 'uygulama']},
    7: {'seviyeleri': [2, 3, 4], 'bloom': ['anlama', 'uygulama', 'analiz']},
    8: {'seviyeleri': [3, 4, 5], 'bloom': ['uygulama', 'analiz', 'değerlendirme']},
    9: {'seviyeleri': [3, 4, 5], 'bloom': ['uygulama', 'analiz', 'değerlendirme']},
    10: {'seviyeleri': [4, 5, 6], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    11: {'seviyeleri': [5, 6], 'bloom': ['değerlendirme', 'yaratma']},
    12: {'seviyeleri': [5, 6], 'bloom': ['değerlendirme', 'yaratma']}
}

# ═══════════════════════════════════════════════════════════════════════════════
# MATEMATİKSEL SÜREÇLER
# ═══════════════════════════════════════════════════════════════════════════════

MATEMATIKSEL_SURECLER = ['formule_etme', 'kullanma', 'yorumlama']

# ═══════════════════════════════════════════════════════════════════════════════
# TÜRK İSİMLERİ HAVUZU
# ═══════════════════════════════════════════════════════════════════════════════

TURK_ISIMLERI = {
    'kiz': ['Elif', 'Zeynep', 'Defne', 'Ecrin', 'Azra', 'Nehir', 'Asya', 'Mira', 'Ela', 'Duru', 
            'Lina', 'Ada', 'Eylül', 'Ceren', 'İpek', 'Sude', 'Yağmur', 'Melis', 'Beren', 'Nil'],
    'erkek': ['Yusuf', 'Eymen', 'Ömer', 'Emir', 'Mustafa', 'Ahmet', 'Kerem', 'Miran', 'Çınar', 'Aras',
              'Kuzey', 'Efe', 'Baran', 'Rüzgar', 'Atlas', 'Arda', 'Doruk', 'Eren', 'Burak', 'Kaan']
}

kullanilan_isimler = set()

def rastgele_isim_sec():
    global kullanilan_isimler
    cinsiyet = random.choice(['kiz', 'erkek'])
    isimler = TURK_ISIMLERI[cinsiyet]
    
    if len(kullanilan_isimler) >= len(isimler) * 0.7:
        kullanilan_isimler.clear()
    
    kullanilabilir = [i for i in isimler if i not in kullanilan_isimler]
    if not kullanilabilir:
        kullanilabilir = isimler
    
    secilen = random.choice(kullanilabilir)
    kullanilan_isimler.add(secilen)
    return secilen

# ═══════════════════════════════════════════════════════════════════════════════
# TEKRAR ÖNLEYİCİ
# ═══════════════════════════════════════════════════════════════════════════════

kullanilan_hashler = set()

def hash_olustur(soru):
    icerik = f"{soru.get('soru_metni', '')}|{soru.get('beklenen_cevap', soru.get('dogru_cevap', ''))}"
    return hashlib.md5(icerik.encode()).hexdigest()

def benzersiz_mi(soru):
    return hash_olustur(soru) not in kullanilan_hashler

def hash_kaydet(soru):
    kullanilan_hashler.add(hash_olustur(soru))

# ═══════════════════════════════════════════════════════════════════════════════
# CURRICULUM'DAN VERİ ÇEK
# ═══════════════════════════════════════════════════════════════════════════════

def curriculum_getir():
    """Curriculum tablosundan SADECE Matematik kazanımlarını çeker (3-12. sınıf)"""
    try:
        # Sadece Matematik dersini ve 3-12 sınıf aralığını çek
        result = supabase.table('curriculum')\
            .select('*')\
            .eq('lesson_name', 'Matematik')\
            .gte('grade_level', 3)\
            .lte('grade_level', 12)\
            .execute()
        
        if result.data:
            print(f"✅ {len(result.data)} Matematik kazanımı bulundu (3-12. sınıf)")
            return result.data
        else:
            # Alternatif: lesson_name farklı yazılmış olabilir
            print("⚠️ 'Matematik' bulunamadı, alternatif arama yapılıyor...")
            result = supabase.table('curriculum')\
                .select('*')\
                .gte('grade_level', 3)\
                .lte('grade_level', 12)\
                .execute()
            
            if result.data:
                # Matematik içerenleri filtrele
                matematik_kayitlari = [
                    r for r in result.data 
                    if 'matematik' in str(r.get('lesson_name', '')).lower()
                    or 'math' in str(r.get('lesson_name', '')).lower()
                ]
                print(f"✅ {len(matematik_kayitlari)} Matematik kazanımı bulundu (alternatif)")
                return matematik_kayitlari
            
            print("⚠️ Curriculum tablosunda Matematik verisi bulunamadı")
            return []
            
    except Exception as e:
        print(f"❌ Curriculum çekme hatası: {str(e)}")
        return []

# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS TAKİP SİSTEMİ
# ═══════════════════════════════════════════════════════════════════════════════

def progress_tablosu_kontrol():
    """Progress tablosunun var olup olmadığını kontrol et, yoksa oluştur"""
    try:
        # Tabloyu test et
        supabase.table(PROGRESS_TABLE).select('id').limit(1).execute()
        return True
    except Exception as e:
        print(f"⚠️ Progress tablosu bulunamadı. Lütfen SQL'i çalıştırın.")
        print(f"   Hata: {str(e)[:50]}")
        return False

def progress_getir(curriculum_id):
    """Bir kazanım için mevcut progress'i getir"""
    try:
        result = supabase.table(PROGRESS_TABLE)\
            .select('*')\
            .eq('curriculum_id', curriculum_id)\
            .execute()
        
        if result.data:
            return result.data[0]
        return None
    except:
        return None

def progress_guncelle(curriculum_id, tur_sayisi, uretilen_soru):
    """Progress'i güncelle veya oluştur"""
    try:
        mevcut = progress_getir(curriculum_id)
        
        if mevcut:
            # Güncelle
            supabase.table(PROGRESS_TABLE)\
                .update({
                    'current_tur': tur_sayisi,
                    'questions_in_current_tur': uretilen_soru,
                    'total_questions': mevcut.get('total_questions', 0) + 1,
                    'last_processed_at': datetime.utcnow().isoformat()
                })\
                .eq('curriculum_id', curriculum_id)\
                .execute()
        else:
            # Yeni kayıt
            supabase.table(PROGRESS_TABLE)\
                .insert({
                    'curriculum_id': curriculum_id,
                    'current_tur': tur_sayisi,
                    'questions_in_current_tur': uretilen_soru,
                    'total_questions': 1,
                    'last_processed_at': datetime.utcnow().isoformat()
                })\
                .execute()
        return True
    except Exception as e:
        print(f"   ⚠️ Progress güncelleme hatası: {str(e)[:50]}")
        return False

def mevcut_tur_getir():
    """Şu anki tur numarasını getir"""
    try:
        result = supabase.table(PROGRESS_TABLE)\
            .select('current_tur')\
            .order('current_tur', desc=True)\
            .limit(1)\
            .execute()
        
        if result.data:
            return result.data[0].get('current_tur', 1)
        return 1
    except:
        return 1

def sonraki_kazanimlari_getir(curriculum_list, tur_sayisi, limit):
    """
    Sıradaki işlenecek kazanımları getir.
    Mevcut turda henüz SORU_PER_KAZANIM'a ulaşmamış kazanımları döndürür.
    """
    islenecekler = []
    
    for curriculum in curriculum_list:
        if len(islenecekler) >= limit:
            break
            
        curriculum_id = curriculum.get('id')
        progress = progress_getir(curriculum_id)
        
        if progress is None:
            # Hiç işlenmemiş - ekle
            islenecekler.append({
                'curriculum': curriculum,
                'tur': tur_sayisi,
                'mevcut_soru': 0
            })
        elif progress.get('current_tur', 1) < tur_sayisi:
            # Önceki turda kalmış, yeni tura geç
            islenecekler.append({
                'curriculum': curriculum,
                'tur': tur_sayisi,
                'mevcut_soru': 0
            })
        elif progress.get('current_tur', 1) == tur_sayisi:
            # Aynı turda, eksik soru var mı?
            mevcut_soru = progress.get('questions_in_current_tur', 0)
            if mevcut_soru < SORU_PER_KAZANIM:
                islenecekler.append({
                    'curriculum': curriculum,
                    'tur': tur_sayisi,
                    'mevcut_soru': mevcut_soru
                })
    
    return islenecekler

def tur_tamamlandi_mi(curriculum_list, tur_sayisi):
    """Mevcut turun tamamlanıp tamamlanmadığını kontrol et"""
    for curriculum in curriculum_list:
        curriculum_id = curriculum.get('id')
        progress = progress_getir(curriculum_id)
        
        if progress is None:
            return False
        if progress.get('current_tur', 0) < tur_sayisi:
            return False
        if progress.get('current_tur') == tur_sayisi and progress.get('questions_in_current_tur', 0) < SORU_PER_KAZANIM:
            return False
    
    return True

# ═══════════════════════════════════════════════════════════════════════════════
# PISA İÇERİK KATEGORİSİ BELİRLE
# ═══════════════════════════════════════════════════════════════════════════════

def icerik_kategorisi_belirle(curriculum_row):
    """Curriculum satırından PISA içerik kategorisini belirler"""
    
    # Kontrol edilecek alanlar
    topic_name = str(curriculum_row.get('topic_name', '')).lower()
    sub_topic = str(curriculum_row.get('sub_topic', '')).lower()
    lesson_name = str(curriculum_row.get('lesson_name', '')).lower()
    
    birlesik_metin = f"{topic_name} {sub_topic} {lesson_name}"
    
    # Her kategori için anahtar kelimeleri kontrol et
    for kategori_key, kategori_val in PISA_ICERIK_KATEGORILERI.items():
        for konu in kategori_val['konular']:
            if konu.lower() in birlesik_metin:
                return kategori_key, kategori_val
    
    # Varsayılan: lesson_name'e göre
    if 'geometri' in birlesik_metin:
        return 'uzay_sekil', PISA_ICERIK_KATEGORILERI['uzay_sekil']
    elif any(k in birlesik_metin for k in ['olasılık', 'veri', 'istatistik']):
        return 'belirsizlik_veri', PISA_ICERIK_KATEGORILERI['belirsizlik_veri']
    elif any(k in birlesik_metin for k in ['denklem', 'fonksiyon', 'cebir', 'eşitsizlik']):
        return 'degisim_iliskiler', PISA_ICERIK_KATEGORILERI['degisim_iliskiler']
    else:
        return 'nicelik', PISA_ICERIK_KATEGORILERI['nicelik']

# ═══════════════════════════════════════════════════════════════════════════════
# RASTGELE BAĞLAM SEÇ
# ═══════════════════════════════════════════════════════════════════════════════

def rastgele_baglam_sec():
    """Rastgele PISA bağlamı seçer"""
    baglam_kategorisi = random.choice(list(PISA_BAGLAM_KATEGORILERI.keys()))
    temalar = PISA_BAGLAM_KATEGORILERI[baglam_kategorisi]['temalar']
    secilen = random.choice(temalar)
    
    return {
        'kategori': baglam_kategorisi,
        'kategori_ad': PISA_BAGLAM_KATEGORILERI[baglam_kategorisi]['ad'],
        'tema': secilen['tema'],
        'aciklama': secilen['aciklama']
    }

# ═══════════════════════════════════════════════════════════════════════════════
# PISA 2022 ANA SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

PISA_2022_SYSTEM_PROMPT = """
# 🎯 OECD PISA 2022 MATEMATİK SORU TASARIM UZMANI

Sen OECD PISA 2022 standartlarında matematik soruları tasarlayan uzman bir eğitimcisin.
Görevin, verilen KAZANIM'a uygun, matematiksel okuryazarlığı ölçen, gerçek yaşam bağlamlarında otantik sorular üretmektir.

## 📚 MATEMATİKSEL OKURYAZARLIK TANIMI (OECD)

"Bireyin matematiksel akıl yürütme kapasitesi ve çeşitli gerçek yaşam bağlamlarında 
problemleri çözmek için matematiği FORMÜLE ETME, KULLANMA ve YORUMLAMA becerisidir."

## 🎯 ÜÇ MATEMATİKSEL SÜREÇ

### 1. FORMÜLE ETME (%25)
- Gerçek dünya problemini matematiksel forma dönüştürme
- Anahtar değişkenleri belirleme

### 2. KULLANMA (%50)
- Matematiksel kavram ve prosedürleri uygulama
- Hesaplamalar yapma

### 3. YORUMLAMA (%25)
- Matematiksel sonuçları bağlama geri yorumlama
- Çözümün makullüğünü değerlendirme

## ⚠️ OTANTİK SENARYO KURALLARI (KRİTİK!)

### YAPILMASI GEREKENLER:
1. ✅ Matematiğin GERÇEKTEN kullanıldığı durumlar seç
2. ✅ Bağlam yapay "sözcük problemi" değil, otantik olmalı
3. ✅ Tüm veriler senaryoda AÇIKÇA belirtilmeli
4. ✅ Öğrenci SADECE senaryoyu okuyarak çözebilmeli
5. ✅ Gerçekçi sayısal değerler kullan

### YAPILMAMASI GEREKENLER:
1. ❌ Formül/kural vermeden hesaplama isteme
2. ❌ "Kurallara göre" deyip kuralları yazmama
3. ❌ Eksik veri ile soru sorma

## 📐 GÖRSEL TEMSİL KURALLARI

Tablo, grafik veya şema gerekiyorsa MUTLAKA metin formatında göster:

### TABLO FORMATI:
**📊 [Tablo Başlığı]**
• Satır 1: Değer A, Değer B, Değer C
• Satır 2: Değer D, Değer E, Değer F

## 🔢 ÇELDİRİCİ TASARIM İLKELERİ (Çoktan Seçmeli için)

Her çeldirici belirli bir kavram yanılgısını temsil etmeli:
- 🔴 Senaryoyu yanlış yorumlama
- 🔴 Bir koşulu gözden kaçırma  
- 🔴 İşlem hatasının sonucu
- 🔴 Birimi dönüştürmeyi unutma
- 🔴 Çözümü bir adım erken bitirme

## ⚠️ DİLSEL STANDARTLAR

- Cümleler kısa ve net olmalı
- Teknik terimler gerektiğinde açıklanmalı
"""

# ═══════════════════════════════════════════════════════════════════════════════
# SEVİYEYE ÖZEL PROMPT EKLERİ
# ═══════════════════════════════════════════════════════════════════════════════

def seviye_prompt_olustur(pisa_seviye):
    """PISA seviyesine göre ek prompt oluşturur"""
    seviye = PISA_YETERLIK_SEVIYELERI.get(pisa_seviye, PISA_YETERLIK_SEVIYELERI[3])
    
    return f"""
## 🎯 HEDEFLENİEN SEVİYE: {seviye['ad']}
Puan Aralığı: {seviye['puan_araligi']}

### Bu seviyede öğrenciden beklenenler:
{chr(10).join(f"• {t}" for t in seviye['tanimlayicilar'])}

### Soru özellikleri:
• Adım sayısı: {seviye['soru_ozellikleri']['adim_sayisi']}
• Veri sunumu: {seviye['soru_ozellikleri']['veri_sunumu']}
• Hesaplama türü: {seviye['soru_ozellikleri']['hesaplama']}

⚠️ Soru bu seviyeye UYGUN zorlukta olmalı!
"""

# ═══════════════════════════════════════════════════════════════════════════════
# JSON FORMAT ŞABLONLARI
# ═══════════════════════════════════════════════════════════════════════════════

JSON_FORMAT_COKTAN_SECMELI = '''
## 📋 JSON FORMATI - ÇOKTAN SEÇMELİ (5 Seçenek: A-E)

```json
{
  "soru_tipi": "coktan_secmeli",
  "senaryo": "[Minimum 100 kelime otantik senaryo. Tüm veriler AÇIKÇA yazılmalı.]",
  "soru_metni": "[Net, anlaşılır soru kökü]",
  "secenekler": {
    "A": "[Seçenek metni]",
    "B": "[Seçenek metni]",
    "C": "[Seçenek metni]",
    "D": "[Seçenek metni]",
    "E": "[Seçenek metni]"
  },
  "dogru_cevap": "[A/B/C/D/E]",
  "celdirici_aciklamalar": {
    "[Yanlış şık]": "Bu şıkkı seçen öğrenci [kavram yanılgısı] yapmış olabilir."
  },
  "cozum_adimlari": [
    "Adım 1: [Açıklama] - [İşlem] = [Sonuç]",
    "Adım 2: [Açıklama] - [İşlem] = [Sonuç]",
    "Adım 3: [Açıklama] - [İşlem] = [Sonuç]",
    "Adım 4: [Açıklama] - [İşlem] = [Sonuç]",
    "Adım 5: [Açıklama] - [İşlem] = [Sonuç]"
  ],
  "solution_short": null,
  "solution_detailed": "[Detaylı, öğrenci dostu, adım adım çözüm açıklaması. Her adımda ne yapıldığı ve neden yapıldığı açıklanmalı.]",
  "aha_moment": "[Kilit matematiksel fikir]",
  "tahmini_sure": "[X dakika]"
}
```

⚠️ JSON KURALLARI:
1. SADECE JSON döndür, başka metin yazma
2. String içinde çift tırnak yerine tek tırnak kullan
3. Seçenekler MUTLAKA 5 tane olmalı (A, B, C, D, E)
4. EN AZ 5 çözüm adımı olmalı
5. solution_detailed öğrenci dostu, detaylı ve anlaşılır olmalı
'''

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA PROMPTU
# ═══════════════════════════════════════════════════════════════════════════════

DEEPSEEK_DOGRULAMA_PROMPT = """
# PISA 2022 SORU DOĞRULAMA UZMANI

Sen OECD PISA standartlarında soru kalitesi değerlendiren uzman bir psikometristsin.

## DOĞRULAMA KRİTERLERİ

### 1. MATEMATİKSEL DOĞRULUK (30 puan)
- Çözüm adımları matematiksel olarak doğru mu?
- Hesaplamalar hatasız mı?
- Verilen cevap gerçekten doğru mu?

### 2. SENARYO KALİTESİ (25 puan)
- Senaryo OTANTİK mi?
- Tüm gerekli veriler senaryoda mevcut mu?
- Öğrenci SADECE senaryoyu okuyarak çözebilir mi?

### 3. PISA UYUMU (25 puan)
- Hedeflenen PISA seviyesine uygun mu?
- Gerçek yaşam bağlamı var mı?

### 4. YAPISAL KALİTE (20 puan)
- Çeldiriciler farklı kavram yanılgılarını temsil ediyor mu?
- Çözüm adımları yeterli mi?

## ÇIKTI FORMATI

```json
{
  "gecerli": true/false,
  "puan": 0-100,
  "detay_puanlar": {
    "matematiksel_dogruluk": 0-30,
    "senaryo_kalitesi": 0-25,
    "pisa_uyumu": 0-25,
    "yapisal_kalite": 0-20
  },
  "sorunlar": ["Sorun 1", "Sorun 2"],
  "aciklama": "Detaylı değerlendirme..."
}
```

## KARAR KURALLARI

GEÇERSİZ (gecerli: false) eğer:
- Matematiksel hata varsa
- Senaryo eksik veya belirsizse
- Cevap yanlışsa
- Toplam puan 65'in altındaysa

SADECE JSON döndür.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# JSON TEMİZLEME
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """AI'dan gelen JSON'u temizle ve parse et"""
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
    if text.lower().startswith('json'):
        text = text[4:].strip()
    
    start = text.find('{')
    end = text.rfind('}')
    
    if start < 0 or end < 0 or end <= start:
        return None
    
    text = text[start:end+1]
    
    # Kontrol karakterlerini temizle
    text = text.replace('\t', ' ')
    text = text.replace('\r\n', ' ')
    text = text.replace('\r', ' ')
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    
    # Trailing comma temizliği
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*\]', ']', text)
    
    try:
        return json.loads(text)
    except:
        pass
    
    try:
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return json.loads(text)
    except:
        pass
    
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# COT ÇÖZÜM OLUŞTUR
# ═══════════════════════════════════════════════════════════════════════════════

def cot_cozum_olustur(curriculum_row, params):
    """Chain of Thought: Önce matematiksel çözümü oluştur"""
    try:
        baglam = params.get('baglam', {})
        icerik = params.get('icerik_kategorisi', {})
        seviye = params.get('pisa_seviye', 3)
        isim1 = rastgele_isim_sec()
        isim2 = rastgele_isim_sec()
        
        # Curriculum bilgilerini çıkar
        topic_name = curriculum_row.get('topic_name', '')
        sub_topic = curriculum_row.get('sub_topic', '')
        grade_level = curriculum_row.get('grade_level', 8)
        category = curriculum_row.get('category', '')
        learning_outcome_code = curriculum_row.get('learning_outcome_code', '')
        
        # JSON alanlarını parse et
        try:
            key_concepts = json.loads(curriculum_row.get('key_concepts', '[]')) if curriculum_row.get('key_concepts') else []
        except:
            key_concepts = []
        
        try:
            real_life_contexts = json.loads(curriculum_row.get('real_life_contexts', '[]')) if curriculum_row.get('real_life_contexts') else []
        except:
            real_life_contexts = []
        
        try:
            included_scope = json.loads(curriculum_row.get('included_scope', '[]')) if curriculum_row.get('included_scope') else []
        except:
            included_scope = []
        
        bloom_level = curriculum_row.get('bloom_level', '')
        cognitive_level = curriculum_row.get('cognitive_level', '')
        
        kazanim_bilgisi = f"{topic_name}"
        if sub_topic:
            kazanim_bilgisi += f" - {sub_topic}"
        
        # Ek bilgileri prompt'a ekle
        ek_bilgiler = ""
        if key_concepts and key_concepts != ["Anahtar kavram 1", "Anahtar kavram 2"]:
            ek_bilgiler += f"\n• Anahtar Kavramlar: {', '.join(key_concepts)}"
        if real_life_contexts and real_life_contexts != ["Gerçek yaşam örneği 1", "Gerçek yaşam örneği 2"]:
            ek_bilgiler += f"\n• Gerçek Yaşam Bağlamları: {', '.join(real_life_contexts)}"
        if included_scope and included_scope != ["Bu konuya dahil olan 1", "Bu konuya dahil olan 2"]:
            ek_bilgiler += f"\n• Kapsam: {', '.join(included_scope)}"
        
        prompt = f'''Sen OECD PISA matematik sorusu tasarlayan bir uzmansın.

## GÖREV
Aşağıdaki KAZANIM'a uygun ÖNCE bir matematik problemi tasarla, SONRA adım adım çöz.

## KAZANIM BİLGİSİ
• Konu: {topic_name}
• Alt Konu: {sub_topic if sub_topic else 'Genel'}
• Sınıf Düzeyi: {grade_level}. Sınıf
• Kategori: {category}
• Kazanım Kodu: {learning_outcome_code if learning_outcome_code else 'Belirtilmemiş'}
• Bloom Seviyesi: {bloom_level if bloom_level else cognitive_level if cognitive_level else 'uygulama'}{ek_bilgiler}

## PARAMETRELER
• İçerik Kategorisi: {icerik.get('ad', 'Nicelik')}
• PISA Seviyesi: {seviye}
• Bağlam: {baglam.get('kategori_ad', 'Kişisel')} - {baglam.get('tema', 'alisveris').replace('_', ' ')}
• Bağlam Açıklaması: {baglam.get('aciklama', 'Günlük yaşam problemi')}

## 👤 KULLANILACAK İSİMLER (ZORUNLU!)
⚠️ Senaryoda MUTLAKA şu isimleri kullan:
• Karakter 1: {isim1}
• Karakter 2: {isim2}

## SEVİYE BEKLENTİLERİ
{seviye_prompt_olustur(seviye)}

## ⚠️ VERİ TAMLIĞI KURALLARI (ÇOK KRİTİK!)

Problem tanımında şunlar MUTLAKA yer almalı:
1. Eğer TABLO gerekiyorsa → Tablo VERİLERİ AÇIKÇA yazılmalı
2. Eğer FİYAT/MALİYET varsa → Her öğenin fiyatı RAKAMLA belirtilmeli
3. Eğer ORAN/KATSAYI varsa → Sayısal değerler AÇIKÇA verilmeli
4. Eğer FORMÜL gerekiyorsa → Formül tam olarak yazılmalı

## ÖNEMLİ KURALLAR
1. Soru MUTLAKA "{kazanim_bilgisi}" konusuyla ilgili olmalı
2. Senaryo OTANTİK olmalı - yapay sözcük problemi değil
3. Küçük, hesaplanabilir sayılar kullan (1-500 arası)
4. EN AZ 5 çözüm adımı olmalı
5. {grade_level}. sınıf düzeyine uygun olmalı

## ÇIKTI FORMATI (JSON)
⚠️ Yanıtında SADECE JSON formatını kullan. Markdown code block KULLANMA.

{{
    "problem_tanimi": "[En az 120 kelime. TÜM VERİLER AÇIKÇA yazılmalı.]",
    "sayisal_veriler_tablosu": "[Birden fazla öğe varsa liste halinde yaz]",
    "kurallar": ["Kural 1: [Açıklama]", "Kural 2: [Açıklama]"],
    "verilen_degerler": {{"degisken1": "değer1", "degisken2": "değer2"}},
    "istenen": "Ne bulunacak",
    "cozum_adimlari": [
        "Adım 1: [Açıklama] - [İşlem] = [Sonuç]",
        "Adım 2: [Açıklama] - [İşlem] = [Sonuç]",
        "Adım 3: [Açıklama] - [İşlem] = [Sonuç]",
        "Adım 4: [Açıklama] - [İşlem] = [Sonuç]",
        "Adım 5: [Açıklama] - [İşlem] = [Sonuç]"
    ],
    "sonuc": "[Kesin sayısal cevap]",
    "sonuc_aciklama": "[Cevabın bağlamdaki anlamı]",
    "aha_moment": "[Kilit matematiksel fikir]",
    "kontrol": "[Doğrulama işlemi]"
}}'''

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=3000,
                response_mime_type="application/json"
            )
        )
        return json_temizle(response.text.strip())
        
    except Exception as e:
        print(f"   ⚠️ CoT Hata: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# ÇÖZÜMDEN SORU OLUŞTUR
# ═══════════════════════════════════════════════════════════════════════════════

def cozumden_soru_olustur(cozum, curriculum_row, params):
    """CoT çözümünden tam PISA sorusu oluştur - 5 seçenekli"""
    try:
        topic_name = curriculum_row.get('topic_name', '')
        sub_topic = curriculum_row.get('sub_topic', '')
        grade_level = curriculum_row.get('grade_level', 8)
        
        prompt = f'''{PISA_2022_SYSTEM_PROMPT}

{seviye_prompt_olustur(params.get('pisa_seviye', 3))}

## KAZANIM
• Konu: {topic_name}
• Alt Konu: {sub_topic if sub_topic else 'Genel'}
• Sınıf: {grade_level}. Sınıf

## HAZIR ÇÖZÜM (Bunu kullan!)

**Problem:** {cozum.get('problem_tanimi', '')}

**Sayısal Veriler:** {cozum.get('sayisal_veriler_tablosu', '')}

**Kurallar:** {json.dumps(cozum.get('kurallar', []), ensure_ascii=False)}

**Veriler:** {json.dumps(cozum.get('verilen_degerler', {}), ensure_ascii=False)}

**Çözüm Adımları:**
{chr(10).join(cozum.get('cozum_adimlari', []))}

**Sonuç:** {cozum.get('sonuc', '')}
**Açıklama:** {cozum.get('sonuc_aciklama', '')}
**Kilit Fikir:** {cozum.get('aha_moment', '')}

## GÖREV

Bu hazır çözümü kullanarak 5 SEÇENEKLİ (A-E) ÇOKTAN SEÇMELİ bir PISA sorusu oluştur.

• Soru Tipi: coktan_secmeli
• Seçenek Sayısı: 5 (A, B, C, D, E)
• İçerik: {params.get('icerik_kategorisi', {}).get('ad', 'Nicelik')}
• Sınıf: {grade_level}
• PISA Seviye: {params.get('pisa_seviye', 3)}
• Bloom Seviye: {params.get('bloom_seviye', 'uygulama')}
• Bağlam: {params.get('baglam', {}).get('kategori_ad', 'Kişisel')}
• Matematiksel Süreç: {params.get('matematiksel_surec', 'kullanma')}

{JSON_FORMAT_COKTAN_SECMELI}

⚠️ ÖNEMLİ: 
- Karakterlerin isimlerini AYNEN koru!
- MUTLAKA 5 seçenek olmalı (A, B, C, D, E)
- String değerlerde satır sonu kullanma
- Markdown code block kullanma
- solution_detailed alanı detaylı ve öğrenci dostu olmalı'''

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=3500,
                response_mime_type="application/json"
            )
        )
        
        soru = json_temizle(response.text.strip())
        
        if not soru:
            return None
        
        # Meta bilgileri ekle
        soru['sinif'] = grade_level
        soru['pisa_seviye'] = params.get('pisa_seviye', 3)
        soru['bloom_seviye'] = params.get('bloom_seviye', 'uygulama')
        soru['matematiksel_surec'] = params.get('matematiksel_surec', 'kullanma')
        soru['curriculum_id'] = curriculum_row.get('id')
        soru['topic_name'] = topic_name
        soru['sub_topic'] = sub_topic
        
        # YENİ: PISA bağlam ve içerik bilgileri
        soru['baglam_kategori'] = params.get('baglam', {}).get('kategori', 'kisisel')
        soru['icerik_kategorisi'] = params.get('icerik_key', 'nicelik')
        
        return soru
        
    except Exception as e:
        print(f"   ⚠️ Soru oluşturma hatası: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_dogrula(soru):
    """DeepSeek ile soru kalitesini doğrula"""
    if not deepseek or not DEEPSEEK_DOGRULAMA:
        return {'gecerli': True, 'puan': 75, 'aciklama': 'DeepSeek devre dışı'}
    
    try:
        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[
                {'role': 'system', 'content': DEEPSEEK_DOGRULAMA_PROMPT},
                {'role': 'user', 'content': f'Bu PISA sorusunu değerlendir:\n\n{json.dumps(soru, ensure_ascii=False, indent=2)}'}
            ],
            max_tokens=1500,
            timeout=API_TIMEOUT
        )
        
        result = json_temizle(response.choices[0].message.content)
        
        if result:
            return result
        return {'gecerli': False, 'puan': 0, 'aciklama': 'Parse hatası'}
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek hatası: {str(e)[:50]}")
        return {'gecerli': True, 'puan': 70, 'aciklama': f'DeepSeek hatası: {str(e)[:30]}'}

# ═══════════════════════════════════════════════════════════════════════════════
# SENARYO VERİ TAMLIĞI DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def senaryo_veri_tamligini_dogrula(soru):
    """Senaryonun kendi kendine yeterli olup olmadığını kontrol eder"""
    senaryo = soru.get('senaryo', '')
    
    if not senaryo or len(senaryo) < 80:
        return False, "Senaryo çok kısa (min 80 karakter)"
    
    tehlikeli_ifadeler = [
        ('tabloya göre', ['|', '•', 'Tablo', '📊', '📋', ':']),
        ('yukarıdaki tablo', ['|', '•', 'Tablo', '📊', '📋']),
        ('aşağıdaki tablo', ['|', '•', 'Tablo', '📊', '📋']),
        ('kurallara göre', ['kural', 'Kural', '•', '1.', '1)']),
        ('fiyat listesi', ['TL', 'lira', '₺', 'fiyat', ':']),
    ]
    
    senaryo_lower = senaryo.lower()
    
    for ifade, gereken_isaretler in tehlikeli_ifadeler:
        if ifade in senaryo_lower:
            if not any(isaret in senaryo for isaret in gereken_isaretler):
                return False, f"'{ifade}' var ama ilgili veri yok"
    
    return True, "OK"

# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION_BANK'A KAYDET
# ═══════════════════════════════════════════════════════════════════════════════

def question_bank_kaydet(soru, curriculum_row, dogrulama_puan=None):
    """Soruyu question_bank tablosuna kaydet - Tüm PISA sütunları dahil"""
    try:
        # Seçenekleri JSONB formatına çevir {"A": "...", "B": "...", ...}
        secenekler = soru.get('secenekler', {})
        if isinstance(secenekler, list):
            secenekler_dict = {}
            for i, s in enumerate(secenekler):
                if isinstance(s, str) and ')' in s:
                    parts = s.split(')', 1)
                    secenekler_dict[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else ''
                else:
                    secenekler_dict[chr(65+i)] = str(s)
            secenekler = secenekler_dict
        
        # Çözüm adımlarını birleştir (solution_text için)
        cozum_adimlari = soru.get('cozum_adimlari', [])
        if isinstance(cozum_adimlari, list):
            solution_text = '\n'.join(cozum_adimlari)
        else:
            solution_text = str(cozum_adimlari)
        
        # Senaryo ve soru metni ayrı ayrı
        senaryo = soru.get('senaryo', '')
        soru_metni = soru.get('soru_metni', '')
        original_text = f"{senaryo}\n\n{soru_metni}" if senaryo else soru_metni
        
        # Zorluk hesapla (PISA seviyesinden, 1-5 arası)
        pisa_seviye = soru.get('pisa_seviye', 3)
        difficulty = min(5, max(1, pisa_seviye))
        
        # Konu bilgisi: "topic_name -> sub_topic" formatında
        topic_name = curriculum_row.get('topic_name', '')
        sub_topic = curriculum_row.get('sub_topic', '')
        topic = f"{topic_name}"
        if sub_topic:
            topic += f" -> {sub_topic}"
        
        # curriculum.id değerini kazanim_id olarak kullan
        curriculum_id = curriculum_row.get('id')
        grade_level = int(curriculum_row.get('grade_level', 8))
        category = curriculum_row.get('category', '')  # Lise, LGS, TYT, AYT vs.
        
        kayit = {
            # Temel alanlar
            'title': None,
            'original_text': original_text,
            'options': json.dumps(secenekler, ensure_ascii=False),
            'solution_text': solution_text,
            'difficulty': difficulty,
            'subject': 'Matematik',
            'grade_level': grade_level,
            'topic': topic,
            'correct_answer': soru.get('dogru_cevap', 'A'),
            'kazanim_id': curriculum_id,
            'is_past_exam': False,
            'question_type': 'coktan_secmeli',
            'solution_short': soru.get('solution_short', None),
            'solution_detailed': soru.get('solution_detailed', soru.get('aha_moment', '')),
            'verified': DEEPSEEK_DOGRULAMA and dogrulama_puan and dogrulama_puan >= MIN_DEEPSEEK_PUAN,
            'verified_at': datetime.utcnow().isoformat() if (dogrulama_puan and dogrulama_puan >= MIN_DEEPSEEK_PUAN) else None,
            'is_active': True,
            'topic_group': category if category else None,
            
            # ═══ YENİ PISA SÜTUNLARI ═══
            'pisa_level': pisa_seviye,
            'bloom_level': soru.get('bloom_seviye', 'uygulama'),
            'mathematical_process': soru.get('matematiksel_surec', 'kullanma'),
            'pisa_context': soru.get('baglam_kategori', soru.get('senaryo_turu', 'kisisel')),
            'pisa_content_category': soru.get('icerik_kategorisi', 'nicelik'),
            'scenario_text': senaryo if senaryo else None,
        }
        
        # None değerleri kaldır (Supabase NULL olarak işler)
        kayit = {k: v for k, v in kayit.items() if v is not None}
        
        result = supabase.table('question_bank').insert(kayit).execute()
        
        if result.data:
            return result.data[0].get('id')
        return None
        
    except Exception as e:
        print(f"   ⚠️ Question Bank kayıt hatası: {str(e)[:80]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU ÜRET
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret(curriculum_row, params):
    """Tek bir curriculum kaydından PISA sorusu üret"""
    
    for deneme in range(MAX_DENEME):
        try:
            # Adım 1: CoT ile çözüm oluştur
            if COT_AKTIF:
                cozum = cot_cozum_olustur(curriculum_row, params)
                if not cozum:
                    print(f"   ⚠️ CoT başarısız (deneme {deneme+1})")
                    continue
            else:
                cozum = {'problem_tanimi': '', 'cozum_adimlari': [], 'sonuc': ''}
            
            # Adım 2: Çözümden soru oluştur
            soru = cozumden_soru_olustur(cozum, curriculum_row, params)
            if not soru:
                print(f"   ⚠️ Soru oluşturulamadı (deneme {deneme+1})")
                continue
            
            # Adım 3: Senaryo veri tamlığı kontrolü
            tamlik_ok, tamlik_mesaj = senaryo_veri_tamligini_dogrula(soru)
            if not tamlik_ok:
                print(f"   ⚠️ Veri eksikliği: {tamlik_mesaj} (deneme {deneme+1})")
                continue
            
            # Adım 4: Benzersizlik kontrolü
            if not benzersiz_mi(soru):
                print(f"   ⚠️ Tekrar soru (deneme {deneme+1})")
                continue
            
            # Adım 5: DeepSeek doğrulama
            dogrulama = deepseek_dogrula(soru)
            dogrulama_puan = dogrulama.get('puan', 0)
            
            if DEEPSEEK_DOGRULAMA and dogrulama_puan < MIN_DEEPSEEK_PUAN:
                print(f"   ⚠️ Düşük puan: {dogrulama_puan} (deneme {deneme+1})")
                continue
            
            # Adım 6: Question Bank'a kaydet
            soru_id = question_bank_kaydet(soru, curriculum_row, dogrulama_puan)
            
            if soru_id:
                hash_kaydet(soru)
                return {
                    'success': True,
                    'id': soru_id,
                    'puan': dogrulama_puan
                }
        
        except Exception as e:
            print(f"   ⚠️ Hata (deneme {deneme+1}): {str(e)[:50]}")
            continue
    
    return {'success': False}

# ═══════════════════════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════════════════════

def toplu_uret():
    """Curriculum tablosundan toplu PISA Matematik sorusu üret - Kaldığı yerden devam eder"""
    
    # Progress tablosunu kontrol et
    if not progress_tablosu_kontrol():
        print("❌ Progress tablosu bulunamadı! Önce SQL'i çalıştırın.")
        print("   SQL dosyası: question_bank_pisa_columns.sql")
        return 0
    
    # Curriculum verilerini çek (sadece Matematik, 3-12. sınıf)
    curriculum_data = curriculum_getir()
    
    if not curriculum_data:
        print("❌ Matematik kazanımı bulunamadı!")
        return 0
    
    # Mevcut tur numarasını al
    mevcut_tur = mevcut_tur_getir()
    
    # Tur tamamlandı mı kontrol et
    if tur_tamamlandi_mi(curriculum_data, mevcut_tur):
        mevcut_tur += 1
        print(f"🔄 Tur {mevcut_tur-1} tamamlandı! Yeni tur başlıyor: Tur {mevcut_tur}")
    
    # Sıradaki kazanımları al
    islenecekler = sonraki_kazanimlari_getir(curriculum_data, mevcut_tur, MAX_ISLEM_PER_RUN)
    
    if not islenecekler:
        print("✅ Tüm kazanımlar bu turda işlendi!")
        # Yeni tura geç
        mevcut_tur += 1
        islenecekler = sonraki_kazanimlari_getir(curriculum_data, mevcut_tur, MAX_ISLEM_PER_RUN)
        if not islenecekler:
            print("⚠️ İşlenecek kazanım bulunamadı!")
            return 0
    
    print(f"\n{'='*70}")
    print(f"🎯 MATEMATİK PISA SORU ÜRETİM - TUR {mevcut_tur}")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Toplam Matematik Kazanımı: {len(curriculum_data)}")
    print(f"   Bu Çalışmada İşlenecek: {len(islenecekler)} kazanım")
    print(f"   Kazanım Başına Soru: {SORU_PER_KAZANIM}")
    print(f"   Soru Tipi: Sadece Çoktan Seçmeli (5 şık)")
    print(f"   CoT: {'✅ AKTİF' if COT_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"   DeepSeek: {'✅ AKTİF (Min: ' + str(MIN_DEEPSEEK_PUAN) + ')' if DEEPSEEK_DOGRULAMA else '❌ DEVRE DIŞI'}")
    print(f"{'='*70}\n")
    
    basarili = 0
    dogrulanan = 0
    toplam_puan = 0
    baslangic = time.time()
    
    for idx, item in enumerate(islenecekler):
        curriculum_row = item['curriculum']
        tur = item['tur']
        mevcut_soru = item['mevcut_soru']
        
        topic_name = curriculum_row.get('topic_name', 'Bilinmeyen')
        sub_topic = curriculum_row.get('sub_topic', '')
        grade_level = curriculum_row.get('grade_level', 8)
        category = curriculum_row.get('category', '')
        curriculum_id = curriculum_row.get('id')
        
        print(f"\n[{idx+1}/{len(islenecekler)}] Kazanım ID: {curriculum_id} (Tur {tur})")
        print(f"   📚 {topic_name}" + (f" - {sub_topic}" if sub_topic else ""))
        print(f"   📊 {grade_level}. Sınıf | {category}")
        print(f"   📝 Mevcut: {mevcut_soru}/{SORU_PER_KAZANIM} soru")
        
        # İçerik kategorisini belirle
        icerik_key, icerik_val = icerik_kategorisi_belirle(curriculum_row)
        
        # Bu kazanım için eksik soruları üret
        eksik_soru = SORU_PER_KAZANIM - mevcut_soru
        
        for soru_idx in range(eksik_soru):
            # PISA seviyesi ve Bloom seviyesi belirle
            sinif_info = SINIF_PISA_MAP.get(grade_level, SINIF_PISA_MAP[8])
            pisa_seviye = random.choice(sinif_info['seviyeleri'])
            bloom_seviye = random.choice(sinif_info['bloom'])
            
            # Bağlam seç
            baglam = rastgele_baglam_sec()
            
            params = {
                'sinif': grade_level,
                'pisa_seviye': pisa_seviye,
                'bloom_seviye': bloom_seviye,
                'icerik_key': icerik_key,
                'icerik_kategorisi': icerik_val,
                'baglam': baglam,
                'matematiksel_surec': random.choice(MATEMATIKSEL_SURECLER),
                'soru_tipi': 'coktan_secmeli'
            }
            
            print(f"\n   Soru {mevcut_soru + soru_idx + 1}/{SORU_PER_KAZANIM}:")
            print(f"      PISA {pisa_seviye} | Bloom: {bloom_seviye}")
            print(f"      Bağlam: {baglam['kategori_ad']} > {baglam['tema'].replace('_', ' ')}")
            
            try:
                sonuc = tek_soru_uret(curriculum_row, params)
                
                if sonuc['success']:
                    basarili += 1
                    puan = sonuc.get('puan')
                    if puan:
                        dogrulanan += 1
                        toplam_puan += puan
                    
                    # Progress güncelle
                    progress_guncelle(curriculum_id, tur, mevcut_soru + soru_idx + 1)
                    
                    print(f"      ✅ Başarılı! ID: {sonuc['id']}")
                    if puan:
                        print(f"      📊 Kalite: {puan}/100")
                else:
                    print(f"      ❌ Başarısız")
                    
            except Exception as e:
                print(f"      ❌ Hata: {str(e)[:50]}")
            
            time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    ort_puan = toplam_puan / dogrulanan if dogrulanan > 0 else 0
    
    # Sonraki çalışma için bilgi
    kalan_bu_tur = len([
        c for c in curriculum_data 
        if not progress_getir(c['id']) or 
        progress_getir(c['id']).get('current_tur', 0) < mevcut_tur or
        (progress_getir(c['id']).get('current_tur') == mevcut_tur and 
         progress_getir(c['id']).get('questions_in_current_tur', 0) < SORU_PER_KAZANIM)
    ])
    
    print(f"\n{'='*70}")
    print(f"📊 SONUÇ RAPORU - TUR {mevcut_tur}")
    print(f"{'='*70}")
    print(f"   ✅ Bu çalışmada üretilen: {basarili} soru")
    print(f"   🔍 Doğrulanan: {dogrulanan}/{basarili}")
    print(f"   📈 Ortalama Kalite: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   📈 Hız: {sure/max(basarili,1):.1f} sn/soru")
    print(f"   ")
    print(f"   📋 Tur {mevcut_tur} Durumu:")
    print(f"      Toplam Kazanım: {len(curriculum_data)}")
    print(f"      Kalan Kazanım: ~{kalan_bu_tur} (tahmini)")
    print(f"{'='*70}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🎯 CURRICULUM PISA SORU ÜRETİCİ BOT V1")
    print("   📚 Curriculum tablosundan MATEMATİK soruları")
    print("   📊 Sınıf Aralığı: 3-12. Sınıf")
    print("   ✅ Sadece Çoktan Seçmeli Sorular (5 şık)")
    print("   ✅ PISA 2022 Standartları")
    print("   ✅ Kaldığı yerden devam eder")
    print("   ✅ Tur sistemi: Tüm kazanımlar bitince yeni tur")
    print("   ✅ kazanim_id = curriculum.id")
    print("="*70 + "\n")
    
    # Gemini testi
    print("🔍 Gemini API test ediliyor...")
    try:
        test_response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents='2+2=?'
        )
        print(f"✅ Gemini çalışıyor: {test_response.text.strip()}")
    except Exception as e:
        print(f"❌ Gemini HATASI: {e}")
        exit(1)
    
    # DeepSeek testi
    if deepseek:
        print("🔍 DeepSeek API test ediliyor...")
        try:
            test = deepseek.chat.completions.create(
                model='deepseek-chat',
                messages=[{'role': 'user', 'content': '3+5=?'}],
                max_tokens=10
            )
            print(f"✅ DeepSeek çalışıyor: {test.choices[0].message.content.strip()}")
        except Exception as e:
            print(f"⚠️ DeepSeek hatası: {e}")
            global DEEPSEEK_DOGRULAMA
            DEEPSEEK_DOGRULAMA = False
    
    print()
    
    # Soru üret
    basarili = toplu_uret()
    
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} PISA standardında soru question_bank'a kaydedildi.")

if __name__ == "__main__":
    main()
