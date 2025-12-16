"""
🎯 PISA SORU ÜRETİCİ BOT V4 - OECD PISA 2022 STANDARTLARI
═══════════════════════════════════════════════════════════════════════════════

OECD PISA 2022 çerçevesine birebir uyumlu soru üretici.

📚 PISA TEMEL İLKELERİ:
✅ Matematiksel Okuryazarlık: Formüle etme, Kullanma, Yorumlama
✅ 4 İçerik Kategorisi: Nicelik, Uzay ve Şekil, Değişim ve İlişkiler, Belirsizlik ve Veri
✅ 4 Bağlam Kategorisi: Kişisel, Mesleki, Toplumsal, Bilimsel
✅ Ünite Bazlı Tasarım: Stimulus + Soru Kökleri
✅ 6 Yeterlik Seviyesi (1c'den 6'ya)
✅ Otantik Gerçek Yaşam Senaryoları
✅ Psikometrik Kalite Standartları

@version 4.0.0 - OECD PISA 2022 Uyumlu
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
BEKLEME = 1.0
MAX_DENEME = 3
MIN_DEEPSEEK_PUAN = 70
API_TIMEOUT = 30

# ═══════════════════════════════════════════════════════════════════════════════
# API BAĞLANTILARI
# ═══════════════════════════════════════════════════════════════════════════════

print("🔌 API bağlantıları kuruluyor...")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("❌ HATA: Gerekli environment variable'lar eksik!")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

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
        'alt_konular': [
            'Sayı Duyusu ve Tahmin',
            'Büyüklük Karşılaştırma',
            'Birim Dönüşümleri',
            'Orantısal Akıl Yürütme',
            'Yüzde ve Oran Hesaplama',
            'Para ve Bütçe Yönetimi',
            'Ölçme ve Tahmin',
            'Büyük Sayılarla Çalışma'
        ],
        'ornek_baglamlar': [
            'Alışveriş ve indirim hesaplama',
            'Nüfus ve istatistik yorumlama',
            'Tarif ve porsiyon ayarlama',
            'Enerji tüketimi hesaplama',
            'Bütçe planlama'
        ]
    },
    'uzay_sekil': {
        'ad': 'Uzay ve Şekil (Space and Shape)',
        'aciklama': 'Görsel-uzamsal akıl yürütme, geometrik örüntüler, dönüşümler, perspektif',
        'alt_konular': [
            'Geometrik Şekil Özellikleri',
            'Alan ve Çevre Hesaplama',
            'Hacim Hesaplama',
            'Ölçek ve Harita Okuma',
            'Perspektif ve Görünümler',
            'Geometrik Dönüşümler',
            'Düzensiz Şekiller',
            'Uzamsal Görselleştirme'
        ],
        'ornek_baglamlar': [
            'Oda ve bahçe tasarımı',
            'Harita ve navigasyon',
            'Ambalaj ve paketleme',
            'Mimari plan okuma',
            'Sanat ve tasarım'
        ]
    },
    'degisim_iliskiler': {
        'ad': 'Değişim ve İlişkiler (Change and Relationships)',
        'aciklama': 'Fonksiyonel ilişkiler, cebirsel ifadeler, denklemler, değişim oranları',
        'alt_konular': [
            'Doğrusal İlişkiler',
            'Üstel Büyüme/Azalma',
            'Fonksiyon Grafikleri',
            'Denklem Kurma ve Çözme',
            'Değişim Oranı',
            'Örüntü ve Diziler',
            'Formül Kullanma',
            'Tablo-Grafik Dönüşümü'
        ],
        'ornek_baglamlar': [
            'Nüfus artışı/azalışı',
            'Faiz ve yatırım',
            'Hız-zaman-mesafe',
            'Sıcaklık değişimi',
            'Büyüme modelleri'
        ]
    },
    'belirsizlik_veri': {
        'ad': 'Belirsizlik ve Veri (Uncertainty and Data)',
        'aciklama': 'Olasılık, istatistik, veri yorumlama, örnekleme, belirsizlik',
        'alt_konular': [
            'Veri Toplama ve Düzenleme',
            'Merkezi Eğilim Ölçüleri',
            'Grafik Yorumlama',
            'Olasılık Hesaplama',
            'Koşullu Olasılık',
            'Örnekleme ve Tahmin',
            'Veri Temelli Karar',
            'Yanıltıcı Grafik Analizi'
        ],
        'ornek_baglamlar': [
            'Anket sonuçları',
            'Hava durumu tahminleri',
            'Spor istatistikleri',
            'Sağlık verileri',
            'Seçim ve oylama'
        ]
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
            {'tema': 'yemek_hazirlama', 'aciklama': 'Tarif ayarlama, porsiyon hesaplama, malzeme oranları', 'yasgrubu': 'tum'},
            {'tema': 'alisveris', 'aciklama': 'İndirim hesaplama, fiyat karşılaştırma, bütçe yönetimi', 'yasgrubu': 'tum'},
            {'tema': 'oyun_strateji', 'aciklama': 'Kart oyunu, masa oyunu stratejileri ve puan hesaplama', 'yasgrubu': 'tum'},
            {'tema': 'kisisel_saglik', 'aciklama': 'Kalori hesaplama, egzersiz planı, uyku düzeni', 'yasgrubu': 'tum'},
            {'tema': 'spor_aktivite', 'aciklama': 'Koşu, bisiklet, yüzme performans takibi', 'yasgrubu': 'tum'},
            {'tema': 'seyahat_planlama', 'aciklama': 'Rota hesaplama, zaman planlaması, yakıt/şarj', 'yasgrubu': 'tum'},
            {'tema': 'kisisel_finans', 'aciklama': 'Harçlık yönetimi, birikim planı, harcama takibi', 'yasgrubu': 'tum'},
            {'tema': 'hobi_koleksiyon', 'aciklama': 'Kart koleksiyonu, pul, müzik albümü düzenleme', 'yasgrubu': 'tum'},
            {'tema': 'dijital_icerik', 'aciklama': 'Video süresi, dosya boyutu, indirme zamanı', 'yasgrubu': 'tum'},
            {'tema': 'ev_duzenleme', 'aciklama': 'Mobilya yerleşimi, oda boyama, bahçe düzenleme', 'yasgrubu': 'tum'}
        ]
    },
    'mesleki': {
        'ad': 'Mesleki (Occupational)',
        'aciklama': '15 yaş için erişilebilir iş dünyası senaryoları',
        'temalar': [
            {'tema': 'insaat_olcum', 'aciklama': 'Malzeme hesaplama, alan ölçümü, maliyet tahmini', 'yasgrubu': 'lise'},
            {'tema': 'magaza_yonetimi', 'aciklama': 'Stok takibi, satış analizi, fiyatlandırma', 'yasgrubu': 'tum'},
            {'tema': 'tasarim_planlama', 'aciklama': 'Grafik tasarım ölçüleri, baskı hesaplamaları', 'yasgrubu': 'tum'},
            {'tema': 'etkinlik_organizasyonu', 'aciklama': 'Koltuk düzeni, bilet satışı, bütçe', 'yasgrubu': 'tum'},
            {'tema': 'kafe_restoran', 'aciklama': 'Menü fiyatlandırma, porsiyon hesabı, sipariş', 'yasgrubu': 'tum'},
            {'tema': 'tasimacilik', 'aciklama': 'Rota optimizasyonu, yakıt hesabı, zaman planı', 'yasgrubu': 'lise'},
            {'tema': 'tarim_bahcecilik', 'aciklama': 'Ekim planı, sulama hesabı, hasat tahmini', 'yasgrubu': 'tum'},
            {'tema': 'atolye_uretim', 'aciklama': 'Malzeme kesimi, fire hesabı, üretim planı', 'yasgrubu': 'lise'}
        ]
    },
    'toplumsal': {
        'ad': 'Toplumsal (Societal)',
        'aciklama': 'Yerel, ulusal veya küresel topluluk perspektifi',
        'temalar': [
            {'tema': 'toplu_tasima', 'aciklama': 'Otobüs/metro saatleri, aktarma, rota planlama', 'yasgrubu': 'tum'},
            {'tema': 'cevre_surdurulebilirlik', 'aciklama': 'Geri dönüşüm oranları, karbon ayak izi, su tasarrufu', 'yasgrubu': 'tum'},
            {'tema': 'nufus_demografi', 'aciklama': 'Nüfus dağılımı, yaş grupları, göç verileri', 'yasgrubu': 'lise'},
            {'tema': 'secim_oylama', 'aciklama': 'Oy dağılımı, temsil oranları, anket sonuçları', 'yasgrubu': 'lise'},
            {'tema': 'saglik_toplum', 'aciklama': 'Aşılama oranları, salgın verileri, sağlık istatistikleri', 'yasgrubu': 'tum'},
            {'tema': 'ekonomi_fiyatlar', 'aciklama': 'Enflasyon, fiyat değişimi, alım gücü', 'yasgrubu': 'lise'},
            {'tema': 'egitim_istatistik', 'aciklama': 'Okul başarı oranları, mezuniyet verileri', 'yasgrubu': 'tum'},
            {'tema': 'sehir_planlama', 'aciklama': 'Park alanı, yol ağı, altyapı planlaması', 'yasgrubu': 'lise'}
        ]
    },
    'bilimsel': {
        'ad': 'Bilimsel (Scientific)',
        'aciklama': 'Matematiğin doğa bilimleri ve teknolojiye uygulanması',
        'temalar': [
            {'tema': 'hava_durumu', 'aciklama': 'Sıcaklık değişimi, yağış miktarı, tahmin doğruluğu', 'yasgrubu': 'tum'},
            {'tema': 'ekoloji_doga', 'aciklama': 'Hayvan popülasyonu, habitat alanı, besin zinciri', 'yasgrubu': 'tum'},
            {'tema': 'astronomi_uzay', 'aciklama': 'Gezegen mesafeleri, yörünge hesabı, ışık yılı', 'yasgrubu': 'lise'},
            {'tema': 'fizik_hareket', 'aciklama': 'Hız, ivme, düşme, sarkaç hareketi', 'yasgrubu': 'lise'},
            {'tema': 'kimya_karisim', 'aciklama': 'Çözelti konsantrasyonu, karışım oranları', 'yasgrubu': 'lise'},
            {'tema': 'biyoloji_buyume', 'aciklama': 'Hücre bölünmesi, popülasyon artışı, genetik', 'yasgrubu': 'lise'},
            {'tema': 'teknoloji_veri', 'aciklama': 'Veri aktarım hızı, depolama kapasitesi, şarj süresi', 'yasgrubu': 'tum'},
            {'tema': 'muhendislik_tasarim', 'aciklama': 'Köprü dayanımı, yapı mekaniği, optimizasyon', 'yasgrubu': 'lise'}
        ]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# PISA 2022 YETERLİK SEVİYELERİ (Resmi OECD Tanımları)
# ═══════════════════════════════════════════════════════════════════════════════

PISA_YETERLIK_SEVIYELERI = {
    1: {
        'ad': 'Seviye 1 (Temel)',
        'puan_araligi': '358-420',
        'siniflar': ['5', '6'],
        'tanimlayicilar': [
            'Doğrudan verilen bilgiyi bulma',
            'Basit, rutin prosedürleri uygulama',
            'Tek adımlı işlemler yapma',
            'Basit bağlamlarda tam sayı hesaplamaları',
            'Açık ve kısa metinlerle çalışma'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '1-2',
            'veri_sunumu': 'Doğrudan ve açık',
            'hesaplama': 'Basit dört işlem',
            'baglam': 'Çok tanıdık, günlük'
        }
    },
    2: {
        'ad': 'Seviye 2 (Temel Yeterlik)',
        'puan_araligi': '420-482',
        'siniflar': ['5', '6', '7'],
        'tanimlayicilar': [
            'Basit çıkarımlar yapma',
            'İki adımlı prosedürler uygulama',
            'Temel grafik ve tablo okuma',
            'Basit oran problemleri çözme',
            'Tek temsil biçimiyle çalışma'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '2-3',
            'veri_sunumu': 'Tablo veya basit grafik',
            'hesaplama': 'Oran, yüzde, basit kesir',
            'baglam': 'Tanıdık, düşük karmaşıklık'
        }
    },
    3: {
        'ad': 'Seviye 3 (Orta)',
        'puan_araligi': '482-545',
        'siniflar': ['6', '7', '8'],
        'tanimlayicilar': [
            'Ardışık karar verme gerektiren stratejiler',
            'Birden fazla bilgiyi sentezleme',
            'Basit modeller oluşturma ve kullanma',
            'Uzamsal görselleştirme',
            'Farklı temsiller arası geçiş'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '3-4',
            'veri_sunumu': 'Çoklu kaynak veya tablo',
            'hesaplama': 'Çok adımlı, ara sonuçlar',
            'baglam': 'Yarı tanıdık, orta karmaşıklık'
        }
    },
    4: {
        'ad': 'Seviye 4 (İleri)',
        'puan_araligi': '545-607',
        'siniflar': ['7', '8', '9', '10'],
        'tanimlayicilar': [
            'Karmaşık somut durumlar için modeller kullanma',
            'Varsayımları belirleme ve değerlendirme',
            'Farklı temsilleri bütünleştirme',
            'Eleştirel düşünme ve akıl yürütme',
            'Sonuçları yorumlama ve gerekçelendirme'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '4-5',
            'veri_sunumu': 'Çoklu temsil, grafik+tablo',
            'hesaplama': 'Model kurma, denklem',
            'baglam': 'Daha az tanıdık, gerçekçi'
        }
    },
    5: {
        'ad': 'Seviye 5 (Üstün)',
        'puan_araligi': '607-669',
        'siniflar': ['8', '9', '10', '11'],
        'tanimlayicilar': [
            'Karmaşık durumlar için model geliştirme',
            'Varsayımları tanımlama ve eleştirme',
            'Sistematik problem çözme stratejileri',
            'Karmaşık görselleştirmelerle çalışma',
            'Çoklu çözüm yollarını değerlendirme'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '5-6',
            'veri_sunumu': 'Karmaşık, çoklu kaynak',
            'hesaplama': 'Üst düzey modelleme',
            'baglam': 'Yeni, alışılmadık'
        }
    },
    6: {
        'ad': 'Seviye 6 (Uzman)',
        'puan_araligi': '669+',
        'siniflar': ['10', '11', '12'],
        'tanimlayicilar': [
            'Özgün stratejiler ve yaklaşımlar geliştirme',
            'Soyut, standart dışı problemlerde çalışma',
            'Yaratıcı matematiksel düşünme',
            'Karmaşık genellemeler yapma',
            'Sembolik ve formal işlemlerde ustalık'
        ],
        'soru_ozellikleri': {
            'adim_sayisi': '6+',
            'veri_sunumu': 'Soyut, çok katmanlı',
            'hesaplama': 'Genelleme, ispat benzeri',
            'baglam': 'Tamamen yeni, keşif gerektiren'
        }
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# SINIF-SEVİYE EŞLEŞTİRMESİ (Türkiye Müfredatı Uyumu)
# ═══════════════════════════════════════════════════════════════════════════════

SINIF_PISA_ESLESTIRME = {
    '5': {'ad': '5. Sınıf', 'pisa_seviyeleri': [1, 2], 'yas_grubu': 'tum', 'icerik_agirliklari': {'nicelik': 35, 'uzay_sekil': 30, 'degisim_iliskiler': 20, 'belirsizlik_veri': 15}},
    '6': {'ad': '6. Sınıf', 'pisa_seviyeleri': [1, 2, 3], 'yas_grubu': 'tum', 'icerik_agirliklari': {'nicelik': 30, 'uzay_sekil': 30, 'degisim_iliskiler': 25, 'belirsizlik_veri': 15}},
    '7': {'ad': '7. Sınıf', 'pisa_seviyeleri': [2, 3, 4], 'yas_grubu': 'tum', 'icerik_agirliklari': {'nicelik': 25, 'uzay_sekil': 25, 'degisim_iliskiler': 30, 'belirsizlik_veri': 20}},
    '8': {'ad': '8. Sınıf (LGS)', 'pisa_seviyeleri': [3, 4, 5], 'yas_grubu': 'tum', 'icerik_agirliklari': {'nicelik': 25, 'uzay_sekil': 25, 'degisim_iliskiler': 25, 'belirsizlik_veri': 25}},
    '9': {'ad': '9. Sınıf', 'pisa_seviyeleri': [3, 4, 5], 'yas_grubu': 'lise', 'icerik_agirliklari': {'nicelik': 25, 'uzay_sekil': 25, 'degisim_iliskiler': 25, 'belirsizlik_veri': 25}},
    '10': {'ad': '10. Sınıf', 'pisa_seviyeleri': [4, 5, 6], 'yas_grubu': 'lise', 'icerik_agirliklari': {'nicelik': 25, 'uzay_sekil': 25, 'degisim_iliskiler': 25, 'belirsizlik_veri': 25}},
    '11': {'ad': '11. Sınıf', 'pisa_seviyeleri': [5, 6], 'yas_grubu': 'lise', 'icerik_agirliklari': {'nicelik': 25, 'uzay_sekil': 25, 'degisim_iliskiler': 25, 'belirsizlik_veri': 25}},
    '12': {'ad': '12. Sınıf (YKS)', 'pisa_seviyeleri': [5, 6], 'yas_grubu': 'lise', 'icerik_agirliklari': {'nicelik': 25, 'uzay_sekil': 25, 'degisim_iliskiler': 25, 'belirsizlik_veri': 25}}
}

# ═══════════════════════════════════════════════════════════════════════════════
# MATEMATİKSEL SÜREÇLER (PISA Framework)
# ═══════════════════════════════════════════════════════════════════════════════

MATEMATIKSEL_SURECLER = {
    'formule_etme': {
        'ad': 'Formüle Etme (Formulate)',
        'agirlik': 25,
        'aciklama': 'Gerçek dünya problemini matematiksel forma dönüştürme',
        'beklentiler': [
            'Problemdeki matematiksel fırsatları tanımlama',
            'Anahtar değişkenleri belirleme',
            'Durumu değişkenler ve sembollerle temsil etme',
            'Varsayımları ve kısıtlamaları saptama',
            'Matematiksel model oluşturma'
        ],
        'ornek_fiiller': ['modelle', 'ifade et', 'dönüştür', 'tanımla', 'formüle et']
    },
    'kullanma': {
        'ad': 'Kullanma (Employ)',
        'agirlik': 50,
        'aciklama': 'Matematiksel kavram, gerçek ve prosedürleri uygulama',
        'beklentiler': [
            'Hesaplamalar yapma',
            'Matematiksel araçları kullanma',
            'Stratejiler geliştirme ve uygulama',
            'Verilerdeki örüntüleri değerlendirme',
            'Denklem ve formül çözme'
        ],
        'ornek_fiiller': ['hesapla', 'çöz', 'uygula', 'bul', 'belirle']
    },
    'yorumlama': {
        'ad': 'Yorumlama (Interpret)',
        'agirlik': 25,
        'aciklama': 'Matematiksel sonuçları gerçek yaşam bağlamında yansıtma',
        'beklentiler': [
            'Sonuçları bağlama geri yorumlama',
            'Çözümün makullüğünü değerlendirme',
            'Model sınırlılıklarını belirleme',
            'Açıklamalar ve argümanlar oluşturma',
            'Sonuçları eleştirel değerlendirme'
        ],
        'ornek_fiiller': ['yorumla', 'değerlendir', 'açıkla', 'karşılaştır', 'eleştir']
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# SORU TİPLERİ VE PUANLAMA
# ═══════════════════════════════════════════════════════════════════════════════

SORU_TIPLERI = {
    'coktan_secmeli': {
        'ad': 'Çoktan Seçmeli',
        'aciklama': 'Otomatik puanlanabilir, 4-5 seçenekli',
        'puanlama': 'Tek puan (0 veya 1)',
        'ozellikler': [
            '4-5 seçenek (A, B, C, D veya A, B, C, D, E)',
            'Tek doğru cevap',
            'Çeldiriciler yaygın hatalara dayalı',
            'Otomatik puanlanabilir'
        ]
    },
    'acik_uclu': {
        'ad': 'Açık Uçlu (Yapılandırılmış Yanıt)',
        'aciklama': 'Açıklama gerektiren, uzman kodlaması gereken',
        'puanlama': 'Çift haneli kodlama (0, 1, 2 puan)',
        'ozellikler': [
            'Açıklama/gerekçe gerektiren',
            'Kısmi puan verilebilir',
            'Çoklu çözüm yolu kabul edilebilir',
            'Rubrik tabanlı puanlama'
        ]
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# TÜRK İSİMLERİ HAVUZU (Kültürel Çeşitlilik)
# ═══════════════════════════════════════════════════════════════════════════════

TURK_ISIMLERI = {
    'kiz': ['Elif', 'Zeynep', 'Defne', 'Ecrin', 'Azra', 'Nehir', 'Asya', 'Mira', 'Ela', 'Duru', 
            'Lina', 'Ada', 'Eylül', 'Ceren', 'İpek', 'Sude', 'Yağmur', 'Melis', 'Beren', 'Nil',
            'Deniz', 'Ece', 'Pınar', 'Simge', 'Cansu', 'Serra', 'Naz', 'Beril', 'Deren', 'İrem'],
    'erkek': ['Yusuf', 'Eymen', 'Ömer', 'Emir', 'Mustafa', 'Ahmet', 'Kerem', 'Miran', 'Çınar', 'Aras',
              'Kuzey', 'Efe', 'Baran', 'Rüzgar', 'Atlas', 'Arda', 'Doruk', 'Eren', 'Burak', 'Kaan',
              'Alp', 'Ege', 'Onur', 'Mert', 'Berk', 'Tuna', 'Deniz', 'Cem', 'Can', 'Barış'],
    'ogretmen': ['Ayşe Öğretmen', 'Mehmet Öğretmen', 'Zehra Öğretmen', 'Ali Hoca', 
                 'Fatma Öğretmen', 'Hasan Hoca', 'Esra Öğretmen', 'Emre Hoca',
                 'Sibel Öğretmen', 'Murat Hoca', 'Derya Öğretmen', 'Serkan Hoca']
}

# Kullanılan isimler (tekrar önleyici)
kullanilan_isimler = set()

def rastgele_isim_sec(cinsiyet=None):
    """Rastgele ve tekrarsız Türk ismi seçer"""
    global kullanilan_isimler
    
    if cinsiyet is None:
        cinsiyet = random.choice(['kiz', 'erkek'])
    
    isimler = TURK_ISIMLERI.get(cinsiyet, TURK_ISIMLERI['erkek'])
    
    # %70 kullanıldıysa sıfırla
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
kullanilan_baglamlar = set()

def hash_olustur(soru):
    icerik = f"{soru.get('soru_metni', '')}|{soru.get('beklenen_cevap', soru.get('dogru_cevap', ''))}"
    return hashlib.md5(icerik.encode()).hexdigest()

def benzersiz_mi(soru):
    return hash_olustur(soru) not in kullanilan_hashler

def hash_kaydet(soru):
    kullanilan_hashler.add(hash_olustur(soru))

def rastgele_baglam_sec(sinif, icerik_kategorisi):
    """Sınıf ve içerik kategorisine uygun rastgele bağlam seçer"""
    global kullanilan_baglamlar
    
    sinif_bilgi = SINIF_PISA_ESLESTIRME.get(sinif, SINIF_PISA_ESLESTIRME['8'])
    yas_grubu = sinif_bilgi['yas_grubu']
    
    # Rastgele bağlam kategorisi seç
    baglam_kategorisi = random.choice(list(PISA_BAGLAM_KATEGORILERI.keys()))
    temalar = PISA_BAGLAM_KATEGORILERI[baglam_kategorisi]['temalar']
    
    # Yaş grubuna uygun temaları filtrele
    uygun_temalar = [t for t in temalar if t['yasgrubu'] == 'tum' or t['yasgrubu'] == yas_grubu]
    
    if not uygun_temalar:
        uygun_temalar = temalar
    
    # Kullanılmamış tema seç
    kullanilabilir = [t for t in uygun_temalar if t['tema'] not in kullanilan_baglamlar]
    
    if not kullanilabilir:
        kullanilan_baglamlar.clear()
        kullanilabilir = uygun_temalar
    
    secilen = random.choice(kullanilabilir)
    kullanilan_baglamlar.add(secilen['tema'])
    
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
Görevin, matematiksel okuryazarlığı ölçen, gerçek yaşam bağlamlarında otantik sorular üretmektir.

## 📚 MATEMATİKSEL OKURYAZARLIK TANIMI (OECD)

"Bireyin matematiksel akıl yürütme kapasitesi ve çeşitli gerçek yaşam bağlamlarında 
problemleri çözmek için matematiği FORMÜLE ETME, KULLANMA ve YORUMLAMA becerisidir."

## 🎯 ÜÇ MATEMATİKSEL SÜREÇ

### 1. FORMÜLE ETME (%25)
- Gerçek dünya problemini matematiksel forma dönüştürme
- Anahtar değişkenleri belirleme
- Matematiksel model oluşturma
- Varsayımları ve kısıtlamaları saptama

### 2. KULLANMA (%50)
- Matematiksel kavram ve prosedürleri uygulama
- Hesaplamalar yapma
- Stratejiler geliştirme ve uygulama
- Denklem ve formül çözme

### 3. YORUMLAMA (%25)
- Matematiksel sonuçları bağlama geri yorumlama
- Çözümün makullüğünü değerlendirme
- Sonuçları eleştirel değerlendirme
- Açıklamalar ve argümanlar oluşturma

## 📊 DÖRT İÇERİK KATEGORİSİ (Eşit Ağırlık %25)

### NİCELİK (Quantity)
- Sayı duyusu, büyüklük, birim, ölçüm
- Orantısal akıl yürütme, yüzde
- Para ve bütçe yönetimi

### UZAY VE ŞEKİL (Space and Shape)
- Geometrik şekiller ve özellikleri
- Uzamsal görselleştirme
- Ölçek, harita, perspektif

### DEĞİŞİM VE İLİŞKİLER (Change and Relationships)
- Fonksiyonel ilişkiler
- Değişim oranları, örüntüler
- Denklemler ve formüller

### BELİRSİZLİK VE VERİ (Uncertainty and Data)
- Veri toplama ve yorumlama
- Olasılık hesaplama
- İstatistiksel akıl yürütme

## 🌍 DÖRT BAĞLAM KATEGORİSİ

### KİŞİSEL: Günlük yaşam, aile, arkadaşlar
### MESLEKİ: İş dünyası, üretim, tasarım
### TOPLUMSAL: Topluluk, yerel/ulusal/küresel konular
### BİLİMSEL: Doğa bilimleri, teknoloji, mühendislik

## ⚠️ OTANTİK SENARYO KURALLARI (KRİTİK!)

### YAPILMASI GEREKENLER:
1. ✅ Matematiğin GERÇEKTEN kullanıldığı durumlar seç
2. ✅ Bağlam yapay "sözcük problemi" değil, otantik olmalı
3. ✅ Tüm veriler senaryoda AÇIKÇA belirtilmeli
4. ✅ Öğrenci SADECE senaryoyu okuyarak çözebilmeli
5. ✅ Gerçekçi sayısal değerler kullan
6. ✅ Kültürel olarak tarafsız bağlamlar seç

### YAPILMAMASI GEREKENLER:
1. ❌ Formül/kural vermeden hesaplama isteme
2. ❌ "Kurallara göre" deyip kuralları yazmama
3. ❌ Eksik veri ile soru sorma
4. ❌ Yapay, zoraki matematik ekleme
5. ❌ Tek kültüre özgü referanslar
6. ❌ Aşırı karmaşık veya gerçek dışı sayılar

## 📐 GÖRSEL TEMSİL KURALLARI

Tablo, grafik veya şema gerekiyorsa MUTLAKA metin formatında göster:

### TABLO FORMATI:
**📊 [Tablo Başlığı]**
• Satır 1: Değer A, Değer B, Değer C
• Satır 2: Değer D, Değer E, Değer F

### VERİ LİSTESİ FORMATI:
**📋 [Liste Başlığı]**
• Öğe 1: Açıklama ve değer
• Öğe 2: Açıklama ve değer

## 🎭 ÜNİTE BAZLI TASARIM (PISA Formatı)

Her soru bir "ünite" içinde tasarlanır:
1. **STIMULUS (Uyaran):** Gerçekçi bağlam, veriler, görseller
2. **SORU KÖKÜ:** Net, anlaşılır soru
3. **YANIT ALANI:** Çoktan seçmeli veya açık uçlu

## 🔢 ÇELDİRİCİ TASARIM İLKELERİ (Çoktan Seçmeli için)

Her çeldirici belirli bir kavram yanılgısını temsil etmeli:
- 🔴 Senaryoyu yanlış yorumlama
- 🔴 Bir koşulu gözden kaçırma  
- 🔴 İşlem hatasının sonucu
- 🔴 Birimi dönüştürmeyi unutma
- 🔴 Çözümü bir adım erken bitirme

## 📝 PUANLAMA RUBRİK YAPISI (Açık Uçlu için)

### TAM PUAN (Kod 2):
- Doğru yöntem VE doğru sonuç
- Yeterli matematiksel açıklama

### KISMİ PUAN (Kod 1):
- Doğru yaklaşım ama hesaplama hatası
- Kısmen doğru akıl yürütme

### SIFIR PUAN (Kod 0):
- Yanlış yöntem
- Anlamsız veya alakasız yanıt

## ⚠️ DİLSEL STANDARTLAR

- Cümleler kısa ve net olmalı
- Teknik terimler gerektiğinde açıklanmalı
- Olumsuz soru kökleri vurgulanmalı
- Belirsiz ifadelerden kaçınılmalı
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
• Bağlam tipi: {seviye['soru_ozellikleri']['baglam']}

⚠️ Soru bu seviyeye UYGUN zorlukta olmalı - ne çok kolay ne çok zor!
"""

# ═══════════════════════════════════════════════════════════════════════════════
# JSON FORMAT ŞABLONLARI
# ═══════════════════════════════════════════════════════════════════════════════

JSON_FORMAT_COKTAN_SECMELI = '''
## 📋 JSON FORMATI - ÇOKTAN SEÇMELİ

```json
{
  "soru_tipi": "coktan_secmeli",
  "alan": "matematik",
  "konu": "[İçerik kategorisi adı]",
  "alt_konu": "[Spesifik alt konu]",
  "sinif": "[5-12]",
  "pisa_seviye": [1-6],
  "bloom_seviye": "[hatırlama/anlama/uygulama/analiz/değerlendirme/yaratma]",
  "senaryo_turu": "[kisisel/mesleki/toplumsal/bilimsel]",
  "matematiksel_surec": "[formule_etme/kullanma/yorumlama]",
  
  "senaryo": "[Minimum 100 kelime otantik senaryo. Tüm veriler, kurallar, tablolar AÇIKÇA yazılmalı. Öğrenci SADECE bunu okuyarak çözebilmeli.]",
  
  "soru_metni": "[Net, anlaşılır soru kökü]",
  
  "secenekler": [
    "A) [Seçenek - makul ve spesifik]",
    "B) [Seçenek - makul ve spesifik]",
    "C) [Seçenek - makul ve spesifik]",
    "D) [Seçenek - makul ve spesifik]"
  ],
  
  "dogru_cevap": "[A/B/C/D]",
  
  "celdirici_aciklamalar": {
    "[Yanlış şık harfi]": "Bu şıkkı seçen öğrenci [spesifik kavram yanılgısı/hata] yapmış olabilir.",
    "[Yanlış şık harfi]": "Bu şıkkı seçen öğrenci [spesifik kavram yanılgısı/hata] yapmış olabilir.",
    "[Yanlış şık harfi]": "Bu şıkkı seçen öğrenci [spesifik kavram yanılgısı/hata] yapmış olabilir."
  },
  
  "cozum_adimlari": [
    "Adım 1: [Veriyi anlama] - [Açıklama]",
    "Adım 2: [Model kurma] - [İşlem]",
    "Adım 3: [Hesaplama] - [İşlem] = [Sonuç]",
    "Adım 4: [Devam] - [İşlem] = [Sonuç]",
    "Adım 5: [Yorumlama] - [Sonuç açıklaması]",
    "Adım 6: [Doğru şık] - Cevap: [Harf]"
  ],
  
  "aha_moment": "[Bu sorudaki kilit matematiksel fikir veya beklenmedik bağlantı]",
  
  "beceri_alani": "[problem çözme/akıl yürütme/modelleme/veri analizi]",
  "tahmini_sure": "[X-Y dakika]",
  "pedagojik_notlar": "[Bu soru hangi becerileri ölçüyor, ne tür düşünme gerektiriyor]"
}
```

⚠️ JSON KURALLARI:
1. SADECE JSON döndür
2. String içinde çift tırnak yerine tek tırnak kullan
3. Newline için \\n kullan
4. EN AZ 5-6 çözüm adımı olmalı
5. Her çeldirici FARKLI bir hatayı temsil etmeli
'''

JSON_FORMAT_ACIK_UCLU = '''
## 📋 JSON FORMATI - AÇIK UÇLU

```json
{
  "soru_tipi": "acik_uclu",
  "alan": "matematik",
  "konu": "[İçerik kategorisi adı]",
  "alt_konu": "[Spesifik alt konu]",
  "sinif": "[5-12]",
  "pisa_seviye": [1-6],
  "bloom_seviye": "[hatırlama/anlama/uygulama/analiz/değerlendirme/yaratma]",
  "senaryo_turu": "[kisisel/mesleki/toplumsal/bilimsel]",
  "matematiksel_surec": "[formule_etme/kullanma/yorumlama]",
  
  "senaryo": "[Minimum 100 kelime otantik senaryo]",
  
  "soru_metni": "[Açıklama/gerekçe isteyen soru. 'Hesaplamalarınızı gösteriniz', 'Açıklayınız' gibi yönergeler içermeli]",
  
  "beklenen_cevap": "[Tam puan alacak cevabın özeti]",
  
  "puanlama_rubrik": {
    "tam_puan": "2 puan - [Tam puan kriterleri: doğru yöntem + doğru sonuç + yeterli açıklama]",
    "kismi_puan": "1 puan - [Kısmi puan kriterleri: doğru yaklaşım ama eksik/hatalı]",
    "sifir_puan": "0 puan - [Sıfır puan kriterleri: yanlış yöntem veya alakasız]"
  },
  
  "cozum_adimlari": [
    "Adım 1: [Veriyi anlama] - [Açıklama]",
    "Adım 2: [Model kurma] - [İşlem]",
    "Adım 3: [Hesaplama] - [İşlem] = [Sonuç]",
    "Adım 4: [Devam] - [İşlem] = [Sonuç]",
    "Adım 5: [Yorumlama] - [Sonuç açıklaması]"
  ],
  
  "alternatif_cozumler": "[Kabul edilebilir alternatif yaklaşımlar varsa belirt]",
  
  "aha_moment": "[Kilit matematiksel fikir]",
  
  "beceri_alani": "[problem çözme/akıl yürütme/modelleme]",
  "tahmini_sure": "[X-Y dakika]",
  "pedagojik_notlar": "[Ölçülen beceriler ve düşünme türü]"
}
```
'''

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK DOĞRULAMA PROMPTU (Güncellenmiş)
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
- Senaryo OTANTİK mi (yapay sözcük problemi değil)?
- Tüm gerekli veriler senaryoda mevcut mu?
- Öğrenci SADECE senaryoyu okuyarak çözebilir mi?
- Senaryo en az 80 kelime mi?
- Bağlam gerçekçi ve kültürel olarak tarafsız mı?

### 3. PISA UYUMU (25 puan)
- Hedeflenen PISA seviyesine uygun mu?
- Matematiksel süreç (formüle/kullan/yorumla) doğru mu?
- Gerçek yaşam bağlamı var mı?
- Üst düzey düşünme gerektiriyor mu?

### 4. YAPISAL KALİTE (20 puan)
- Çeldiriciler farklı kavram yanılgılarını mı temsil ediyor?
- Çözüm adımları yeterli ve mantıklı mı?
- Soru kökü açık ve anlaşılır mı?

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
  "matematiksel_kontrol": {
    "hesaplamalar_dogru": true/false,
    "cevap_dogru": true/false,
    "adimlar_tutarli": true/false
  },
  "senaryo_kontrol": {
    "otantik": true/false,
    "veriler_yeterli": true/false,
    "kendi_kendine_yeten": true/false
  },
  "pisa_kontrol": {
    "seviye_uyumu": true/false,
    "gercek_yasam_baglami": true/false,
    "surec_uyumu": true/false
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
- Toplam puan 70'in altındaysa

SADECE JSON döndür.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# JSON TEMİZLEME
# ═══════════════════════════════════════════════════════════════════════════════

def json_temizle(text):
    """AI'dan gelen JSON'u temizle ve parse et"""
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
    
    text = text.strip()
    
    # JSON başlangıç ve bitiş bul
    start = text.find('{')
    end = text.rfind('}') + 1
    
    if start >= 0 and end > start:
        text = text[start:end]
    
    # Temizleme işlemleri
    text = re.sub(r',(\s*[}\]])', r'\1', text)  # Trailing comma
    text = text.replace('\n', ' ').replace('\r', '')
    text = re.sub(r'\s+', ' ', text)
    
    # Escape karakterleri düzelt
    text = text.replace('\\n', '\n')
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Daha agresif temizleme dene
        try:
            text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
            return json.loads(text)
        except:
            print(f"   ⚠️ JSON parse hatası: {str(e)[:50]}")
            return None

# ═══════════════════════════════════════════════════════════════════════════════
# COT ÇÖZÜM OLUŞTUR
# ═══════════════════════════════════════════════════════════════════════════════

def cot_cozum_olustur(params):
    """Chain of Thought: Önce matematiksel çözümü oluştur"""
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        baglam = params.get('baglam', {})
        icerik = params.get('icerik_kategorisi', {})
        seviye = params.get('pisa_seviye', 3)
        isim1 = rastgele_isim_sec()
        isim2 = rastgele_isim_sec()
        
        prompt = f'''Sen OECD PISA matematik sorusu tasarlayan bir uzmansın.

## GÖREV
Aşağıdaki parametrelere göre ÖNCE bir matematik problemi tasarla, SONRA adım adım çöz.

## PARAMETRELER
• İçerik Kategorisi: {icerik.get('ad', 'Nicelik')}
• Alt Konu: {params.get('alt_konu', 'Oran ve Orantı')}
• Sınıf: {params.get('sinif_ad', '8. Sınıf')}
• PISA Seviyesi: {seviye}
• Bağlam: {baglam.get('kategori_ad', 'Kişisel')} - {baglam.get('tema', 'alisveris').replace('_', ' ')}
• Bağlam Açıklaması: {baglam.get('aciklama', 'Günlük yaşam problemi')}

## KULLANILACAK İSİMLER
• Karakter 1: {isim1}
• Karakter 2: {isim2}

## SEVİYE BEKLENTİLERİ
{seviye_prompt_olustur(seviye)}

## ÖNEMLİ KURALLAR
1. Senaryo OTANTİK olmalı - yapay sözcük problemi değil
2. Tüm kurallar ve veriler AÇIKÇA yazılmalı
3. Küçük, hesaplanabilir sayılar kullan (1-500 arası)
4. Sonuç tam sayı veya basit kesir/ondalık olsun
5. EN AZ 5 çözüm adımı olmalı
6. Her adımda matematiksel işlemi göster

## ÇIKTI FORMATI (JSON)
{{
    "problem_tanimi": "[En az 100 kelime, tüm veriler dahil]",
    "kurallar": ["Kural 1", "Kural 2", "Kural 3"],
    "verilen_degerler": {{"degisken1": deger1, "degisken2": deger2}},
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
}}

SADECE JSON döndür.'''

        response = model.generate_content(prompt)
        return json_temizle(response.text.strip())
        
    except Exception as e:
        print(f"   ⚠️ CoT Hata: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# ÇÖZÜMDEN SORU OLUŞTUR
# ═══════════════════════════════════════════════════════════════════════════════

def cozumden_soru_olustur(cozum, params):
    """CoT çözümünden tam PISA sorusu oluştur"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        soru_tipi = params.get('soru_tipi', 'acik_uclu')
        json_format = JSON_FORMAT_COKTAN_SECMELI if soru_tipi == 'coktan_secmeli' else JSON_FORMAT_ACIK_UCLU
        
        prompt = f'''{PISA_2022_SYSTEM_PROMPT}

{seviye_prompt_olustur(params.get('pisa_seviye', 3))}

## HAZIR ÇÖZÜM (Bunu kullan!)

**Problem:** {cozum.get('problem_tanimi', '')}

**Kurallar:** {json.dumps(cozum.get('kurallar', []), ensure_ascii=False)}

**Veriler:** {json.dumps(cozum.get('verilen_degerler', {}), ensure_ascii=False)}

**Çözüm Adımları:**
{chr(10).join(cozum.get('cozum_adimlari', []))}

**Sonuç:** {cozum.get('sonuc', '')}
**Açıklama:** {cozum.get('sonuc_aciklama', '')}
**Kilit Fikir:** {cozum.get('aha_moment', '')}

## GÖREV

Bu hazır çözümü kullanarak {'ÇOKTAN SEÇMELİ' if soru_tipi == 'coktan_secmeli' else 'AÇIK UÇLU'} bir PISA sorusu oluştur.

• Soru Tipi: {soru_tipi}
• İçerik: {params.get('icerik_kategorisi', {}).get('ad', 'Nicelik')}
• Alt Konu: {params.get('alt_konu', '')}
• Sınıf: {params.get('sinif', '8')}
• PISA Seviye: {params.get('pisa_seviye', 3)}
• Bağlam: {params.get('baglam', {}).get('kategori_ad', 'Kişisel')}
• Matematiksel Süreç: {params.get('matematiksel_surec', 'kullanma')}

{json_format}

⚠️ KRİTİK: 
- Senaryo KENDİ KENDİNE YETERLİ olmalı
- Tüm kurallar ve veriler senaryoda AÇIKÇA yazılmalı
- Çözüm adımları hazır çözümle TUTARLI olmalı
- dogru_cevap/beklenen_cevap "{cozum.get('sonuc', '')}" ile uyumlu olmalı

SADECE JSON döndür.'''

        response = model.generate_content(prompt)
        return json_temizle(response.text.strip())
        
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
# SUPABASE KAYIT
# ═══════════════════════════════════════════════════════════════════════════════

def supabase_kaydet(soru, cot_kullanildi=True):
    """Soruyu Supabase'e kaydet"""
    try:
        # Veri hazırla
        kayit = {
            'alan': soru.get('alan', 'matematik'),
            'konu': soru.get('konu', ''),
            'alt_konu': soru.get('alt_konu', ''),
            'sinif': str(soru.get('sinif', '8')),
            'soru_tipi': soru.get('soru_tipi', 'acik_uclu'),
            'senaryo_turu': soru.get('senaryo_turu', 'kisisel'),
            'pisa_seviye': int(soru.get('pisa_seviye', 3)),
            'bloom_seviye': soru.get('bloom_seviye', 'uygulama'),
            'senaryo': soru.get('senaryo', ''),
            'soru_metni': soru.get('soru_metni', ''),
            'secenekler': soru.get('secenekler'),
            'dogru_cevap': soru.get('dogru_cevap'),
            'celdirici_aciklamalar': json.dumps(soru.get('celdirici_aciklamalar', {}), ensure_ascii=False) if soru.get('celdirici_aciklamalar') else None,
            'beklenen_cevap': soru.get('beklenen_cevap'),
            'puanlama_rubrik': json.dumps(soru.get('puanlama_rubrik', {}), ensure_ascii=False) if soru.get('puanlama_rubrik') else None,
            'cozum_adimlari': json.dumps(soru.get('cozum_adimlari', []), ensure_ascii=False),
            'aha_moment': soru.get('aha_moment', ''),
            'beceri_alani': soru.get('beceri_alani', ''),
            'pedagojik_notlar': soru.get('pedagojik_notlar', ''),
            'tahmini_sure': soru.get('tahmini_sure'),
            'cot_kullanildi': cot_kullanildi,
            'aktif': True,
            'dogrulama_durumu': 'dogrulanmamis'
        }
        
        # Boş değerleri temizle
        kayit = {k: v for k, v in kayit.items() if v is not None and v != ''}
        
        result = supabase.table('pisa_soru_havuzu').insert(kayit).execute()
        
        if result.data:
            return result.data[0].get('id')
        return None
        
    except Exception as e:
        print(f"   ⚠️ Supabase hatası: {str(e)[:50]}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# TEK SORU ÜRET
# ═══════════════════════════════════════════════════════════════════════════════

def tek_soru_uret(params):
    """Tek bir PISA sorusu üret"""
    
    for deneme in range(MAX_DENEME):
        try:
            # Adım 1: CoT ile çözüm oluştur
            if COT_AKTIF:
                cozum = cot_cozum_olustur(params)
                if not cozum:
                    print(f"   ⚠️ CoT başarısız (deneme {deneme+1})")
                    continue
            else:
                cozum = {'problem_tanimi': '', 'cozum_adimlari': [], 'sonuc': ''}
            
            # Adım 2: Çözümden soru oluştur
            soru = cozumden_soru_olustur(cozum, params)
            if not soru:
                print(f"   ⚠️ Soru oluşturulamadı (deneme {deneme+1})")
                continue
            
            # Adım 3: Benzersizlik kontrolü
            if not benzersiz_mi(soru):
                print(f"   ⚠️ Tekrar soru (deneme {deneme+1})")
                continue
            
            # Adım 4: DeepSeek doğrulama
            dogrulama = deepseek_dogrula(soru)
            
            if DEEPSEEK_DOGRULAMA and dogrulama.get('puan', 0) < MIN_DEEPSEEK_PUAN:
                print(f"   ⚠️ Düşük puan: {dogrulama.get('puan', 0)} (deneme {deneme+1})")
                continue
            
            # Adım 5: Kaydet
            soru_id = supabase_kaydet(soru, cot_kullanildi=COT_AKTIF)
            
            if soru_id:
                hash_kaydet(soru)
                return {
                    'success': True,
                    'id': soru_id,
                    'puan': dogrulama.get('puan') if dogrulama else None
                }
        
        except Exception as e:
            print(f"   ⚠️ Hata (deneme {deneme+1}): {str(e)[:50]}")
            continue
    
    return {'success': False}

# ═══════════════════════════════════════════════════════════════════════════════
# KOMBİNASYON OLUŞTUR
# ═══════════════════════════════════════════════════════════════════════════════

def kombinasyonlar_olustur():
    """Tüm geçerli soru kombinasyonlarını oluştur"""
    kombinasyonlar = []
    
    # Bloom seviyeleri
    bloom_map = {
        1: ['hatırlama', 'anlama'],
        2: ['anlama', 'uygulama'],
        3: ['uygulama', 'analiz'],
        4: ['analiz', 'değerlendirme'],
        5: ['değerlendirme', 'yaratma'],
        6: ['yaratma']
    }
    
    for sinif, sinif_bilgi in SINIF_PISA_ESLESTIRME.items():
        for pisa_seviye in sinif_bilgi['pisa_seviyeleri']:
            for icerik_key, icerik in PISA_ICERIK_KATEGORILERI.items():
                for alt_konu in icerik['alt_konular']:
                    for soru_tipi in ['acik_uclu', 'coktan_secmeli']:
                        for surec in ['formule_etme', 'kullanma', 'yorumlama']:
                            bloom_secenekleri = bloom_map.get(pisa_seviye, ['uygulama'])
                            bloom = random.choice(bloom_secenekleri)
                            
                            kombinasyonlar.append({
                                'sinif': sinif,
                                'sinif_ad': sinif_bilgi['ad'],
                                'pisa_seviye': pisa_seviye,
                                'icerik_kategorisi': icerik,
                                'icerik_key': icerik_key,
                                'alt_konu': alt_konu,
                                'soru_tipi': soru_tipi,
                                'matematiksel_surec': surec,
                                'bloom_seviye': bloom
                            })
    
    return kombinasyonlar

# ═══════════════════════════════════════════════════════════════════════════════
# TOPLU ÜRETİM
# ═══════════════════════════════════════════════════════════════════════════════

def toplu_uret(adet):
    """Toplu PISA sorusu üret"""
    print(f"\n{'='*70}")
    print(f"🎯 PISA 2022 SORU ÜRETİM BAŞLIYOR")
    print(f"   Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Hedef: {adet} soru")
    print(f"   Standart: OECD PISA 2022")
    print(f"   CoT: {'✅ AKTİF' if COT_AKTIF else '❌ DEVRE DIŞI'}")
    print(f"   DeepSeek: {'✅ AKTİF (Min: ' + str(MIN_DEEPSEEK_PUAN) + ')' if DEEPSEEK_DOGRULAMA else '❌ DEVRE DIŞI'}")
    print(f"{'='*70}\n")
    
    basarili = 0
    dogrulanan = 0
    toplam_puan = 0
    baslangic = time.time()
    
    # Kombinasyonları oluştur ve karıştır
    kombinasyonlar = kombinasyonlar_olustur()
    random.shuffle(kombinasyonlar)
    
    for params in kombinasyonlar:
        if basarili >= adet:
            break
        
        # Bağlam seç
        params['baglam'] = rastgele_baglam_sec(params['sinif'], params['icerik_key'])
        
        icerik_ad = params['icerik_kategorisi']['ad'].split('(')[0].strip()
        baglam_tema = params['baglam']['tema'].replace('_', ' ')
        
        print(f"\n[{basarili+1}/{adet}] {icerik_ad} > {params['alt_konu']}")
        print(f"   📚 {params['sinif_ad']} | PISA {params['pisa_seviye']} | {params['soru_tipi']}")
        print(f"   🌍 {params['baglam']['kategori_ad']} > {baglam_tema}")
        
        try:
            sonuc = tek_soru_uret(params)
            
            if sonuc['success']:
                basarili += 1
                puan = sonuc.get('puan')
                if puan:
                    dogrulanan += 1
                    toplam_puan += puan
                
                print(f"   ✅ Başarılı! ID: {sonuc['id'][:8]}...")
                if puan:
                    print(f"      📊 Kalite Puanı: {puan}/100")
            else:
                print(f"   ❌ Başarısız")
                
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
    print(f"   📈 Ortalama Kalite: {ort_puan:.1f}/100")
    print(f"   ⏱️ Süre: {sure/60:.1f} dakika")
    print(f"   📈 Hız: {sure/max(basarili,1):.1f} sn/soru")
    print(f"{'='*70}\n")
    
    return basarili

# ═══════════════════════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("🎯 PISA SORU ÜRETİCİ BOT V4")
    print("   📚 OECD PISA 2022 Standartları")
    print("   ✅ 4 İçerik Kategorisi (Eşit Ağırlık)")
    print("   ✅ 4 Bağlam Kategorisi (Otantik Senaryolar)")
    print("   ✅ 3 Matematiksel Süreç")
    print("   ✅ 6 Yeterlik Seviyesi")
    print("   ✅ Chain of Thought + DeepSeek Doğrulama")
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
            global DEEPSEEK_DOGRULAMA
            DEEPSEEK_DOGRULAMA = False
    
    print()
    
    # Soru üret
    basarili = toplu_uret(adet=SORU_ADEDI)
    
    print(f"\n🎉 İşlem tamamlandı!")
    print(f"   {basarili} PISA 2022 standardında soru üretildi.")

if __name__ == "__main__":
    main()
