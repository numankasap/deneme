# SymPy Soru Doğrulama Sistemi v2.0

MATAİ PRO için `question_bank` tablosundaki soruların matematiksel doğrulamasını yapan sistem.

## 🎯 Desteklenen Soru Tipleri (17 Tip)

### Temel İşlemler
| Tip | Açıklama | Güvenilirlik |
|-----|----------|--------------|
| `ekok` | En Küçük Ortak Kat | ✅ Yüksek |
| `ebob` | En Büyük Ortak Bölen | ✅ Yüksek |
| `denklem_1` | Birinci Derece Denklem | ⚠️ Orta |
| `denklem_2` | İkinci Derece Denklem | ⚠️ Orta |

### Sayılar ve Kümeler
| Tip | Açıklama | Güvenilirlik |
|-----|----------|--------------|
| `sayi_kumeleri` | N, Z, Q, R Kümeleri | ⚠️ Orta |
| `mutlak_deger` | Mutlak Değer | ✅ Yüksek |
| `esitsizlik` | Eşitsizlikler | ⚠️ Orta |
| `basamak` | Basamak Kavramı | ✅ Yüksek |

### Kesirler ve Sayılar
| Tip | Açıklama | Güvenilirlik |
|-----|----------|--------------|
| `kesir` | Kesirler | ✅ Yüksek |
| `ondalik` | Ondalık Kesirler | ⚠️ Orta |
| `rasyonel` | Rasyonel Sayılar | ⚠️ Orta |

### İleri Konular
| Tip | Açıklama | Güvenilirlik |
|-----|----------|--------------|
| `faktoriyel` | Faktöriyel, Permütasyon, Kombinasyon | ✅ Yüksek |
| `carpanlara_ayirma` | Asal Çarpanlara Ayırma, Bölenler | ✅ Yüksek |
| `polinom` | Polinomlar | ✅ Yüksek |
| `fonksiyon` | Fonksiyonlar | ✅ Yüksek |
| `kume` | Küme İşlemleri (∩, ∪, Fark) | ✅ Yüksek |
| `mantik` | Mantık Önermeleri | ⚠️ Orta |

### Diğer
| Tip | Açıklama | Güvenilirlik |
|-----|----------|--------------|
| `asal` | Asal Sayılar | ✅ Yüksek |
| `uslu` | Üslü Sayılar | ✅ Yüksek |
| `koklu` | Köklü Sayılar | ⚠️ Orta |
| `bolunebilme` | Bölünebilirlik | ✅ Yüksek |

## 📦 Kurulum

### 1. Bağımlılıkları Kur
```bash
pip install -r requirements.txt
```

### 2. Supabase Kolonlarını Ekle
`migrations/001_add_sympy_columns.sql` dosyasını Supabase SQL Editor'da çalıştır.

### 3. Environment Variables
```bash
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1..."
```

## 🚀 Kullanım

### Yerel Test (İnternet Gerektirmez)
```bash
cd sympy_verification
python test_local.py
```

### Tüm Soruları Doğrula
```bash
python main.py --limit 100
```

### Belirli Konuyu Doğrula
```bash
python main.py --topic "EKOK" --limit 50
```

### Tek Soru Doğrula
```bash
python main.py --id 16180
```

### Sadece Doğrulanmamış Sorular
```bash
python main.py --unverified --limit 200
```

## 📊 Sonuçları Görüntüleme

### SQL ile İstatistikler
```sql
-- Genel istatistikler
SELECT * FROM v_verification_stats;

-- Yanlış bulunan sorular
SELECT * FROM v_incorrect_questions;

-- Bekleyen sorular
SELECT * FROM v_pending_verification LIMIT 10;
```

### JSON Sonuç Yapısı
```json
{
  "status": "verified",
  "question_type": "ekok",
  "is_correct": true,
  "confidence": "high",
  "sympy_answer": 72,
  "expected_answer": "72",
  "numbers_found": [18, 24],
  "message": "✓ EKOK(18, 24) = 72"
}
```

## 🔄 GitHub Actions

Otomatik çalıştırma için:

1. Repository'de `SUPABASE_URL` ve `SUPABASE_SERVICE_KEY` secret'larını ekle
2. `.github/workflows/sympy-verify.yml` dosyasını kopyala
3. Her gece 03:00'te otomatik çalışır veya manuel tetikle

## 📁 Dosya Yapısı

```
sympy_verification/
├── main.py           # Ana çalıştırıcı
├── parsers.py        # Soru ayrıştırıcılar
├── verifiers.py      # SymPy doğrulayıcılar
├── test_local.py     # Yerel test scripti
├── requirements.txt  # Python bağımlılıkları
├── README.md         # Bu dosya
├── migrations/
│   └── 001_add_sympy_columns.sql
└── .github/
    └── workflows/
        └── sympy-verify.yml
```

## ⚠️ Limitasyonlar

- **Geometri soruları**: Şekil analizi yapılamaz
- **Grafik soruları**: Görsel veri okunamaz
- **Karmaşık sözel problemler**: Doğal dil işleme sınırlı
- **LaTeX formüller**: Kısmi destek

## 🔧 Genişletme

Yeni soru tipi eklemek için:

1. `parsers.py`'de `TOPIC_PATTERNS`'e pattern ekle
2. `verifiers.py`'de yeni doğrulama fonksiyonu yaz
3. `verify_question` fonksiyonuna ekle

Örnek:
```python
def verify_yeni_tip(question: Dict) -> Dict[str, Any]:
    result = {
        "status": "not_verifiable",
        "question_type": "yeni_tip",
        # ...
    }
    # Doğrulama mantığı
    return result
```
