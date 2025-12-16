"""
🤖 PISA SORU ÜRETİCİ BOT - GitHub Actions Version
Otomatik PISA tarzı matematik sorusu üretir ve Supabase'e kaydeder
"""

import os
import json
import random
import time
import hashlib
from datetime import datetime

import google.generativeai as genai
from supabase import create_client

# ═══════════════════════════════════════════════════════════════
# YAPILANDIRMA
# ═══════════════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SORU_ADEDI = int(os.environ.get('SORU_ADEDI', '50'))

# Sabitler
BEKLEME = 2.0
MAX_DENEME = 2

# ═══════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    print(f"   SUPABASE_URL: {'✅' if SUPABASE_URL else '❌'}")
    print(f"   SUPABASE_KEY: {'✅' if SUPABASE_KEY else '❌'}")
    print(f"   GEMINI_API_KEY: {'✅' if GEMINI_API_KEY else '❌'}")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

print("✅ API bağlantıları hazır!")

# ═══════════════════════════════════════════════════════════════
# VERİ YAPILARI
# ═══════════════════════════════════════════════════════════════

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
    '8': {'ad': '8. Sınıf', 'pisa': [3, 4, 5], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    '9': {'ad': '9. Sınıf', 'pisa': [3, 4, 5], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    '10': {'ad': '10. Sınıf', 'pisa': [4, 5], 'bloom': ['analiz', 'değerlendirme', 'yaratma']},
    '11': {'ad': '11. Sınıf', 'pisa': [4, 5, 6], 'bloom': ['değerlendirme', 'yaratma']},
    '12': {'ad': '12. Sınıf', 'pisa': [5, 6], 'bloom': ['değerlendirme', 'yaratma']}
}

SENARYO_TURLERI = ['diyalog', 'uygulama', 'tablo', 'grafik', 'infografik', 'günlük', 'haber']
SORU_TIPLERI = ['coktan_secmeli', 'acik_uclu']

# 100 Senaryo Bağlamı
SENARYO_BAGLAMLARI = [
    {'tema': 'market', 'aciklama': 'Süpermarket alışverişi'},
    {'tema': 'online', 'aciklama': 'E-ticaret sitesi'},
    {'tema': 'pazar', 'aciklama': 'Semt pazarı'},
    {'tema': 'kredi', 'aciklama': 'Taksitli alışveriş'},
    {'tema': 'doviz', 'aciklama': 'Döviz kuru'},
    {'tema': 'banka', 'aciklama': 'Vadeli mevduat'},
    {'tema': 'harclik', 'aciklama': 'Aylık harçlık'},
    {'tema': 'koop', 'aciklama': 'Okul kooperatifi'},
    {'tema': 'butce', 'aciklama': 'Aile bütçesi'},
    {'tema': 'yatirim', 'aciklama': 'Yatırım getirisi'},
    {'tema': 'vergi', 'aciklama': 'KDV hesabı'},
    {'tema': 'maas', 'aciklama': 'Net maaş'},
    {'tema': 'kira', 'aciklama': 'Ev kirası'},
    {'tema': 'sigorta', 'aciklama': 'Sigorta primi'},
    {'tema': 'tasarruf', 'aciklama': 'Birikim hedefi'},
    {'tema': 'tarif', 'aciklama': 'Yemek tarifi'},
    {'tema': 'pizza', 'aciklama': 'Pizza siparişi'},
    {'tema': 'kurabiye', 'aciklama': 'Kurabiye tarifi'},
    {'tema': 'smoothie', 'aciklama': 'Meyve karışımı'},
    {'tema': 'kafe', 'aciklama': 'Kafeterya menü'},
    {'tema': 'restoran', 'aciklama': 'Restoran hesabı'},
    {'tema': 'pasta', 'aciklama': 'Doğum günü pastası'},
    {'tema': 'catering', 'aciklama': 'Yemek planlama'},
    {'tema': 'kalori', 'aciklama': 'Besin değeri'},
    {'tema': 'kahvalti', 'aciklama': 'Kahvaltı hazırlık'},
    {'tema': 'piknik', 'aciklama': 'Piknik planı'},
    {'tema': 'kantin', 'aciklama': 'Okul kantini'},
    {'tema': 'diyet', 'aciklama': 'Kalori takibi'},
    {'tema': 'su', 'aciklama': 'Su tüketimi'},
    {'tema': 'liste', 'aciklama': 'Alışveriş listesi'},
    {'tema': 'seyahat', 'aciklama': 'Tatil planı'},
    {'tema': 'servis', 'aciklama': 'Okul servisi'},
    {'tema': 'bisiklet', 'aciklama': 'Bisiklet turu'},
    {'tema': 'metro', 'aciklama': 'Metro aktarma'},
    {'tema': 'otobus', 'aciklama': 'Otobüs saatleri'},
    {'tema': 'taksi', 'aciklama': 'Taksi ücreti'},
    {'tema': 'ucak', 'aciklama': 'Uçuş süresi'},
    {'tema': 'tren', 'aciklama': 'Tren yolculuğu'},
    {'tema': 'benzin', 'aciklama': 'Yakıt tüketimi'},
    {'tema': 'otopark', 'aciklama': 'Otopark ücreti'},
    {'tema': 'navi', 'aciklama': 'En kısa yol'},
    {'tema': 'kargo', 'aciklama': 'Teslimat süresi'},
    {'tema': 'kurye', 'aciklama': 'Kurye rotası'},
    {'tema': 'feribot', 'aciklama': 'Gemi seferi'},
    {'tema': 'trafik', 'aciklama': 'Hız hesabı'},
    {'tema': 'basket', 'aciklama': 'Maç istatistiği'},
    {'tema': 'futbol', 'aciklama': 'Lig puan durumu'},
    {'tema': 'fitness', 'aciklama': 'Egzersiz programı'},
    {'tema': 'satranc', 'aciklama': 'Turnuva puanlama'},
    {'tema': 'espor', 'aciklama': 'Oyun ligi'},
    {'tema': 'oyun', 'aciklama': 'Oyun skoru'},
    {'tema': 'maraton', 'aciklama': 'Koşu temposu'},
    {'tema': 'yuzme', 'aciklama': 'Yüzme yarışı'},
    {'tema': 'voleybol', 'aciklama': 'Set sayısı'},
    {'tema': 'atletizm', 'aciklama': 'Derece sıralama'},
    {'tema': 'tenis', 'aciklama': 'Turnuva eşleşmesi'},
    {'tema': 'bowling', 'aciklama': 'Skor hesabı'},
    {'tema': 'dart', 'aciklama': 'Puan sistemi'},
    {'tema': 'pingpong', 'aciklama': 'Turnuva sistemi'},
    {'tema': 'yaris', 'aciklama': 'Etap hesabı'},
    {'tema': 'video', 'aciklama': 'Video süresi'},
    {'tema': '3dprint', 'aciklama': '3D baskı'},
    {'tema': 'podcast', 'aciklama': 'Dinlenme sayısı'},
    {'tema': 'sosyal', 'aciklama': 'Takipçi analizi'},
    {'tema': 'app', 'aciklama': 'İndirme sayısı'},
    {'tema': 'internet', 'aciklama': 'İndirme süresi'},
    {'tema': 'bulut', 'aciklama': 'Depolama'},
    {'tema': 'pil', 'aciklama': 'Pil ömrü'},
    {'tema': 'veri', 'aciklama': 'Veri kullanımı'},
    {'tema': 'sunucu', 'aciklama': 'Sunucu kapasitesi'},
    {'tema': 'yazilim', 'aciklama': 'Proje süresi'},
    {'tema': 'pixel', 'aciklama': 'Piksel oranı'},
    {'tema': 'kod', 'aciklama': 'Yarışma puanı'},
    {'tema': 'saat', 'aciklama': 'Adım sayacı'},
    {'tema': 'robot', 'aciklama': 'Robot hareketi'},
    {'tema': 'sinav', 'aciklama': 'Not hesaplama'},
    {'tema': 'kitap', 'aciklama': 'Kitap ödünç'},
    {'tema': 'ders', 'aciklama': 'Kredi hesabı'},
    {'tema': 'devam', 'aciklama': 'Devamsızlık etkisi'},
    {'tema': 'proje', 'aciklama': 'Grup ödevi'},
    {'tema': 'tercih', 'aciklama': 'Okul tercihi'},
    {'tema': 'burs', 'aciklama': 'Burs kriteri'},
    {'tema': 'program', 'aciklama': 'Ders programı'},
    {'tema': 'oy', 'aciklama': 'Sınıf başkanı'},
    {'tema': 'gezi', 'aciklama': 'Okul gezisi'},
    {'tema': 'donusum', 'aciklama': 'Geri dönüşüm'},
    {'tema': 'agac', 'aciklama': 'Ağaç dikimi'},
    {'tema': 'bahce', 'aciklama': 'Bitki dikimi'},
    {'tema': 'enerji', 'aciklama': 'Enerji tasarrufu'},
    {'tema': 'karbon', 'aciklama': 'Karbon ayak izi'},
    {'tema': 'yagmur', 'aciklama': 'Yağmur suyu'},
    {'tema': 'gunes', 'aciklama': 'Güneş paneli'},
    {'tema': 'hava', 'aciklama': 'Hava kalitesi'},
    {'tema': 'plastik', 'aciklama': 'Plastik azaltma'},
    {'tema': 'sutasarr', 'aciklama': 'Su tasarrufu'},
    {'tema': 'muzik', 'aciklama': 'Nota değerleri'},
    {'tema': 'resim', 'aciklama': 'Çerçeve boyutu'},
    {'tema': 'kart', 'aciklama': 'Koleksiyon kartı'},
    {'tema': 'lego', 'aciklama': 'LEGO projesi'},
    {'tema': 'sinema', 'aciklama': 'Bilet fiyatı'}
]

print(f"✅ {len(MATEMATIK_KONULARI)} konu, {len(SENARYO_BAGLAMLARI)} senaryo yüklendi")

# ═══════════════════════════════════════════════════════════════
# TEKRAR ÖNLEYİCİ
# ═══════════════════════════════════════════════════════════════

kullanilan_hashler = set()

def hash_olustur(soru):
    icerik = f"{soru.get('soru_metni', '')}|{soru.get('dogru_cevap', '')}"
    return hashlib.md5(icerik.encode()).hexdigest()

def benzersiz_mi(soru):
    return hash_olustur(soru) not in kullanilan_hashler

def hash_kaydet(soru):
    kullanilan_hashler.add(hash_olustur(soru))

# ═══════════════════════════════════════════════════════════════
# GEMINI SORU ÜRETİCİ
# ═══════════════════════════════════════════════════════════════

def gemini_soru_uret(params):
    """Gemini API ile PISA tarzı soru üretir"""
    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        if params['soru_tipi'] == 'coktan_secmeli':
            json_format = '''{"senaryo": "Detaylı senaryo (min 80 kelime)", "soru_metni": "Soru", "secenekler": ["A) ...", "B) ...", "C) ...", "D) ...", "E) ..."], "dogru_cevap": "A", "celdirici_aciklamalar": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}, "cozum_adimlari": ["Adım 1", "Adım 2", "Adım 3", "Adım 4"], "aha_moment": "Kilit fikir", "beceri_alani": "problem çözme", "tahmini_sure": "5-8 dk", "pedagojik_notlar": "Ölçülen beceriler"}'''
        else:
            json_format = '''{"senaryo": "Detaylı senaryo (min 80 kelime)", "soru_metni": "Soru", "beklenen_cevap": "Detaylı cevap", "puanlama_rubrik": {"tam_puan": "2p", "kismi_puan": "1p", "sifir_puan": "0p"}, "cozum_adimlari": ["Adım 1", "Adım 2", "Adım 3", "Adım 4"], "aha_moment": "Kilit fikir", "beceri_alani": "akıl yürütme", "tahmini_sure": "8-12 dk", "pedagojik_notlar": "Ölçülen beceriler"}'''

        prompt = f'''PISA standartlarında matematik sorusu üret.

KONU: {params['konu_ad']} - {params['alt_konu']}
SINIF: {params['sinif_ad']}
PISA: {params['pisa_seviye']} | BLOOM: {params['bloom_seviye']}
SENARYO: {params['senaryo_baglami']['tema']} - {params['senaryo_baglami']['aciklama']}
TİP: {params['soru_tipi']}

KURALLAR:
1. Senaryo gerçek hayattan, min 80 kelime
2. Tüm veriler açık yazılmalı
3. Min 4 çözüm adımı
4. Matematiksel doğru olmalı

SADECE JSON döndür:
{json_format}'''

        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # JSON temizle
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            for part in text.split('```'):
                if '{' in part and '}' in part:
                    text = part
                    break
        if text.startswith('json'):
            text = text[4:]
        
        soru = json.loads(text.strip())
        
        # Meta ekle
        soru['alan'] = 'matematik'
        soru['konu'] = params['konu_ad']
        soru['alt_konu'] = params['alt_konu']
        soru['sinif'] = params['sinif']
        soru['pisa_seviye'] = params['pisa_seviye']
        soru['bloom_seviye'] = params['bloom_seviye']
        soru['senaryo_turu'] = params['senaryo_turu']
        soru['soru_tipi'] = params['soru_tipi']
        
        return soru
        
    except Exception as e:
        print(f"   ⚠️ Gemini: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════
# SUPABASE KAYIT
# ═══════════════════════════════════════════════════════════════

def supabase_kaydet(soru):
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
            'aktif': True
        }
        
        result = supabase.table('pisa_soru_havuzu').insert(data).execute()
        
        if result.data:
            return result.data[0]['id']
        return None
        
    except Exception as e:
        print(f"   ⚠️ Kayıt: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════
# TEK SORU ÜRET
# ═══════════════════════════════════════════════════════════════

def tek_soru_uret(params):
    """Tek soru üretir ve kaydeder"""
    for _ in range(MAX_DENEME):
        soru = gemini_soru_uret(params)
        
        if not soru:
            time.sleep(1)
            continue
        
        if not benzersiz_mi(soru):
            continue
        
        if len(soru.get('senaryo', '')) < 50:
            continue
        
        if len(soru.get('cozum_adimlari', [])) < 3:
            continue
        
        soru_id = supabase_kaydet(soru)
        
        if soru_id:
            hash_kaydet(soru)
            return {'success': True, 'id': soru_id}
    
    return {'success': False}

# ═══════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════

def toplu_uret(adet):
    """Toplu soru üretir"""
    print(f"\n{'='*60}")
    print(f"🚀 PISA SORU ÜRETİM BAŞLIYOR")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hedef: {adet} soru")
    print(f"{'='*60}\n")
    
    basarili = 0
    baslangic = time.time()
    
    # Kombinasyonlar
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
                                    'senaryo_baglami': random.choice(SENARYO_BAGLAMLARI),
                                    'soru_tipi': tip
                                })
    
    random.shuffle(kombinasyonlar)
    
    for params in kombinasyonlar:
        if basarili >= adet:
            break
        
        print(f"[{basarili+1}/{adet}] {params['konu_ad']} > {params['alt_konu']}")
        
        try:
            sonuc = tek_soru_uret(params)
            
            if sonuc['success']:
                basarili += 1
                print(f"   ✅ {sonuc['id'][:8]}...")
            else:
                print(f"   ❌")
                
        except Exception as e:
            print(f"   ❌ {str(e)[:30]}")
        
        time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    
    print(f"\n{'='*60}")
    print(f"📊 SONUÇ")
    print(f"   ✅ Başarılı: {basarili}/{adet}")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   📈 Benzersiz: {len(kullanilan_hashler)}")
    print(f"{'='*60}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*60)
    print("🤖 PISA SORU ÜRETİCİ BOT - GitHub Actions")
    print("="*60 + "\n")
    
    # API testi
    print("🔍 Gemini API test ediliyor...")
    try:
        test_model = genai.GenerativeModel('gemini-2.0-flash-lite')
        test_response = test_model.generate_content('2+2=?')
        print(f"✅ Gemini çalışıyor: {test_response.text.strip()}")
    except Exception as e:
        print(f"❌ Gemini HATASI: {e}")
        exit(1)
    
    # Soru üret
    basarili = toplu_uret(adet=SORU_ADEDI)
    
    # Özet
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} soru üretildi ve Supabase'e kaydedildi.")

if __name__ == "__main__":
    main()
