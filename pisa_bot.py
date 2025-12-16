"""
🤖 PISA SORU ÜRETİCİ BOT V2 - GitHub Actions
✅ CoT (Chain of Thought) - Önce çöz, sonra soru oluştur
✅ DeepSeek Doğrulama - Matematiksel kontrol
✅ Çift katmanlı kalite güvencesi
"""

import os
import json
import random
import time
import hashlib
from datetime import datetime
from openai import OpenAI

import google.generativeai as genai
from supabase import create_client

# ═══════════════════════════════════════════════════════════════
# YAPILANDIRMA
# ═══════════════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
SORU_ADEDI = int(os.environ.get('SORU_ADEDI', '50'))

# Ayarlar
DEEPSEEK_DOGRULAMA = bool(DEEPSEEK_API_KEY)  # DeepSeek varsa aktif
COT_AKTIF = True  # Chain of Thought aktif
BEKLEME = 2.5
MAX_DENEME = 3

# ═══════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# DeepSeek client (opsiyonel)
deepseek = None
if DEEPSEEK_API_KEY:
    deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url='https://api.deepseek.com/v1')
    print("✅ DeepSeek doğrulama AKTİF")
else:
    print("⚠️ DeepSeek API key yok, doğrulama DEVRE DIŞI")

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
# ADIM 1: COT - ÖNCE ÇÖZÜMÜ OLUŞTUR (Chain of Thought)
# ═══════════════════════════════════════════════════════════════

def cot_cozum_olustur(params):
    """
    Chain of Thought: Önce matematiksel çözümü oluştur
    Bu adımda sadece problem ve çözüm üretilir
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite')
        
        prompt = f'''Sen bir matematik öğretmenisin. Aşağıdaki parametrelere göre ÖNCE bir matematik problemi ve ÇÖZÜMÜNÜ oluştur.

KONU: {params['konu_ad']} - {params['alt_konu']}
SINIF: {params['sinif_ad']}
ZORLUK: PISA {params['pisa_seviye']} seviyesi
SENARYO: {params['senaryo_baglami']['tema']} - {params['senaryo_baglami']['aciklama']}

ÖNEMLİ KURALLAR:
1. ÖNCE problemi tanımla
2. SONRA adım adım çöz
3. Her adımda matematiksel işlemi yaz
4. Son cevabı net olarak belirt
5. Tüm sayısal değerler tutarlı olmalı

Aşağıdaki JSON formatında yanıt ver:
{{
    "problem_tanimi": "Problemin açık tanımı ve tüm veriler",
    "verilen_degerler": ["değer1", "değer2", ...],
    "istenen": "Ne bulunması gerekiyor",
    "cozum_adimlari": [
        "Adım 1: [işlem] = [sonuç]",
        "Adım 2: [işlem] = [sonuç]",
        "Adım 3: [işlem] = [sonuç]",
        "Adım 4: [işlem] = [sonuç]"
    ],
    "sonuc": "Kesin sayısal cevap",
    "sonuc_aciklama": "Cevabın ne anlama geldiği",
    "kontrol": "Cevabın doğruluğunu kontrol eden işlem"
}}

SADECE JSON döndür, başka bir şey yazma.'''

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
        
        cozum = json.loads(text.strip())
        return cozum
        
    except Exception as e:
        print(f"   ⚠️ CoT Hata: {str(e)[:40]}")
        return None

# ═══════════════════════════════════════════════════════════════
# ADIM 2: ÇÖZÜMDEN SORU OLUŞTUR
# ═══════════════════════════════════════════════════════════════

def cozumden_soru_olustur(cozum, params):
    """
    Doğrulanmış çözümden PISA formatında soru oluştur
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        if params['soru_tipi'] == 'coktan_secmeli':
            format_talimati = '''
"secenekler": ["A) ...", "B) ...", "C) ...", "D) ...", "E) ..."],
"dogru_cevap": "A/B/C/D/E harfi",
"celdirici_aciklamalar": {"A": "neden yanlış/doğru", "B": "...", "C": "...", "D": "...", "E": "..."}'''
        else:
            format_talimati = '''
"beklenen_cevap": "Detaylı beklenen cevap",
"puanlama_rubrik": {"tam_puan": "2 puan kriterleri", "kismi_puan": "1 puan kriterleri", "sifir_puan": "0 puan kriterleri"}'''

        prompt = f'''Aşağıdaki ÇÖZÜLMÜŞ problemden PISA formatında soru oluştur.

ÇÖZÜM BİLGİLERİ:
- Problem: {cozum.get('problem_tanimi', '')}
- Verilen Değerler: {cozum.get('verilen_degerler', [])}
- İstenen: {cozum.get('istenen', '')}
- Çözüm Adımları: {cozum.get('cozum_adimlari', [])}
- DOĞRU CEVAP: {cozum.get('sonuc', '')}
- Açıklama: {cozum.get('sonuc_aciklama', '')}

SENARYO TÜRÜ: {params['senaryo_turu']}
SORU TİPİ: {params['soru_tipi']}

GÖREV:
1. Bu çözümü kullanarak gerçekçi bir SENARYO yaz (min 80 kelime)
2. Senaryodan doğal bir SORU oluştur
3. Doğru cevap MUTLAKA "{cozum.get('sonuc', '')}" olmalı
4. Çeldiriciler mantıklı ama yanlış olmalı

JSON formatında döndür:
{{
    "senaryo": "Detaylı gerçekçi senaryo metni (min 80 kelime)",
    "soru_metni": "Soru metni",
    {format_talimati},
    "cozum_adimlari": {json.dumps(cozum.get('cozum_adimlari', []), ensure_ascii=False)},
    "aha_moment": "Bu sorudaki kilit fikir",
    "beceri_alani": "problem çözme / akıl yürütme / modelleme",
    "tahmini_sure": "5-8 dakika",
    "pedagojik_notlar": "Bu soru hangi becerileri ölçüyor"
}}

SADECE JSON döndür.'''

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
        
        # Meta bilgileri ekle
        soru['alan'] = 'matematik'
        soru['konu'] = params['konu_ad']
        soru['alt_konu'] = params['alt_konu']
        soru['sinif'] = params['sinif']
        soru['pisa_seviye'] = params['pisa_seviye']
        soru['bloom_seviye'] = params['bloom_seviye']
        soru['senaryo_turu'] = params['senaryo_turu']
        soru['soru_tipi'] = params['soru_tipi']
        soru['cot_cozum'] = cozum  # Orijinal çözümü sakla
        
        return soru
        
    except Exception as e:
        print(f"   ⚠️ Soru oluşturma: {str(e)[:40]}")
        return None

# ═══════════════════════════════════════════════════════════════
# ADIM 3: DEEPSEEK DOĞRULAMA
# ═══════════════════════════════════════════════════════════════

def deepseek_dogrula(soru):
    """
    DeepSeek ile matematiksel doğrulama
    Soruyu bağımsız olarak çözer ve cevabı karşılaştırır
    """
    if not deepseek:
        return {'gecerli': True, 'aciklama': 'DeepSeek devre dışı'}
    
    try:
        # Soru metnini ve senaryoyu al
        senaryo = soru.get('senaryo', '')
        soru_metni = soru.get('soru_metni', '')
        
        # Doğru cevabı al
        if soru.get('soru_tipi') == 'coktan_secmeli':
            beklenen = soru.get('dogru_cevap', '')
            secenekler = soru.get('secenekler', [])
            secenekler_text = '\n'.join(secenekler)
        else:
            beklenen = soru.get('beklenen_cevap', '')
            secenekler_text = ''

        prompt = f'''Bu matematik sorusunu ADIM ADIM çöz ve cevabını ver.

SENARYO:
{senaryo}

SORU:
{soru_metni}

{f"SEÇENEKLER:{chr(10)}{secenekler_text}" if secenekler_text else ""}

ADIM ADIM ÇÖZ:
1. Verilenleri listele
2. İsteneni belirle
3. Çözüm yolunu uygula
4. Sonucu hesapla

JSON formatında cevap ver:
{{
    "cozum_adimlari": ["adım 1", "adım 2", ...],
    "hesaplanan_sonuc": "sayısal sonuç",
    "secilen_secenek": "A/B/C/D/E (çoktan seçmeliyse)",
    "guven_seviyesi": "yüksek/orta/düşük",
    "notlar": "varsa ek açıklamalar"
}}'''

        response = deepseek.chat.completions.create(
            model='deepseek-chat',
            messages=[
                {'role': 'system', 'content': 'Sen bir matematik doğrulama uzmanısın. Soruları adım adım çöz ve sonucu JSON formatında ver.'},
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=2000,
            temperature=0.1  # Düşük temperature = daha tutarlı
        )
        
        text = response.choices[0].message.content.strip()
        
        # JSON temizle
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            for part in text.split('```'):
                if '{' in part and '}' in part:
                    text = part
                    break
        
        dogrulama = json.loads(text.strip())
        
        # Cevabı karşılaştır
        if soru.get('soru_tipi') == 'coktan_secmeli':
            ds_cevap = dogrulama.get('secilen_secenek', '').strip().upper()
            beklenen_harf = beklenen.strip().upper()
            eslesme = ds_cevap == beklenen_harf
        else:
            # Açık uçlu için sonuç karşılaştırma (daha esnek)
            ds_sonuc = str(dogrulama.get('hesaplanan_sonuc', '')).strip()
            # Sayısal değerleri karşılaştır
            try:
                ds_num = float(''.join(c for c in ds_sonuc if c.isdigit() or c in '.-'))
                bek_num = float(''.join(c for c in beklenen if c.isdigit() or c in '.-'))
                eslesme = abs(ds_num - bek_num) < 0.01
            except:
                eslesme = ds_sonuc in beklenen or beklenen in ds_sonuc
        
        guven = dogrulama.get('guven_seviyesi', 'orta')
        
        return {
            'gecerli': eslesme,
            'deepseek_cevap': dogrulama.get('secilen_secenek') or dogrulama.get('hesaplanan_sonuc'),
            'beklenen_cevap': beklenen,
            'guven': guven,
            'cozum_adimlari': dogrulama.get('cozum_adimlari', []),
            'aciklama': 'Cevaplar eşleşiyor' if eslesme else 'CEVAPLAR EŞLEŞMİYOR!'
        }
        
    except Exception as e:
        print(f"   ⚠️ DeepSeek: {str(e)[:40]}")
        return {'gecerli': True, 'aciklama': f'DeepSeek hatası: {str(e)[:30]}'}

# ═══════════════════════════════════════════════════════════════
# SUPABASE KAYIT
# ═══════════════════════════════════════════════════════════════

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
            # Yeni alanlar
            'dogrulama_durumu': 'dogrulanmis' if (dogrulama_sonucu and dogrulama_sonucu.get('gecerli')) else 'dogrulanmamis',
            'cot_kullanildi': COT_AKTIF
        }
        
        result = supabase.table('pisa_soru_havuzu').insert(data).execute()
        
        if result.data:
            return result.data[0]['id']
        return None
        
    except Exception as e:
        print(f"   ⚠️ Kayıt: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════
# TEK SORU ÜRET (COT + DOĞRULAMA)
# ═══════════════════════════════════════════════════════════════

def tek_soru_uret(params):
    """
    Gelişmiş soru üretim pipeline:
    1. CoT ile çözüm oluştur
    2. Çözümden soru oluştur
    3. DeepSeek ile doğrula
    4. Kaydet
    """
    for deneme in range(MAX_DENEME):
        print(f"      🔄 Deneme {deneme + 1}/{MAX_DENEME}")
        
        # ADIM 1: CoT - Önce çözümü oluştur
        if COT_AKTIF:
            print(f"      📐 CoT: Çözüm oluşturuluyor...")
            cozum = cot_cozum_olustur(params)
            
            if not cozum:
                print(f"      ⚠️ CoT başarısız")
                time.sleep(1)
                continue
            
            print(f"      ✓ Çözüm: {cozum.get('sonuc', '?')}")
            
            # ADIM 2: Çözümden soru oluştur
            print(f"      📝 Soru oluşturuluyor...")
            soru = cozumden_soru_olustur(cozum, params)
        else:
            # CoT devre dışıysa eski yöntem
            soru = gemini_soru_uret_eski(params)
        
        if not soru:
            time.sleep(1)
            continue
        
        # Benzersizlik kontrolü
        if not benzersiz_mi(soru):
            print(f"      🔁 Tekrar soru, yeniden...")
            continue
        
        # Temel kontroller
        if len(soru.get('senaryo', '')) < 50:
            print(f"      ⚠️ Senaryo çok kısa")
            continue
        
        if len(soru.get('cozum_adimlari', [])) < 3:
            print(f"      ⚠️ Çözüm adımları yetersiz")
            continue
        
        # ADIM 3: DeepSeek Doğrulama
        dogrulama = None
        if DEEPSEEK_DOGRULAMA:
            print(f"      🔍 DeepSeek doğruluyor...")
            dogrulama = deepseek_dogrula(soru)
            
            if not dogrulama.get('gecerli'):
                print(f"      ❌ Doğrulama BAŞARISIZ: {dogrulama.get('aciklama')}")
                print(f"         Beklenen: {dogrulama.get('beklenen_cevap')}")
                print(f"         DeepSeek: {dogrulama.get('deepseek_cevap')}")
                continue
            else:
                print(f"      ✓ Doğrulama OK (Güven: {dogrulama.get('guven', '?')})")
        
        # ADIM 4: Kaydet
        soru_id = supabase_kaydet(soru, dogrulama)
        
        if soru_id:
            hash_kaydet(soru)
            return {
                'success': True, 
                'id': soru_id,
                'dogrulama': dogrulama
            }
    
    return {'success': False}

# ═══════════════════════════════════════════════════════════════
# ESKİ YÖNTEM (CoT olmadan) - Fallback
# ═══════════════════════════════════════════════════════════════

def gemini_soru_uret_eski(params):
    """Eski tek adımlı yöntem - fallback olarak"""
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite')
        
        if params['soru_tipi'] == 'coktan_secmeli':
            json_format = '''{"senaryo": "...", "soru_metni": "...", "secenekler": ["A) ...", "B) ...", "C) ...", "D) ...", "E) ..."], "dogru_cevap": "A", "celdirici_aciklamalar": {...}, "cozum_adimlari": [...], "aha_moment": "...", "beceri_alani": "...", "tahmini_sure": "...", "pedagojik_notlar": "..."}'''
        else:
            json_format = '''{"senaryo": "...", "soru_metni": "...", "beklenen_cevap": "...", "puanlama_rubrik": {...}, "cozum_adimlari": [...], "aha_moment": "...", "beceri_alani": "...", "tahmini_sure": "...", "pedagojik_notlar": "..."}'''

        prompt = f'''PISA matematik sorusu üret.
KONU: {params['konu_ad']} - {params['alt_konu']}
SINIF: {params['sinif_ad']} | PISA: {params['pisa_seviye']}
SENARYO: {params['senaryo_baglami']['tema']}
TİP: {params['soru_tipi']}

JSON: {json_format}'''

        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        
        soru = json.loads(text.strip())
        soru['alan'] = 'matematik'
        soru['konu'] = params['konu_ad']
        soru['alt_konu'] = params['alt_konu']
        soru['sinif'] = params['sinif']
        soru['pisa_seviye'] = params['pisa_seviye']
        soru['bloom_seviye'] = params['bloom_seviye']
        soru['senaryo_turu'] = params['senaryo_turu']
        soru['soru_tipi'] = params['soru_tipi']
        
        return soru
    except:
        return None

# ═══════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════

def toplu_uret(adet):
    """Toplu soru üretir"""
    print(f"\n{'='*60}")
    print(f"🚀 PISA SORU ÜRETİM BAŞLIYOR (V2)")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hedef: {adet} soru")
    print(f"   CoT: {'✅ AKTİF' if COT_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"   DeepSeek: {'✅ AKTİF' if DEEPSEEK_DOGRULAMA else '❌ DEVRE DIŞI'}")
    print(f"{'='*60}\n")
    
    basarili = 0
    dogrulanan = 0
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
        
        print(f"\n[{basarili+1}/{adet}] {params['konu_ad']} > {params['alt_konu']} ({params['sinif_ad']})")
        
        try:
            sonuc = tek_soru_uret(params)
            
            if sonuc['success']:
                basarili += 1
                if sonuc.get('dogrulama', {}).get('gecerli'):
                    dogrulanan += 1
                print(f"   ✅ Başarılı! ID: {sonuc['id'][:8]}...")
            else:
                print(f"   ❌ Başarısız")
                
        except Exception as e:
            print(f"   ❌ Hata: {str(e)[:40]}")
        
        time.sleep(BEKLEME)
    
    sure = time.time() - baslangic
    
    print(f"\n{'='*60}")
    print(f"📊 SONUÇ RAPORU")
    print(f"{'='*60}")
    print(f"   ✅ Başarılı: {basarili}/{adet}")
    print(f"   🔍 Doğrulanan: {dogrulanan}/{basarili}")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   📈 Ortalama: {sure/max(basarili,1):.1f} sn/soru")
    print(f"{'='*60}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*60)
    print("🤖 PISA SORU ÜRETİCİ BOT V2")
    print("   ✅ Chain of Thought (CoT)")
    print("   ✅ DeepSeek Doğrulama")
    print("="*60 + "\n")
    
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
    print(f"   {basarili} soru üretildi ve Supabase'e kaydedildi.")

if __name__ == "__main__":
    main()
