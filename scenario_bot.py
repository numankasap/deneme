"""
Senaryo Görsel Botu v3.0
========================
ESNEK VE ZENGİN GÖRSEL DESTEĞİ:
- Geometrik şekiller (silindir, küp, prizma, koni, küre)
- Grafikler (çubuk, çizgi, pasta, alan)
- Tablolar (dinamik boyut)
- Karşılaştırma kartları
- İnfografikler
- Hareket diyagramları
- Zaman çizelgeleri

Dinamik soru metni - statik "Hangisi avantajlı?" yerine gerçek soru

GitHub Actions ile çalışır.
"""

import os
import json
import time
import logging
import math
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from string import Template

# Supabase
from supabase import create_client, Client

# Gemini
try:
    from google import genai
    from google.genai import types
    NEW_GENAI = True
except ImportError:
    import google.generativeai as genai
    NEW_GENAI = False

# HTML to PNG
from playwright.sync_api import sync_playwright

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== YAPILANDIRMA ==============

class Config:
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    GEMINI_MODEL = 'gemini-2.5-pro'
    STORAGE_BUCKET = 'questions-images'
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30'))
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 10
    IMAGE_WIDTH = 900
    QUALITY_THRESHOLD = 7


# ============== RENK PALETİ ==============

COLORS = {
    'blue': {'primary': '#3b82f6', 'light': '#dbeafe', 'dark': '#1e40af', 'gradient': 'linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)'},
    'pink': {'primary': '#ec4899', 'light': '#fce7f3', 'dark': '#9d174d', 'gradient': 'linear-gradient(135deg, #ec4899 0%, #9d174d 100%)'},
    'green': {'primary': '#22c55e', 'light': '#dcfce7', 'dark': '#166534', 'gradient': 'linear-gradient(135deg, #22c55e 0%, #166534 100%)'},
    'orange': {'primary': '#f59e0b', 'light': '#fef3c7', 'dark': '#92400e', 'gradient': 'linear-gradient(135deg, #f59e0b 0%, #92400e 100%)'},
    'purple': {'primary': '#8b5cf6', 'light': '#f3e8ff', 'dark': '#6b21a8', 'gradient': 'linear-gradient(135deg, #8b5cf6 0%, #6b21a8 100%)'},
    'teal': {'primary': '#14b8a6', 'light': '#ccfbf1', 'dark': '#115e59', 'gradient': 'linear-gradient(135deg, #14b8a6 0%, #115e59 100%)'},
    'red': {'primary': '#ef4444', 'light': '#fee2e2', 'dark': '#991b1b', 'gradient': 'linear-gradient(135deg, #ef4444 0%, #991b1b 100%)'},
    'indigo': {'primary': '#6366f1', 'light': '#e0e7ff', 'dark': '#4338ca', 'gradient': 'linear-gradient(135deg, #6366f1 0%, #4338ca 100%)'},
}


# ============== ANA HTML ŞABLONU ==============

BASE_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Nunito', sans-serif;
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            width: ${width}px;
            background: #ffffff;
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            padding: 30px;
            position: relative;
            overflow: hidden;
        }
        
        .container::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image: 
                linear-gradient(rgba(148, 163, 184, 0.06) 1px, transparent 1px),
                linear-gradient(90deg, rgba(148, 163, 184, 0.06) 1px, transparent 1px);
            background-size: 25px 25px;
            pointer-events: none;
        }
        
        .header {
            text-align: center;
            margin-bottom: 24px;
            position: relative;
            z-index: 1;
        }
        
        .header h1 {
            font-size: 22px;
            font-weight: 800;
            color: #1e293b;
            margin-bottom: 8px;
        }
        
        .header .subtitle {
            font-size: 14px;
            color: #64748b;
        }
        
        .content {
            position: relative;
            z-index: 1;
        }
        
        /* Soru kutusu - DİNAMİK METİN */
        .question-box {
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border: 3px solid #f59e0b;
            border-radius: 16px;
            padding: 18px 24px;
            margin-top: 20px;
        }
        
        .question-box .label {
            font-size: 11px;
            color: #92400e;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 6px;
            font-weight: 700;
        }
        
        .question-box .text {
            font-size: 16px;
            font-weight: 700;
            color: #78350f;
            line-height: 1.5;
        }
        
        ${extra_css}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>${title}</h1>
            ${subtitle_html}
        </div>
        <div class="content">
            ${content_html}
        </div>
        ${question_html}
    </div>
</body>
</html>
"""


# ============== GEOMETRİK ŞEKİLLER ==============

class GeometryRenderer:
    """SVG tabanlı geometrik şekil çizimleri"""
    
    @staticmethod
    def cylinder(width: int, height: int, color: dict, label: str = "", 
                 dimensions: dict = None, show_dimensions: bool = True) -> str:
        """3D silindir çizimi"""
        cx, cy = width // 2, height // 2
        rx = min(width, height) // 3  # Elips yarıçapı
        ry = rx // 3  # Perspektif için
        h = height // 2  # Silindir yüksekliği
        
        dims_html = ""
        if show_dimensions and dimensions:
            cap = dimensions.get('cap', '')
            yukseklik = dimensions.get('yukseklik', '')
            if cap:
                dims_html += f'''
                    <line x1="{cx - rx - 20}" y1="{cy - h//2}" x2="{cx - rx - 20}" y2="{cy + h//2}" 
                          stroke="#64748b" stroke-width="2" marker-start="url(#arrow)" marker-end="url(#arrow)"/>
                    <text x="{cx - rx - 35}" y="{cy}" fill="#334155" font-size="14" font-weight="700" 
                          transform="rotate(-90, {cx - rx - 35}, {cy})" text-anchor="middle">{yukseklik}</text>
                '''
            if yukseklik:
                dims_html += f'''
                    <line x1="{cx - rx}" y1="{cy + h//2 + ry + 15}" x2="{cx + rx}" y2="{cy + h//2 + ry + 15}" 
                          stroke="#64748b" stroke-width="2" marker-start="url(#arrow)" marker-end="url(#arrow)"/>
                    <text x="{cx}" y="{cy + h//2 + ry + 35}" fill="#334155" font-size="14" font-weight="700" text-anchor="middle">Çap: {cap}</text>
                '''
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <defs>
                <linearGradient id="cylGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:{color['dark']};stop-opacity:1" />
                    <stop offset="50%" style="stop-color:{color['primary']};stop-opacity:1" />
                    <stop offset="100%" style="stop-color:{color['dark']};stop-opacity:1" />
                </linearGradient>
                <marker id="arrow" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto">
                    <path d="M0,0 L10,5 L0,10 Z" fill="#64748b"/>
                </marker>
            </defs>
            
            <!-- Silindir gövdesi -->
            <ellipse cx="{cx}" cy="{cy + h//2}" rx="{rx}" ry="{ry}" fill="{color['dark']}" opacity="0.3"/>
            <rect x="{cx - rx}" y="{cy - h//2}" width="{rx * 2}" height="{h}" fill="url(#cylGrad)"/>
            <ellipse cx="{cx}" cy="{cy - h//2}" rx="{rx}" ry="{ry}" fill="{color['light']}" stroke="{color['primary']}" stroke-width="2"/>
            
            <!-- Kenar çizgileri -->
            <line x1="{cx - rx}" y1="{cy - h//2}" x2="{cx - rx}" y2="{cy + h//2}" stroke="{color['dark']}" stroke-width="2"/>
            <line x1="{cx + rx}" y1="{cy - h//2}" x2="{cx + rx}" y2="{cy + h//2}" stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Alt elips (görünen kısım) -->
            <path d="M {cx - rx} {cy + h//2} A {rx} {ry} 0 0 0 {cx + rx} {cy + h//2}" 
                  fill="none" stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Etiket -->
            <text x="{cx}" y="{cy + 5}" fill="white" font-size="18" font-weight="800" text-anchor="middle">{label}</text>
            
            {dims_html}
        </svg>
        '''
    
    @staticmethod
    def cube(width: int, height: int, color: dict, label: str = "", 
             dimensions: dict = None) -> str:
        """3D küp çizimi"""
        size = min(width, height) // 2
        cx, cy = width // 2, height // 2
        offset = size // 3  # 3D offset
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <defs>
                <linearGradient id="cubeTop" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:{color['light']};stop-opacity:1" />
                    <stop offset="100%" style="stop-color:{color['primary']};stop-opacity:1" />
                </linearGradient>
            </defs>
            
            <!-- Arka yüz -->
            <rect x="{cx - size//2 + offset}" y="{cy - size//2 - offset}" width="{size}" height="{size}" 
                  fill="{color['dark']}" opacity="0.5"/>
            
            <!-- Sol yüz -->
            <polygon points="{cx - size//2},{cy - size//2} {cx - size//2 + offset},{cy - size//2 - offset} 
                           {cx - size//2 + offset},{cy + size//2 - offset} {cx - size//2},{cy + size//2}"
                     fill="{color['primary']}" opacity="0.7"/>
            
            <!-- Ön yüz -->
            <rect x="{cx - size//2}" y="{cy - size//2}" width="{size}" height="{size}" 
                  fill="{color['primary']}" stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Üst yüz -->
            <polygon points="{cx - size//2},{cy - size//2} {cx - size//2 + offset},{cy - size//2 - offset} 
                           {cx + size//2 + offset},{cy - size//2 - offset} {cx + size//2},{cy - size//2}"
                     fill="url(#cubeTop)" stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Etiket -->
            <text x="{cx}" y="{cy + 8}" fill="white" font-size="18" font-weight="800" text-anchor="middle">{label}</text>
        </svg>
        '''
    
    @staticmethod  
    def cone(width: int, height: int, color: dict, label: str = "",
             dimensions: dict = None) -> str:
        """3D koni çizimi"""
        cx, cy = width // 2, height // 2
        rx = min(width, height) // 3
        ry = rx // 4
        h = height // 2
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <defs>
                <linearGradient id="coneGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:{color['dark']};stop-opacity:1" />
                    <stop offset="50%" style="stop-color:{color['primary']};stop-opacity:1" />
                    <stop offset="100%" style="stop-color:{color['dark']};stop-opacity:1" />
                </linearGradient>
            </defs>
            
            <!-- Koni gövdesi -->
            <polygon points="{cx},{cy - h//2} {cx - rx},{cy + h//2} {cx + rx},{cy + h//2}"
                     fill="url(#coneGrad)"/>
            
            <!-- Taban elipsi -->
            <ellipse cx="{cx}" cy="{cy + h//2}" rx="{rx}" ry="{ry}" 
                     fill="{color['light']}" stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Kenarlar -->
            <line x1="{cx}" y1="{cy - h//2}" x2="{cx - rx}" y2="{cy + h//2}" 
                  stroke="{color['dark']}" stroke-width="2"/>
            <line x1="{cx}" y1="{cy - h//2}" x2="{cx + rx}" y2="{cy + h//2}" 
                  stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Etiket -->
            <text x="{cx}" y="{cy + h//4}" fill="white" font-size="16" font-weight="800" text-anchor="middle">{label}</text>
        </svg>
        '''
    
    @staticmethod
    def sphere(width: int, height: int, color: dict, label: str = "",
               dimensions: dict = None) -> str:
        """3D küre çizimi"""
        cx, cy = width // 2, height // 2
        r = min(width, height) // 3
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <defs>
                <radialGradient id="sphereGrad" cx="30%" cy="30%" r="70%">
                    <stop offset="0%" style="stop-color:{color['light']};stop-opacity:1" />
                    <stop offset="70%" style="stop-color:{color['primary']};stop-opacity:1" />
                    <stop offset="100%" style="stop-color:{color['dark']};stop-opacity:1" />
                </radialGradient>
            </defs>
            
            <!-- Küre -->
            <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#sphereGrad)" 
                    stroke="{color['dark']}" stroke-width="2"/>
            
            <!-- Ekvator çizgisi -->
            <ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r//4}" 
                     fill="none" stroke="{color['dark']}" stroke-width="1" stroke-dasharray="5,5"/>
            
            <!-- Etiket -->
            <text x="{cx}" y="{cy + 8}" fill="white" font-size="18" font-weight="800" text-anchor="middle">{label}</text>
        </svg>
        '''


# ============== GRAFİKLER ==============

class ChartRenderer:
    """SVG tabanlı grafik çizimleri"""
    
    @staticmethod
    def bar_chart(width: int, height: int, data: List[dict], 
                  title: str = "", show_values: bool = True) -> str:
        """Çubuk grafik"""
        if not data:
            return ""
        
        padding = 60
        chart_width = width - padding * 2
        chart_height = height - padding * 2
        
        max_val = max(d.get('value', 0) for d in data)
        bar_width = chart_width // (len(data) * 2)
        
        bars_html = ""
        for i, d in enumerate(data):
            val = d.get('value', 0)
            label = d.get('label', '')
            color = COLORS.get(d.get('color', 'blue'), COLORS['blue'])
            
            bar_height = (val / max_val) * chart_height if max_val > 0 else 0
            x = padding + i * (bar_width * 2) + bar_width // 2
            y = padding + chart_height - bar_height
            
            bars_html += f'''
                <rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" 
                      fill="{color['gradient']}" rx="4"/>
                <text x="{x + bar_width//2}" y="{padding + chart_height + 20}" 
                      fill="#334155" font-size="12" font-weight="600" text-anchor="middle">{label}</text>
            '''
            if show_values:
                bars_html += f'''
                    <text x="{x + bar_width//2}" y="{y - 8}" 
                          fill="{color['dark']}" font-size="13" font-weight="700" text-anchor="middle">{val}</text>
                '''
        
        # Eksen çizgileri
        axis_html = f'''
            <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{padding + chart_height}" 
                  stroke="#cbd5e1" stroke-width="2"/>
            <line x1="{padding}" y1="{padding + chart_height}" x2="{padding + chart_width}" y2="{padding + chart_height}" 
                  stroke="#cbd5e1" stroke-width="2"/>
        '''
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            {axis_html}
            {bars_html}
        </svg>
        '''
    
    @staticmethod
    def line_chart(width: int, height: int, data: List[dict],
                   title: str = "", show_points: bool = True) -> str:
        """Çizgi grafik"""
        if not data:
            return ""
        
        padding = 60
        chart_width = width - padding * 2
        chart_height = height - padding * 2
        
        max_val = max(d.get('value', 0) for d in data)
        min_val = min(d.get('value', 0) for d in data)
        val_range = max_val - min_val if max_val != min_val else 1
        
        points = []
        for i, d in enumerate(data):
            val = d.get('value', 0)
            x = padding + (i / (len(data) - 1)) * chart_width if len(data) > 1 else padding + chart_width // 2
            y = padding + chart_height - ((val - min_val) / val_range) * chart_height
            points.append((x, y, d))
        
        # Çizgi path
        path_d = f"M {points[0][0]} {points[0][1]}"
        for x, y, _ in points[1:]:
            path_d += f" L {x} {y}"
        
        color = COLORS['blue']
        
        points_html = ""
        labels_html = ""
        for x, y, d in points:
            if show_points:
                points_html += f'<circle cx="{x}" cy="{y}" r="6" fill="{color["primary"]}" stroke="white" stroke-width="2"/>'
            labels_html += f'''
                <text x="{x}" y="{padding + chart_height + 20}" 
                      fill="#334155" font-size="11" text-anchor="middle">{d.get('label', '')}</text>
            '''
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{padding + chart_height}" stroke="#cbd5e1" stroke-width="2"/>
            <line x1="{padding}" y1="{padding + chart_height}" x2="{padding + chart_width}" y2="{padding + chart_height}" stroke="#cbd5e1" stroke-width="2"/>
            <path d="{path_d}" fill="none" stroke="{color['primary']}" stroke-width="3"/>
            {points_html}
            {labels_html}
        </svg>
        '''
    
    @staticmethod
    def pie_chart(width: int, height: int, data: List[dict], 
                  show_labels: bool = True) -> str:
        """Pasta grafik"""
        if not data:
            return ""
        
        cx, cy = width // 2, height // 2
        r = min(width, height) // 3
        
        total = sum(d.get('value', 0) for d in data)
        if total == 0:
            return ""
        
        slices_html = ""
        labels_html = ""
        start_angle = -90  # 12 o'clock position
        
        color_keys = list(COLORS.keys())
        
        for i, d in enumerate(data):
            val = d.get('value', 0)
            percentage = val / total
            angle = percentage * 360
            
            color = COLORS.get(d.get('color', color_keys[i % len(color_keys)]), COLORS['blue'])
            
            # SVG arc path
            end_angle = start_angle + angle
            large_arc = 1 if angle > 180 else 0
            
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            
            x1 = cx + r * math.cos(start_rad)
            y1 = cy + r * math.sin(start_rad)
            x2 = cx + r * math.cos(end_rad)
            y2 = cy + r * math.sin(end_rad)
            
            slices_html += f'''
                <path d="M {cx} {cy} L {x1} {y1} A {r} {r} 0 {large_arc} 1 {x2} {y2} Z"
                      fill="{color['primary']}" stroke="white" stroke-width="2"/>
            '''
            
            # Label
            if show_labels:
                mid_angle = math.radians(start_angle + angle / 2)
                label_r = r * 0.7
                lx = cx + label_r * math.cos(mid_angle)
                ly = cy + label_r * math.sin(mid_angle)
                labels_html += f'''
                    <text x="{lx}" y="{ly}" fill="white" font-size="12" font-weight="700" 
                          text-anchor="middle" dominant-baseline="middle">{d.get('label', '')}</text>
                '''
            
            start_angle = end_angle
        
        return f'''
        <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            {slices_html}
            {labels_html}
        </svg>
        '''


# ============== KARŞILAŞTIRMA KARTI ==============

class ComparisonRenderer:
    """Yan yana karşılaştırma kartları"""
    
    @staticmethod
    def render_cards(items: List[dict], show_geometry: bool = False) -> str:
        """Karşılaştırma kartları oluştur"""
        if not items:
            return ""
        
        cards_html = ""
        color_order = ['blue', 'pink', 'green', 'orange', 'purple', 'teal']
        
        for i, item in enumerate(items):
            color_name = item.get('color', color_order[i % len(color_order)])
            color = COLORS.get(color_name, COLORS['blue'])
            
            # Özellikler
            props_html = ""
            for prop in item.get('properties', []):
                props_html += f'''
                    <div class="prop-row">
                        <span class="prop-label">{prop.get('label', '')}</span>
                        <span class="prop-value" style="color: {color['dark']}">{prop.get('value', '')}</span>
                    </div>
                '''
            
            # Geometrik şekil (opsiyonel)
            geometry_html = ""
            if show_geometry and item.get('geometry'):
                geo = item.get('geometry', {})
                geo_type = geo.get('type', 'cylinder')
                if geo_type == 'cylinder':
                    geometry_html = GeometryRenderer.cylinder(
                        150, 120, color, item.get('name', ''),
                        geo.get('dimensions', {})
                    )
            
            icon_letter = item.get('icon', chr(65 + i))
            
            cards_html += f'''
                <div class="compare-card" style="background: {color['light']}; border-color: {color['primary']}">
                    <div class="card-header">
                        <span class="card-icon" style="background: {color['gradient']}">{icon_letter}</span>
                        <span class="card-title" style="color: {color['dark']}">{item.get('name', f'Seçenek {i+1}')}</span>
                    </div>
                    {geometry_html}
                    <div class="card-props">
                        {props_html}
                    </div>
                </div>
            '''
        
        return f'''
            <div class="comparison-grid" style="grid-template-columns: repeat({len(items)}, 1fr);">
                {cards_html}
                <div class="vs-badge">VS</div>
            </div>
        '''


# ============== TABLO ==============

class TableRenderer:
    """Dinamik tablo oluşturucu"""
    
    @staticmethod
    def render(headers: List[str], rows: List[List[str]], 
               highlight_col: int = None, color: str = 'blue') -> str:
        """Tablo HTML oluştur"""
        if not headers or not rows:
            return ""
        
        c = COLORS.get(color, COLORS['blue'])
        
        headers_html = "".join(f"<th>{h}</th>" for h in headers)
        
        rows_html = ""
        for row in rows:
            cells = ""
            for j, cell in enumerate(row):
                css_class = "highlight-cell" if j == highlight_col else ""
                cells += f'<td class="{css_class}">{cell}</td>'
            rows_html += f"<tr>{cells}</tr>"
        
        return f'''
            <div class="table-wrapper">
                <table style="--table-color: {c['primary']}; --table-dark: {c['dark']}; --table-light: {c['light']}">
                    <thead><tr>{headers_html}</tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
        '''


# ============== ANA RENDERER ==============

class VisualRenderer:
    """Ana görsel oluşturucu"""
    
    # Ek CSS stilleri
    EXTRA_CSS = """
        /* Karşılaştırma kartları */
        .comparison-grid {
            display: grid;
            gap: 20px;
            position: relative;
        }
        
        .compare-card {
            border: 3px solid;
            border-radius: 18px;
            padding: 20px;
        }
        
        .card-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .card-icon {
            width: 36px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
            font-weight: 800;
            font-size: 16px;
        }
        
        .card-title {
            font-size: 18px;
            font-weight: 800;
        }
        
        .prop-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 14px;
            background: rgba(255,255,255,0.7);
            border-radius: 10px;
            margin-bottom: 8px;
        }
        
        .prop-label {
            font-size: 13px;
            color: #475569;
            font-weight: 600;
        }
        
        .prop-value {
            font-size: 15px;
            font-weight: 700;
        }
        
        .vs-badge {
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 50px;
            height: 50px;
            background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 14px;
            font-weight: 800;
            color: #64748b;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border: 3px solid white;
            z-index: 10;
        }
        
        /* Tablo */
        .table-wrapper {
            overflow: hidden;
            border-radius: 14px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            background: linear-gradient(135deg, var(--table-color) 0%, var(--table-dark) 100%);
            color: white;
            padding: 14px 16px;
            font-weight: 700;
            font-size: 13px;
        }
        
        td {
            padding: 12px 16px;
            text-align: center;
            font-size: 14px;
            font-weight: 600;
            color: #334155;
            border-bottom: 1px solid #e2e8f0;
            background: white;
        }
        
        tr:nth-child(even) td { background: #f8fafc; }
        
        .highlight-cell {
            background: var(--table-light) !important;
            color: var(--table-dark);
            font-weight: 700;
        }
        
        /* Geometri container */
        .geometry-container {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        
        .geometry-item {
            text-align: center;
        }
        
        .geometry-label {
            margin-top: 10px;
            font-weight: 700;
            color: #334155;
        }
        
        /* Grafik container */
        .chart-container {
            background: white;
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06);
        }
        
        .chart-title {
            text-align: center;
            font-size: 16px;
            font-weight: 700;
            color: #334155;
            margin-bottom: 15px;
        }
        
        /* Info kartları */
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .info-card {
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            border-radius: 12px;
            padding: 14px;
            text-align: center;
        }
        
        .info-card .icon { font-size: 24px; margin-bottom: 6px; }
        .info-card .label { font-size: 11px; color: #64748b; text-transform: uppercase; }
        .info-card .value { font-size: 18px; font-weight: 800; color: #334155; }
    """
    
    def render(self, analysis: Dict) -> Tuple[Optional[str], str]:
        """Ana render fonksiyonu"""
        visual_type = analysis.get('visual_type', 'comparison')
        
        try:
            if visual_type == 'comparison_geometry':
                content, desc = self._render_comparison_with_geometry(analysis)
            elif visual_type == 'comparison':
                content, desc = self._render_comparison(analysis)
            elif visual_type == 'table':
                content, desc = self._render_table(analysis)
            elif visual_type == 'bar_chart':
                content, desc = self._render_bar_chart(analysis)
            elif visual_type == 'line_chart':
                content, desc = self._render_line_chart(analysis)
            elif visual_type == 'pie_chart':
                content, desc = self._render_pie_chart(analysis)
            elif visual_type == 'geometry':
                content, desc = self._render_geometry(analysis)
            elif visual_type == 'infographic':
                content, desc = self._render_infographic(analysis)
            else:
                content, desc = self._render_comparison(analysis)
            
            # Soru kutusu - DİNAMİK
            question_text = analysis.get('question_text', '')
            question_html = ""
            if question_text:
                question_html = f'''
                    <div class="question-box">
                        <div class="label">❓ SORU</div>
                        <div class="text">{question_text}</div>
                    </div>
                '''
            
            # Subtitle
            subtitle = analysis.get('subtitle', '')
            subtitle_html = f'<div class="subtitle">{subtitle}</div>' if subtitle else ''
            
            # Final HTML
            html = Template(BASE_HTML).safe_substitute(
                width=Config.IMAGE_WIDTH,
                title=analysis.get('title', 'Problem'),
                subtitle_html=subtitle_html,
                content_html=content,
                question_html=question_html,
                extra_css=self.EXTRA_CSS
            )
            
            return html, desc
            
        except Exception as e:
            logger.error(f"Render hatası: {e}")
            return None, ""
    
    def _render_comparison_with_geometry(self, analysis: Dict) -> Tuple[str, str]:
        """Geometrik şekillerle karşılaştırma"""
        items = analysis.get('items', [])
        geo_type = analysis.get('geometry_type', 'cylinder')
        
        # Geometrik şekiller
        geo_html = '<div class="geometry-container">'
        color_order = ['blue', 'pink', 'green', 'orange']
        
        for i, item in enumerate(items):
            color = COLORS.get(item.get('color', color_order[i % len(color_order)]))
            dims = item.get('dimensions', {})
            label = item.get('name', chr(65 + i))
            
            if geo_type == 'cylinder':
                svg = GeometryRenderer.cylinder(180, 160, color, label, dims)
            elif geo_type == 'cube':
                svg = GeometryRenderer.cube(160, 160, color, label, dims)
            elif geo_type == 'cone':
                svg = GeometryRenderer.cone(160, 160, color, label, dims)
            elif geo_type == 'sphere':
                svg = GeometryRenderer.sphere(160, 160, color, label, dims)
            else:
                svg = GeometryRenderer.cylinder(180, 160, color, label, dims)
            
            # Boyut bilgileri
            dims_text = ""
            if dims:
                dims_parts = [f"{k}: {v}" for k, v in dims.items()]
                dims_text = f'<div class="geometry-label">{" | ".join(dims_parts)}</div>'
            
            geo_html += f'''
                <div class="geometry-item">
                    {svg}
                    {dims_text}
                </div>
            '''
        
        geo_html += '</div>'
        
        # Özellik tablosu
        if items and items[0].get('properties'):
            headers = ['Özellik'] + [item.get('name', f'Model {chr(65+i)}') for i, item in enumerate(items)]
            rows = []
            
            # Tüm özellikleri topla
            all_props = []
            for item in items:
                for prop in item.get('properties', []):
                    if prop.get('label') not in all_props:
                        all_props.append(prop.get('label'))
            
            for prop_name in all_props:
                row = [prop_name]
                for item in items:
                    val = next((p.get('value', '-') for p in item.get('properties', []) 
                               if p.get('label') == prop_name), '-')
                    row.append(val)
                rows.append(row)
            
            table_html = TableRenderer.render(headers, rows, color='blue')
            content = geo_html + table_html
        else:
            content = geo_html
        
        desc = f"Geometrik karşılaştırma ({geo_type}): {len(items)} öğe"
        return content, desc
    
    def _render_comparison(self, analysis: Dict) -> Tuple[str, str]:
        """Basit karşılaştırma kartları"""
        items = analysis.get('items', [])
        content = ComparisonRenderer.render_cards(items)
        desc = f"Karşılaştırma: {len(items)} seçenek"
        return content, desc
    
    def _render_table(self, analysis: Dict) -> Tuple[str, str]:
        """Tablo görselleştirme"""
        table_data = analysis.get('table', {})
        headers = table_data.get('headers', [])
        rows = table_data.get('rows', [])
        highlight = table_data.get('highlight_column')
        
        content = TableRenderer.render(headers, rows, highlight)
        desc = f"Tablo: {len(headers)} sütun, {len(rows)} satır"
        return content, desc
    
    def _render_bar_chart(self, analysis: Dict) -> Tuple[str, str]:
        """Çubuk grafik"""
        chart_data = analysis.get('chart_data', [])
        chart_title = analysis.get('chart_title', '')
        
        svg = ChartRenderer.bar_chart(800, 300, chart_data, chart_title)
        content = f'''
            <div class="chart-container">
                <div class="chart-title">{chart_title}</div>
                {svg}
            </div>
        '''
        desc = f"Çubuk grafik: {len(chart_data)} veri noktası"
        return content, desc
    
    def _render_line_chart(self, analysis: Dict) -> Tuple[str, str]:
        """Çizgi grafik"""
        chart_data = analysis.get('chart_data', [])
        chart_title = analysis.get('chart_title', '')
        
        svg = ChartRenderer.line_chart(800, 300, chart_data, chart_title)
        content = f'''
            <div class="chart-container">
                <div class="chart-title">{chart_title}</div>
                {svg}
            </div>
        '''
        desc = f"Çizgi grafik: {len(chart_data)} veri noktası"
        return content, desc
    
    def _render_pie_chart(self, analysis: Dict) -> Tuple[str, str]:
        """Pasta grafik"""
        chart_data = analysis.get('chart_data', [])
        chart_title = analysis.get('chart_title', '')
        
        svg = ChartRenderer.pie_chart(400, 300, chart_data)
        content = f'''
            <div class="chart-container">
                <div class="chart-title">{chart_title}</div>
                <div style="display: flex; justify-content: center;">{svg}</div>
            </div>
        '''
        desc = f"Pasta grafik: {len(chart_data)} dilim"
        return content, desc
    
    def _render_geometry(self, analysis: Dict) -> Tuple[str, str]:
        """Sadece geometrik şekiller"""
        shapes = analysis.get('shapes', [])
        geo_type = analysis.get('geometry_type', 'cylinder')
        
        geo_html = '<div class="geometry-container">'
        color_order = ['blue', 'pink', 'green', 'orange']
        
        for i, shape in enumerate(shapes):
            color = COLORS.get(shape.get('color', color_order[i % len(color_order)]))
            label = shape.get('label', '')
            dims = shape.get('dimensions', {})
            
            if geo_type == 'cylinder':
                svg = GeometryRenderer.cylinder(200, 180, color, label, dims, True)
            elif geo_type == 'cube':
                svg = GeometryRenderer.cube(180, 180, color, label, dims)
            elif geo_type == 'cone':
                svg = GeometryRenderer.cone(180, 180, color, label, dims)
            else:
                svg = GeometryRenderer.sphere(180, 180, color, label, dims)
            
            geo_html += f'<div class="geometry-item">{svg}</div>'
        
        geo_html += '</div>'
        
        desc = f"Geometri ({geo_type}): {len(shapes)} şekil"
        return geo_html, desc
    
    def _render_infographic(self, analysis: Dict) -> Tuple[str, str]:
        """Bilgi kartları infografik"""
        info_items = analysis.get('info_items', [])
        
        cards_html = ""
        for item in info_items:
            cards_html += f'''
                <div class="info-card">
                    <div class="icon">{item.get('icon', '📊')}</div>
                    <div class="label">{item.get('label', '')}</div>
                    <div class="value">{item.get('value', '')}</div>
                </div>
            '''
        
        content = f'<div class="info-grid">{cards_html}</div>'
        desc = f"İnfografik: {len(info_items)} bilgi kartı"
        return content, desc


# ============== GEMİNİ ANALİZÖR ==============

class GeminiAnalyzer:
    """Akıllı soru analizi"""
    
    PROMPT = """
Sen bir matematik eğitimi görsel tasarım uzmanısın. Verilen soruyu analiz et ve EN UYGUN görsel tipini seç.

🎯 AMAÇ: Soruyu anlamayı kolaylaştıracak, profesyonel ve eğitici bir görsel oluşturmak.

═══════════════════════════════════════════════════════════════
📊 MEVCUT GÖRSEL TİPLERİ
═══════════════════════════════════════════════════════════════

1. "comparison_geometry" → Geometrik şekillerle karşılaştırma
   - SİLİNDİR bataryalar, depolar, kutular
   - KÜP şeklinde cisimler
   - KONİ, KÜRE
   - İki veya daha fazla şeklin boyut/özellik karşılaştırması
   
2. "comparison" → Basit karşılaştırma kartları
   - Firmalar, tarifeler, planlar
   - Sayısal değerlerin yan yana gösterimi
   
3. "table" → Veri tablosu
   - Çoklu satır-sütun verisi
   - Zaman serileri
   
4. "bar_chart" → Çubuk grafik
   - Kategorik karşılaştırmalar
   - Miktarların görsel karşılaştırması
   
5. "line_chart" → Çizgi grafik
   - Zamanla değişim
   - Trend gösterimi
   
6. "pie_chart" → Pasta grafik
   - Yüzde dağılımları
   - Oransal veriler
   
7. "geometry" → Sadece geometrik şekiller
   - Tek veya çoklu şekil
   - Ölçüler ve boyutlar
   
8. "infographic" → Bilgi kartları
   - Ayrı ayrı veri noktaları
   - İkon + değer formatı

═══════════════════════════════════════════════════════════════
🔍 ANALİZ KRİTERLERİ
═══════════════════════════════════════════════════════════════

✅ "comparison_geometry" KULLAN:
- "silindir", "batarya", "kutu", "depo", "kap" gibi 3D cisimler varsa
- "çap", "yarıçap", "yükseklik", "kenar" gibi geometrik ölçüler varsa
- İki veya daha fazla cismin karşılaştırılması isteniyorsa
- Yüzey alanı, hacim hesabı gerekiyorsa

✅ "comparison" KULLAN:
- Sadece sayısal değer karşılaştırması varsa
- Geometrik şekil YOK ama iki seçenek varsa

✅ "table" KULLAN:
- 3+ satır veri varsa
- Açık tablo formatı verilmişse

✅ "bar_chart" KULLAN:
- Kategorilerin miktarları karşılaştırılıyorsa
- "en çok", "en az", "karşılaştır" ifadeleri varsa

✅ "line_chart" KULLAN:
- Zamanla değişim varsa (gün, ay, yıl)
- Trend, artış, azalış analizi

✅ "geometry" KULLAN:
- Tek bir geometrik şeklin detaylı gösterimi
- Karşılaştırma YOK ama şekil var

═══════════════════════════════════════════════════════════════
📋 JSON ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════

{
  "visual_required": true,
  "visual_type": "comparison_geometry|comparison|table|bar_chart|line_chart|pie_chart|geometry|infographic",
  "geometry_type": "cylinder|cube|cone|sphere",  // geometry içeriyorsa
  
  "title": "Başlık",
  "subtitle": "Alt başlık (opsiyonel)",
  
  "items": [  // comparison ve comparison_geometry için
    {
      "name": "Model A",
      "color": "blue",
      "icon": "A",
      "dimensions": {"cap": "4 cm", "yukseklik": "10 cm"},  // geometri varsa
      "properties": [
        {"label": "Kapasite", "value": "5000 mAh"},
        {"label": "Şarj Süresi", "value": "1 saat"}
      ]
    }
  ],
  
  "table": {  // table tipi için
    "headers": ["Sütun1", "Sütun2"],
    "rows": [["değer1", "değer2"]],
    "highlight_column": null
  },
  
  "chart_data": [  // grafikler için
    {"label": "A", "value": 100, "color": "blue"}
  ],
  "chart_title": "Grafik Başlığı",
  
  "question_text": "SORUNUN TAM METNİ - Statik değil, gerçek soru!",
  
  "simplified_text": "Sadeleştirilmiş soru metni",
  
  "quality_score": 8
}

═══════════════════════════════════════════════════════════════
⚠️ KRİTİK KURALLAR
═══════════════════════════════════════════════════════════════

1. "question_text" ASLA statik olmamalı!
   ❌ YANLIŞ: "Hangisi daha avantajlı?"
   ✅ DOĞRU: "Seçilen bataryanın dış yüzeyini kaplamak için kullanılacak ısı yalıtım malzemesinin maliyeti kaç TL olacaktır?"

2. Geometrik cisimler varsa MUTLAKA "comparison_geometry" veya "geometry" kullan!

3. "items" içindeki "properties" ASLA boş olmamalı!

4. Tüm sayısal değerler görsele aktarılmalı!

═══════════════════════════════════════════════════════════════
📝 ÖRNEK: SİLİNDİR BATARYA SORUSU
═══════════════════════════════════════════════════════════════

SORU: "A ve B silindir bataryalarını karşılaştırıyorlar. A: çap 4cm, yükseklik 10cm, 5000mAh. B: çap 6cm, yükseklik 8cm, 6000mAh. Enerji yoğunluğu en yüksek olanın yüzey kaplaması kaç TL?"

ÇIKTI:
{
  "visual_required": true,
  "visual_type": "comparison_geometry",
  "geometry_type": "cylinder",
  "title": "Silindir Batarya Karşılaştırması",
  "items": [
    {
      "name": "Model A",
      "color": "blue",
      "icon": "A",
      "dimensions": {"cap": "4 cm", "yukseklik": "10 cm"},
      "properties": [
        {"label": "Çap", "value": "4 cm"},
        {"label": "Yükseklik", "value": "10 cm"},
        {"label": "Kapasite", "value": "5000 mAh"},
        {"label": "Şarj Süresi", "value": "1 saat"},
        {"label": "Birim Maliyet", "value": "15 TL"}
      ]
    },
    {
      "name": "Model B",
      "color": "pink",
      "icon": "B",
      "dimensions": {"cap": "6 cm", "yukseklik": "8 cm"},
      "properties": [
        {"label": "Çap", "value": "6 cm"},
        {"label": "Yükseklik", "value": "8 cm"},
        {"label": "Kapasite", "value": "6000 mAh"},
        {"label": "Şarj Süresi", "value": "1.2 saat"},
        {"label": "Birim Maliyet", "value": "20 TL"}
      ]
    }
  ],
  "question_text": "Enerji yoğunluğu (mAh/cm³) en yüksek olan bataryanın dış yüzeyini kaplamak için kullanılacak ısı yalıtım malzemesinin maliyeti kaç TL olacaktır? (π = 3)",
  "simplified_text": "Görselde özellikleri verilen silindir bataryalardan enerji yoğunluğu en yüksek olanın yüzey kaplama maliyetini hesaplayınız.",
  "quality_score": 9
}

═══════════════════════════════════════════════════════════════

Şimdi aşağıdaki soruyu analiz et:

"""
    
    def __init__(self):
        if not Config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY gerekli!")
        
        if NEW_GENAI:
            self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        else:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        
        logger.info(f"Gemini hazır: {Config.GEMINI_MODEL}")
    
    def analyze(self, question_text: str, scenario_text: str = None) -> Optional[Dict]:
        """Soruyu analiz et"""
        try:
            full_text = question_text
            if scenario_text:
                full_text = f"SENARYO:\n{scenario_text}\n\nSORU:\n{question_text}"
            
            prompt = self.PROMPT + full_text
            
            if NEW_GENAI:
                response = self.client.models.generate_content(
                    model=Config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json"
                    )
                )
                result_text = response.text
            else:
                response = self.model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': 0.3,
                        'response_mime_type': 'application/json'
                    }
                )
                result_text = response.text
            
            result = json.loads(result_text)
            
            if not result.get('visual_required', False):
                logger.info("Görsel gerekmez")
                return None
            
            return result
            
        except Exception as e:
            logger.error(f"Analiz hatası: {e}")
            return None


# ============== VERİTABANI ==============

class DatabaseManager:
    def __init__(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("Supabase bilgileri gerekli!")
        self.client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_scenario_questions(self, limit: int = 30) -> List[Dict]:
        try:
            response = self.client.table('question_bank') \
                .select('*') \
                .is_('image_url', 'null') \
                .eq('is_active', True) \
                .not_.is_('scenario_text', 'null') \
                .limit(limit) \
                .execute()
            questions = response.data if response.data else []
            logger.info(f"{len(questions)} senaryo sorusu bulundu")
            return questions
        except Exception as e:
            logger.error(f"Soru çekme hatası: {e}")
            return []
    
    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        try:
            self.client.storage.from_(Config.STORAGE_BUCKET).upload(
                filename, image_bytes, {'content-type': 'image/png', 'upsert': 'true'}
            )
            return self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
        except Exception as e:
            logger.error(f"Upload hatası: {e}")
            return None
    
    def update_question(self, qid: int, image_url: str, new_text: str = None) -> bool:
        try:
            data = {'image_url': image_url}
            if new_text:
                data['original_text'] = new_text
            self.client.table('question_bank').update(data).eq('id', qid).execute()
            return True
        except Exception as e:
            logger.error(f"Güncelleme hatası: {e}")
            return False


# ============== HTML -> PNG ==============

class ImageConverter:
    def __init__(self):
        self.playwright = None
        self.browser = None
    
    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        logger.info("Playwright başlatıldı")
    
    def stop(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Playwright kapatıldı")
    
    def html_to_png(self, html: str) -> Optional[bytes]:
        try:
            page = self.browser.new_page(viewport={'width': Config.IMAGE_WIDTH + 100, 'height': 800})
            page.set_content(html)
            page.wait_for_load_state('networkidle')
            container = page.query_selector('.container')
            screenshot = container.screenshot(type='png') if container else page.screenshot(type='png')
            page.close()
            return screenshot
        except Exception as e:
            logger.error(f"Screenshot hatası: {e}")
            return None


# ============== ANA BOT ==============

class ScenarioBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.analyzer = GeminiAnalyzer()
        self.renderer = VisualRenderer()
        self.converter = ImageConverter()
        self.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0}
    
    def run(self):
        logger.info("=" * 60)
        logger.info("SENARYO GÖRSEL BOTU v3.0 BAŞLADI")
        logger.info("=" * 60)
        
        self.converter.start()
        
        try:
            batch_size = Config.TEST_BATCH_SIZE if Config.TEST_MODE else Config.BATCH_SIZE
            logger.info(f"Mod: {'TEST' if Config.TEST_MODE else 'PRODUCTION'}")
            logger.info(f"Batch: {batch_size}")
            
            questions = self.db.get_scenario_questions(batch_size)
            if not questions:
                logger.warning("Soru bulunamadı!")
                return
            
            self.stats['total'] = len(questions)
            
            for i, q in enumerate(questions):
                logger.info(f"\n--- Soru {i+1}/{len(questions)} (ID: {q['id']}) ---")
                self._process(q)
                time.sleep(1)
            
            self._report()
        finally:
            self.converter.stop()
    
    def _process(self, question: Dict):
        qid = question['id']
        text = question.get('original_text', '')
        scenario = question.get('scenario_text', '')
        
        if not text:
            self.stats['skipped'] += 1
            return
        
        logger.info("Analiz...")
        analysis = self.analyzer.analyze(text, scenario)
        
        if not analysis:
            self.stats['skipped'] += 1
            return
        
        visual_type = analysis.get('visual_type', 'comparison')
        logger.info(f"Görsel tipi: {visual_type}")
        
        logger.info("Render...")
        html, desc = self.renderer.render(analysis)
        
        if not html:
            self.stats['failed'] += 1
            return
        
        logger.info("PNG...")
        png = self.converter.html_to_png(html)
        
        if not png:
            self.stats['failed'] += 1
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"scenario/q_{qid}_{timestamp}.png"
        
        logger.info("Upload...")
        url = self.db.upload_image(png, filename)
        
        if not url:
            self.stats['failed'] += 1
            return
        
        simplified = analysis.get('simplified_text')
        if self.db.update_question(qid, url, simplified if simplified != text else None):
            logger.info(f"✅ #{qid}: BAŞARILI ({visual_type})")
            self.stats['success'] += 1
        else:
            self.stats['failed'] += 1
    
    def _report(self):
        logger.info("\n" + "=" * 60)
        logger.info("SONUÇ RAPORU")
        logger.info("=" * 60)
        logger.info(f"Toplam: {self.stats['total']}")
        logger.info(f"✅ Başarılı: {self.stats['success']}")
        logger.info(f"⏭️ Atlanan: {self.stats['skipped']}")
        logger.info(f"❌ Başarısız: {self.stats['failed']}")
        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"Oran: %{rate:.1f}")


if __name__ == "__main__":
    try:
        bot = ScenarioBot()
        bot.run()
    except Exception as e:
        logger.error(f"Bot hatası: {e}")
        raise
