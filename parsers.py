"""
Soru Ayrıştırıcılar (Parsers) - Genişletilmiş Versiyon v2
Soru metinlerinden matematiksel ifadeleri çıkarır

Desteklenen Tipler (15+):
- EKOK/EBOB
- Denklemler (1. ve 2. derece)
- Sayı Kümeleri (N, Z, Q, R)
- Mutlak Değer
- Eşitsizlikler
- Basamak Kavramı
- Kesirler
- Ondalık Kesirler
- Rasyonel Sayılar
- Faktöriyel (Permütasyon, Kombinasyon)
- Çarpanlara Ayırma
- Polinomlar
- Fonksiyonlar
- Kümeler
- Mantık
"""

import re
import json
from typing import Dict, List, Tuple, Optional, Any


# ============================================================
# KONU BAZLI SORU TİPİ EŞLEŞTİRME
# ============================================================

TOPIC_PATTERNS = {
    # Temel İşlemler - Yüksek Öncelik
    "ekok": ["ekok", "en küçük ortak kat", "ortak katı", "tekrar aynı gün", "aynı anda"],
    "ebob": ["ebob", "en büyük ortak bölen", "ortak böleni"],
    
    # Mutlak Değer - Sembol tespiti
    "mutlak_deger": ["mutlak değer", "mutlak değeri", "|x", "| ="],
    
    # Eşitsizlikler
    "esitsizlik": ["eşitsizlik", "eşitsizliğin", "çözüm kümesi", "aralık"],
    
    # Basamak Kavramı
    "basamak": [
        "basamak", "birler basamağı", "onlar basamağı", "yüzler basamağı",
        "rakamları toplamı", "rakamları çarpımı", "basamak değeri"
    ],
    
    # Faktöriyel - ! sembolü öncelikli
    "faktoriyel": ["faktöriyel", "permütasyon", "kombinasyon", "P(", "C("],
    
    # Çarpanlara Ayırma
    "carpanlara_ayirma": [
        "çarpanlara ayır", "asal çarpan", "bölen sayısı", 
        "pozitif bölen", "asal faktör"
    ],
    
    # Polinomlar
    "polinom": ["polinom", "p(x)", "q(x)", "derecesi", "katsayısı", "sabit terim"],
    
    # Fonksiyonlar
    "fonksiyon": [
        "fonksiyon", "f(x)", "g(x)", "tanım kümesi", "değer kümesi",
        "görüntü kümesi", "bileşke", "ters fonksiyon", "fog", "gof"
    ],
    
    # Kümeler
    "kume": [
        "küme", "eleman sayısı", "kesişim", "birleşim", "fark", 
        "alt küme", "∩", "∪", "s(a)", "n(a)"
    ],
    
    # Mantık
    "mantik": [
        "önerme", "doğruluk değeri", "doğruluk tablosu", 
        "bileşik önerme", "koşullu önerme"
    ],
    
    # Sayı Kümeleri
    "sayi_kumeleri": [
        "doğal sayı", "tam sayı", "rasyonel sayı", "irrasyonel",
        "n kümesi", "z kümesi", "q kümesi", "gerçek sayı"
    ],
    
    # Kesirler
    "kesir": [
        "kesir", "pay", "payda", "sadeleştir", "genişlet",
        "kesirleri topla", "kesir işlemi", "1/2", "1/3", "1/4", "2/3", "3/4"
    ],
    
    # Ondalık
    "ondalik": ["ondalık", "virgüllü sayı", "ondalık kesir", "ondalık gösterim"],
    
    # Rasyonel
    "rasyonel": ["rasyonel sayı", "p/q", "a/b şeklinde"],
    
    # Denklemler
    "denklem_2": ["ikinci derece", "x²", "karesel denklem"],
    "denklem_1": ["birinci derece", "doğrusal denklem"],
    
    # Diğer
    "uslu": ["üslü", "üs", "kuvvet"],
    "koklu": ["köklü", "karekök", "√"],
    "asal": ["asal sayı", "asal mı"],
    "bolunebilme": ["bölünebilme", "tam bölünür", "kalansız böl"],
}


def detect_question_type(question: Dict) -> str:
    """Sorunun tipini belirle"""
    
    # None kontrolü - veritabanından NULL gelebilir
    topic = (question.get("topic") or "").lower()
    text = (question.get("original_text") or "").lower()
    solution = (question.get("solution_text") or "").lower()
    solution_short = (question.get("solution_short") or "").lower()
    
    combined = f"{topic} {text} {solution} {solution_short}"
    
    # 1. Regex ile öncelikli tespit
    if re.search(r'\d+\s*!', combined):
        return "faktoriyel"
    
    if re.search(r'\|[^|]+\|\s*=', combined):
        return "mutlak_deger"
    
    if re.search(r'ekok\s*\(|en küçük ortak kat', combined):
        return "ekok"
    
    if re.search(r'ebob\s*\(|en büyük ortak bölen', combined):
        return "ebob"
    
    # Kesir: a/b formatı
    if re.search(r'\d+\s*/\s*\d+', combined):
        return "kesir"
    
    if re.search(r'[A-Z]\s*=\s*\{[^}]+\}', text):
        return "kume"
    
    if re.search(r'[fgh]\s*\(\s*x\s*\)\s*=', combined):
        return "fonksiyon"
    
    if re.search(r'[pq]\s*\(\s*x\s*\)\s*=', combined):
        return "polinom"
    
    # 2. Pattern listesinden tespit
    priority_order = [
        "ekok", "ebob", "mutlak_deger", "esitsizlik", "basamak",
        "faktoriyel", "carpanlara_ayirma", "polinom", "fonksiyon",
        "kume", "mantik", "sayi_kumeleri", "kesir", "ondalik",
        "rasyonel", "denklem_2", "denklem_1", "uslu", "koklu",
        "asal", "bolunebilme"
    ]
    
    for q_type in priority_order:
        patterns = TOPIC_PATTERNS.get(q_type, [])
        for pattern in patterns:
            if pattern in combined:
                return q_type
    
    return "genel"


# ============================================================
# SAYI ÇIKARMA FONKSİYONLARI
# ============================================================

def extract_numbers_from_text(text: str) -> List[int]:
    """Metinden tüm tam sayıları çıkar"""
    numbers = re.findall(r'\b(\d+)\b', text)
    return [int(n) for n in numbers]


def extract_signed_numbers(text: str) -> List[int]:
    """Metinden işaretli sayıları çıkar"""
    numbers = re.findall(r'(-?\d+)', text)
    return [int(n) for n in numbers]


def extract_fractions(text: str) -> List[Tuple[int, int]]:
    """Metinden kesirleri çıkar (pay, payda)"""
    fractions = re.findall(r'(\d+)\s*/\s*(\d+)', text)
    return [(int(f[0]), int(f[1])) for f in fractions]


def extract_decimals(text: str) -> List[float]:
    """Metinden ondalık sayıları çıkar"""
    decimals = re.findall(r'(\d+[,\.]\d+)', text)
    return [float(d.replace(',', '.')) for d in decimals]


# ============================================================
# EKOK/EBOB
# ============================================================

def extract_ekok_ebob_numbers(question: Dict) -> Tuple[Optional[List[int]], str]:
    """EKOK/EBOB sorusundan sayıları çıkar"""
    
    text = question.get("original_text", "")
    solution = question.get("solution_text", "")
    combined = f"{text} {solution}"
    
    operation = "ekok" if "ekok" in combined.lower() else "ebob"
    
    # EKOK(18, 24) formatı
    match = re.search(r'EKOK\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', combined, re.I)
    if match:
        return [int(match.group(1)), int(match.group(2))], "ekok"
    
    match = re.search(r'EBOB\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', combined, re.I)
    if match:
        return [int(match.group(1)), int(match.group(2))], "ebob"
    
    # X ve Y sayılarının formatı
    match = re.search(r'(\d+)\s*ve\s*(\d+)\s*sayı', combined)
    if match:
        return [int(match.group(1)), int(match.group(2))], operation
    
    # Periyodik: X günde bir, Y günde bir
    matches = re.findall(r'(\d+)\s*gün', combined.lower())
    if len(matches) >= 2:
        return [int(matches[0]), int(matches[1])], operation
    
    return None, operation


# ============================================================
# MUTLAK DEĞER
# ============================================================

def extract_absolute_value_expr(text: str) -> List[Dict]:
    """Mutlak değer ifadelerini çıkar"""
    results = []
    
    # |x - a| = b formatı
    match = re.search(r'\|\s*x\s*([\+\-])\s*(\d+)\s*\|\s*=\s*(\d+)', text)
    if match:
        results.append({
            "type": "equation",
            "operator": match.group(1),
            "constant": int(match.group(2)),
            "equals": int(match.group(3))
        })
    
    # |sayı| formatı
    matches = re.findall(r'\|\s*(-?\d+)\s*\|', text)
    for m in matches:
        results.append({"type": "numeric", "value": int(m)})
    
    return results


# ============================================================
# EŞİTSİZLİK
# ============================================================

def extract_inequality_expr(text: str) -> Optional[Dict]:
    """Eşitsizlik ifadesini çıkar"""
    
    # ax + b > c formatı
    match = re.search(r'(-?\d*)x\s*([\+\-])\s*(\d+)\s*([<>≤≥]|<=|>=)\s*(-?\d+)', text)
    if match:
        coef = int(match.group(1)) if match.group(1) and match.group(1) != '-' else (
            -1 if match.group(1) == '-' else 1)
        return {
            "coefficient": coef,
            "operator": match.group(2),
            "constant": int(match.group(3)),
            "inequality": match.group(4),
            "right_side": int(match.group(5))
        }
    return None


# ============================================================
# BASAMAK
# ============================================================

def extract_digit_info(number: int) -> Dict:
    """Sayının basamak bilgilerini hesapla"""
    digits = [int(d) for d in str(abs(number))]
    
    return {
        "number": number,
        "digits": digits,
        "digit_count": len(digits),
        "digit_sum": sum(digits),
        "digit_product": eval('*'.join(map(str, digits))) if all(d > 0 for d in digits) else 0,
        "positions": {
            "birler": digits[-1] if len(digits) >= 1 else 0,
            "onlar": digits[-2] if len(digits) >= 2 else 0,
            "yuzler": digits[-3] if len(digits) >= 3 else 0,
            "binler": digits[-4] if len(digits) >= 4 else 0,
        }
    }


# ============================================================
# KESİR
# ============================================================

def extract_fraction_operation(text: str) -> Dict:
    """Kesir işlemini belirle"""
    
    fractions = extract_fractions(text)
    
    operation = None
    if "+" in text or "topla" in text.lower():
        operation = "add"
    elif "-" in text or "çıkar" in text.lower():
        operation = "subtract"
    elif "×" in text or "*" in text or "çarp" in text.lower():
        operation = "multiply"
    elif "÷" in text or "/" in text or "böl" in text.lower():
        operation = "divide"
    elif "sadeleştir" in text.lower():
        operation = "simplify"
    
    return {"fractions": fractions, "operation": operation}


# ============================================================
# FAKTÖRİYEL
# ============================================================

def extract_factorial_expr(text: str) -> Dict:
    """Faktöriyel ifadelerini çıkar"""
    
    result = {"factorials": [], "permutation": None, "combination": None}
    
    # n! formatı
    matches = re.findall(r'(\d+)!', text)
    result["factorials"] = [int(m) for m in matches]
    
    # P(n,r) permütasyon
    match = re.search(r'P\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', text)
    if match:
        result["permutation"] = (int(match.group(1)), int(match.group(2)))
    
    # C(n,r) kombinasyon
    match = re.search(r'C\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', text)
    if match:
        result["combination"] = (int(match.group(1)), int(match.group(2)))
    
    return result


# ============================================================
# ÇARPANLARA AYIRMA
# ============================================================

def extract_factorization_target(text: str) -> Optional[int]:
    """Çarpanlara ayrılacak sayıyı bul"""
    
    # "72'nin asal çarpanları" formatı
    match = re.search(r"(\d+)'?(?:nin|nın|nun|nün|in|ın|un|ün)", text)
    if match:
        return int(match.group(1))
    
    numbers = extract_numbers_from_text(text)
    return max(numbers) if numbers else None


# ============================================================
# POLİNOM
# ============================================================

def extract_polynomial_expr(text: str) -> Dict:
    """Polinom ifadesini çıkar"""
    
    result = {"expression": None, "evaluate_at": None, "degree_asked": False}
    
    # P(x) = 2x² + 3x - 5 formatı (daha esnek)
    match = re.search(r'[PpQq]\s*\(\s*x\s*\)\s*=\s*(.+?)(?:\s+polinom|\s+ise|\s*,|$)', text)
    if match:
        result["expression"] = match.group(1).strip()
    
    # P(3) hesaplama - tüm P(sayı) değerlerini bul
    matches = re.findall(r'[PpQq]\s*\(\s*(-?\d+)\s*\)', text)
    for m in matches:
        val = int(m)
        if val != 0:  # x için 0 olabilir, onu atlayalım
            result["evaluate_at"] = val
            break
    
    if "derece" in text.lower():
        result["degree_asked"] = True
    
    return result


# ============================================================
# FONKSİYON
# ============================================================

def extract_function_expr(text: str) -> Dict:
    """Fonksiyon ifadesini çıkar"""
    
    result = {"expression": None, "evaluate_at": None, "composite": False}
    
    # f(x) = 3x + 2 formatı (daha esnek)
    match = re.search(r'[fFgG]\s*\(\s*x\s*\)\s*=\s*(.+?)(?:\s+fonksiyon|\s+ise|\s+için|\s*,|$)', text)
    if match:
        result["expression"] = match.group(1).strip()
    
    # f(5) hesaplama - tüm f(sayı) değerlerini bul
    matches = re.findall(r'[fFgG]\s*\(\s*(-?\d+)\s*\)', text)
    for m in matches:
        result["evaluate_at"] = int(m)
        break
    
    if "fog" in text.lower() or "gof" in text.lower():
        result["composite"] = True
    
    return result


# ============================================================
# KÜME
# ============================================================

def extract_set_expr(text: str) -> Dict:
    """Küme ifadelerini çıkar"""
    
    result = {"sets": {}, "operation": None}
    
    # A = {1, 2, 3} formatı
    matches = re.findall(r'([A-Z])\s*=\s*\{([^}]+)\}', text)
    for name, elements in matches:
        try:
            nums = [int(e.strip()) for e in elements.split(',') if e.strip().lstrip('-').isdigit()]
            result["sets"][name] = set(nums)
        except:
            pass
    
    # İşlem türü
    if "∩" in text or "kesişim" in text.lower():
        result["operation"] = "intersection"
    elif "∪" in text or "birleşim" in text.lower():
        result["operation"] = "union"
    elif "fark" in text.lower() or "\\" in text:
        result["operation"] = "difference"
    
    return result


# ============================================================
# MANTIK
# ============================================================

def extract_logic_expr(text: str) -> Dict:
    """Mantık ifadesini çıkar"""
    
    result = {"propositions": [], "connective": None, "values": {}}
    
    # p, q, r önermelerini bul
    props = re.findall(r'\b([pqrs])\b', text.lower())
    result["propositions"] = list(set(props))
    
    # Doğruluk değerleri (p: D, q: Y)
    if "p" in result["propositions"]:
        if "p: d" in text.lower() or "p doğru" in text.lower():
            result["values"]["p"] = True
        elif "p: y" in text.lower() or "p yanlış" in text.lower():
            result["values"]["p"] = False
    
    if "q" in result["propositions"]:
        if "q: d" in text.lower() or "q doğru" in text.lower():
            result["values"]["q"] = True
        elif "q: y" in text.lower() or "q yanlış" in text.lower():
            result["values"]["q"] = False
    
    # Bağlaç
    if "∧" in text or " ve " in text.lower():
        result["connective"] = "and"
    elif "∨" in text or " veya " in text.lower():
        result["connective"] = "or"
    elif "¬" in text or "değil" in text.lower():
        result["connective"] = "not"
    elif "→" in text or " ise " in text.lower():
        result["connective"] = "implies"
    
    return result


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def parse_options(options: Any) -> Dict[str, str]:
    """Seçenekleri parse et"""
    if isinstance(options, str):
        try:
            return json.loads(options)
        except:
            return {}
    return options if isinstance(options, dict) else {}


def get_correct_answer_value(question: Dict) -> Optional[str]:
    """Doğru cevabın değerini al"""
    correct_letter = question.get("correct_answer", "")
    options = parse_options(question.get("options", {}))
    return options.get(correct_letter)


def clean_number(value: str) -> Optional[float]:
    """String değeri sayıya çevir"""
    if value is None:
        return None
    
    cleaned = str(value).strip().replace(',', '.').replace(' ', '')
    
    if '/' in cleaned:
        try:
            parts = cleaned.split('/')
            return float(parts[0]) / float(parts[1])
        except:
            return None
    
    try:
        return float(cleaned)
    except:
        return None
