"""
Senaryo Görsel Botu v3.2
========================
YENİ ÖZELLİKLER:
- Gemini kalite puanlaması (soru + görsel)
- Kazanım filtresi (geometri dışlanır)
- Minimum puan kontrolü (7+)
- Soru metnini DEĞİŞTİRMEZ

HEDEF KAZANIMLAR:
✅ Sayılar ve İşlemler (EKOK, EBOB, üslü sayılar)
✅ Cebir (denklemler, fonksiyonlar → grafik)
✅ Veri İşleme (istatistik, olasılık → tablo, grafik)
✅ Problemler (senaryo bazlı)

❌ GEOMETRİ DIŞLANIYOR (ayrı bot ile işlenecek)
"""

import os
import json
import time
import logging
import math
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from string import Template

from supabase import create_client, Client

try:
    from google import genai
    from google.genai import types
    NEW_GENAI = True
except ImportError:
    import google.generativeai as genai
    NEW_GENAI = False

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    GEMINI_MODEL = 'gemini-2.5-pro'
    STORAGE_BUCKET = 'questions-images'
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30'))
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 5
    IMAGE_WIDTH = 900
    MIN_PNG_SIZE = 5000
    MIN_QUALITY_SCORE = 7  # Minimum kalite puanı


COLORS = {
    'blue': {'primary': '#3b82f6', 'light': '#dbeafe', 'dark': '#1e40af'},
    'pink': {'primary': '#ec4899', 'light': '#fce7f3', 'dark': '#9d174d'},
    'green': {'primary': '#22c55e', 'light': '#dcfce7', 'dark': '#166534'},
    'orange': {'primary': '#f59e0b', 'light': '#fef3c7', 'dark': '#92400e'},
    'purple': {'primary': '#8b5cf6', 'light': '#f3e8ff', 'dark': '#6b21a8'},
    'teal': {'primary': '#14b8a6', 'light': '#ccfbf1', 'dark': '#115e59'},
    'red': {'primary': '#ef4444', 'light': '#fee2e2', 'dark': '#991b1b'},
}


# ============== KAZANIM FİLTRESİ ==============

class LearningOutcomeFilter:
    """Kazanım filtresi - Geometri dışla, matematik/istatistik/problem al"""
    
    # GEOMETRİ KAZANIMLARI - DIŞLA
    GEOMETRY_PATTERNS = [
        r'M\.\d\.3\.',     # x.3. genelde geometri
        r'M\.[5-8]\.3\.',  # 5-8. sınıf geometri
        r'geometri',
        r'üçgen', r'dörtgen', r'çokgen',
        r'açı', r'kenar', r'köşegen',
        r'çember', r'daire',  # Bunlar geometri
        r'prizma', r'piramit', r'silindir', r'koni', r'küre',
        r'alan', r'çevre',  # Geometrik alan/çevre
        r'pythagoras', r'pisagor',
        r'benzerlik', r'eşlik',
        r'dönüşüm', r'öteleme', r'yansıma',
    ]
    
    # İZİN VERİLEN KONULAR
    ALLOWED_PATTERNS = [
        r'ekok', r'ebob', r'obeb', r'okek',
        r'üslü', r'köklü', r'faktöriyel',
        r'oran', r'orantı', r'yüzde',
        r'kar', r'zarar', r'faiz',
        r'fonksiyon', r'grafik',
        r'denklem', r'eşitsizlik',
        r'istatistik', r'veri', r'ortalama', r'medyan', r'mod',
        r'olasılık', r'permütasyon', r'kombinasyon',
        r'tablo', r'karşılaştır',
        r'problem', r'senaryo',
        r'hız', r'zaman', r'yol',
        r'işçi', r'havuz', r'musluk',
        r'yaş', r'para', r'fiyat',
    ]
    
    @classmethod
    def should_process(cls, question: Dict) -> Tuple[bool, str]:
        """Soru işlenmeli mi?"""
        text = (question.get('original_text', '') + ' ' + 
                question.get('scenario_text', '') + ' ' +
                question.get('learning_outcome', '') + ' ' +
                question.get('tags', '')).lower()
        
        # Geometri kontrolü
        for pattern in cls.GEOMETRY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"Geometri içeriği tespit edildi: {pattern}"
        
        # İzin verilen konu kontrolü (opsiyonel - şimdilik her şeyi al)
        has_allowed = False
        for pattern in cls.ALLOWED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                has_allowed = True
                break
        
        # Senaryo varsa ve geometri değilse işle
        if question.get('scenario_text'):
            return True, "Senaryo sorusu"
        
        # İzin verilen konu varsa işle
        if has_allowed:
            return True, "İzin verilen konu"
        
        return True, "Genel soru"  # Varsayılan olarak işle, Gemini karar verir


# ============== GEOMETRİ RENDERER ==============

class GeometryRenderer:
    """SVG geometrik şekiller - sadece tablo/grafik için basit şekiller"""
    
    @staticmethod
    def rectangle(label: str, dims: dict, color: dict, size: int = 180) -> str:
        """Dikdörtgen (tablo hücresi gibi)"""
        en = dims.get('en', dims.get('genislik', '?'))
        boy = dims.get('boy', dims.get('yukseklik', '?'))
        cx, cy = size // 2, size // 2
        rw, rh = size * 2 // 5, size * 3 // 5
        
        return f'''
        <div class="geo-card">
            <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
                <rect x="{cx-rw//2}" y="{cy-rh//2}" width="{rw}" height="{rh}" 
                      fill="{color['light']}" stroke="{color['primary']}" stroke-width="3" rx="4"/>
                <text x="{cx}" y="{cy-rh//2-12}" fill="#334155" font-size="11" font-weight="700" text-anchor="middle">{en}</text>
                <text x="{cx+rw//2+12}" y="{cy}" fill="#334155" font-size="11" font-weight="700">{boy}</text>
            </svg>
            <div class="geo-label" style="color:{color['dark']}">{label}</div>
        </div>'''
    
    @staticmethod
    def venn_diagram(label: str, sets: dict, color: dict, size: int = 220) -> str:
        """Venn diyagramı (EKOK/EBOB için)"""
        cx, cy = size // 2, size // 2
        r = size // 4
        
        set_a = sets.get('A', sets.get('a', '?'))
        set_b = sets.get('B', sets.get('b', '?'))
        intersection = sets.get('kesisim', sets.get('ortak', '?'))
        
        return f'''
        <div class="geo-card">
            <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
                <!-- Sol daire (A) -->
                <circle cx="{cx-r//2}" cy="{cy}" r="{r}" fill="{color['light']}" stroke="{color['primary']}" stroke-width="2" opacity="0.7"/>
                <!-- Sağ daire (B) -->
                <circle cx="{cx+r//2}" cy="{cy}" r="{r}" fill="#fce7f3" stroke="#ec4899" stroke-width="2" opacity="0.7"/>
                
                <!-- Etiketler -->
                <text x="{cx-r}" y="{cy}" fill="{color['dark']}" font-size="14" font-weight="700" text-anchor="middle">{set_a}</text>
                <text x="{cx+r}" y="{cy}" fill="#9d174d" font-size="14" font-weight="700" text-anchor="middle">{set_b}</text>
                <text x="{cx}" y="{cy}" fill="#334155" font-size="12" font-weight="700" text-anchor="middle">{intersection}</text>
                
                <!-- Set isimleri -->
                <text x="{cx-r}" y="{cy-r-10}" fill="{color['dark']}" font-size="12" font-weight="700" text-anchor="middle">A</text>
                <text x="{cx+r}" y="{cy-r-10}" fill="#9d174d" font-size="12" font-weight="700" text-anchor="middle">B</text>
            </svg>
            <div class="geo-label" style="color:{color['dark']}">{label}</div>
        </div>'''
    
    @staticmethod
    def number_line(label: str, points: list, color: dict, size: int = 300) -> str:
        """Sayı doğrusu"""
        padding = 40
        line_y = size // 3
        
        points_html = ""
        if points:
            min_val = min(p.get('value', 0) for p in points)
            max_val = max(p.get('value', 0) for p in points)
            range_val = max_val - min_val if max_val != min_val else 1
            
            for p in points:
                val = p.get('value', 0)
                x = padding + ((val - min_val) / range_val) * (size - 2 * padding)
                points_html += f'''
                    <circle cx="{x}" cy="{line_y}" r="6" fill="{color['primary']}"/>
                    <text x="{x}" y="{line_y + 25}" fill="#334155" font-size="11" font-weight="700" text-anchor="middle">{p.get('label', val)}</text>
                '''
        
        return f'''
        <div class="geo-card" style="width: {size}px">
            <svg width="{size}" height="{size//2}" viewBox="0 0 {size} {size//2}">
                <line x1="{padding}" y1="{line_y}" x2="{size-padding}" y2="{line_y}" stroke="#64748b" stroke-width="2"/>
                <polygon points="{size-padding},{line_y} {size-padding-10},{line_y-5} {size-padding-10},{line_y+5}" fill="#64748b"/>
                {points_html}
            </svg>
            <div class="geo-label" style="color:{color['dark']}">{label}</div>
        </div>'''


# ============== GRAFİK RENDERER ==============

class ChartRenderer:
    """Grafik çizimleri"""
    
    @staticmethod
    def bar_chart(data: list, width: int = 400, height: int = 250, title: str = "") -> str:
        """Çubuk grafik"""
        if not data:
            return ""
        
        padding = 50
        chart_w = width - padding * 2
        chart_h = height - padding * 2
        max_val = max(d.get('value', 0) for d in data) or 1
        bar_w = chart_w // (len(data) * 2)
        
        bars = ""
        color_keys = list(COLORS.keys())
        
        for i, d in enumerate(data):
            val = d.get('value', 0)
            c = COLORS.get(d.get('color', color_keys[i % len(color_keys)]))
            bar_h = (val / max_val) * chart_h
            x = padding + i * (bar_w * 2) + bar_w // 2
            y = padding + chart_h - bar_h
            
            bars += f'''
                <rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{c['primary']}" rx="4"/>
                <text x="{x + bar_w//2}" y="{y - 8}" fill="{c['dark']}" font-size="12" font-weight="700" text-anchor="middle">{val}</text>
                <text x="{x + bar_w//2}" y="{padding + chart_h + 18}" fill="#334155" font-size="10" font-weight="600" text-anchor="middle">{d.get('label', '')}</text>
            '''
        
        title_html = f'<text x="{width//2}" y="20" fill="#1e293b" font-size="14" font-weight="700" text-anchor="middle">{title}</text>' if title else ''
        
        return f'''
        <div class="chart-box">
            <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
                {title_html}
                <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{padding + chart_h}" stroke="#cbd5e1" stroke-width="2"/>
                <line x1="{padding}" y1="{padding + chart_h}" x2="{padding + chart_w}" y2="{padding + chart_h}" stroke="#cbd5e1" stroke-width="2"/>
                {bars}
            </svg>
        </div>'''
    
    @staticmethod
    def line_chart(data: list, width: int = 400, height: int = 250, title: str = "") -> str:
        """Çizgi grafik (fonksiyon için)"""
        if not data or len(data) < 2:
            return ""
        
        padding = 50
        chart_w = width - padding * 2
        chart_h = height - padding * 2
        
        values = [d.get('value', 0) for d in data]
        max_val = max(values) if values else 1
        min_val = min(values) if values else 0
        val_range = max_val - min_val if max_val != min_val else 1
        
        points = []
        for i, d in enumerate(data):
            val = d.get('value', 0)
            x = padding + (i / (len(data) - 1)) * chart_w
            y = padding + chart_h - ((val - min_val) / val_range) * chart_h
            points.append((x, y, d))
        
        path = f"M {points[0][0]} {points[0][1]}"
        for x, y, _ in points[1:]:
            path += f" L {x} {y}"
        
        c = COLORS['blue']
        
        points_html = ""
        labels_html = ""
        for x, y, d in points:
            points_html += f'<circle cx="{x}" cy="{y}" r="5" fill="{c["primary"]}" stroke="white" stroke-width="2"/>'
            labels_html += f'<text x="{x}" y="{padding + chart_h + 18}" fill="#334155" font-size="10" font-weight="600" text-anchor="middle">{d.get("label", "")}</text>'
        
        title_html = f'<text x="{width//2}" y="20" fill="#1e293b" font-size="14" font-weight="700" text-anchor="middle">{title}</text>' if title else ''
        
        return f'''
        <div class="chart-box">
            <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
                {title_html}
                <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{padding + chart_h}" stroke="#cbd5e1" stroke-width="2"/>
                <line x1="{padding}" y1="{padding + chart_h}" x2="{padding + chart_w}" y2="{padding + chart_h}" stroke="#cbd5e1" stroke-width="2"/>
                <path d="{path}" fill="none" stroke="{c['primary']}" stroke-width="3"/>
                {points_html}
                {labels_html}
            </svg>
        </div>'''
    
    @staticmethod
    def pie_chart(data: list, width: int = 300, height: int = 300, title: str = "") -> str:
        """Pasta grafik"""
        if not data:
            return ""
        
        cx, cy = width // 2, height // 2
        r = min(width, height) // 2 - 40
        total = sum(d.get('value', 0) for d in data) or 1
        
        slices = ""
        legend = ""
        start_angle = -90
        color_keys = list(COLORS.keys())
        
        for i, d in enumerate(data):
            val = d.get('value', 0)
            pct = val / total
            angle = pct * 360
            c = COLORS.get(d.get('color', color_keys[i % len(color_keys)]))
            
            end_angle = start_angle + angle
            large = 1 if angle > 180 else 0
            
            x1 = cx + r * math.cos(math.radians(start_angle))
            y1 = cy + r * math.sin(math.radians(start_angle))
            x2 = cx + r * math.cos(math.radians(end_angle))
            y2 = cy + r * math.sin(math.radians(end_angle))
            
            slices += f'<path d="M {cx} {cy} L {x1} {y1} A {r} {r} 0 {large} 1 {x2} {y2} Z" fill="{c["primary"]}" stroke="white" stroke-width="2"/>'
            
            if pct > 0.05:
                mid = math.radians(start_angle + angle / 2)
                lx = cx + r * 0.6 * math.cos(mid)
                ly = cy + r * 0.6 * math.sin(mid)
                slices += f'<text x="{lx}" y="{ly}" fill="white" font-size="11" font-weight="700" text-anchor="middle">%{int(pct*100)}</text>'
            
            legend += f'<div class="legend-item"><span class="legend-dot" style="background:{c["primary"]}"></span><span>{d.get("label", "")} ({val})</span></div>'
            
            start_angle = end_angle
        
        title_html = f'<text x="{cx}" y="20" fill="#1e293b" font-size="14" font-weight="700" text-anchor="middle">{title}</text>' if title else ''
        
        return f'''
        <div class="chart-box pie-box">
            <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
                {title_html}
                {slices}
            </svg>
            <div class="legend">{legend}</div>
        </div>'''


# ============== TABLO RENDERER ==============

class TableRenderer:
    """Tablo oluşturucu"""
    
    @staticmethod
    def render(headers: list, rows: list, title: str = "", highlight_col: int = None) -> str:
        if not headers or not rows:
            return ""
        
        c = COLORS['blue']
        h_html = "".join(f'<th class="{"hl" if i == highlight_col else ""}">{h}</th>' for i, h in enumerate(headers))
        r_html = "".join(f'<tr>{"".join(f"<td class={chr(34)}hl{chr(34)} " if j == highlight_col else "<td" for j in range(len(row)))}{"</td>".join(f">{cell}" for cell in row)}</td></tr>' for row in rows)
        
        # Düzeltilmiş satır oluşturma
        r_html = ""
        for row in rows:
            cells = ""
            for j, cell in enumerate(row):
                hl = ' class="hl"' if j == highlight_col else ''
                cells += f'<td{hl}>{cell}</td>'
            r_html += f'<tr>{cells}</tr>'
        
        t_html = f'<div class="table-title">{title}</div>' if title else ''
        
        return f'''
        <div class="table-box">
            {t_html}
            <table style="--tc:{c['primary']};--td:{c['dark']};--tl:{c['light']}">
                <thead><tr>{h_html}</tr></thead>
                <tbody>{r_html}</tbody>
            </table>
        </div>'''


# ============== KARŞILAŞTIRMA RENDERER ==============

class ComparisonRenderer:
    """Karşılaştırma kartları"""
    
    @staticmethod
    def render(items: list) -> str:
        if not items:
            return ""
        
        cards = ""
        color_keys = list(COLORS.keys())
        
        for i, item in enumerate(items):
            c = COLORS.get(item.get('color', color_keys[i % len(color_keys)]))
            
            props = ""
            for p in item.get('properties', []):
                props += f'''
                    <div class="prop-row">
                        <span class="prop-label">{p.get('label', '')}</span>
                        <span class="prop-value" style="color:{c['dark']}">{p.get('value', '')}</span>
                    </div>'''
            
            if not item.get('properties'):
                props = '<div class="prop-row"><span class="prop-label">Veri yok</span></div>'
            
            icon = item.get('icon', chr(65 + i))
            
            cards += f'''
                <div class="cmp-card" style="background:{c['light']};border-color:{c['primary']}">
                    <div class="card-head">
                        <span class="card-icon" style="background:{c['primary']}">{icon}</span>
                        <span class="card-title" style="color:{c['dark']}">{item.get('name', f'Seçenek {i+1}')}</span>
                    </div>
                    <div class="card-props">{props}</div>
                </div>'''
        
        return f'<div class="cmp-grid">{cards}<div class="vs-badge">VS</div></div>'


# ============== BİLGİ KARTLARI ==============

class InfoCardRenderer:
    """Bilgi kartları"""
    
    @staticmethod
    def render(items: list, formula: str = None) -> str:
        if not items:
            return ""
        
        icons = ['📊', '📈', '🎯', '⏱️', '💰', '📏', '🔢', '📐', '🌡️', '⚡', '🏷️', '📦']
        
        cards = ""
        for i, item in enumerate(items):
            ic = item.get('icon', icons[i % len(icons)])
            cards += f'''
                <div class="info-card">
                    <div class="info-icon">{ic}</div>
                    <div class="info-label">{item.get('label', '')}</div>
                    <div class="info-value">{item.get('value', '')}</div>
                    <div class="info-unit">{item.get('unit', '')}</div>
                </div>'''
        
        formula_html = ""
        if formula:
            formula_html = f'''
                <div class="formula-box">
                    <div class="formula-label">📐 Formül</div>
                    <div class="formula-text">{formula}</div>
                </div>'''
        
        return f'<div class="info-grid">{cards}</div>{formula_html}'


# ============== HTML ŞABLONU ==============

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Nunito',sans-serif;background:linear-gradient(135deg,#f8fafc,#e2e8f0);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}
.container{width:${width}px;background:#fff;border-radius:24px;box-shadow:0 20px 60px rgba(0,0,0,0.1);padding:32px;position:relative}
.header{text-align:center;margin-bottom:24px}
.header h1{font-size:22px;font-weight:800;color:#1e293b;margin-bottom:6px}
.header .subtitle{font-size:14px;color:#64748b}
.content{min-height:180px}

.geo-card{text-align:center;padding:15px;background:#f8fafc;border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,0.05);display:inline-block;margin:10px}
.geo-label{margin-top:8px;font-size:14px;font-weight:700}
.geo-grid{display:flex;justify-content:center;flex-wrap:wrap;gap:20px;margin:20px 0}

.table-box{margin:20px 0}
.table-title{font-size:15px;font-weight:700;color:#334155;margin-bottom:12px;text-align:center}
table{width:100%;border-collapse:collapse;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.08)}
th{background:linear-gradient(135deg,var(--tc),var(--td));color:#fff;padding:14px 16px;font-weight:700;font-size:13px}
td{padding:12px 16px;text-align:center;font-size:13px;font-weight:600;color:#334155;border-bottom:1px solid #e2e8f0;background:#fff}
tr:nth-child(even) td{background:#f8fafc}
th.hl,td.hl{background:var(--tl) !important;color:var(--td)}

.cmp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;position:relative;margin:20px 0}
.cmp-card{border:3px solid;border-radius:18px;padding:20px}
.card-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.card-icon{width:38px;height:38px;border-radius:10px;display:flex;justify-content:center;align-items:center;color:#fff;font-weight:800;font-size:16px}
.card-title{font-size:18px;font-weight:800}
.prop-row{display:flex;justify-content:space-between;padding:10px 14px;background:rgba(255,255,255,0.7);border-radius:10px;margin-bottom:8px}
.prop-label{font-size:12px;color:#475569;font-weight:600}
.prop-value{font-size:14px;font-weight:700}
.vs-badge{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:50px;height:50px;background:linear-gradient(135deg,#f1f5f9,#e2e8f0);border-radius:50%;display:flex;justify-content:center;align-items:center;font-size:14px;font-weight:800;color:#64748b;box-shadow:0 4px 12px rgba(0,0,0,0.1);border:3px solid #fff;z-index:10}

.info-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:14px;margin:20px 0}
.info-card{background:linear-gradient(135deg,#f8fafc,#e2e8f0);border-radius:14px;padding:16px;text-align:center;border:2px solid #e2e8f0}
.info-icon{font-size:28px;margin-bottom:8px}
.info-label{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px}
.info-value{font-size:20px;font-weight:800;color:#334155;margin-top:4px}
.info-unit{font-size:11px;color:#94a3b8}

.formula-box{background:linear-gradient(135deg,#dbeafe,#bfdbfe);border:2px solid #3b82f6;border-radius:14px;padding:16px 24px;text-align:center;margin:20px 0}
.formula-label{font-size:11px;color:#1e40af;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.formula-text{font-size:18px;font-weight:700;color:#1e3a8a;font-family:'Courier New',monospace}

.chart-box{background:#fff;border-radius:14px;padding:16px;box-shadow:0 4px 12px rgba(0,0,0,0.05);margin:20px 0;text-align:center}
.pie-box{display:flex;flex-direction:column;align-items:center}
.legend{display:flex;flex-wrap:wrap;justify-content:center;gap:12px;margin-top:12px}
.legend-item{display:flex;align-items:center;gap:6px;font-size:12px;color:#475569}
.legend-dot{width:12px;height:12px;border-radius:3px}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>${title}</h1><div class="subtitle">${subtitle}</div></div>
<div class="content">${content}</div>
</div>
</body>
</html>"""


# ============== ANA RENDERER ==============

class VisualRenderer:
    """Ana görsel oluşturucu"""
    
    def render(self, analysis: Dict) -> Tuple[Optional[str], str]:
        vtype = analysis.get('visual_type', 'infographic')
        
        try:
            if vtype == 'comparison':
                content, desc = self._render_comparison(analysis)
            elif vtype == 'table':
                content, desc = self._render_table(analysis)
            elif vtype == 'bar_chart':
                content, desc = self._render_bar_chart(analysis)
            elif vtype == 'line_chart':
                content, desc = self._render_line_chart(analysis)
            elif vtype == 'pie_chart':
                content, desc = self._render_pie_chart(analysis)
            elif vtype == 'venn':
                content, desc = self._render_venn(analysis)
            elif vtype == 'number_line':
                content, desc = self._render_number_line(analysis)
            else:
                content, desc = self._render_infographic(analysis)
            
            if not content or len(content.strip()) < 50:
                logger.error("İçerik çok kısa!")
                return None, ""
            
            html = Template(HTML_TEMPLATE).safe_substitute(
                width=Config.IMAGE_WIDTH,
                title=analysis.get('title', 'Problem'),
                subtitle=analysis.get('subtitle', ''),
                content=content
            )
            return html, desc
        except Exception as e:
            logger.error(f"Render hatası: {e}")
            return None, ""
    
    def _render_comparison(self, a: Dict) -> Tuple[str, str]:
        items = a.get('items', [])
        if not items:
            return self._render_infographic(a)
        content = ComparisonRenderer.render(items)
        formula = a.get('formula', '')
        if formula:
            content += f'<div class="formula-box"><div class="formula-label">📐 Formül</div><div class="formula-text">{formula}</div></div>'
        return content, f"Karşılaştırma: {len(items)} seçenek"
    
    def _render_table(self, a: Dict) -> Tuple[str, str]:
        t = a.get('table', {})
        headers = t.get('headers', [])
        rows = t.get('rows', [])
        if not headers or not rows:
            return self._render_infographic(a)
        content = TableRenderer.render(headers, rows, t.get('title', ''), t.get('highlight_col'))
        formula = a.get('formula', '')
        if formula:
            content += f'<div class="formula-box"><div class="formula-label">📐 Formül</div><div class="formula-text">{formula}</div></div>'
        return content, f"Tablo: {len(rows)} satır"
    
    def _render_bar_chart(self, a: Dict) -> Tuple[str, str]:
        data = a.get('chart_data', [])
        if not data:
            return self._render_infographic(a)
        content = ChartRenderer.bar_chart(data, 700, 280, a.get('chart_title', ''))
        return content, f"Çubuk grafik: {len(data)} veri"
    
    def _render_line_chart(self, a: Dict) -> Tuple[str, str]:
        data = a.get('chart_data', [])
        if not data:
            return self._render_infographic(a)
        content = ChartRenderer.line_chart(data, 700, 280, a.get('chart_title', ''))
        return content, f"Çizgi grafik: {len(data)} veri"
    
    def _render_pie_chart(self, a: Dict) -> Tuple[str, str]:
        data = a.get('chart_data', [])
        if not data:
            return self._render_infographic(a)
        content = ChartRenderer.pie_chart(data, 320, 320, a.get('chart_title', ''))
        return content, f"Pasta grafik: {len(data)} dilim"
    
    def _render_venn(self, a: Dict) -> Tuple[str, str]:
        sets = a.get('venn_data', {})
        c = COLORS['blue']
        content = f'<div class="geo-grid">{GeometryRenderer.venn_diagram("EKOK/EBOB", sets, c)}</div>'
        formula = a.get('formula', '')
        if formula:
            content += f'<div class="formula-box"><div class="formula-label">📐 Formül</div><div class="formula-text">{formula}</div></div>'
        return content, "Venn diyagramı"
    
    def _render_number_line(self, a: Dict) -> Tuple[str, str]:
        points = a.get('number_line_data', [])
        c = COLORS['blue']
        content = f'<div class="geo-grid">{GeometryRenderer.number_line("Sayı Doğrusu", points, c, 500)}</div>'
        return content, f"Sayı doğrusu: {len(points)} nokta"
    
    def _render_infographic(self, a: Dict) -> Tuple[str, str]:
        info = a.get('info_items', [])
        if not info:
            for item in a.get('items', []):
                for p in item.get('properties', []):
                    info.append({'icon': '📊', 'label': p.get('label', ''), 'value': p.get('value', ''), 'unit': ''})
        if not info:
            info = [{'icon': '📋', 'label': 'Bilgi', 'value': 'Veri yok', 'unit': ''}]
        content = InfoCardRenderer.render(info, a.get('formula'))
        return content, f"İnfografik: {len(info)} kart"


# ============== GEMİNİ ANALİZÖR ==============

class GeminiAnalyzer:
    """Akıllı soru analizi + KALİTE PUANLAMASI"""
    
    PROMPT = """Sen matematik eğitimi görsel tasarım uzmanısın.

⚠️ KRİTİK KURALLAR:
1. "simplified_text" = null (soru metnini DEĞİŞTİRME!)
2. Kalite puanı ver: question_quality (1-10), visual_quality (1-10)
3. Sadece GÖRSEL GEREKTİREN sorular için görsel tasarla

═══════════════════════════════════════════════════════════════
🎯 GÖRSEL TİPLERİ (Geometri YOK!)
═══════════════════════════════════════════════════════════════

"comparison" → Karşılaştırma kartları (firmalar, tarifeler, planlar)
"table" → Veri tablosu (çoklu satır-sütun)
"bar_chart" → Çubuk grafik (kategorik karşılaştırma)
"line_chart" → Çizgi grafik (fonksiyon, zaman serisi)
"pie_chart" → Pasta grafik (yüzde dağılımları)
"venn" → Venn diyagramı (EKOK, EBOB, küme)
"number_line" → Sayı doğrusu (eşitsizlik, aralık)
"infographic" → Bilgi kartları (genel veriler)

═══════════════════════════════════════════════════════════════
✅ GÖRSEL GEREKLİ DURUMLAR
═══════════════════════════════════════════════════════════════

- Karşılaştırma (2+ seçenek, firma, plan)
- Tablo verisi (satır-sütun yapısı)
- İstatistik (ortalama, medyan, mod)
- Fonksiyon grafiği
- EKOK/EBOB (Venn diyagramı)
- Yüzde dağılımı
- Oran-orantı problemleri
- Kar-zarar tabloları
- Tarife karşılaştırması

❌ GÖRSEL GEREKSİZ DURUMLAR
═══════════════════════════════════════════════════════════════

- Basit dört işlem
- Tek adımlı hesaplamalar
- Kısa denklem çözümü
- Geometri soruları (alan, çevre, açı)

═══════════════════════════════════════════════════════════════
📋 JSON ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════

{
  "visual_required": true/false,
  "visual_type": "comparison|table|bar_chart|line_chart|pie_chart|venn|number_line|infographic",
  
  "question_quality": 8,  // Soru kalitesi (1-10)
  "visual_quality": 9,    // Görsel kalitesi (1-10)
  "quality_reason": "Açıklama",
  
  "title": "Başlık",
  "subtitle": "Alt başlık",
  
  "items": [
    {"name": "A Firması", "color": "blue", "properties": [{"label": "Fiyat", "value": "100 TL"}]}
  ],
  
  "table": {"title": "", "headers": ["A", "B"], "rows": [["1", "2"]], "highlight_col": null},
  
  "chart_data": [{"label": "A", "value": 100, "color": "blue"}],
  "chart_title": "",
  
  "venn_data": {"A": "12, 24", "B": "18, 36", "kesisim": "6"},
  
  "number_line_data": [{"value": 0, "label": "0"}, {"value": 5, "label": "5"}],
  
  "info_items": [{"icon": "💰", "label": "Fiyat", "value": "100", "unit": "TL"}],
  
  "formula": "Formül",
  
  "simplified_text": null
}

═══════════════════════════════════════════════════════════════
📝 PUANLAMA KRİTERLERİ
═══════════════════════════════════════════════════════════════

question_quality (Soru Kalitesi):
- 9-10: Mükemmel senaryo, zengin veri, net soru
- 7-8: İyi senaryo, yeterli veri
- 5-6: Orta, bazı eksikler
- 1-4: Zayıf, belirsiz, eksik

visual_quality (Görsel Kalitesi):
- 9-10: Tüm veriler çıkarıldı, zengin içerik
- 7-8: Çoğu veri çıkarıldı
- 5-6: Temel veriler var
- 1-4: Eksik, boş alanlar

⚠️ Kalite puanı 7'nin altındaysa görsel KAYDEDILMEYECEK!

═══════════════════════════════════════════════════════════════

Şimdi analiz et:
"""
    
    def __init__(self):
        if NEW_GENAI:
            self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        else:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        logger.info(f"Gemini hazır: {Config.GEMINI_MODEL}")
    
    def analyze(self, text: str, scenario: str = None) -> Optional[Dict]:
        try:
            full = f"SENARYO:\n{scenario}\n\nSORU:\n{text}" if scenario else text
            prompt = self.PROMPT + full
            
            if NEW_GENAI:
                resp = self.client.models.generate_content(
                    model=Config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json")
                )
                txt = resp.text
            else:
                resp = self.model.generate_content(prompt, generation_config={'temperature': 0.2, 'response_mime_type': 'application/json'})
                txt = resp.text
            
            result = json.loads(txt)
            
            # Görsel gerekli mi?
            if not result.get('visual_required', False):
                logger.info("Görsel gerekmez")
                return None
            
            # Kalite kontrolü
            q_quality = result.get('question_quality', 0)
            v_quality = result.get('visual_quality', 0)
            
            logger.info(f"Kalite: Soru={q_quality}/10, Görsel={v_quality}/10")
            
            if q_quality < Config.MIN_QUALITY_SCORE or v_quality < Config.MIN_QUALITY_SCORE:
                reason = result.get('quality_reason', 'Düşük kalite')
                logger.warning(f"Kalite yetersiz: {reason}")
                return None
            
            # İçerik kontrolü
            has_content = (result.get('items') or result.get('table', {}).get('headers') or 
                          result.get('chart_data') or result.get('info_items') or
                          result.get('venn_data') or result.get('number_line_data'))
            
            if not has_content:
                logger.warning("İçerik boş!")
                return None
            
            result['simplified_text'] = None
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON hatası: {e}")
            return None
        except Exception as e:
            logger.error(f"Analiz hatası: {e}")
            return None


# ============== VERİTABANI ==============

class DatabaseManager:
    def __init__(self):
        self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_scenario_questions(self, limit: int = 30) -> List[Dict]:
        try:
            resp = self.client.table('question_bank').select('*').is_('image_url', 'null').eq('is_active', True).not_.is_('scenario_text', 'null').limit(limit).execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"Soru çekme hatası: {e}")
            return []
    
    def upload_image(self, data: bytes, filename: str) -> Optional[str]:
        try:
            self.client.storage.from_(Config.STORAGE_BUCKET).upload(filename, data, {'content-type': 'image/png', 'upsert': 'true'})
            return self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
        except Exception as e:
            logger.error(f"Upload hatası: {e}")
            return None
    
    def update_image_only(self, qid: int, url: str) -> bool:
        """SADECE image_url güncelle - soru metnine DOKUNMA!"""
        try:
            self.client.table('question_bank').update({'image_url': url}).eq('id', qid).execute()
            return True
        except Exception as e:
            logger.error(f"Güncelleme hatası: {e}")
            return False


# ============== PNG DÖNÜŞTÜRÜCÜ ==============

class ImageConverter:
    def __init__(self):
        self.pw = None
        self.br = None
    
    def start(self):
        self.pw = sync_playwright().start()
        self.br = self.pw.chromium.launch()
        logger.info("Playwright başlatıldı")
    
    def stop(self):
        if self.br: self.br.close()
        if self.pw: self.pw.stop()
        logger.info("Playwright kapatıldı")
    
    def to_png(self, html: str) -> Optional[bytes]:
        try:
            page = self.br.new_page(viewport={'width': Config.IMAGE_WIDTH + 100, 'height': 800})
            page.set_content(html)
            page.wait_for_load_state('networkidle')
            cont = page.query_selector('.container')
            if not cont:
                page.close()
                return None
            png = cont.screenshot(type='png')
            page.close()
            return png
        except Exception as e:
            logger.error(f"PNG hatası: {e}")
            return None


# ============== ANA BOT ==============

class ScenarioBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.analyzer = GeminiAnalyzer()
        self.renderer = VisualRenderer()
        self.converter = ImageConverter()
        self.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'filtered': 0}
    
    def run(self):
        logger.info("=" * 60)
        logger.info("SENARYO GÖRSEL BOTU v3.2")
        logger.info("=" * 60)
        logger.info("✅ Kalite kontrolü aktif (min: 7/10)")
        logger.info("✅ Geometri soruları dışlanıyor")
        logger.info("✅ Soru metinleri DEĞİŞTİRİLMEYECEK")
        logger.info("=" * 60)
        
        self.converter.start()
        
        try:
            batch = Config.TEST_BATCH_SIZE if Config.TEST_MODE else Config.BATCH_SIZE
            logger.info(f"Mod: {'TEST' if Config.TEST_MODE else 'PRODUCTION'}, Batch: {batch}")
            
            questions = self.db.get_scenario_questions(batch)
            if not questions:
                logger.warning("Soru bulunamadı!")
                return
            
            logger.info(f"{len(questions)} soru bulundu")
            self.stats['total'] = len(questions)
            
            for i, q in enumerate(questions):
                logger.info(f"\n{'─'*50}")
                logger.info(f"Soru {i+1}/{len(questions)} (ID: {q['id']})")
                logger.info(f"{'─'*50}")
                self._process(q)
                time.sleep(1)
            
            self._report()
        finally:
            self.converter.stop()
    
    def _process(self, q: Dict):
        qid = q['id']
        text = q.get('original_text', '')
        scenario = q.get('scenario_text', '')
        
        if not text:
            self.stats['skipped'] += 1
            return
        
        # Kazanım filtresi
        should_process, reason = LearningOutcomeFilter.should_process(q)
        if not should_process:
            logger.info(f"⏭️ Filtrelendi: {reason}")
            self.stats['filtered'] += 1
            return
        
        # Analiz
        logger.info("🔍 Analiz...")
        analysis = self.analyzer.analyze(text, scenario)
        
        if not analysis:
            self.stats['skipped'] += 1
            return
        
        vtype = analysis.get('visual_type', 'unknown')
        logger.info(f"📊 Tip: {vtype}")
        
        # Render
        logger.info("🎨 Render...")
        html, desc = self.renderer.render(analysis)
        
        if not html:
            logger.error("Render başarısız!")
            self.stats['failed'] += 1
            return
        
        # PNG
        logger.info("📸 PNG...")
        png = self.converter.to_png(html)
        
        if not png:
            self.stats['failed'] += 1
            return
        
        if len(png) < Config.MIN_PNG_SIZE:
            logger.error(f"PNG çok küçük ({len(png)} bytes)!")
            self.stats['failed'] += 1
            return
        
        logger.info(f"📦 {len(png)/1024:.1f} KB")
        
        # Upload
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fn = f"scenario/q_{qid}_{ts}.png"
        
        logger.info("☁️ Upload...")
        url = self.db.upload_image(png, fn)
        
        if not url:
            self.stats['failed'] += 1
            return
        
        # Kaydet
        if self.db.update_image_only(qid, url):
            q_score = analysis.get('question_quality', '?')
            v_score = analysis.get('visual_quality', '?')
            logger.info(f"✅ #{qid}: BAŞARILI ({vtype}) [Q:{q_score} V:{v_score}]")
            self.stats['success'] += 1
        else:
            self.stats['failed'] += 1
    
    def _report(self):
        logger.info("\n" + "=" * 60)
        logger.info("📊 SONUÇ RAPORU")
        logger.info("=" * 60)
        logger.info(f"📝 Toplam: {self.stats['total']}")
        logger.info(f"✅ Başarılı: {self.stats['success']}")
        logger.info(f"🔄 Filtrelenen: {self.stats['filtered']}")
        logger.info(f"⏭️ Atlanan: {self.stats['skipped']}")
        logger.info(f"❌ Başarısız: {self.stats['failed']}")
        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"📈 Oran: %{rate:.1f}")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        ScenarioBot().run()
    except Exception as e:
        logger.error(f"Bot hatası: {e}")
        raise
