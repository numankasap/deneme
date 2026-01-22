"""
SymPy Doğrulayıcılar (Verifiers) - Genişletilmiş Versiyon v2
Her soru tipi için özel doğrulama fonksiyonları

Desteklenen Tipler (15+):
- EKOK/EBOB ✓
- Denklemler (1. ve 2. derece) ✓
- Sayı Kümeleri (N, Z, Q, R) ✓
- Mutlak Değer ✓
- Eşitsizlikler ✓
- Basamak Kavramı ✓
- Kesirler ✓
- Ondalık Kesirler ✓
- Rasyonel Sayılar ✓
- Faktöriyel (P, C) ✓
- Çarpanlara Ayırma ✓
- Polinomlar ✓
- Fonksiyonlar ✓
- Kümeler ✓
- Mantık ✓
"""

from sympy import (
    Symbol, symbols, sympify, simplify, expand, factor, Poly,
    solve, Eq, sqrt, Rational, gcd, lcm, factorial, binomial,
    Abs, S, N, Integer, isprime, primefactors, factorint, divisors
)
from sympy.parsing.sympy_parser import parse_expr
from typing import Dict, Any, Optional, List
import re
import math

from parsers import (
    extract_ekok_ebob_numbers, extract_numbers_from_text, extract_fractions,
    extract_absolute_value_expr, extract_inequality_expr, extract_digit_info,
    extract_fraction_operation, extract_factorial_expr, extract_factorization_target,
    extract_polynomial_expr, extract_function_expr, extract_set_expr,
    extract_logic_expr, get_correct_answer_value, clean_number, parse_options
)

# Semboller
x, y, z = symbols('x y z')


def verify_question(question: Dict, question_type: str) -> Dict[str, Any]:
    """Ana doğrulama fonksiyonu - soru tipine göre yönlendirir"""
    
    verifiers = {
        # Temel
        "ekok": verify_ekok,
        "ebob": verify_ebob,
        "denklem_1": verify_linear_equation,
        "denklem_2": verify_quadratic_equation,
        
        # Genişletilmiş
        "sayi_kumeleri": verify_number_sets,
        "mutlak_deger": verify_absolute_value,
        "esitsizlik": verify_inequality,
        "basamak": verify_digit,
        "kesir": verify_fraction,
        "ondalik": verify_decimal,
        "rasyonel": verify_rational,
        "faktoriyel": verify_factorial,
        "carpanlara_ayirma": verify_factorization,
        "polinom": verify_polynomial,
        "fonksiyon": verify_function,
        "kume": verify_set,
        "mantik": verify_logic,
        
        # Diğer
        "asal": verify_prime,
        "uslu": verify_exponent,
        "koklu": verify_root,
        "bolunebilme": verify_divisibility,
        "genel": verify_general,
    }
    
    verifier = verifiers.get(question_type, verify_general)
    
    try:
        return verifier(question)
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "question_type": question_type,
            "is_correct": None,
            "confidence": "none"
        }


# ============================================================
# EKOK / EBOB
# ============================================================

def verify_ekok(question: Dict) -> Dict[str, Any]:
    """EKOK doğrulama"""
    result = _init_result("ekok")
    
    numbers, _ = extract_ekok_ebob_numbers(question)
    if not numbers or len(numbers) < 2:
        result["message"] = "EKOK için sayılar bulunamadı"
        return result
    
    # SymPy ile hesapla
    sympy_result = lcm(numbers[0], numbers[1])
    for n in numbers[2:]:
        sympy_result = lcm(sympy_result, n)
    
    result["sympy_answer"] = int(sympy_result)
    result["numbers"] = numbers
    result["status"] = "calculated"
    result["confidence"] = "high"
    
    # Beklenen cevapla karşılaştır
    _compare_answer(question, result)
    
    return result


def verify_ebob(question: Dict) -> Dict[str, Any]:
    """EBOB doğrulama"""
    result = _init_result("ebob")
    
    numbers, _ = extract_ekok_ebob_numbers(question)
    if not numbers or len(numbers) < 2:
        result["message"] = "EBOB için sayılar bulunamadı"
        return result
    
    sympy_result = gcd(numbers[0], numbers[1])
    for n in numbers[2:]:
        sympy_result = gcd(sympy_result, n)
    
    result["sympy_answer"] = int(sympy_result)
    result["numbers"] = numbers
    result["status"] = "calculated"
    result["confidence"] = "high"
    
    _compare_answer(question, result)
    return result


# ============================================================
# DENKLEMLER
# ============================================================

def verify_linear_equation(question: Dict) -> Dict[str, Any]:
    """Birinci derece denklem doğrulama"""
    result = _init_result("denklem_1")
    
    text = (question.get("original_text") or "") + " " + (question.get("solution_text") or "")
    
    # ax + b = c
    match = re.search(r'(-?\d*)x\s*([\+\-])\s*(\d+)\s*=\s*(-?\d+)', text)
    if match:
        coef = int(match.group(1)) if match.group(1) and match.group(1) not in ['-', ''] else (
            -1 if match.group(1) == '-' else 1)
        const = int(match.group(3)) * (-1 if match.group(2) == '-' else 1)
        right = int(match.group(4))
        
        solution = solve(Eq(coef*x + const, right), x)
        if solution:
            result["sympy_answer"] = float(solution[0])
            result["equation"] = f"{coef}x + {const} = {right}"
            result["status"] = "calculated"
            result["confidence"] = "high"
            _compare_answer(question, result)
    
    return result


def verify_quadratic_equation(question: Dict) -> Dict[str, Any]:
    """İkinci derece denklem doğrulama"""
    result = _init_result("denklem_2")
    
    text = (question.get("original_text") or "") + " " + (question.get("solution_text") or "")
    
    # x² + bx + c = 0
    match = re.search(r'x[²2]\s*([\+\-])\s*(\d+)x\s*([\+\-])\s*(\d+)\s*=\s*0', text)
    if match:
        b = int(match.group(2)) * (-1 if match.group(1) == '-' else 1)
        c = int(match.group(4)) * (-1 if match.group(3) == '-' else 1)
        
        roots = solve(x**2 + b*x + c, x)
        if roots:
            result["roots"] = [float(r) for r in roots]
            result["roots_sum"] = sum(result["roots"])
            result["roots_product"] = result["roots"][0] * result["roots"][1] if len(roots) == 2 else None
            result["status"] = "calculated"
            result["confidence"] = "medium"
    
    return result


# ============================================================
# SAYI KÜMELERİ
# ============================================================

def verify_number_sets(question: Dict) -> Dict[str, Any]:
    """Sayı kümeleri doğrulama (N, Z, Q, R)"""
    result = _init_result("sayi_kumeleri")
    
    text = (question.get("original_text") or "").lower()
    numbers = extract_numbers_from_text(text)
    
    if numbers:
        n = numbers[0]
        result["number"] = n
        result["classifications"] = {
            "N (Doğal)": n >= 0,
            "Z (Tam)": True,
            "Q (Rasyonel)": True,
            "R (Gerçek)": True
        }
        result["status"] = "calculated"
        result["confidence"] = "medium"
        
        # Aralık sorusu mu?
        if "arasında" in text and len(numbers) >= 2:
            a, b = min(numbers[:2]), max(numbers[:2])
            if "doğal" in text or "n kümesi" in text:
                count = len([i for i in range(a, b+1) if i >= 0])
            elif "tam sayı" in text:
                count = b - a + 1
            else:
                count = b - a + 1
            result["range"] = [a, b]
            result["count"] = count
            result["sympy_answer"] = count
    
    return result


# ============================================================
# MUTLAK DEĞER
# ============================================================

def verify_absolute_value(question: Dict) -> Dict[str, Any]:
    """Mutlak değer doğrulama"""
    result = _init_result("mutlak_deger")
    
    text = (question.get("original_text") or "")
    exprs = extract_absolute_value_expr(text)
    
    for expr in exprs:
        if expr["type"] == "equation":
            # |x - a| = b → x = a ± b
            a = expr["constant"]
            b = expr["equals"]
            op = expr["operator"]
            
            if op == '-':
                solutions = [a + b, a - b]
            else:
                solutions = [-a + b, -a - b]
            
            result["solutions"] = solutions
            result["sum_of_solutions"] = sum(solutions)
            result["product_of_solutions"] = solutions[0] * solutions[1]
            result["sympy_answer"] = sum(solutions)  # Toplam varsayılan
            result["status"] = "calculated"
            result["confidence"] = "high"
            
            # Toplam mı çarpım mı?
            text_lower = text.lower()
            if "çarpım" in text_lower:
                result["sympy_answer"] = solutions[0] * solutions[1]
            
            break
        
        elif expr["type"] == "numeric":
            result["sympy_answer"] = abs(expr["value"])
            result["status"] = "calculated"
            result["confidence"] = "high"
            break
    
    _compare_answer(question, result)
    return result


# ============================================================
# EŞİTSİZLİK
# ============================================================

def verify_inequality(question: Dict) -> Dict[str, Any]:
    """Eşitsizlik doğrulama"""
    result = _init_result("esitsizlik")
    
    text = (question.get("original_text") or "")
    expr = extract_inequality_expr(text)
    
    if expr:
        coef = expr["coefficient"]
        const = expr["constant"] * (-1 if expr["operator"] == '-' else 1)
        right = expr["right_side"]
        ineq = expr["inequality"]
        
        # ax + b ≤ c → x ≤ (c - b) / a
        boundary = (right - const) / coef
        
        result["boundary"] = boundary
        result["inequality_type"] = ineq
        result["status"] = "calculated"
        result["confidence"] = "medium"
        
        # Tam sayı sayısı soruluyorsa
        if "tam sayı" in text.lower() and "kaç" in text.lower():
            # Basit aralık hesabı
            result["sympy_answer"] = int(boundary)
    
    return result


# ============================================================
# BASAMAK
# ============================================================

def verify_digit(question: Dict) -> Dict[str, Any]:
    """Basamak kavramı doğrulama"""
    result = _init_result("basamak")
    
    text = (question.get("original_text") or "")
    numbers = extract_numbers_from_text(text)
    
    if numbers:
        # En büyük sayıyı al (genellikle soru sayısı)
        target = max(numbers)
        info = extract_digit_info(target)
        
        result.update(info)
        result["status"] = "calculated"
        result["confidence"] = "high"
        
        text_lower = text.lower()
        if "toplam" in text_lower and "rakam" in text_lower:
            result["sympy_answer"] = info["digit_sum"]
        elif "çarpım" in text_lower and "rakam" in text_lower:
            result["sympy_answer"] = info["digit_product"]
        elif "kaç basamak" in text_lower:
            result["sympy_answer"] = info["digit_count"]
        
        _compare_answer(question, result)
    
    return result


# ============================================================
# KESİR
# ============================================================

def verify_fraction(question: Dict) -> Dict[str, Any]:
    """Kesir doğrulama"""
    result = _init_result("kesir")
    
    text = (question.get("original_text") or "")
    data = extract_fraction_operation(text)
    fractions = data["fractions"]
    operation = data["operation"]
    
    if fractions:
        sympy_fracs = [Rational(f[0], f[1]) for f in fractions]
        result["fractions"] = [str(f) for f in sympy_fracs]
        result["operation"] = operation
        result["status"] = "calculated"
        result["confidence"] = "medium"
        
        if len(sympy_fracs) >= 2:
            if operation == "add" or "+" in text:
                ans = sum(sympy_fracs)
            elif operation == "subtract":
                ans = sympy_fracs[0] - sympy_fracs[1]
            elif operation == "multiply":
                ans = sympy_fracs[0] * sympy_fracs[1]
            elif operation == "divide":
                ans = sympy_fracs[0] / sympy_fracs[1]
            else:
                ans = sum(sympy_fracs)  # Varsayılan toplama
            
            result["sympy_answer"] = str(ans)
            result["decimal_value"] = float(ans)
        elif len(sympy_fracs) == 1:
            result["sympy_answer"] = str(sympy_fracs[0])
            result["decimal_value"] = float(sympy_fracs[0])
    
    return result


# ============================================================
# ONDALIK
# ============================================================

def verify_decimal(question: Dict) -> Dict[str, Any]:
    """Ondalık kesir doğrulama"""
    result = _init_result("ondalik")
    
    text = (question.get("original_text") or "").replace(',', '.')
    
    # Ondalık sayıları bul
    decimals = re.findall(r'\b(\d+\.\d+)\b', text)
    
    if decimals:
        values = [float(d) for d in decimals]
        result["decimals"] = values
        result["as_fractions"] = [str(Rational(d).limit_denominator(1000)) for d in values]
        result["status"] = "calculated"
        result["confidence"] = "medium"
        
        if "kesir" in text.lower() and len(values) == 1:
            result["sympy_answer"] = str(Rational(values[0]).limit_denominator(1000))
    
    return result


# ============================================================
# RASYONEL
# ============================================================

def verify_rational(question: Dict) -> Dict[str, Any]:
    """Rasyonel sayı doğrulama"""
    result = _init_result("rasyonel")
    
    text = (question.get("original_text") or "")
    fractions = extract_fractions(text)
    
    if fractions:
        pay, payda = fractions[0]
        r = Rational(pay, payda)
        
        result["rational"] = str(r)
        result["decimal"] = float(r)
        result["is_integer"] = r.is_integer
        result["sympy_answer"] = str(r)
        result["status"] = "calculated"
        result["confidence"] = "medium"
    
    return result


# ============================================================
# FAKTÖRİYEL
# ============================================================

def verify_factorial(question: Dict) -> Dict[str, Any]:
    """Faktöriyel, Permütasyon, Kombinasyon doğrulama"""
    result = _init_result("faktoriyel")
    
    text = (question.get("original_text") or "")
    data = extract_factorial_expr(text)
    
    # Tek faktöriyel: 5!
    if data["factorials"]:
        n = data["factorials"][0]
        result["sympy_answer"] = int(factorial(n))
        result["n"] = n
        result["status"] = "calculated"
        result["confidence"] = "high"
        
        # Birden fazla faktöriyel varsa işlem yap
        if len(data["factorials"]) >= 2:
            vals = [factorial(f) for f in data["factorials"]]
            if "/" in text:
                result["sympy_answer"] = int(vals[0] / vals[1])
            elif "+" in text:
                result["sympy_answer"] = int(sum(vals))
            elif "-" in text:
                result["sympy_answer"] = int(vals[0] - vals[1])
            elif "*" in text or "×" in text:
                result["sympy_answer"] = int(vals[0] * vals[1])
    
    # Permütasyon: P(n, r)
    if data["permutation"]:
        n, r = data["permutation"]
        perm = factorial(n) / factorial(n - r)
        result["sympy_answer"] = int(perm)
        result["permutation"] = {"n": n, "r": r}
        result["status"] = "calculated"
        result["confidence"] = "high"
    
    # Kombinasyon: C(n, r)
    if data["combination"]:
        n, r = data["combination"]
        comb = binomial(n, r)
        result["sympy_answer"] = int(comb)
        result["combination"] = {"n": n, "r": r}
        result["status"] = "calculated"
        result["confidence"] = "high"
    
    _compare_answer(question, result)
    return result


# ============================================================
# ÇARPANLARA AYIRMA
# ============================================================

def verify_factorization(question: Dict) -> Dict[str, Any]:
    """Çarpanlara ayırma doğrulama"""
    result = _init_result("carpanlara_ayirma")
    
    text = (question.get("original_text") or "")
    number = extract_factorization_target(text)
    
    if number and number > 1:
        factors = factorint(number)
        prime_list = list(primefactors(number))
        divisor_list = list(divisors(number))
        
        result["number"] = number
        result["prime_factorization"] = factors
        result["prime_factors"] = prime_list
        result["all_divisors"] = divisor_list
        result["divisor_count"] = len(divisor_list)
        result["divisor_sum"] = sum(divisor_list)
        result["status"] = "calculated"
        result["confidence"] = "high"
        
        # Çarpım formatı
        factor_str = " × ".join([f"{p}^{e}" if e > 1 else str(p) for p, e in factors.items()])
        result["factorization_str"] = factor_str
        
        text_lower = text.lower()
        if "bölen" in text_lower and "kaç" in text_lower:
            result["sympy_answer"] = len(divisor_list)
        elif "asal çarpan" in text_lower and "kaç" in text_lower:
            result["sympy_answer"] = len(prime_list)
        elif "asal çarpan" in text_lower and "toplam" in text_lower:
            result["sympy_answer"] = sum(prime_list)
        
        _compare_answer(question, result)
    
    return result


# ============================================================
# POLİNOM
# ============================================================

def verify_polynomial(question: Dict) -> Dict[str, Any]:
    """Polinom doğrulama"""
    result = _init_result("polinom")
    
    text = (question.get("original_text") or "")
    solution = (question.get("solution_text") or "")
    combined = text + " " + solution
    
    data = extract_polynomial_expr(combined)
    
    if data["expression"]:
        expr_str = data["expression"]
        # Unicode karakterleri dönüştür
        expr_str = expr_str.replace('²', '**2').replace('³', '**3').replace('^', '**')
        expr_str = expr_str.replace('×', '*').replace('·', '*')
        # 2x → 2*x dönüşümü
        expr_str = re.sub(r'(\d)([x])', r'\1*\2', expr_str)
        # x² → x**2 (zaten yapıldı)
        
        try:
            poly_expr = sympify(expr_str)
            poly = Poly(poly_expr, x)
            
            result["polynomial"] = str(poly_expr)
            result["degree"] = poly.degree()
            result["leading_coef"] = int(poly.LC())
            result["constant"] = int(poly_expr.subs(x, 0))
            result["status"] = "calculated"
            result["confidence"] = "medium"
            
            # P(a) hesaplama
            if data["evaluate_at"] is not None:
                val = data["evaluate_at"]
                evaluated = poly_expr.subs(x, val)
                result["evaluated_at"] = val
                result["sympy_answer"] = int(evaluated) if evaluated.is_integer else float(evaluated)
            
            _compare_answer(question, result)
            
        except Exception as e:
            result["parse_error"] = str(e)
            result["raw_expression"] = expr_str
    
    return result


# ============================================================
# FONKSİYON
# ============================================================

def verify_function(question: Dict) -> Dict[str, Any]:
    """Fonksiyon doğrulama"""
    result = _init_result("fonksiyon")
    
    text = (question.get("original_text") or "")
    solution = (question.get("solution_text") or "")
    combined = text + " " + solution
    
    data = extract_function_expr(combined)
    
    if data["expression"]:
        expr_str = data["expression"]
        # Unicode karakterleri dönüştür
        expr_str = expr_str.replace('²', '**2').replace('³', '**3').replace('^', '**')
        expr_str = expr_str.replace('×', '*').replace('·', '*')
        # 3x → 3*x dönüşümü
        expr_str = re.sub(r'(\d)([x])', r'\1*\2', expr_str)
        
        try:
            func_expr = sympify(expr_str)
            result["function"] = str(func_expr)
            result["status"] = "calculated"
            result["confidence"] = "medium"
            
            # f(a) hesaplama
            if data["evaluate_at"] is not None:
                val = data["evaluate_at"]
                evaluated = func_expr.subs(x, val)
                result["evaluated_at"] = val
                result["sympy_answer"] = int(evaluated) if evaluated.is_integer else float(evaluated)
            
            _compare_answer(question, result)
            
        except Exception as e:
            result["parse_error"] = str(e)
            result["raw_expression"] = expr_str
    
    return result


# ============================================================
# KÜME
# ============================================================

def verify_set(question: Dict) -> Dict[str, Any]:
    """Küme doğrulama"""
    result = _init_result("kume")
    
    text = (question.get("original_text") or "")
    data = extract_set_expr(text)
    
    if data["sets"]:
        result["sets"] = {k: sorted(list(v)) for k, v in data["sets"].items()}
        result["operation"] = data["operation"]
        result["status"] = "calculated"
        result["confidence"] = "medium"
        
        set_names = sorted(data["sets"].keys())
        
        if len(set_names) >= 2:
            A = data["sets"][set_names[0]]
            B = data["sets"][set_names[1]]
            
            if data["operation"] == "intersection":
                res = A & B
                result["result_set"] = sorted(list(res))
                result["sympy_answer"] = len(res)
            elif data["operation"] == "union":
                res = A | B
                result["result_set"] = sorted(list(res))
                result["sympy_answer"] = len(res)
            elif data["operation"] == "difference":
                res = A - B
                result["result_set"] = sorted(list(res))
                result["sympy_answer"] = len(res)
        
        elif len(set_names) == 1:
            A = data["sets"][set_names[0]]
            result["element_count"] = len(A)
            if "eleman" in text.lower() and "kaç" in text.lower():
                result["sympy_answer"] = len(A)
        
        _compare_answer(question, result)
    
    return result


# ============================================================
# MANTIK
# ============================================================

def verify_logic(question: Dict) -> Dict[str, Any]:
    """Mantık doğrulama"""
    result = _init_result("mantik")
    
    text = (question.get("original_text") or "")
    data = extract_logic_expr(text)
    
    result["propositions"] = data["propositions"]
    result["connective"] = data["connective"]
    result["values"] = data["values"]
    result["status"] = "calculated"
    result["confidence"] = "low"
    
    # Basit mantık işlemleri
    p_val = data["values"].get("p")
    q_val = data["values"].get("q")
    
    if p_val is not None and q_val is not None:
        if data["connective"] == "and":
            result["logic_result"] = p_val and q_val
            result["sympy_answer"] = "Doğru" if result["logic_result"] else "Yanlış"
        elif data["connective"] == "or":
            result["logic_result"] = p_val or q_val
            result["sympy_answer"] = "Doğru" if result["logic_result"] else "Yanlış"
        elif data["connective"] == "implies":
            result["logic_result"] = (not p_val) or q_val
            result["sympy_answer"] = "Doğru" if result["logic_result"] else "Yanlış"
    
    return result


# ============================================================
# DİĞER DOĞRULAYICILAR
# ============================================================

def verify_prime(question: Dict) -> Dict[str, Any]:
    """Asal sayı doğrulama"""
    result = _init_result("asal")
    
    text = (question.get("original_text") or "")
    numbers = extract_numbers_from_text(text)
    
    if numbers:
        n = max(numbers)
        result["number"] = n
        result["is_prime"] = isprime(n)
        result["prime_factors"] = list(primefactors(n))
        result["status"] = "calculated"
        result["confidence"] = "high"
        
        # Aralıktaki asallar
        if "arasında" in text.lower() and len(numbers) >= 2:
            a, b = min(numbers[:2]), max(numbers[:2])
            primes = [i for i in range(a, b+1) if isprime(i)]
            result["primes_in_range"] = primes
            result["prime_count"] = len(primes)
            if "kaç" in text.lower():
                result["sympy_answer"] = len(primes)
    
    return result


def verify_exponent(question: Dict) -> Dict[str, Any]:
    """Üslü sayı doğrulama"""
    result = _init_result("uslu")
    
    text = (question.get("original_text") or "")
    
    # a^b veya a² formatı
    match = re.search(r'(\d+)\s*[\^]\s*(\d+)', text)
    if not match:
        # Unicode üst simge
        superscript = {'²': 2, '³': 3, '⁴': 4, '⁵': 5}
        for char, exp in superscript.items():
            m = re.search(rf'(\d+){char}', text)
            if m:
                match = (m.group(1), str(exp))
                break
    
    if match:
        base = int(match[0] if isinstance(match, tuple) else match.group(1))
        exp = int(match[1] if isinstance(match, tuple) else match.group(2))
        
        result["base"] = base
        result["exponent"] = exp
        result["sympy_answer"] = base ** exp
        result["status"] = "calculated"
        result["confidence"] = "high"
        
        _compare_answer(question, result)
    
    return result


def verify_root(question: Dict) -> Dict[str, Any]:
    """Köklü sayı doğrulama"""
    result = _init_result("koklu")
    
    text = (question.get("original_text") or "")
    
    # √n formatı
    match = re.search(r'[√]\s*(\d+)', text)
    if not match:
        match = re.search(r'karekök\s*\(?\s*(\d+)', text.lower())
    
    if match:
        n = int(match.group(1))
        result["n"] = n
        result["sympy_answer"] = str(sqrt(n))
        result["decimal"] = float(sqrt(n))
        result["is_perfect_square"] = int(math.sqrt(n))**2 == n
        result["status"] = "calculated"
        result["confidence"] = "medium"
    
    return result


def verify_divisibility(question: Dict) -> Dict[str, Any]:
    """Bölünebilirlik doğrulama"""
    result = _init_result("bolunebilme")
    
    text = (question.get("original_text") or "")
    numbers = extract_numbers_from_text(text)
    
    if len(numbers) >= 2:
        a, b = numbers[0], numbers[1]
        
        result["dividend"] = a
        result["divisor"] = b
        result["is_divisible"] = a % b == 0
        result["quotient"] = a // b
        result["remainder"] = a % b
        result["status"] = "calculated"
        result["confidence"] = "high"
        
        if "kalan" in text.lower():
            result["sympy_answer"] = a % b
        elif "bölüm" in text.lower():
            result["sympy_answer"] = a // b
        
        _compare_answer(question, result)
    
    return result


def verify_general(question: Dict) -> Dict[str, Any]:
    """Genel doğrulama"""
    result = _init_result("genel")
    result["message"] = "Bu soru tipi için özel doğrulama yok"
    
    expected = get_correct_answer_value(question)
    if expected:
        result["expected_answer"] = expected
        result["status"] = "answer_found"
    
    return result


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def _init_result(question_type: str) -> Dict[str, Any]:
    """Sonuç dictionary'si başlat"""
    return {
        "status": "not_verifiable",
        "question_type": question_type,
        "is_correct": None,
        "confidence": "none",
        "sympy_answer": None,
        "expected_answer": None,
        "message": None
    }


def _compare_answer(question: Dict, result: Dict) -> None:
    """Beklenen cevapla karşılaştır"""
    expected = get_correct_answer_value(question)
    
    if expected and result.get("sympy_answer") is not None:
        result["expected_answer"] = expected
        expected_num = clean_number(expected)
        sympy_num = clean_number(str(result["sympy_answer"]))
        
        if expected_num is not None and sympy_num is not None:
            result["is_correct"] = abs(sympy_num - expected_num) < 0.0001
            result["status"] = "verified"
            
            if result["is_correct"]:
                result["message"] = f"✓ Doğrulandı: {result['sympy_answer']}"
            else:
                result["message"] = f"✗ Beklenen: {expected}, Hesaplanan: {result['sympy_answer']}"
