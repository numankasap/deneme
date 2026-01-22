"""
SymPy Soru Doğrulama Sistemi
MATAİ PRO - question_bank tablosu için

Kullanım:
    python main.py --limit 100
    python main.py --topic "EKOK"
    python main.py --id 16180
"""

import os
import json
import argparse
from datetime import datetime, timezone
from supabase import create_client
from verifiers import verify_question
from parsers import extract_numbers_from_text, detect_question_type

# Supabase bağlantısı
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL ve SUPABASE_SERVICE_KEY environment variable'ları gerekli!")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_questions(limit=100, topic_filter=None, question_id=None, only_unverified=False):
    """Doğrulanacak soruları çek"""
    
    query = supabase.table("question_bank").select(
        "id, original_text, options, correct_answer, solution_text, "
        "solution_short, solution_detailed, topic, topic_group, grade_level"
    )
    
    # Filtreler
    if question_id:
        query = query.eq("id", question_id)
    elif topic_filter:
        query = query.ilike("topic", f"%{topic_filter}%")
    
    if only_unverified:
        query = query.eq("verified", False)
    
    query = query.eq("is_active", True).limit(limit)
    
    response = query.execute()
    return response.data


def update_verification_result(question_id, result):
    """Doğrulama sonucunu veritabanına yaz"""
    
    update_data = {
        "sympy_verification": result,
        "sympy_verified_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Eğer doğrulama başarılıysa verified'ı da güncelle
    if result.get("is_correct") and result.get("confidence") == "high":
        update_data["verified"] = True
        update_data["verified_at"] = datetime.now(timezone.utc).isoformat()
    
    supabase.table("question_bank").update(update_data).eq("id", question_id).execute()


def process_questions(questions, verbose=True):
    """Soruları işle ve doğrula"""
    
    stats = {
        "total": len(questions),
        "verified_correct": 0,
        "verified_incorrect": 0,
        "not_verifiable": 0,
        "errors": 0
    }
    
    results = []
    
    for i, q in enumerate(questions, 1):
        if verbose:
            print(f"\n{'='*60}")
            print(f"[{i}/{len(questions)}] Soru ID: {q['id']}")
            print(f"Konu: {q.get('topic', 'Belirtilmemiş')[:50]}...")
        
        try:
            # Soru tipini belirle
            question_type = detect_question_type(q)
            
            if verbose:
                print(f"Soru Tipi: {question_type}")
            
            # Doğrulama yap
            result = verify_question(q, question_type)
            
            # Sonucu kaydet
            update_verification_result(q['id'], result)
            
            # İstatistikleri güncelle
            if result.get("status") == "verified":
                if result.get("is_correct"):
                    stats["verified_correct"] += 1
                    status_icon = "✅"
                else:
                    stats["verified_incorrect"] += 1
                    status_icon = "❌"
            elif result.get("status") == "not_verifiable":
                stats["not_verifiable"] += 1
                status_icon = "⚠️"
            else:
                stats["errors"] += 1
                status_icon = "🔴"
            
            if verbose:
                print(f"Durum: {status_icon} {result.get('status')}")
                print(f"Beklenen: {q.get('correct_answer')}")
                print(f"SymPy Sonuç: {result.get('sympy_answer')}")
                if result.get("message"):
                    print(f"Mesaj: {result.get('message')}")
            
            results.append({
                "id": q['id'],
                "status": result.get("status"),
                "is_correct": result.get("is_correct"),
                "result": result
            })
            
        except Exception as e:
            stats["errors"] += 1
            if verbose:
                print(f"🔴 Hata: {str(e)}")
            
            error_result = {
                "status": "error",
                "error": str(e),
                "is_correct": None
            }
            update_verification_result(q['id'], error_result)
            results.append({
                "id": q['id'],
                "status": "error",
                "error": str(e)
            })
    
    return stats, results


def print_summary(stats):
    """Özet istatistikleri yazdır"""
    
    print("\n" + "="*60)
    print("📊 DOĞRULAMA ÖZETİ")
    print("="*60)
    print(f"Toplam Soru      : {stats['total']}")
    print(f"✅ Doğru         : {stats['verified_correct']}")
    print(f"❌ Yanlış        : {stats['verified_incorrect']}")
    print(f"⚠️  Doğrulanamaz : {stats['not_verifiable']}")
    print(f"🔴 Hata          : {stats['errors']}")
    
    if stats['total'] > 0:
        success_rate = (stats['verified_correct'] / stats['total']) * 100
        print(f"\n📈 Başarı Oranı: %{success_rate:.1f}")


def main():
    parser = argparse.ArgumentParser(description='SymPy Soru Doğrulama Sistemi')
    parser.add_argument('--limit', type=int, default=100, help='İşlenecek soru sayısı')
    parser.add_argument('--topic', type=str, help='Konu filtresi (örn: EKOK, denklem)')
    parser.add_argument('--id', type=int, help='Belirli bir soru ID')
    parser.add_argument('--unverified', action='store_true', help='Sadece doğrulanmamış soruları işle')
    parser.add_argument('--quiet', action='store_true', help='Sessiz mod')
    
    args = parser.parse_args()
    
    verbose = not args.quiet
    
    if verbose:
        print("🔬 SymPy Soru Doğrulama Sistemi Başlatılıyor...")
        print(f"Limit: {args.limit}, Konu: {args.topic or 'Tümü'}")
    
    # Soruları çek
    questions = get_questions(
        limit=args.limit,
        topic_filter=args.topic,
        question_id=args.id,
        only_unverified=args.unverified
    )
    
    if not questions:
        print("❌ Hiç soru bulunamadı!")
        return
    
    if verbose:
        print(f"\n📋 {len(questions)} soru bulundu, işleniyor...")
    
    # Soruları işle
    stats, results = process_questions(questions, verbose=verbose)
    
    # Özet yazdır
    print_summary(stats)
    
    # Yanlış soruları listele
    incorrect = [r for r in results if r.get("is_correct") == False]
    if incorrect and verbose:
        print("\n⚠️  YANLIŞ BULUNAN SORULAR:")
        for r in incorrect:
            print(f"  - ID: {r['id']}")


if __name__ == "__main__":
    main()
