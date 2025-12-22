"""
MATAI PRO - Embedding Bot
Soru bankasındaki soruları Gemini ile vektörel formata çevirir

Çalışma: Günde 4 kez, her seferinde 50 soru
Model: Gemini text-embedding-004 (768 boyut)
"""

import os
import json
import time
from datetime import datetime
from supabase import create_client, Client
import google.generativeai as genai

# ============== YAPILANDIRMA ==============
CONFIG = {
    "BATCH_SIZE": 50,                      # Her çalışmada işlenecek soru sayısı
    "EMBEDDING_MODEL": "text-embedding-004",  # Gemini embedding modeli
    "MAX_TEXT_LENGTH": 8000,               # Max karakter
    "RETRY_ATTEMPTS": 3,                   # Hata durumunda tekrar deneme
    "RETRY_DELAY": 2,                      # Tekrar deneme arası bekleme (saniye)
}

# ============== İSTEMCİLER ==============
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY")
)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))


def build_embedding_text(question: dict) -> str:
    """Soru verilerinden embedding için zengin metin oluşturur"""
    parts = []
    
    # Konu bilgisi (semantic context için önemli)
    if question.get("subject"):
        parts.append(f"Ders: {question['subject']}")
    if question.get("topic_group"):
        parts.append(f"Konu Grubu: {question['topic_group']}")
    if question.get("topic"):
        parts.append(f"Alt Konu: {question['topic']}")
    if question.get("kazanim_kodu"):
        parts.append(f"Kazanım: {question['kazanim_kodu']}")
    
    # Seviye bilgileri
    if question.get("grade_level"):
        parts.append(f"Sınıf: {question['grade_level']}")
    if question.get("difficulty"):
        parts.append(f"Zorluk: {question['difficulty']}/5")
    if question.get("bloom_level"):
        parts.append(f"Bloom: {question['bloom_level']}")
    if question.get("pisa_level"):
        parts.append(f"PISA Seviye: {question['pisa_level']}")
    
    # Senaryo (varsa)
    if question.get("scenario_text"):
        parts.append(f"Senaryo: {question['scenario_text']}")
    
    # Ana soru metni
    if question.get("original_text"):
        parts.append(f"Soru: {question['original_text']}")
    elif question.get("title"):
        parts.append(f"Soru: {question['title']}")
    
    # Şıklar
    options = question.get("options")
    if options and isinstance(options, dict):
        options_text = " | ".join([f"{k}) {v}" for k, v in options.items()])
        parts.append(f"Şıklar: {options_text}")
    
    # Çözüm
    if question.get("solution_short"):
        parts.append(f"Çözüm: {question['solution_short']}")
    elif question.get("solution_text"):
        parts.append(f"Çözüm: {question['solution_text']}")
    
    # Doğru cevap
    if question.get("correct_answer"):
        parts.append(f"Doğru Cevap: {question['correct_answer']}")
    
    # Birleştir ve uzunluğu kontrol et
    full_text = "\n\n".join(parts)
    
    if len(full_text) > CONFIG["MAX_TEXT_LENGTH"]:
        full_text = full_text[:CONFIG["MAX_TEXT_LENGTH"]] + "..."
    
    return full_text


def get_embedding(text: str, retry_count: int = 0) -> list:
    """Gemini API ile embedding oluşturur (retry mekanizmalı)"""
    try:
        result = genai.embed_content(
            model=f"models/{CONFIG['EMBEDDING_MODEL']}",
            content=text
        )
        return result['embedding']
    except Exception as e:
        if retry_count < CONFIG["RETRY_ATTEMPTS"]:
            print(f"⚠️  Embedding hatası, tekrar deneniyor ({retry_count + 1}/{CONFIG['RETRY_ATTEMPTS']})...")
            time.sleep(CONFIG["RETRY_DELAY"] * (retry_count + 1))
            return get_embedding(text, retry_count + 1)
        raise e


def vector_to_postgres(vector: list) -> str:
    """Vector'ü PostgreSQL formatına çevirir"""
    return f"[{','.join(map(str, vector))}]"


def process_embeddings():
    """Ana işlem fonksiyonu"""
    start_time = time.time()
    
    print("\n" + "=" * 60)
    print("🚀 MATAI PRO Embedding Bot Başlatıldı")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    try:
        # 1. Embedding'i NULL olan soruları getir
        print(f"📥 Embedding bekleyen sorular alınıyor (limit: {CONFIG['BATCH_SIZE']})...")
        
        response = supabase.table("question_bank") \
            .select("id, title, original_text, options, solution_text, solution_short, subject, topic, topic_group, grade_level, difficulty, kazanim_kodu, bloom_level, pisa_level, scenario_text, correct_answer") \
            .is_("embedding", "null") \
            .eq("is_active", True) \
            .limit(CONFIG["BATCH_SIZE"]) \
            .execute()
        
        questions = response.data
        
        if not questions:
            print("✅ Tüm sorular zaten embed edilmiş! İşlem tamamlandı.\n")
            return {"processed": 0, "failed": 0, "remaining": 0}
        
        print(f"📊 {len(questions)} soru bulundu, işleniyor...\n")
        
        # 2. Her soru için embedding oluştur
        processed = 0
        failed = 0
        errors = []
        
        for question in questions:
            try:
                # Embedding metni oluştur
                embedding_text = build_embedding_text(question)
                
                if not embedding_text or len(embedding_text.strip()) < 10:
                    print(f"⚠️  Soru #{question['id']}: Yetersiz metin, atlanıyor")
                    failed += 1
                    continue
                
                # Gemini'den embedding al
                embedding = get_embedding(embedding_text)
                
                # Supabase'e kaydet
                supabase.table("question_bank") \
                    .update({"embedding": vector_to_postgres(embedding)}) \
                    .eq("id", question["id"]) \
                    .execute()
                
                processed += 1
                progress = round((processed / len(questions)) * 100)
                topic = question.get("topic") or "Genel"
                print(f"✓ Soru #{question['id']} embed edildi [{progress}%] - {topic}")
                
                # Rate limit için kısa bekleme
                time.sleep(0.1)
                
            except Exception as e:
                failed += 1
                errors.append({"id": question["id"], "error": str(e)})
                print(f"✗ Soru #{question['id']} HATA: {str(e)}")
        
        # 3. Kalan soru sayısını kontrol et
        remaining_response = supabase.table("question_bank") \
            .select("id", count="exact") \
            .is_("embedding", "null") \
            .eq("is_active", True) \
            .execute()
        
        remaining_count = remaining_response.count or 0
        
        # 4. Sonuç raporu
        duration = round(time.time() - start_time, 1)
        
        print("\n" + "=" * 60)
        print("📊 İŞLEM RAPORU")
        print("=" * 60)
        print(f"✅ Başarılı: {processed} soru")
        print(f"❌ Başarısız: {failed} soru")
        print(f"⏳ Kalan: {remaining_count} soru")
        print(f"⏱️  Süre: {duration} saniye")
        print("=" * 60 + "\n")
        
        if errors:
            print("📋 Hata Detayları:")
            for e in errors:
                print(f"   - Soru #{e['id']}: {e['error']}")
        
        # 5. Log kaydı (opsiyonel)
        try:
            supabase.table("bot_logs").insert({
                "bot_name": "embedding_bot",
                "status": "success" if failed == 0 else "partial",
                "processed_count": processed,
                "failed_count": failed,
                "remaining_count": remaining_count,
                "duration_seconds": duration,
                "details": {"errors": errors} if errors else None,
                "created_at": datetime.now().isoformat()
            }).execute()
        except Exception as log_error:
            print("ℹ️  Log kaydı atlandı (bot_logs tablosu mevcut değil)")
        
        return {"processed": processed, "failed": failed, "remaining": remaining_count}
        
    except Exception as e:
        print(f"\n❌ KRİTİK HATA: {str(e)}")
        raise e


if __name__ == "__main__":
    try:
        result = process_embeddings()
        print("🎉 Bot başarıyla tamamlandı!")
    except Exception as e:
        print(f"💥 Bot hatası: {str(e)}")
        exit(1)
