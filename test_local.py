"""
Test Script - SymPy Doğrulama Sistemi v2
Tüm soru tiplerini test eder
"""

from verifiers import verify_question
from parsers import detect_question_type
import json

# ============================================================
# TEST SORULARI - Her tip için örnek
# ============================================================

TEST_QUESTIONS = {
    "ekok": {
        "original_text": "18 günde bir ve 24 günde bir yapılan işler kaç gün sonra aynı anda yapılır?",
        "options": {"A": "72", "B": "6", "C": "42", "D": "144"},
        "solution_text": "EKOK(18, 24) = 72",
        "correct_answer": "A",
        "expected_result": 72
    },
    
    "ebob": {
        "original_text": "36 ve 48 sayılarının EBOB'u kaçtır?",
        "options": {"A": "6", "B": "12", "C": "24", "D": "144"},
        "solution_text": "EBOB(36, 48) = 12",
        "correct_answer": "B",
        "expected_result": 12
    },
    
    "mutlak_deger": {
        "original_text": "|x - 5| = 3 denkleminin köklerinin toplamı kaçtır?",
        "options": {"A": "8", "B": "10", "C": "12", "D": "6"},
        "solution_text": "x = 8 veya x = 2, toplam = 10",
        "correct_answer": "B",
        "expected_result": 10
    },
    
    "basamak": {
        "original_text": "4725 sayısının rakamları toplamı kaçtır?",
        "options": {"A": "16", "B": "17", "C": "18", "D": "19"},
        "solution_text": "4 + 7 + 2 + 5 = 18",
        "correct_answer": "C",
        "expected_result": 18
    },
    
    "faktoriyel": {
        "original_text": "5! kaçtır?",
        "options": {"A": "60", "B": "100", "C": "120", "D": "150"},
        "solution_text": "5! = 120",
        "correct_answer": "C",
        "expected_result": 120
    },
    
    "carpanlara_ayirma": {
        "original_text": "72 sayısının kaç tane pozitif böleni vardır?",
        "options": {"A": "10", "B": "12", "C": "14", "D": "8"},
        "solution_text": "72 = 2³ × 3², bölen sayısı = 12",
        "correct_answer": "B",
        "expected_result": 12
    },
    
    "polinom": {
        "original_text": "P(x) = 2x² + 3x - 5 polinomunda P(2) kaçtır?",
        "options": {"A": "7", "B": "9", "C": "11", "D": "13"},
        "solution_text": "P(2) = 8 + 6 - 5 = 9",
        "correct_answer": "B",
        "expected_result": 9
    },
    
    "fonksiyon": {
        "original_text": "f(x) = 3x + 2 fonksiyonunda f(4) kaçtır?",
        "options": {"A": "12", "B": "14", "C": "16", "D": "10"},
        "solution_text": "f(4) = 12 + 2 = 14",
        "correct_answer": "B",
        "expected_result": 14
    },
    
    "kume": {
        "original_text": "A = {1, 2, 3, 4} ve B = {3, 4, 5, 6} kümeleri için A ∩ B kümesinin eleman sayısı kaçtır?",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "solution_text": "A ∩ B = {3, 4}, eleman sayısı = 2",
        "correct_answer": "B",
        "expected_result": 2
    },
    
    "kesir": {
        "original_text": "1/2 + 1/3 işleminin sonucu kaçtır?",
        "options": {"A": "2/5", "B": "5/6", "C": "1/6", "D": "2/3"},
        "solution_text": "3/6 + 2/6 = 5/6",
        "correct_answer": "B",
        "expected_result": "5/6"
    },
    
    "asal": {
        "original_text": "10 ile 20 arasında kaç tane asal sayı vardır?",
        "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
        "solution_text": "11, 13, 17, 19 → 4 tane",
        "correct_answer": "B",
        "expected_result": 4
    },
}


def run_all_tests():
    """Tüm testleri çalıştır"""
    
    print("=" * 70)
    print("🧪 SymPy Doğrulama Sistemi - Test Raporu")
    print("=" * 70)
    
    passed = 0
    failed = 0
    results = {}
    
    for name, question in TEST_QUESTIONS.items():
        expected = question.pop("expected_result")
        
        # Soru tipini tespit et
        detected_type = detect_question_type(question)
        
        # Doğrulama yap
        result = verify_question(question, detected_type)
        results[name] = result
        
        # Sonucu kontrol et
        sympy_answer = result.get("sympy_answer")
        
        # Karşılaştırma
        if isinstance(expected, str):
            is_pass = str(sympy_answer) == expected
        else:
            try:
                is_pass = abs(float(sympy_answer) - float(expected)) < 0.001
            except:
                is_pass = sympy_answer == expected
        
        # Rapor
        status = "✅" if is_pass else "❌"
        print(f"\n{status} {name.upper()}")
        print(f"   Tespit: {detected_type}")
        print(f"   SymPy : {sympy_answer}")
        print(f"   Beklenen: {expected}")
        
        if is_pass:
            passed += 1
        else:
            failed += 1
            print(f"   ⚠️  Durum: {result.get('status')}")
            if result.get('message'):
                print(f"   Mesaj: {result.get('message')}")
    
    # Özet
    print("\n" + "=" * 70)
    print("📊 TEST ÖZETİ")
    print("=" * 70)
    total = passed + failed
    print(f"   Toplam : {total}")
    print(f"   ✅ Başarılı : {passed}")
    print(f"   ❌ Başarısız: {failed}")
    print(f"   📈 Başarı Oranı: %{(passed/total)*100:.1f}")
    
    if failed == 0:
        print("\n🎉 TÜM TESTLER BAŞARILI!")
    
    return failed == 0


def test_type_detection():
    """Tip tespit testleri"""
    
    print("\n" + "=" * 70)
    print("🔍 TİP TESPİT TESTLERİ")
    print("=" * 70)
    
    tests = [
        ("18 ve 24'ün EKOK'u", "ekok"),
        ("EBOB(36, 48) kaçtır", "ebob"),
        ("|x - 5| = 3", "mutlak_deger"),
        ("rakamları toplamı", "basamak"),
        ("5! kaçtır", "faktoriyel"),
        ("asal çarpanlarına ayır", "carpanlara_ayirma"),
        ("P(x) = 2x + 1", "polinom"),
        ("f(x) = 3x fonksiyonu", "fonksiyon"),
        ("A ∩ B kümesi", "kume"),
        ("1/2 + 1/3 kesir", "kesir"),
    ]
    
    passed = 0
    for text, expected_type in tests:
        q = {"original_text": text, "solution_text": "", "topic": ""}
        detected = detect_question_type(q)
        status = "✅" if detected == expected_type else "❌"
        print(f"   {status} '{text[:30]}...' → {detected} (beklenen: {expected_type})")
        if detected == expected_type:
            passed += 1
    
    print(f"\n   Başarı: {passed}/{len(tests)}")


if __name__ == "__main__":
    test_type_detection()
    print()
    success = run_all_tests()
    exit(0 if success else 1)
