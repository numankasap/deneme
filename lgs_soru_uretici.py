#!/usr/bin/env python3
"""
LGS Matematik Soru Üretici Bot
8. sınıf öğrencileri için senaryolu, otantik matematik soruları üretir.
Supabase question_bank tablosuna kaydeder.
"""

import os
import sys
import json
import random
import hashlib
import argparse
from datetime import datetime
from typing import Dict, List, Optional
import io

# ==================== YAPILANDIRMA ====================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DIFFICULTY_LEVELS = {
    "kolay": {"steps": 2, "min_words": 100, "difficulty_value": 2},
    "orta": {"steps": 3, "min_words": 120, "difficulty_value": 3},
    "zor": {"steps": 4, "min_words": 150, "difficulty_value": 4}
}

BLOOM_LEVELS = ["Uygulama", "Analiz", "Sentez", "Değerlendirme"]
PISA_CONTEXTS = ["Kişisel", "Mesleki", "Toplumsal", "Bilimsel"]
MATHEMATICAL_PROCESSES = ["Formüle Etme", "Uygulama", "Yorumlama"]

LIFE_SKILL_CATEGORIES = [
    "Finansal Okuryazarlık", "Problem Çözme", "Eleştirel Düşünme",
    "Veri Analizi", "Karar Verme", "Planlama", "Kaynak Yönetimi"
]

SCENARIO_THEMES = [
    "market_alisveris", "spor_aktivite", "okul_proje", "aile_etkinlik",
    "seyahat_planlama", "tasarruf_hesap", "yemek_tarif", "insaat_proje",
    "bahce_duzenleme", "teknoloji_uygulama", "cevre_koruma", "enerji_tasarrufu",
    "su_tuketimi", "ulasim_plani", "kargo_teslimat", "sinema_bilet"
]

GRADE_8_UNITS = {
    "unite1": {"name": "Çarpanlar ve Katlar", "topics": ["EBOB", "EKOK"], "topic_group": "sayilar_islemler"},
    "unite2": {"name": "Üslü İfadeler", "topics": ["Tam Sayı Üslü İfadeler"], "topic_group": "sayilar_islemler"},
    "unite3": {"name": "Kareköklü İfadeler", "topics": ["Karekök", "Kareköklü İşlemler"], "topic_group": "sayilar_islemler"},
    "unite4": {"name": "Veri Analizi", "topics": ["Çizgi Grafik", "Sütun Grafik", "Daire Grafik"], "topic_group": "veri_isleme"},
    "unite5": {"name": "Olasılık", "topics": ["Deneysel Olasılık", "Teorik Olasılık"], "topic_group": "olasilik"},
    "unite6": {"name": "Cebirsel İfadeler", "topics": ["Özdeşlikler", "Çarpanlara Ayırma"], "topic_group": "cebir"},
    "unite7": {"name": "Doğrusal Denklemler", "topics": ["Birinci Dereceden Denklemler"], "topic_group": "cebir"},
    "unite8": {"name": "Eşitsizlikler", "topics": ["Birinci Dereceden Eşitsizlikler"], "topic_group": "cebir"},
    "unite9": {"name": "Üçgenler", "topics": ["Pisagor Teoremi", "Benzerlik"], "topic_group": "geometri"},
    "unite10": {"name": "Dönüşüm Geometrisi", "topics": ["Yansıma", "Öteleme", "Dönme"], "topic_group": "geometri"},
    "unite11": {"name": "Geometrik Cisimler", "topics": ["Prizma", "Silindir", "Koni", "Küre"], "topic_group": "geometri"},
    "unite12": {"name": "Eğim", "topics": ["Doğrunun Eğimi"], "topic_group": "cebir"}
}


# ==================== SUPABASE İŞLEMLERİ ====================

class SupabaseDB:
    def __init__(self):
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL ve SUPABASE_KEY gerekli!")
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    def get_kazanimlar_by_ids(self, ids: List[str]) -> List[Dict]:
        return self.client.table("meb_kazanimlar").select("*").in_("id", ids).execute().data
    
    def get_grade8_kazanimlar(self, topic_group: str = None) -> List[Dict]:
        query = self.client.table("meb_kazanimlar").select("*").eq("grade", 8)
        if topic_group:
            query = query.ilike("topic_group", f"%{topic_group}%")
        return query.limit(20).execute().data
    
    def insert_question(self, data: Dict) -> Dict:
        response = self.client.table("question_bank").insert(data).execute()
        return response.data[0] if response.data else None
    
    def question_exists(self, title: str) -> bool:
        response = self.client.table("question_bank").select("id").eq("title", title).limit(1).execute()
        return len(response.data) > 0
    
    def upload_image(self, question_id: int, svg_data: bytes) -> str:
        bucket = "question-images"
        path = f"questions/q_{question_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.svg"
        self.client.storage.from_(bucket).upload(path, svg_data, {"content-type": "image/svg+xml"})
        url = self.client.storage.from_(bucket).get_public_url(path)
        self.client.table("question_bank").update({"image_url": url}).eq("id", question_id).execute()
        return url


# ==================== AI SORU ÜRETİCİ ====================

class QuestionGenerator:
    def __init__(self):
        import google.generativeai as genai
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY gerekli!")
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
    
    def _system_prompt(self) -> str:
        return """Sen bir LGS matematik soru yazarısın.

GÖREV: 8. sınıf için otantik, senaryolu matematik soruları üret.

KURALLAR:
1. scenario_text: EN AZ 120 kelime gerçekçi senaryo (TEK SATIRDA, satır sonu YOK)
2. original_text: Senaryoya dayalı matematiksel soru
3. 3-4 adımda çözülebilmeli
4. 4 seçenek (A,B,C,D), sadece biri doğru
5. Her çeldirici için neden yanlış açıkla
6. Türkçe dil bilgisi kurallarına uygun

ÖNEMLİ JSON KURALLARI:
- Tüm string değerler TEK SATIRDA olmalı
- String içinde satır sonu KULLANMA
- String içinde çift tırnak yerine tek tırnak kullan
- Sayısal değerler tırnak içinde OLMAMALI

ÖRNEK FORMAT:
{"title":"Market Alışverişi","scenario_text":"Ahmet markete gitti. Rafları inceledi. 3 kg elma aldı...","original_text":"Ahmet toplam kaç TL ödedi?","options":{"A":"45 TL","B":"50 TL","C":"55 TL","D":"60 TL"},"correct_answer":"B","distractor_explanations":{"A":"KDV eklenmedi","B":"Doğru cevap","C":"Fazla hesaplandı","D":"İki kat alındı"},"solution_short":"3x10+20=50 TL","solution_detailed":"1. Elmalar: 3x10=30 TL. 2. Diğer: 20 TL. 3. Toplam: 30+20=50 TL","difficulty":3,"bloom_level":"Uygulama","pisa_level":3,"pisa_context":"Kişisel","mathematical_process":"Uygulama","life_skill_category":"Finansal Okuryazarlık","visual_needed":false,"visual_description":""}

Sadece JSON döndür, başka açıklama YAZMA."""
    
    def _topic_prompt(self, kazanim: Dict, difficulty: str) -> str:
        cfg = DIFFICULTY_LEVELS.get(difficulty, DIFFICULTY_LEVELS["orta"])
        theme = random.choice(SCENARIO_THEMES).replace("_", " ").title()
        bloom = random.choice(BLOOM_LEVELS)
        pisa = random.choice(PISA_CONTEXTS)
        
        return f"""
KAZANIM: {kazanim.get('id', '')} - {kazanim.get('description', kazanim.get('topic', ''))}
KONU: {kazanim.get('topic', 'Matematik')}
ZORLUK: {difficulty.upper()} (Adım: {cfg['steps']}, Min kelime: {cfg['min_words']})
TEMA: {theme}
BLOOM: {bloom}
PISA: {pisa}

Yukarıdaki kurallara uygun BİR soru üret, JSON döndür."""
    
    def _clean_json(self, text: str) -> str:
        """JSON string'i temizle ve düzelt"""
        import re
        
        # Markdown kod bloklarını kaldır
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
        
        text = text.strip()
        
        # JSON başlangıç ve bitişini bul
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
        
        # Satır sonlarını ve tab'ları temizle
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        
        # Çift boşlukları tek boşluğa indir
        while '  ' in text:
            text = text.replace('  ', ' ')
        
        # String içindeki sorunlu karakterleri düzelt
        # Escape edilmemiş tırnak işaretlerini düzelt
        text = re.sub(r'(?<!\\)"([^"]*?)(?<!\\)"', lambda m: '"' + m.group(1).replace('"', '\\"') + '"', text)
        
        return text
    
    def generate(self, kazanim: Dict, difficulty: str = "orta") -> Optional[Dict]:
        import google.generativeai as genai
        try:
            response = self.model.generate_content(
                f"{self._system_prompt()}\n\n{self._topic_prompt(kazanim, difficulty)}",
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Daha düşük sıcaklık = daha tutarlı çıktı
                    max_output_tokens=4000,
                    candidate_count=1
                )
            )
            
            text = response.text
            text = self._clean_json(text)
            
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                # İkinci deneme: daha agresif temizlik
                import re
                # Tüm kontrol karakterlerini kaldır
                text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
                # String içindeki yeni satırları \n ile değiştir
                text = re.sub(r'"([^"]*)"', lambda m: '"' + m.group(1).replace('\n', '\\n') + '"', text)
                data = json.loads(text)
            
            # Validasyon
            if len(data.get("scenario_text", "").split()) < 100:
                print("  ✗ Senaryo çok kısa")
                return None
            if data.get("correct_answer") not in ["A", "B", "C", "D"]:
                print("  ✗ Geçersiz cevap")
                return None
            
            data["kazanim_kodu"] = kazanim.get("id", kazanim.get("kazanim_kodu"))
            data["kazanim_id"] = kazanim.get("kazanim_id", kazanim.get("id"))
            data["topic"] = kazanim.get("topic", "Matematik")
            data["topic_group"] = kazanim.get("topic_group", "")
            
            return data
        except Exception as e:
            print(f"  ✗ Hata: {e}")
            return None
    
    def generate_batch(self, kazanim: Dict, count: int, difficulty: str) -> List[Dict]:
        questions = []
        for i in range(count * 3):
            if len(questions) >= count:
                break
            diff = random.choice(["kolay", "orta", "zor"]) if difficulty == "karisik" else difficulty
            q = self.generate(kazanim, diff)
            if q and not any(x.get("title") == q.get("title") for x in questions):
                questions.append(q)
                print(f"  ✓ Soru {len(questions)}/{count}")
        return questions
    
    def format_for_db(self, q: Dict) -> Dict:
        return {
            "title": q.get("title", "")[:500],
            "original_text": q.get("original_text", ""),
            "scenario_text": q.get("scenario_text", ""),
            "options": q.get("options", {}),
            "correct_answer": q.get("correct_answer", ""),
            "distractor_explanations": q.get("distractor_explanations", {}),
            "solution_short": q.get("solution_short", ""),
            "solution_detailed": q.get("solution_detailed", ""),
            "solution_text": q.get("solution_detailed", ""),
            "difficulty": q.get("difficulty", 3),
            "subject": "Matematik",
            "grade_level": 8,
            "topic": q.get("topic", "Genel"),
            "topic_group": q.get("topic_group", ""),
            "kazanim_kodu": q.get("kazanim_kodu"),
            "kazanim_id": q.get("kazanim_id"),
            "question_type": "senaryo",
            "bloom_level": q.get("bloom_level", "Uygulama"),
            "pisa_level": q.get("pisa_level", 3),
            "pisa_context": q.get("pisa_context", "Kişisel"),
            "mathematical_process": q.get("mathematical_process", "Uygulama"),
            "life_skill_category": q.get("life_skill_category", "Problem Çözme"),
            "is_past_exam": False,
            "verified": False,
            "is_active": True
        }


# ==================== GÖRSEL ÜRETİCİ ====================

class VisualGenerator:
    def __init__(self):
        import matplotlib
        matplotlib.use('Agg')
    
    def generate(self, question: Dict) -> Optional[str]:
        if not question.get("visual_needed"):
            return None
        
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
        
        fig, ax = plt.subplots(figsize=(7, 4))
        box = FancyBboxPatch((0.5, 1), 6, 2, boxstyle="round,pad=0.1",
                              facecolor='#e0e7ff', edgecolor='#6366f1', linewidth=3)
        ax.add_patch(box)
        ax.text(3.5, 2, question.get("title", "Soru")[:40], fontsize=11, ha='center', va='center', fontweight='bold')
        ax.set_xlim(0, 7); ax.set_ylim(0, 4); ax.axis('off')
        
        buf = io.BytesIO()
        fig.savefig(buf, format='svg', bbox_inches='tight', transparent=True)
        buf.seek(0)
        svg = buf.read().decode('utf-8')
        plt.close(fig)
        
        if '<?xml' in svg:
            svg = svg[svg.find('<svg'):]
        return svg


# ==================== ANA FONKSİYON ====================

def get_kazanimlar(ids: str, topic_group: str, db) -> List[Dict]:
    if db:
        if ids and ids != "auto":
            id_list = [x.strip() for x in ids.split(",")]
            return db.get_kazanimlar_by_ids(id_list) or []
        kazanimlar = db.get_grade8_kazanimlar(topic_group if topic_group != "all" else None)
        if kazanimlar:
            return kazanimlar[:10]
    
    # Fallback
    result = []
    for key, unit in list(GRADE_8_UNITS.items())[:3]:
        if topic_group == "all" or unit["topic_group"] == topic_group:
            for i, topic in enumerate(unit["topics"][:2]):
                result.append({
                    "id": f"M.8.{key}.{i+1}",
                    "description": f"{topic} problemleri çözer",
                    "topic": unit["name"],
                    "topic_group": unit["topic_group"]
                })
    return result[:5]


def main():
    parser = argparse.ArgumentParser(description='LGS Soru Üretici')
    parser.add_argument('--kazanim-ids', '-k', default='auto')
    parser.add_argument('--count', '-n', type=int, default=5)
    parser.add_argument('--difficulty', '-d', choices=['kolay', 'orta', 'zor', 'karisik'], default='orta')
    parser.add_argument('--topic-group', '-t', choices=['all', 'sayilar_islemler', 'cebir', 'geometri', 'veri_isleme', 'olasilik'], default='all')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', '-o', default='reports')
    args = parser.parse_args()
    
    print("=" * 50)
    print("🚀 LGS Soru Üretici Bot")
    print("=" * 50)
    
    start = datetime.now()
    
    # Bileşenler
    try:
        generator = QuestionGenerator()
    except Exception as e:
        print(f"❌ Generator hatası: {e}")
        return 1
    
    db = None
    if not args.dry_run:
        try:
            db = SupabaseDB()
        except:
            print("⚠️ DB bağlantısı yok, dry-run modu")
            args.dry_run = True
    
    visual_gen = VisualGenerator()
    
    # Kazanımlar
    kazanimlar = get_kazanimlar(args.kazanim_ids, args.topic_group, db)
    print(f"\n📚 {len(kazanimlar)} kazanım bulundu")
    
    results = {"generated": 0, "saved": 0, "failed": 0}
    all_questions = []
    
    for i, kaz in enumerate(kazanimlar, 1):
        print(f"\n📌 [{i}/{len(kazanimlar)}] {kaz.get('id', 'K')} - {kaz.get('topic', '')[:30]}")
        
        questions = generator.generate_batch(kaz, args.count, args.difficulty)
        results["generated"] += len(questions)
        
        for q in questions:
            # Görsel
            if q.get("visual_needed"):
                svg = visual_gen.generate(q)
                if svg:
                    q["svg_content"] = svg
            
            if args.dry_run:
                all_questions.append(generator.format_for_db(q))
                results["saved"] += 1
            elif db:
                try:
                    record = generator.format_for_db(q)
                    if not db.question_exists(record["title"]):
                        saved = db.insert_question(record)
                        if saved:
                            results["saved"] += 1
                            if q.get("svg_content"):
                                db.upload_image(saved["id"], q["svg_content"].encode())
                        else:
                            results["failed"] += 1
                except Exception as e:
                    print(f"  ❌ Kayıt hatası: {e}")
                    results["failed"] += 1
    
    # Dry-run kaydet
    if args.dry_run and all_questions:
        os.makedirs(args.output, exist_ok=True)
        path = os.path.join(args.output, f'questions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(all_questions, f, ensure_ascii=False, indent=2)
        print(f"\n📁 Kaydedildi: {path}")
    
    # Özet
    duration = (datetime.now() - start).total_seconds()
    print(f"""
{'='*50}
📊 SONUÇ
{'='*50}
✅ Üretilen: {results['generated']}
✅ Kaydedilen: {results['saved']}
❌ Başarısız: {results['failed']}
⏱️ Süre: {duration:.1f}s
{'='*50}
🎉 Tamamlandı!
""")
    
    return 0 if results["failed"] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
