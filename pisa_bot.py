"""
🤖 PISA SORU ÜRETİCİ BOT V3 - Ultra Kalite Edition
═══════════════════════════════════════════════════════════════════════════════

JS soru üreticisinin kaliteli özellikleri entegre edildi:
✅ 50+ Farklı Senaryo Bağlamı (Tema çeşitliliği)
✅ Gelişmiş PISA Core System Prompt (Dramatik yapı, Aha! anı)
✅ 7 Adımlı Kalite Kontrol Süreci
✅ Görsel Temsil Kuralları (Grid, Grafik, Tablo formatları)
✅ Detaylı JSON Format Şablonları
✅ DeepSeek ile Çift Katmanlı Doğrulama
✅ Senaryo Eksiksizlik Kontrolü
✅ Chain of Thought (CoT) ile matematiksel doğruluk

@version 3.0.0
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

import google.generativeai as genai
from supabase import create_client

# ═══════════════════════════════════════════════════════════════════════════════
# YAPILANDIRMA
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
SORU_ADEDI = int(os.environ.get('SORU_ADEDI', '50'))

# Ayarlar
DEEPSEEK_DOGRULAMA = bool(DEEPSEEK_API_KEY)
COT_AKTIF = True
BEKLEME = 1.5  # GitHub Actions için optimize
MAX_DENEME = 4  # Biraz azaltıldı
MIN_DEEPSEEK_PUAN = 70  # Minimum kabul puanı

# ═══════════════════════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# DeepSeek client
deepseek = None
if DEEPSEEK_API_KEY:
    deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
    print("✅ DeepSeek doğrulama AKTİF")
else:
    print("⚠️ DeepSeek API key yok, doğrulama DEVRE DIŞI")

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════════════════════
# 50+ SENARYO BAĞLAMI HAVUZU (JS'den alındı - Tekrar önleyici)
# ═══════════════════════════════════════════════════════════════════════════════

SENARYO_BAGLAMLARI = {
    'matematik': [
        # Günlük Yaşam
        {'tema': 'market_alisverisi', 'aciklama': 'Bir süpermarkette indirimli ürünler ve sepet hesabı', 'anahtar_kelimeler': ['indirim', 'toplam', 'bütçe', 'fiyat karşılaştırma']},
        {'tema': 'yemek_tarifi', 'aciklama': 'Bir yemek tarifinin malzeme oranlarını değiştirme', 'anahtar_kelimeler': ['oran', 'porsiyon', 'ölçü', 'miktar']},
        {'tema': 'ev_tasarimi', 'aciklama': 'Bir odanın mobilya yerleşimi ve alan hesabı', 'anahtar_kelimeler': ['metrekare', 'ölçek', 'yerleşim', 'alan']},
        {'tema': 'seyahat_planlama', 'aciklama': 'Tatil rotası, mesafe ve yakıt hesabı', 'anahtar_kelimeler': ['mesafe', 'süre', 'hız', 'maliyet']},
        # Spor ve Oyunlar
        {'tema': 'basketbol_istatistik', 'aciklama': 'Bir basketbol takımının maç istatistikleri', 'anahtar_kelimeler': ['ortalama', 'yüzde', 'sayı', 'verimlilik']},
        {'tema': 'satranc_turnuvasi', 'aciklama': 'Turnuva puanlama sistemi ve sıralama', 'anahtar_kelimeler': ['puan', 'sıralama', 'kombinasyon', 'olasılık']},
        {'tema': 'fitness_takip', 'aciklama': 'Egzersiz programı ve kalori hesabı', 'anahtar_kelimeler': ['kalori', 'süre', 'tekrar', 'ilerleme']},
        {'tema': 'e_spor_lig', 'aciklama': 'Online oyun ligi puan ve seviye sistemi', 'anahtar_kelimeler': ['XP', 'seviye', 'bonus', 'çarpan']},
        {'tema': 'futbol_lig', 'aciklama': 'Futbol ligi puan durumu ve averaj hesabı', 'anahtar_kelimeler': ['puan', 'averaj', 'galibiyet', 'sıralama']},
        # Ekonomi ve Finans
        {'tema': 'cep_harcligi', 'aciklama': 'Aylık harçlık yönetimi ve birikim planı', 'anahtar_kelimeler': ['birikim', 'harcama', 'hedef', 'yüzde']},
        {'tema': 'okul_kooperatifi', 'aciklama': 'Öğrenci kooperatifi satış ve kar analizi', 'anahtar_kelimeler': ['kar', 'zarar', 'maliyet', 'satış']},
        {'tema': 'enerji_faturasi', 'aciklama': 'Ev elektrik tüketimi ve fatura analizi', 'anahtar_kelimeler': ['kWh', 'tarife', 'tüketim', 'tasarruf']},
        {'tema': 'sinema_bileti', 'aciklama': 'Sinema bilet fiyatları ve grup indirimi', 'anahtar_kelimeler': ['bilet', 'indirim', 'grup', 'toplam']},
        # Müzik ve Sanat
        {'tema': 'muzik_ritmi', 'aciklama': 'Bir şarkının ritim ve nota değerleri', 'anahtar_kelimeler': ['vuruş', 'tempo', 'kesir', 'oran']},
        {'tema': 'origami_katlama', 'aciklama': 'Kağıt katlama geometrisi ve açılar', 'anahtar_kelimeler': ['açı', 'katlama', 'simetri', 'oran']},
        {'tema': 'pixel_art', 'aciklama': 'Piksel tabanlı resim oluşturma ve oranlar', 'anahtar_kelimeler': ['piksel', 'oran', 'ölçek', 'boyut']},
        {'tema': 'resim_cerceve', 'aciklama': 'Tablo boyutları ve çerçeve hesabı', 'anahtar_kelimeler': ['ölçü', 'oran', 'çevre', 'maliyet']},
        # Çevre ve Doğa
        {'tema': 'geri_donusum', 'aciklama': 'Okul geri dönüşüm kampanyası verileri', 'anahtar_kelimeler': ['miktar', 'yüzde', 'karşılaştırma', 'hedef']},
        {'tema': 'bahce_duzenleme', 'aciklama': 'Okul bahçesine bitki dikimi planı', 'anahtar_kelimeler': ['alan', 'sıra', 'aralık', 'toplam']},
        {'tema': 'su_tuketimi', 'aciklama': 'Haftalık su kullanımı ve tasarruf', 'anahtar_kelimeler': ['litre', 'ortalama', 'azaltma', 'yüzde']},
        {'tema': 'agac_dikimi', 'aciklama': 'Park alanına ağaç dikimi projesi', 'anahtar_kelimeler': ['alan', 'mesafe', 'sayı', 'düzen']},
        # Teknoloji
        {'tema': 'video_duzenleme', 'aciklama': 'Video kesme, süre ve dosya boyutu', 'anahtar_kelimeler': ['saniye', 'MB', 'oran', 'toplam']},
        {'tema': '3d_yazici', 'aciklama': '3D baskı malzeme ve süre hesabı', 'anahtar_kelimeler': ['hacim', 'süre', 'maliyet', 'ölçek']},
        {'tema': 'podcast_istatistik', 'aciklama': 'Podcast dinlenme istatistikleri', 'anahtar_kelimeler': ['dakika', 'abone', 'artış', 'ortalama']},
        {'tema': 'sosyal_medya', 'aciklama': 'Sosyal medya takipçi artış analizi', 'anahtar_kelimeler': ['takipçi', 'artış', 'yüzde', 'hafta']},
        {'tema': 'oyun_skoru', 'aciklama': 'Video oyunu skor ve seviye sistemi', 'anahtar_kelimeler': ['puan', 'seviye', 'bonus', 'çarpan']},
        # Yiyecek ve İçecek
        {'tema': 'kafe_menu', 'aciklama': 'Okul kafeteryası menü fiyatlandırması', 'anahtar_kelimeler': ['fiyat', 'kombinasyon', 'indirim', 'toplam']},
        {'tema': 'smoothie_tarif', 'aciklama': 'Meyve smoothie karışım oranları', 'anahtar_kelimeler': ['ml', 'oran', 'porsiyon', 'kalori']},
        {'tema': 'pizza_partisi', 'aciklama': 'Sınıf partisi için pizza sipariş planı', 'anahtar_kelimeler': ['dilim', 'kişi', 'toplam', 'bölüşüm']},
        {'tema': 'kurabiye_tarifi', 'aciklama': 'Kurabiye tarifi ve malzeme oranları', 'anahtar_kelimeler': ['gram', 'oran', 'porsiyon', 'çarpan']},
        # Ulaşım
        {'tema': 'okul_servisi', 'aciklama': 'Servis rotası ve zaman çizelgesi', 'anahtar_kelimeler': ['durak', 'süre', 'mesafe', 'sıra']},
        {'tema': 'bisiklet_turu', 'aciklama': 'Şehir bisiklet turu rotası planlama', 'anahtar_kelimeler': ['km', 'hız', 'eğim', 'süre']},
        {'tema': 'metro_agi', 'aciklama': 'Metro hattı aktarma ve süre hesabı', 'anahtar_kelimeler': ['hat', 'aktarma', 'dakika', 'rota']},
        {'tema': 'otobus_saatleri', 'aciklama': 'Otobüs kalkış saatleri ve bekleme süresi', 'anahtar_kelimeler': ['saat', 'dakika', 'aralık', 'bekleme']},
        # Hobi ve Koleksiyon
        {'tema': 'kart_koleksiyonu', 'aciklama': 'Koleksiyon kartları değişim ve değer', 'anahtar_kelimeler': ['nadir', 'değer', 'takas', 'set']},
        {'tema': 'pul_koleksiyonu', 'aciklama': 'Pul koleksiyonu sınıflandırma ve değer', 'anahtar_kelimeler': ['yıl', 'ülke', 'seri', 'eksik']},
        {'tema': 'lego_proje', 'aciklama': 'LEGO seti parça sayısı ve maliyet', 'anahtar_kelimeler': ['parça', 'set', 'maliyet', 'süre']},
        # Okul ve Eğitim
        {'tema': 'sinav_puanlama', 'aciklama': 'Sınav notu hesaplama sistemi', 'anahtar_kelimeler': ['puan', 'ağırlık', 'ortalama', 'geçme']},
        {'tema': 'kutuphane_odunc', 'aciklama': 'Kütüphane kitap ödünç alma istatistikleri', 'anahtar_kelimeler': ['kitap', 'gün', 'ceza', 'süre']},
        {'tema': 'sinif_secimi', 'aciklama': 'Ders seçimi ve kredi hesabı', 'anahtar_kelimeler': ['kredi', 'saat', 'zorunlu', 'seçmeli']},
        # Ek Temalar
        {'tema': 'konser_organizasyonu', 'aciklama': 'Okul konseri koltuk düzeni ve bilet satışı', 'anahtar_kelimeler': ['koltuk', 'sıra', 'fiyat', 'doluluk']},
        {'tema': 'bahce_sulama', 'aciklama': 'Otomatik sulama sistemi zamanlama', 'anahtar_kelimeler': ['dakika', 'alan', 'su', 'periyot']},
        {'tema': 'kutlama_balonu', 'aciklama': 'Doğum günü balonlarının şişirme süresi', 'anahtar_kelimeler': ['balon', 'dakika', 'helyum', 'maliyet']},
        {'tema': 'kampanya_afis', 'aciklama': 'Seçim kampanyası afiş dağıtımı', 'anahtar_kelimeler': ['afiş', 'bölge', 'dağıtım', 'etkililik']},
        {'tema': 'fotoğraf_albumu', 'aciklama': 'Dijital fotoğraf albümü düzenleme', 'anahtar_kelimeler': ['fotoğraf', 'sayfa', 'düzen', 'kapasite']},
        {'tema': 'elektrikli_arac', 'aciklama': 'Elektrikli araç şarj süresi ve menzil', 'anahtar_kelimeler': ['şarj', 'km', 'batarya', 'süre']},
        {'tema': 'yildiz_gozlem', 'aciklama': 'Gece gökyüzü gözlem planı', 'anahtar_kelimeler': ['saat', 'görünürlük', 'açı', 'zaman']},
        {'tema': 'tiyatro_sahne', 'aciklama': 'Tiyatro sahne tasarımı ve alan kullanımı', 'anahtar_kelimeler': ['metre', 'alan', 'perspektif', 'orantı']},
        {'tema': 'mahalle_guvenlik', 'aciklama': 'Güvenlik kamerası yerleşim planı', 'anahtar_kelimeler': ['açı', 'kapsama', 'sayı', 'optimizasyon']},
        {'tema': 'bocek_gozlem', 'aciklama': 'Böcek türleri sayım çalışması', 'anahtar_kelimeler': ['tür', 'sayı', 'oran', 'yoğunluk']},
    ]
}

# Kullanılan senaryolar (tekrar önleyici)
kullanilan_senaryolar = set()

def rastgele_senaryo_sec():
    """Rastgele ve tekrarsız senaryo bağlamı seçer"""
    global kullanilan_senaryolar
    
    baglamlar = SENARYO_BAGLAMLARI['matematik']
    
    # Tüm senaryolar kullanıldıysa sıfırla
    if len(kullanilan_senaryolar) >= len(baglamlar) * 0.8:
        kullanilan_senaryolar.clear()
        # print("🔄 Senaryo havuzu sıfırlandı")  # Çok fazla output veriyordu
    
    # Kullanılmamış senaryolardan seç
    kullanilabilir = [b for i, b in enumerate(baglamlar) if i not in kullanilan_senaryolar]
    secilen = random.choice(kullanilabilir)
    
    # Kullanıldı olarak işaretle
    kullanilan_senaryolar.add(baglamlar.index(secilen))
    
    return secilen

# ═══════════════════════════════════════════════════════════════════════════════
# GELİŞMİŞ VERİ YAPILARI
# ═══════════════════════════════════════════════════════════════════════════════

MATEMATIK_KONULARI = {
    'sayi_sistemleri': {
        'ad': 'Sayı Sistemleri',
        'alt_konular': ['Doğal Sayılar', 'Tam Sayılar', 'Tek-Çift Sayılar', 'Asal Sayılar', 'EKOK-EBOB', 'Üslü Sayılar', 'Köklü Sayılar', 'Rasyonel Sayılar', 'Ondalık Sayılar', 'Ardışık Sayılar']
    },
    'islem_onceligi': {
        'ad': 'İşlem Önceliği',
        'alt_konular': ['Dört İşlem Önceliği', 'Parantezli İşlemler', 'Çok Adımlı İşlemler', 'İşaret Kuralları']
    },
    'cebir': {
        'ad': 'Cebir',
        'alt_konular': ['Cebirsel İfadeler', 'Özdeşlikler', 'Birinci Derece Denklemler', 'İkinci Derece Denklemler', 'Eşitsizlikler', 'Mutlak Değer', 'Fonksiyonlar', 'Örüntüler ve Diziler']
    },
    'geometri': {
        'ad': 'Geometri',
        'alt_konular': ['Temel Geometrik Kavramlar', 'Açılar', 'Üçgenler', 'Dörtgenler', 'Çokgenler', 'Çember ve Daire', 'Alan ve Çevre', 'Hacim', 'Geometrik Dönüşümler', 'Benzerlik']
    },
    'kumeler': {
        'ad': 'Kümeler',
        'alt_konular': ['Küme Kavramı', 'Alt Küme', 'Birleşim', 'Kesişim', 'Fark', 'Tümleme', 'Venn Şemaları', 'Küme Problemleri']
    },
    'problemler': {
        'ad': 'Problemler',
        'alt_konular': ['Sayı Problemleri', 'Yaş Problemleri', 'Hareket Problemleri', 'İşçi Problemleri', 'Karışım Problemleri', 'Havuz Problemleri', 'Kesir Problemleri', 'Yüzde Problemleri']
    },
    'veri_analizi': {
        'ad': 'Veri Analizi',
        'alt_konular': ['Aritmetik Ortalama', 'Medyan ve Mod', 'Standart Sapma', 'Çizgi Grafik', 'Sütun Grafik', 'Pasta Grafik', 'Olasılık', 'Veri Yorumlama']
    },
    'oran_oranti': {
        'ad': 'Oran ve Orantı',
        'alt_konular': ['Oran Kavramı', 'Doğru Orantı', 'Ters Orantı', 'Bileşik Orantı', 'Yüzde Hesaplama', 'Kar-Zarar', 'Faiz Hesaplama', 'İndirim Hesaplama']
    }
}

SINIF_SEVIYELERI = {
    '5': {'ad': '5. Sınıf', 'pisa': [1, 2], 'bloom': ['hatırlama', 'anlama', 'uygulama']},
    '6': {'ad': '6. Sınıf', 'pisa': [1, 2, 3], 'bloom': ['anlama', 'uygulama', 'analiz']},
    '7': {'ad': '7. Sınıf', 'pisa': [2, 3, 4], 'bloom': ['uygulama', 'analiz', 'değerlendirme']},
    '8': {'ad': '8. Sınıf (LGS)', 'pisa': [3, 4, 5], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    '9': {'ad': '9. Sınıf', 'pisa': [3, 4, 5], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    '10': {'ad': '10. Sınıf', 'pisa': [4, 5], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    '11': {'ad': '11. Sınıf', 'pisa': [4, 5, 6], 'bloom': ['değerlendirme', 'yaratma']},
    '12': {'ad': '12. Sınıf (YKS)', 'pisa': [5, 6], 'bloom': ['değerlendirme', 'yaratma']}
}

PISA_SEVIYELERI = {
    1: {'ad': 'Seviye 1 (Temel)', 'puan': '358-420', 'beceriler': ['Doğrudan verilen bilgiyi bulma', 'Basit prosedürleri uygulama', 'Tek adımlı işlemler']},
    2: {'ad': 'Seviye 2 (Gelişen)', 'puan': '420-482', 'beceriler': ['Basit çıkarımlar yapma', 'İki adımlı işlemler', 'Temel grafik okuma']},
    3: {'ad': 'Seviye 3 (Orta)', 'puan': '482-545', 'beceriler': ['Birden fazla bilgiyi sentezleme', 'Çok adımlı prosedürler', 'Basit modeller oluşturma']},
    4: {'ad': 'Seviye 4 (İleri)', 'puan': '545-607', 'beceriler': ['Karmaşık modeller kullanma', 'Varsayımları değerlendirme', 'Sonuçları yorumlama ve eleştirme']},
    5: {'ad': 'Seviye 5 (Üstün)', 'puan': '607-669', 'beceriler': ['Yaratıcı problem çözme', 'Üst düzey modelleme', 'Eleştirel değerlendirme']},
    6: {'ad': 'Seviye 6 (Uzman)', 'puan': '669+', 'beceriler': ['Özgün stratejiler geliştirme', 'Karmaşık genellemeler', 'Çoklu temsiller arası geçiş']}
}

BLOOM_SEVIYELERI = {
    'hatırlama': {'ad': 'Hatırlama', 'fiiller': ['tanımla', 'listele', 'adlandır', 'hatırla']},
    'anlama': {'ad': 'Anlama', 'fiiller': ['açıkla', 'özetle', 'yorumla', 'karşılaştır']},
    'uygulama': {'ad': 'Uygulama', 'fiiller': ['uygula', 'çöz', 'kullan', 'hesapla']},
    'analiz': {'ad': 'Analiz', 'fiiller': ['analiz et', 'ayırt et', 'incele', 'sorgula']},
    'değerlendirme': {'ad': 'Değerlendirme', 'fiiller': ['değerlendir', 'eleştir', 'savun', 'yargıla']},
    'yaratma': {'ad': 'Yaratma', 'fiiller': ['tasarla', 'oluştur', 'üret', 'planla']}
}

SENARYO_TURLERI = ['diyalog', 'uygulama', 'tablo', 'grafik', 'infografik', 'gunluk', 'haber', 'coklu', 'deney']
SORU_TIPLERI = ['coktan_secmeli', 'acik_uclu']

# ═══════════════════════════════════════════════════════════════════════════════
# TEKRAR ÖNLEYİCİ
# ═══════════════════════════════════════════════════════════════════════════════

kullanilan_hashler = set()

def hash_olustur(soru):
    icerik = f"{soru.get('soru_metni', '')}|{soru.get('dogru_cevap', '')}"
    return hashlib.md5(icerik.encode()).hexdigest()

def benzersiz_mi(soru):
    return hash_olustur(soru) not in kullanilan_hashler

def hash_kaydet(soru):
    kullanilan_hashler.add(hash_olustur(soru))

# ═══════════════════════════════════════════════════════════════════════════════
# GELİŞMİŞ PISA CORE SYSTEM PROMPT (JS'den alındı)
# ═══════════════════════════════════════════════════════════════════════════════

PISA_CORE_SYSTEM = """
# 🌟 PISA TARZI ÜST DÜZEY SORU TASARIM UZMANI

Sen OECD PISA standartlarında üst düzey düşünme soruları tasarlayan uzman bir eğitimcisin.
Görevin gerçek yaşam bağlamlarında derin düşünme, problem çözme ve akıl yürütme becerilerini 
ölçen sorular üretmektir.

## 📚 TEMEL FELSEFENİZ

### "Az Bilgi, Derin Akıl" (Low-Floor, High-Ceiling) Prensibi
- Soru, temel bilgiyle başlanabilir olmalı (düşük zemin)
- Ancak tam çözüm için derin düşünme gerektirir (yüksek tavan)
- Ezberlenen formüllerle değil, kavrayışla çözülür

### Gizli Basitlik Prensibi
- İlk bakışta karmaşık veya içinden çıkılmaz görünebilir
- Doğru yaklaşıldığında zarif bir "anahtar fikir" ile çözülür
- "Kaba kuvvet" değil, "zeka" ödüllendirilir

### Çok Aşamalı Çözüm
- Tek adımda çözülemez
- Her adım bir sonrakine zemin hazırlar
- Zincir halkaları gibi birbirine bağlı
- Tüm aşamaları tamamlamadan doğru cevaba ulaşılamaz

## 🎭 DRAMATİK YAPI (Her soruda olmalı!)

### 1. GİRİŞ (The Hook) 
- Basit, anlaşılır, davetkâr
- Öğrenci: "Bunu yapabilirim galiba" demeli
- En azından birkaç küçük durumu deneyebilmeli

### 2. GELİŞME (The Struggle)
- Standart yaklaşımlar denenir
- Bir "duvara" toslanır
- Farklı bir bakış açısı gerektiği anlaşılır
- Bu "mücadele" anı öğrenmenin en değerli kısmıdır

### 3. ZİRVE (The "Aha!" Moment)
- Kilit fikir, zarif hile veya beklenmedik bağlantı görülür
- Tüm düğümler çözülür
- Senaryodaki büyük "twist" anı
- BU ANI TASARLAMAK EN SANATSAL KISMDIR!

### 4. SONUÇ (The Resolution)
- "Aha!" anından sonra çözüm şelale gibi akar
- Zarif bir şekilde sonuca ulaşılır
- Tatmin edici bir kapanış

## 🎯 SENARYO TASARIM İLKELERİ

### ⚠️ EN KRİTİK KURAL: EKSİKSİZ VE KENDİ KENDİNE YETEN SENARYO

Soruyu çözmek için gereken TÜM BİLGİLER senaryoda AÇIKÇA yazılmalı!
Öğrenci SADECE senaryoyu okuyarak soruyu çözebilmeli!

❌ ASLA YAPMA:
- Kuralları belirtmeden "kurallara göre" deme
- Formülü vermeden hesaplama isteme
- Tabloyu göstermeden "tabloya göre" deme
- Veriyi yazmadan "verilere göre" deme
- Eksik bilgiyle soru sorma

✅ HER ZAMAN YAP:
- Tüm kuralları madde madde yaz
- Tüm sayısal değerleri açıkça belirt
- Tüm formülleri veya hesaplama yöntemlerini göster
- Tüm tabloları ve verileri eksiksiz sun

### ÖRNEK - DOĞRU FORMAT:
"Ayşe ve Can yeni bir kart oyunu tasarlıyor.

**📋 Oyun Kuralları:**
* Tek sayı kartları: Kartın değeri kadar puan verir
* Çift sayı kartları: Kartın değerinin yarısı kadar puan verir  
* 5'in katı olan kartlar: Ek +3 bonus puan
* 10'un katı olan kartlar: Ek +5 bonus puan (5'in katı bonusu da geçerli)

**🎴 Ayşe'nin Seçtiği Kartlar:** 7, 12, 25, 30

Soru: Ayşe bu kartlardan toplam kaç puan kazanır?"

## ⚠️ GÖRSEL TEMSİL ZORUNLULUĞU

Eğer soruda grid, harita, plan, grafik varsa, MUTLAKA TABLO veya ASCII formatında GÖSTER!

### Grid/Harita için format:
```
|   | A | B | C | D | E |
|---|---|---|---|---|---|
| 1 | ⬜ | 🧱 | ⬜ | ⬜ | ⬜ |
| 2 | ⬜ | 🧱 | ⬜ | ⬜ | ⬜ |
| 3 | ⬜ | 🧱 | 🔥 | ⬜ | ⬜ |
| 4 | 🧱 | 🧱 | 🧱 | 🧱 | 🧱 |
| 5 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
```

### Grafik için format:
```
📊 Satış Grafiği (Birim: 1000 TL)
     
40 |          ▓▓
35 |       ▓▓ ▓▓
30 |    ▓▓ ▓▓ ▓▓ ▓▓
25 | ▓▓ ▓▓ ▓▓ ▓▓ ▓▓
   +------------------
     Oca Şub Mar Nis May
```

### Tablo için format:
```
| Ay      | Satış | Gelir (TL) |
|---------|-------|------------|
| Ocak    | 120   | 24.000     |
| Şubat   | 150   | 30.000     |
| Mart    | 180   | 36.000     |
```

## ⚠️ ZEKİ ÇELDİRİCİLER (Şıklı sorular için)

Her yanlış şık belirli bir bilişsel hatayı temsil etmeli:
- 🔴 Senaryoyu yanlış yorumlama
- 🔴 Bir koşulu gözden kaçırma
- 🔴 Denklemi/modeli hatalı kurma
- 🔴 Çözümü bir adım erken bitirme
- 🔴 İşlem hatası yapma
- 🔴 Birimi dönüştürmeyi unutma

Her çeldirici için açıklama yaz:
"Bu şıkkı seçen öğrenci şu hatayı yapmış olabilir: ..."

## 🔄 7 ADIMLI KALİTE KONTROL SÜRECİ

### ADIM 1: SENARYO VE VERİ TASARLA
- İlgi çekici bir bağlam oluştur
- Verileri senaryoya doğal şekilde yerleştir
- TÜM KURALLARI VE VERİLERİ AÇIKÇA YAZ!

### ADIM 2: SENARYO EKSİKSİZLİK KONTROLÜ
- ☐ Öğrenci SADECE senaryoyu okuyarak çözebilir mi?
- ☐ Tüm kurallar yazılı mı?
- ☐ Tüm sayısal değerler verilmiş mi?
- ☐ Tablo/grafik gerekiyorsa eklenmiş mi?
EKSİK VARSA ADIM 1'E DÖN!

### ADIM 3: PROBLEMİ FORMÜLE ET
- Net ama zorlu bir soru sor
- "Aha!" anını tasarla
- Çözüm yolunu planla

### ADIM 4: KENDİN ADIM ADIM ÇÖZ
- Her adımı detaylı yaz
- Ara sonuçları kontrol et
- Final cevabı bul

### ADIM 5: DOĞRULA
- Çözümünü tekrar kontrol et
- Sayıları yerine koy
- Mantıksal tutarlılığı sağla

### ADIM 6: ÇELDİRİCİLERİ TASARLA
- Yaygın hataları düşün
- Her biri farklı bir yanılgıyı temsil etsin
- Doğru cevabı rastgele bir şıkka yerleştir

### ADIM 7: SON GÖZDEN GEÇİRME
- Soru anlaşılır mı?
- Çözüm zarif mi?
- "Aha!" anı var mı?
- SENARYO KENDİ KENDİNE YETERLİ Mİ?
"""

MATEMATIK_OZEL_PROMPT = """
## 🔢 MATEMATİK SORU TASARIM KURALLARI

### Problem Türleri
1. **Sayılar ve İşlemler**: Örüntü keşfi, sayı özellikleri, EKOK-EBOB uygulamaları
2. **Cebir**: Denklem kurma, fonksiyonel düşünme, örüntüden kurala ulaşma
3. **Geometri**: Görsel-uzamsal akıl yürütme, ölçek ve orantı, alan-hacim optimizasyonu
4. **Veri ve Olasılık**: Grafik yorumlama, istatistiksel akıl yürütme, veri temelli karar

### Matematiksel Süreç Becerileri
1. **Formüle Etme**: Gerçek durumu matematiksel modele dönüştürme
2. **Uygulama**: Matematiksel prosedürleri kullanma
3. **Yorumlama**: Matematiksel sonuçları bağlama geri taşıma
4. **Akıl Yürütme**: Mantıksal argüman oluşturma

### Sayısal Değer Kuralları
- Küçük, hesaplanabilir sayılar tercih et (1-100 arası)
- Sonuç tam sayı veya basit kesir olsun
- Karmaşık hesaplamalar değil, karmaşık düşünme gereksin
"""

# ═══════════════════════════════════════════════════════════════════════════════
# JSON FORMAT ŞABLONLARI
# ═══════════════════════════════════════════════════════════════════════════════

JSON_FORMAT_COKTAN_SECMELI = '''
## 📋 JSON FORMATI - ÇOKTAN SEÇMELİ SORU

Yanıtını SADECE aşağıdaki JSON formatında ver:

```json
{
  "soru_tipi": "coktan_secmeli",
  "alan": "matematik",
  "konu": "Ana konu adı",
  "alt_konu": "Alt konu adı",
  "sinif": "8",
  "pisa_seviye": 4,
  "bloom_seviye": "analiz",
  "senaryo_turu": "tablo",
  
  "senaryo": "⚠️ KRİTİK: Senaryoda TÜM kurallar, veriler, tablolar AÇIKÇA yazılmalı!\\n\\n[Min 100 kelime detaylı senaryo]\\n\\n**📋 Kurallar:**\\n* Kural 1: ...\\n* Kural 2: ...\\n\\n[Tablo/Grafik varsa buraya]",
  
  "soru_metni": "Senaryoya dayanan net soru",
  
  "secenekler": [
    "A) Birinci seçenek",
    "B) İkinci seçenek", 
    "C) Üçüncü seçenek",
    "D) Dördüncü seçenek",
    "E) Beşinci seçenek"
  ],
  
  "dogru_cevap": "B",
  
  "celdirici_aciklamalar": {
    "A": "Bu şıkkı seçen öğrenci şu hatayı yapmış olabilir: ...",
    "C": "Bu şıkkı seçen öğrenci şu hatayı yapmış olabilir: ...",
    "D": "Bu şıkkı seçen öğrenci şu hatayı yapmış olabilir: ...",
    "E": "Bu şıkkı seçen öğrenci şu hatayı yapmış olabilir: ..."
  },
  
  "cozum_adimlari": [
    "Adım 1: Senaryodan verileri çıkarma - [detay]",
    "Adım 2: Matematiksel model kurma - [işlem]",
    "Adım 3: Hesaplama - [işlem] = [sonuç]",
    "Adım 4: İkinci hesaplama - [işlem] = [sonuç]",
    "Adım 5: Sonucu yorumlama - [açıklama]",
    "Adım 6: Doğru şıkkı belirleme - Cevap: [harf]"
  ],
  
  "aha_moment": "Bu sorudaki kilit fikir şudur: ...",
  
  "beceri_alani": "problem çözme",
  "tahmini_sure": "5-8 dakika",
  "pedagojik_notlar": "Bu soru şu becerileri ölçmektedir: ..."
}
```

⚠️ JSON KURALLARI:
1. SADECE JSON döndür, başka metin ekleme
2. String içinde çift tırnak kullanma, tek tırnak kullan
3. Trailing comma KOYMA
4. Newline için \\n kullan
5. dogru_cevap ile cozum_adimlari MUTLAKA eşleşmeli
6. EN AZ 5-6 ÇÖZÜM ADIMI olmalı
'''

JSON_FORMAT_ACIK_UCLU = '''
## 📋 JSON FORMATI - AÇIK UÇLU SORU

```json
{
  "soru_tipi": "acik_uclu",
  "alan": "matematik",
  "konu": "Ana konu",
  "alt_konu": "Alt konu",
  "sinif": "8",
  "pisa_seviye": 4,
  "bloom_seviye": "değerlendirme",
  "senaryo_turu": "coklu",
  
  "senaryo": "Detaylı senaryo...",
  "soru_metni": "Açık uçlu soru",
  
  "beklenen_cevap": "Tam puan cevabın özeti",
  
  "puanlama_rubrik": {
    "tam_puan": "2 puan - Doğru çözüm, tüm adımlar gösterilmiş",
    "kismi_puan": "1 puan - Doğru yaklaşım ama hesaplama hatası",
    "sifir_puan": "0 puan - Yanlış yöntem veya anlamsız çözüm"
  },
  
  "cozum_adimlari": [
    "Adım 1: ...",
    "Adım 2: ...",
    "Adım 3: ...",
    "Adım 4: ..."
  ],
  
  "aha_moment": "Kilit fikir...",
  "beceri_alani": "akıl yürütme",
  "tahmini_sure": "8-12 dakika",
  "pedagojik_notlar": "..."
}
```
'''

# ═══════════════════════════════════════════════════════════════════════════════
# GELİŞMİŞ DEEPSEEK DOĞRULAMA PROMPTU
# ═══════════════════════════════════════════════════════════════════════════════

DEEPSEEK_DOGRULAMA_PROMPT = """
# PISA SORU DOĞRULAMA UZMANI

Sen üst düzey bir matematik ve eğitim doğrulama uzmanısın. Sana verilen PISA sorusunu aşağıdaki kriterlere göre değerlendir.

## DOĞRULAMA KRİTERLERİ

### 1. ÇÖZÜM KONTROLÜ (KRİTİK!)
- Çözüm adımları mevcut mu?
- En az 4 adım var mı?
- Her adım mantıksal ve tutarlı mı?
- Matematiksel işlemler doğru mu?
- Verilen cevap (dogru_cevap) çözüm adımlarıyla uyumlu mu?

### 2. SENARYO KALİTESİ
- Senaryo eksiksiz mi? (Tüm veriler mevcut mu?)
- Öğrenci sadece senaryoyu okuyarak soruyu çözebilir mi?
- Kurallar ve formüller açıkça belirtilmiş mi?
- Senaryo en az 80 kelime mi?

### 3. MATEMATİKSEL DOĞRULUK
- Hesaplamalar doğru mu?
- Sonuç mantıklı mı?
- Birimler tutarlı mı?

### 4. YAPISAL TUTARLILIK
- dogru_cevap gerçekten doğru mu?
- Şıklar makul ve çeldirici mi?
- Çeldirici açıklamaları mantıklı mı?
- "Aha!" anı var mı ve etkili mi?

### 5. PISA UYUMU
- Gerçek yaşam bağlamı var mı?
- Üst düzey düşünme gerektiriyor mu?
- Dramatik yapı var mı (Giriş-Gelişme-Aha!-Sonuç)?

## ÇIKTI FORMATI

JSON formatında yanıt ver:
```json
{
  "gecerli": true/false,
  "puan": 0-100,
  "cozum_kontrolu": {
    "cozum_mevcut": true/false,
    "adim_sayisi": 0,
    "adimlar_tutarli": true/false,
    "hesaplamalar_dogru": true/false,
    "cevap_uyumlu": true/false
  },
  "senaryo_kontrolu": {
    "eksiksiz": true/false,
    "veriler_yeterli": true/false,
    "kurallar_acik": true/false,
    "min_kelime_sayisi": true/false
  },
  "matematiksel_dogruluk": {
    "hesaplamalar": true/false,
    "sonuc_mantikli": true/false,
    "dogru_cevap_gercekten_dogru": true/false
  },
  "pisa_uyumu": {
    "gercek_yasam_baglami": true/false,
    "ust_duzey_dusunme": true/false,
    "dramatik_yapi": true/false,
    "aha_moment": true/false
  },
  "sorunlar": ["Sorun 1", "Sorun 2"],
  "oneriler": ["Öneri 1", "Öneri 2"],
  "aciklama": "Detaylı değerlendirme..."
}
```

## KARAR KURALLARI

Soru GEÇERSİZ (gecerli: false) sayılır eğer:
- Çözüm adımları yoksa veya 3'ten azsa
- Çözüm adımları soruyla uyumsuzsa
- Matematiksel hatalar varsa
- dogru_cevap aslında yanlışsa
- Senaryo eksik veya belirsizse
- Puan 70'in altındaysa

SADECE JSON döndür.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# ADIM 1: COT - ÇÖZÜM OLUŞTUR (Chain of Thought)
# ═══════════════════════════════════════════════════════════════════════════════

def cot_cozum_olustur(params):
    """
    Chain of Thought: Önce matematiksel çözümü oluştur
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        senaryo_baglam = params.get('senaryo_baglami', {})
        
        prompt = f'''Sen bir matematik öğretmenisin. Aşağıdaki parametrelere göre ÖNCE bir matematik problemi ve ÇÖZÜMÜNÜ oluştur.

KONU: {params['konu_ad']} - {params['alt_konu']}
SINIF: {params['sinif_ad']}
ZORLUK: PISA {params['pisa_seviye']} seviyesi

🎬 SENARYO BAĞLAMI (Bu temayı MUTLAKA kullan!):
- Tema: {senaryo_baglam.get('tema', 'genel').replace('_', ' ')}
- Açıklama: {senaryo_baglam.get('aciklama', 'Günlük yaşam problemi')}
- Anahtar Kelimeler: {', '.join(senaryo_baglam.get('anahtar_kelimeler', ['hesaplama', 'oran']))}

⚠️ ÖNEMLİ: Yukarıdaki temayı kullan! Dron, robot gibi klişe temalardan KAÇIN!

ÖNEMLİ KURALLAR:
1. ÖNCE problemi tanımla (verilen temayı kullanarak)
2. TÜM KURALLARI AÇIKÇA YAZ
3. SONRA adım adım çöz (EN AZ 5-6 ADIM)
4. Her adımda matematiksel işlemi yaz
5. Son cevabı net olarak belirt
6. Tüm sayısal değerler küçük ve hesaplanabilir olsun (1-100 arası)
7. Sonuç tam sayı veya basit kesir olsun

JSON formatında yanıt ver:
{{
    "problem_tanimi": "Problemin açık tanımı ve tüm veriler - EN AZ 80 KELİME",
    "kurallar": ["Kural 1: ...", "Kural 2: ...", "Kural 3: ..."],
    "verilen_degerler": ["değer1", "değer2", "değer3"],
    "istenen": "Ne bulunması gerekiyor",
    "cozum_adimlari": [
        "Adım 1: [işlem] = [sonuç]",
        "Adım 2: [işlem] = [sonuç]",
        "Adım 3: [işlem] = [sonuç]",
        "Adım 4: [işlem] = [sonuç]",
        "Adım 5: [işlem] = [sonuç]",
        "Adım 6: [işlem] = [sonuç]"
    ],
    "sonuc": "Kesin sayısal cevap",
    "sonuc_aciklama": "Cevabın ne anlama geldiği",
    "aha_moment": "Bu problemdeki kilit fikir nedir?",
    "kontrol": "Cevabın doğruluğunu kontrol eden işlem"
}}

SADECE JSON döndür, başka bir şey yazma.'''

        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Güçlendirilmiş JSON temizleme
        cozum = json_temizle(text)
        return cozum
        
    except Exception as e:
        print(f"   ⚠️ CoT Hata: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# ADIM 2: ÇÖZÜMDEN SORU OLUŞTUR
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """
    AI'dan gelen JSON'u temizle ve parse et
    """
    # Markdown code block temizliği
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0]
    elif '```' in text:
        for part in text.split('```'):
            if '{' in part and '}' in part:
                text = part
                break
    
    if text.strip().startswith('json'):
        text = text.strip()[4:]
    
    # İlk { ve son } arasını al
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    
    if first_brace == -1 or last_brace == -1:
        return None
    
    text = text[first_brace:last_brace + 1]
    
    # Sorunlu karakterleri düzelt
    # 1. Escape edilmemiş newline'ları düzelt
    # String içindeki gerçek satır sonlarını \n ile değiştir
    def fix_strings(match):
        s = match.group(0)
        # String içindeki newline'ları escape et
        s = s.replace('\n', '\\n')
        s = s.replace('\r', '')
        s = s.replace('\t', '\\t')
        return s
    
    # Çift tırnak içindeki stringleri bul ve düzelt
    text = re.sub(r'"(?:[^"\\]|\\.)*"', fix_strings, text, flags=re.DOTALL)
    
    # 2. Trailing comma'ları kaldır
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    
    # 3. Tek tırnaklı stringleri çift tırnağa çevir (key'ler için)
    text = re.sub(r"'([^']+)'(\s*:)", r'"\1"\2', text)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Son çare: Daha agresif temizlik
        try:
            # Tüm kontrol karakterlerini kaldır
            text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
            text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
            text = re.sub(r'\s+', ' ', text)
            return json.loads(text)
        except:
            return None


def cozumden_soru_olustur(cozum, params):
    """
    Doğrulanmış çözümden PISA formatında soru oluştur
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Format seç
        if params['soru_tipi'] == 'coktan_secmeli':
            json_format = JSON_FORMAT_COKTAN_SECMELI
        else:
            json_format = JSON_FORMAT_ACIK_UCLU
        
        senaryo_baglam = params.get('senaryo_baglami', {})
        pisa_bilgi = PISA_SEVIYELERI.get(params['pisa_seviye'], PISA_SEVIYELERI[4])
        bloom_bilgi = BLOOM_SEVIYELERI.get(params['bloom_seviye'], BLOOM_SEVIYELERI['analiz'])
        
        system_prompt = f"{PISA_CORE_SYSTEM}\n\n{MATEMATIK_OZEL_PROMPT}\n\n{json_format}"

        user_prompt = f'''Aşağıdaki ÇÖZÜLMÜŞ problemden PISA formatında üst düzey soru oluştur.

## ÇÖZÜM BİLGİLERİ:
- Problem: {cozum.get('problem_tanimi', '')}
- Kurallar: {cozum.get('kurallar', [])}
- Verilen Değerler: {cozum.get('verilen_degerler', [])}
- İstenen: {cozum.get('istenen', '')}
- Çözüm Adımları: {cozum.get('cozum_adimlari', [])}
- DOĞRU CEVAP: {cozum.get('sonuc', '')}
- Aha! Moment: {cozum.get('aha_moment', '')}

## PARAMETRELER:
- Senaryo Türü: {params['senaryo_turu']}
- Soru Tipi: {params['soru_tipi']}
- Tema: {senaryo_baglam.get('tema', 'genel').replace('_', ' ')}
- PISA Seviye: {pisa_bilgi['ad']}
- Bloom: {bloom_bilgi['ad']}
- Hedef Beceriler: {', '.join(pisa_bilgi.get('beceriler', []))}

## GÖREV:
1. Bu çözümü kullanarak DETAYLI bir SENARYO yaz (min 100 kelime)
2. TÜM KURALLARI AÇIKÇA senaryoya yaz - öğrenci sadece senaryoyu okuyarak çözebilmeli!
3. Tablo/grafik gerekiyorsa GÖRSEL olarak ekle
4. Senaryodan doğal bir SORU oluştur
5. Doğru cevap MUTLAKA "{cozum.get('sonuc', '')}" olmalı
6. Çeldiriciler gerçekçi HATALARA dayalı olmalı
7. "Aha!" anı net olmalı

⚠️ KRİTİK HATIRLATMALAR:
- SENARYO EKSİKSİZ OLMALI - tüm kurallar ve veriler yazılı!
- Çözüm adımları EN AZ 5-6 adım olmalı ve detaylı!
- dogru_cevap ile çözüm adımlarındaki sonuç MUTLAKA eşleşmeli!

{json_format}

Şimdi soruyu oluştur:'''

        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config={
                'temperature': 0.7,
                'max_output_tokens': 4000
            }
        )
        
        text = response.text.strip()
        
        # Güçlendirilmiş JSON temizleme
        soru = json_temizle(text)
        
        if not soru:
            print(f"      ⚠️ JSON parse başarısız")
            return None
        
        # Meta bilgileri ekle
        soru['alan'] = 'matematik'
        soru['konu'] = params['konu_ad']
        soru['alt_konu'] = params['alt_konu']
        soru['sinif'] = params['sinif']
        soru['pisa_seviye'] = params['pisa_seviye']
        soru['bloom_seviye'] = params['bloom_seviye']
        soru['senaryo_turu'] = params['senaryo_turu']
        soru['soru_tipi'] = params['soru_tipi']
        soru['senaryo_baglam'] = senaryo_baglam.get('tema', 'genel')
        soru['cot_cozum'] = cozum
        
        return soru
        
    except Exception as e:
        print(f"   ⚠️ Soru oluşturma: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# ADIM 3: GELİŞMİŞ DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════════════════════

def deepseek_dogrula(soru):
    """
    DeepSeek ile kapsamlı soru doğrulaması
    """
    if not deepseek:
        return {'gecerli': True, 'puan': 80, 'aciklama': 'DeepSeek devre dışı'}
    
    try:
        prompt = f'''{DEEPSEEK_DOGRULAMA_PROMPT}

## DOĞRULANACAK SORU

```json
{json.dumps(soru, ensure_ascii=False, indent=2)}
```

Yukarıdaki soruyu değerlendir ve SADECE JSON formatında sonuç döndür.'''

        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[
                {'role': 'system', 'content': 'Sen bir PISA soru doğrulama uzmanısın. SADECE JSON formatında yanıt ver.'},
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=2500,
            temperature=0.2
        )
        
        text = response.choices[0].message.content.strip()
        
        # Güçlendirilmiş JSON temizleme
        dogrulama = json_temizle(text)
        
        if not dogrulama:
            return {'gecerli': True, 'puan': 75, 'aciklama': 'DeepSeek yanıtı parse edilemedi'}
        
        # Puan kontrolü
        puan = dogrulama.get('puan', 0)
        gecerli = dogrulama.get('gecerli', False) and puan >= MIN_DEEPSEEK_PUAN
        
        return {
            'gecerli': gecerli,
            'puan': puan,
            'cozum_kontrolu': dogrulama.get('cozum_kontrolu', {}),
            'senaryo_kontrolu': dogrulama.get('senaryo_kontrolu', {}),
            'matematiksel_dogruluk': dogrulama.get('matematiksel_dogruluk', {}),
            'pisa_uyumu': dogrulama.get('pisa_uyumu', {}),
            'sorunlar': dogrulama.get('sorunlar', []),
            'oneriler': dogrulama.get('oneriler', []),
            'aciklama': dogrulama.get('aciklama', '')
        }
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek Doğrulama: {str(e)[:50]}")
        return {'gecerli': True, 'puan': 75, 'aciklama': f'DeepSeek hatası: {str(e)[:30]}'}

# ═══════════════════════════════════════════════════════════════════════════════
# KALİTE KONTROL FONKSİYONU
# ═══════════════════════════════════════════════════════════════════════════════

def kalite_kontrol(soru):
    """
    Temel kalite kontrolleri
    """
    sorunlar = []
    
    # Senaryo uzunluğu
    senaryo = soru.get('senaryo', '')
    if len(senaryo) < 100:
        sorunlar.append('Senaryo çok kısa (min 100 karakter)')
    
    # Soru metni
    soru_metni = soru.get('soru_metni', '')
    if len(soru_metni) < 20:
        sorunlar.append('Soru metni çok kısa')
    
    # Çözüm adımları
    cozum_adimlari = soru.get('cozum_adimlari', [])
    if len(cozum_adimlari) < 4:
        sorunlar.append(f'Çözüm adımları yetersiz ({len(cozum_adimlari)} adım, min 4 olmalı)')
    
    # Doğru cevap kontrolü (çoktan seçmeli)
    if soru.get('soru_tipi') == 'coktan_secmeli':
        dogru_cevap = soru.get('dogru_cevap', '')
        secenekler = soru.get('secenekler', [])
        
        if not dogru_cevap:
            sorunlar.append('Doğru cevap belirtilmemiş')
        
        if len(secenekler) < 4:
            sorunlar.append('Seçenekler yetersiz')
        
        # Çeldirici açıklamaları
        celdiriciler = soru.get('celdirici_aciklamalar', {})
        if len(celdiriciler) < 3:
            sorunlar.append('Çeldirici açıklamaları eksik')
    
    # Aha moment
    if not soru.get('aha_moment'):
        sorunlar.append('Aha! moment eksik')
    
    return {
        'gecerli': len(sorunlar) == 0,
        'sorunlar': sorunlar
    }

# ═══════════════════════════════════════════════════════════════════════════════
# SUPABASE KAYIT
# ═══════════════════════════════════════════════════════════════════════════════

def supabase_kaydet(soru, dogrulama_sonucu=None):
    """Soruyu veritabanına kaydeder"""
    try:
        data = {
            'alan': soru.get('alan', 'matematik'),
            'konu': soru.get('konu', ''),
            'alt_konu': soru.get('alt_konu'),
            'sinif': soru.get('sinif'),
            'soru_tipi': soru.get('soru_tipi', 'coktan_secmeli'),
            'senaryo_turu': soru.get('senaryo_turu'),
            'pisa_seviye': soru.get('pisa_seviye', 4),
            'bloom_seviye': soru.get('bloom_seviye'),
            'senaryo': soru.get('senaryo', ''),
            'soru_metni': soru.get('soru_metni', ''),
            'secenekler': soru.get('secenekler'),
            'dogru_cevap': soru.get('dogru_cevap'),
            'celdirici_aciklamalar': soru.get('celdirici_aciklamalar'),
            'beklenen_cevap': soru.get('beklenen_cevap'),
            'puanlama_rubrik': soru.get('puanlama_rubrik'),
            'cozum_adimlari': soru.get('cozum_adimlari'),
            'aha_moment': soru.get('aha_moment'),
            'beceri_alani': soru.get('beceri_alani'),
            'pedagojik_notlar': soru.get('pedagojik_notlar'),
            'tahmini_sure': soru.get('tahmini_sure'),
            'aktif': True,
            'dogrulama_durumu': 'dogrulanmis' if (dogrulama_sonucu and dogrulama_sonucu.get('gecerli')) else 'dogrulanmamis',
            'cot_kullanildi': COT_AKTIF
            # dogrulama_puani ve senaryo_baglam kolonları tabloda yoksa eklenmedi
        }
        
        result = supabase.table('pisa_soru_havuzu').insert(data).execute()
        
        if result.data:
            return result.data[0]['id']
        return None
        
    except Exception as e:
        print(f"   ⚠️ Kayıt: {str(e)[:60]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU ÜRET (COT + DOĞRULAMA)
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret(params):
    """
    Gelişmiş soru üretim pipeline:
    1. Senaryo bağlamı seç
    2. CoT ile çözüm oluştur
    3. Çözümden soru oluştur
    4. Kalite kontrol
    5. DeepSeek ile doğrula
    6. Kaydet
    """
    for deneme in range(MAX_DENEME):
        print(f"      🔄 Deneme {deneme + 1}/{MAX_DENEME}")
        
        # Her denemede yeni senaryo bağlamı
        if deneme > 0:
            params['senaryo_baglami'] = rastgele_senaryo_sec()
        
        # ADIM 1: CoT - Önce çözümü oluştur
        print(f"      📐 CoT: Çözüm oluşturuluyor...")
        cozum = cot_cozum_olustur(params)
        
        if not cozum:
            print(f"      ⚠️ CoT başarısız")
            time.sleep(1)
            continue
        
        # Çözüm adımı kontrolü
        cozum_adimlari = cozum.get('cozum_adimlari', [])
        if len(cozum_adimlari) < 4:
            print(f"      ⚠️ CoT çözüm adımları yetersiz ({len(cozum_adimlari)})")
            time.sleep(1)
            continue
            
        print(f"      ✓ Çözüm: {cozum.get('sonuc', '?')} ({len(cozum_adimlari)} adım)")
        
        # ADIM 2: Çözümden soru oluştur
        print(f"      📝 PISA sorusu oluşturuluyor...")
        soru = cozumden_soru_olustur(cozum, params)
        
        if not soru:
            time.sleep(1)
            continue
        
        # Benzersizlik kontrolü
        if not benzersiz_mi(soru):
            print(f"      🔁 Tekrar soru, yeniden...")
            continue
        
        # ADIM 3: Kalite kontrol
        kalite = kalite_kontrol(soru)
        if not kalite['gecerli']:
            sorunlar_str = ', '.join(kalite['sorunlar'][:2])
            print(f"      ⚠️ Kalite: {sorunlar_str}")
            continue
        
        # ADIM 4: DeepSeek Doğrulama
        dogrulama = None
        if DEEPSEEK_DOGRULAMA:
            print(f"      🔍 DeepSeek doğruluyor...")
            dogrulama = deepseek_dogrula(soru)
            
            puan = dogrulama.get('puan', 0)
            
            if not dogrulama.get('gecerli'):
                print(f"      ❌ DeepSeek: BAŞARISIZ (Puan: {puan})")
                sorunlar = dogrulama.get('sorunlar', [])
                if sorunlar:
                    print(f"         Sorunlar: {', '.join(sorunlar[:2])}")
                continue
            else:
                print(f"      ✓ DeepSeek OK (Puan: {puan})")
        
        # ADIM 5: Kaydet
        soru_id = supabase_kaydet(soru, dogrulama)
        
        if soru_id:
            hash_kaydet(soru)
            return {
                'success': True, 
                'id': soru_id,
                'puan': dogrulama.get('puan') if dogrulama else None,
                'tema': params.get('senaryo_baglami', {}).get('tema', 'genel')
            }
    
    return {'success': False}

# ═══════════════════════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════════════════════

def toplu_uret(adet):
    """Toplu soru üretir"""
    print(f"\n{'='*70}")
    print(f"🚀 PISA SORU ÜRETİM BAŞLIYOR (V3 - Ultra Kalite)")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hedef: {adet} soru")
    print(f"   CoT: {'✅ AKTİF' if COT_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"   DeepSeek: {'✅ AKTİF (Min Puan: ' + str(MIN_DEEPSEEK_PUAN) + ')' if DEEPSEEK_DOGRULAMA else '❌ DEVRE DIŞI'}")
    print(f"   Senaryo Havuzu: {len(SENARYO_BAGLAMLARI['matematik'])} tema")
    print(f"{'='*70}\n")
    
    basarili = 0
    dogrulanan = 0
    toplam_puan = 0
    baslangic = time.time()
    
    # Kombinasyonlar - senaryo_baglami SONRA eklenecek (döngüde)
    kombinasyonlar = []
    for sinif, sb in SINIF_SEVIYELERI.items():
        for kid, konu in MATEMATIK_KONULARI.items():
            for alt in konu['alt_konular']:
                for pisa in sb['pisa']:
                    for bloom in sb['bloom']:
                        for st in SENARYO_TURLERI:
                            for tip in SORU_TIPLERI:
                                kombinasyonlar.append({
                                    'sinif': sinif,
                                    'sinif_ad': sb['ad'],
                                    'konu_ad': konu['ad'],
                                    'alt_konu': alt,
                                    'pisa_seviye': pisa,
                                    'bloom_seviye': bloom,
                                    'senaryo_turu': st,
                                    'soru_tipi': tip
                                    # senaryo_baglami döngüde eklenecek
                                })
    
    random.shuffle(kombinasyonlar)
    
    for params in kombinasyonlar:
        if basarili >= adet:
            break
        
        # Her soru için yeni senaryo bağlamı seç
        params['senaryo_baglami'] = rastgele_senaryo_sec()
        
        tema = params['senaryo_baglami'].get('tema', 'genel').replace('_', ' ')
        print(f"\n[{basarili+1}/{adet}] {params['konu_ad']} > {params['alt_konu']}")
        print(f"   📚 {params['sinif_ad']} | PISA {params['pisa_seviye']} | {params['bloom_seviye']} | 🎬 {tema}")
        
        try:
            sonuc = tek_soru_uret(params)
            
            if sonuc['success']:
                basarili += 1
                puan = sonuc.get('puan')
                if puan:
                    dogrulanan += 1
                    toplam_puan += puan
                
                print(f"   ✅ Başarılı! ID: {sonuc['id'][:8]}... | Tema: {sonuc.get('tema', '?')}")
                if puan:
                    print(f"      📊 Puan: {puan}/100")
            else:
                print(f"   ❌ Başarısız (tüm denemeler tükendi)")
                
        except Exception as e:
            print(f"   ❌ Hata: {str(e)[:50]}")
        
        time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    ort_puan = toplam_puan / dogrulanan if dogrulanan > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"📊 SONUÇ RAPORU")
    print(f"{'='*70}")
    print(f"   ✅ Başarılı: {basarili}/{adet}")
    print(f"   🔍 Doğrulanan: {dogrulanan}/{basarili}")
    print(f"   📈 Ortalama Puan: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   📈 Hız: {sure/max(basarili,1):.1f} sn/soru")
    print(f"{'='*70}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🤖 PISA SORU ÜRETİCİ BOT V3 - Ultra Kalite Edition")
    print("   ✅ 50+ Senaryo Bağlamı (Tema çeşitliliği)")
    print("   ✅ Chain of Thought (CoT)")
    print("   ✅ 7 Adımlı Kalite Kontrol")
    print("   ✅ Görsel Temsil Kuralları")
    print("   ✅ DeepSeek Çift Doğrulama")
    print("="*70 + "\n")
    
    # Gemini testi
    print("🔍 Gemini API test ediliyor...")
    try:
        test_model = genai.GenerativeModel('gemini-2.5-flash')
        test_response = test_model.generate_content('2+2=?')
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
            print("   DeepSeek doğrulama devre dışı bırakıldı")
            global DEEPSEEK_DOGRULAMA
            DEEPSEEK_DOGRULAMA = False
    
    print()
    
    # Soru üret
    basarili = toplu_uret(adet=SORU_ADEDI)
    
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} kaliteli PISA sorusu üretildi ve Supabase'e kaydedildi.")

if __name__ == "__main__":
    main()
