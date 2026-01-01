"""
Senaryo Görsel Botu v2.0
========================
- Senaryo sorularındaki tablo ve verileri görsele aktarır
- Soru metnini sadeleştirir (tablo/veri kısmını çıkarır)
- Gemini ile kalite kontrolü yapar (puan sistemi)
- Onay gelirse değişikliği uygular

GitHub Actions ile çalışır.
Günde 3 seans, her seansta 30 soru işler.
"""

import os
import json
import time
import logging
import base64
import re
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from string import Template
import tempfile

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

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============== YAPILANDIRMA ==============

class Config:
    """Bot yapılandırması"""
    # Supabase
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    
    # Gemini
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    GEMINI_MODEL = 'gemini-2.5-pro'
    
    # Storage
    STORAGE_BUCKET = 'questions-images'
    
    # İşlem limitleri
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30'))
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 10
    
    # Görsel ayarları
    IMAGE_WIDTH = 900
    IMAGE_HEIGHT = 600
    
    # Kalite eşiği (10 üzerinden)
    QUALITY_THRESHOLD = 7


# ============== HTML TEMPLATE'LERİ ==============

class HTMLTemplates:
    """Soru tiplerine göre HTML şablonları"""
    
    # Renk paleti
    COLORS = {
        'blue': {'primary': '#3b82f6', 'light': '#dbeafe', 'dark': '#1e40af'},
        'red': {'primary': '#ef4444', 'light': '#fee2e2', 'dark': '#991b1b'},
        'green': {'primary': '#22c55e', 'light': '#dcfce7', 'dark': '#166534'},
        'purple': {'primary': '#8b5cf6', 'light': '#f3e8ff', 'dark': '#6b21a8'},
        'orange': {'primary': '#f59e0b', 'light': '#fef3c7', 'dark': '#92400e'},
        'pink': {'primary': '#ec4899', 'light': '#fce7f3', 'dark': '#9d174d'},
        'teal': {'primary': '#14b8a6', 'light': '#ccfbf1', 'dark': '#115e59'},
        'indigo': {'primary': '#6366f1', 'light': '#e0e7ff', 'dark': '#4338ca'},
    }
    
    # Ana CSS stilleri
    BASE_CSS = """
        @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Nunito', -apple-system, BlinkMacSystemFont, sans-serif;
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
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image: 
                linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px),
                linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px);
            background-size: 30px 30px;
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
            margin-bottom: 12px;
        }
        
        .badges {
            display: flex;
            justify-content: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        
        .content {
            position: relative;
            z-index: 1;
        }
        
        .card {
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 16px;
        }
        
        .card h3 {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .data-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.7);
            border-radius: 10px;
            margin-bottom: 8px;
        }
        
        .data-label {
            font-size: 13px;
            color: #475569;
            font-weight: 600;
        }
        
        .data-value {
            font-size: 15px;
            font-weight: 700;
        }
        
        .highlight-box {
            padding: 16px 20px;
            border-radius: 14px;
            text-align: center;
            margin-top: 12px;
        }
        
        .question-mark {
            font-size: 28px;
            font-weight: 800;
            color: #dc2626;
        }
    """
    
    # ==================== VERİ TABLOSU TEMPLATE ====================
    TABLO_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .table-card {
                background: ${color_light};
                border: 3px solid ${color_primary};
                border-radius: 18px;
                padding: 24px;
                margin-bottom: 20px;
            }
            
            .table-card h3 {
                color: ${color_dark};
                font-size: 18px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            table {
                width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                background: white;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
            }
            
            th {
                background: linear-gradient(135deg, ${color_primary} 0%, ${color_dark} 100%);
                color: white;
                padding: 14px 18px;
                text-align: center;
                font-weight: 700;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            td {
                padding: 12px 18px;
                text-align: center;
                font-size: 15px;
                font-weight: 600;
                color: #334155;
                border-bottom: 1px solid #e2e8f0;
            }
            
            tr:last-child td {
                border-bottom: none;
            }
            
            tr:nth-child(even) td {
                background: #f8fafc;
            }
            
            tr:hover td {
                background: ${color_light};
            }
            
            .question-cell {
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%) !important;
                color: #92400e;
                font-weight: 800;
                font-size: 18px;
            }
            
            .highlight-row td {
                background: linear-gradient(135deg, ${color_light} 0%, white 100%) !important;
                font-weight: 700;
            }
            
            .source-note {
                margin-top: 16px;
                padding: 12px 16px;
                background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                border-radius: 10px;
                font-size: 12px;
                color: #64748b;
                text-align: center;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="content">
                <div class="table-card">
                    <h3>📊 ${tablo_baslik}</h3>
                    <table>
                        ${table_html}
                    </table>
                    ${source_note_html}
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== VERİ KARTLARI TEMPLATE ====================
    VERI_KARTLARI_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .data-grid {
                display: grid;
                grid-template-columns: repeat(${grid_cols}, 1fr);
                gap: 16px;
                margin-bottom: 20px;
            }
            
            .data-card {
                background: linear-gradient(135deg, ${color_light} 0%, white 100%);
                border: 2px solid ${color_primary};
                border-radius: 16px;
                padding: 20px;
                text-align: center;
                transition: transform 0.2s;
            }
            
            .data-card:hover {
                transform: translateY(-3px);
            }
            
            .data-card .icon {
                font-size: 32px;
                margin-bottom: 10px;
            }
            
            .data-card .label {
                font-size: 12px;
                color: #64748b;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 6px;
            }
            
            .data-card .value {
                font-size: 24px;
                font-weight: 800;
                color: ${color_dark};
            }
            
            .data-card .unit {
                font-size: 14px;
                color: #94a3b8;
                margin-top: 4px;
            }
            
            .data-card.highlight {
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border-color: #f59e0b;
            }
            
            .data-card.highlight .value {
                color: #92400e;
            }
            
            .formula-box {
                background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                border-radius: 14px;
                padding: 16px 24px;
                text-align: center;
                margin-top: 16px;
            }
            
            .formula-box .formula {
                font-size: 18px;
                font-weight: 700;
                color: #334155;
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="content">
                <div class="data-grid">
                    ${cards_html}
                </div>
                ${formula_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== KARŞILAŞTIRMA TEMPLATE ====================
    KARSILASTIRMA_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .comparison {
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
                position: relative;
            }
            
            .compare-card {
                flex: 1;
                border-radius: 18px;
                padding: 20px;
                border: 3px solid;
            }
            
            .compare-card h3 {
                font-size: 18px;
                margin-bottom: 16px;
            }
            
            .compare-card .icon {
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
                font-size: 16px;
                font-weight: 800;
                color: #64748b;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                border: 3px solid white;
                z-index: 10;
            }
            
            .question-box {
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border: 3px solid #f59e0b;
                border-radius: 16px;
                padding: 20px;
                text-align: center;
            }
            
            .question-box .title {
                font-size: 12px;
                color: #92400e;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 8px;
                font-weight: 700;
            }
            
            .question-box .question {
                font-size: 18px;
                font-weight: 800;
                color: #78350f;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="content">
                <div class="comparison">
                    ${cards_html}
                    <div class="vs-badge">VS</div>
                </div>
                
                <div class="question-box">
                    <div class="title">❓ Soru</div>
                    <div class="question">${soru_metni}</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== HAREKET/YOL TEMPLATE ====================
    HAREKET_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .road-diagram {
                position: relative;
                height: 320px;
                margin: 20px 0;
            }
            
            .road {
                position: absolute;
                border-radius: 8px;
            }
            
            .road-vertical {
                width: 70px;
                background: linear-gradient(180deg, ${color1_primary} 0%, ${color1_dark} 100%);
            }
            
            .road-horizontal {
                height: 70px;
                background: linear-gradient(90deg, ${color2_primary} 0%, ${color2_dark} 100%);
            }
            
            .road::after {
                content: '';
                position: absolute;
                background: repeating-linear-gradient(
                    var(--line-direction),
                    #ffffff 0px, #ffffff 15px,
                    transparent 15px, transparent 30px
                );
                opacity: 0.7;
            }
            
            .road-vertical::after {
                --line-direction: 180deg;
                left: 50%;
                top: 15px;
                bottom: 15px;
                width: 3px;
                transform: translateX(-50%);
            }
            
            .road-horizontal::after {
                --line-direction: 90deg;
                top: 50%;
                left: 15px;
                right: 15px;
                height: 3px;
                transform: translateY(-50%);
            }
            
            .vehicle {
                position: absolute;
                padding: 10px 16px;
                border-radius: 10px;
                font-weight: 700;
                font-size: 14px;
                color: white;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                z-index: 10;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            
            .info-label {
                position: absolute;
                padding: 8px 14px;
                border-radius: 20px;
                font-weight: 700;
                font-size: 13px;
                box-shadow: 0 3px 12px rgba(0, 0, 0, 0.1);
                z-index: 15;
                white-space: nowrap;
            }
            
            .target-label {
                position: absolute;
                background: linear-gradient(135deg, #f3e8ff 0%, #e9d5ff 100%);
                color: #6b21a8;
                padding: 10px 20px;
                border-radius: 25px;
                font-weight: 700;
                font-size: 13px;
                border: 2px solid #8b5cf6;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.2);
                z-index: 20;
                display: flex;
                align-items: center;
                gap: 8px;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="road-diagram">
                ${diagram_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== HAVUZ/MUSLUK TEMPLATE ====================
    HAVUZ_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .pool-diagram {
                display: flex;
                justify-content: center;
                align-items: flex-end;
                gap: 40px;
                padding: 30px;
                background: linear-gradient(180deg, #e0f2fe 0%, #bae6fd 100%);
                border-radius: 16px;
                margin-bottom: 20px;
                min-height: 250px;
            }
            
            .pool {
                width: 200px;
                height: 150px;
                background: linear-gradient(180deg, #0ea5e9 0%, #0284c7 100%);
                border-radius: 0 0 20px 20px;
                border: 4px solid #0369a1;
                position: relative;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            
            .pool-label {
                color: white;
                font-size: 20px;
                font-weight: 800;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
            }
            
            .pipe {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 10px;
            }
            
            .pipe-icon {
                width: 60px;
                height: 80px;
                border-radius: 10px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                color: white;
                font-weight: 700;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            }
            
            .pipe-icon .emoji {
                font-size: 24px;
                margin-bottom: 4px;
            }
            
            .pipe-icon .name {
                font-size: 12px;
            }
            
            .pipe-info {
                background: white;
                padding: 10px 16px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            
            .pipe-info .label {
                font-size: 11px;
                color: #64748b;
            }
            
            .pipe-info .value {
                font-size: 16px;
                font-weight: 800;
            }
            
            .fill-pipe .pipe-icon {
                background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%);
            }
            
            .fill-pipe .pipe-info .value {
                color: #166534;
            }
            
            .drain-pipe .pipe-icon {
                background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%);
            }
            
            .drain-pipe .pipe-info .value {
                color: #991b1b;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="pool-diagram">
                ${diagram_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== YAŞ PROBLEMİ TEMPLATE ====================
    YAS_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .timeline {
                position: relative;
                padding: 30px 0;
                margin: 20px 0;
            }
            
            .timeline-line {
                position: absolute;
                left: 50px;
                right: 50px;
                top: 50%;
                height: 6px;
                background: linear-gradient(90deg, #94a3b8 0%, #64748b 50%, #94a3b8 100%);
                border-radius: 3px;
            }
            
            .timeline-points {
                display: flex;
                justify-content: space-between;
                position: relative;
                z-index: 1;
                padding: 0 30px;
            }
            
            .timeline-point {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 10px;
            }
            
            .point-marker {
                width: 24px;
                height: 24px;
                background: white;
                border: 4px solid ${color_primary};
                border-radius: 50%;
            }
            
            .point-label {
                font-size: 13px;
                font-weight: 700;
                color: #64748b;
            }
            
            .people-row {
                display: flex;
                justify-content: center;
                gap: 30px;
                margin: 30px 0;
            }
            
            .person-card {
                background: linear-gradient(135deg, ${color_light} 0%, white 100%);
                border: 3px solid ${color_primary};
                border-radius: 18px;
                padding: 20px;
                text-align: center;
                min-width: 140px;
            }
            
            .person-card .avatar {
                font-size: 48px;
                margin-bottom: 10px;
            }
            
            .person-card .name {
                font-size: 16px;
                font-weight: 800;
                color: ${color_dark};
                margin-bottom: 8px;
            }
            
            .person-card .age {
                font-size: 24px;
                font-weight: 800;
                color: ${color_primary};
            }
            
            .person-card .age-label {
                font-size: 12px;
                color: #64748b;
            }
            
            .relation-box {
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border: 2px solid #f59e0b;
                border-radius: 12px;
                padding: 14px 20px;
                text-align: center;
                margin-top: 16px;
            }
            
            .relation-box .relation {
                font-size: 16px;
                font-weight: 700;
                color: #92400e;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="content">
                ${timeline_html}
                
                <div class="people-row">
                    ${people_html}
                </div>
                
                ${relations_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== GENEL SENARYO TEMPLATE ====================
    GENEL_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .scenario-card {
                background: linear-gradient(135deg, ${color_light} 0%, white 100%);
                border: 3px solid ${color_primary};
                border-radius: 18px;
                padding: 24px;
                margin-bottom: 20px;
            }
            
            .scenario-card h3 {
                color: ${color_dark};
                font-size: 18px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .characters {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 20px;
            }
            
            .character {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 8px;
            }
            
            .character-avatar {
                font-size: 48px;
            }
            
            .character-name {
                font-size: 14px;
                font-weight: 700;
                color: #334155;
            }
            
            .info-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 12px;
            }
            
            .info-item {
                background: white;
                border-radius: 12px;
                padding: 14px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            }
            
            .info-item .label {
                font-size: 11px;
                color: #64748b;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 4px;
            }
            
            .info-item .value {
                font-size: 16px;
                font-weight: 700;
                color: ${color_dark};
            }
            
            .question-box {
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border: 3px solid #f59e0b;
                border-radius: 16px;
                padding: 20px;
                text-align: center;
            }
            
            .question-box .title {
                font-size: 12px;
                color: #92400e;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 8px;
                font-weight: 700;
            }
            
            .question-box .question {
                font-size: 18px;
                font-weight: 800;
                color: #78350f;
            }
        </style>
    </head>
    <body>
        <div class="container" style="width: ${width}px;">
            <div class="header">
                <h1>${baslik}</h1>
                <div class="badges">
                    ${badges_html}
                </div>
            </div>
            
            <div class="content">
                ${characters_html}
                
                <div class="scenario-card">
                    <h3>${icon} ${senaryo_baslik}</h3>
                    <div class="info-grid">
                        ${info_items_html}
                    </div>
                </div>
                
                <div class="question-box">
                    <div class="title">❓ Soru</div>
                    <div class="question">${soru_metni}</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


# ============== VERİTABANI ==============

class DatabaseManager:
    """Veritabanı işlemleri"""
    
    def __init__(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("Supabase bilgileri gerekli!")
        
        self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_scenario_questions(self, limit: int = 30) -> List[Dict]:
        """Görsel olmayan senaryo sorularını getir"""
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
        """Görseli storage'a yükle"""
        try:
            response = self.client.storage \
                .from_(Config.STORAGE_BUCKET) \
                .upload(filename, image_bytes, {
                    'content-type': 'image/png',
                    'upsert': 'true'
                })
            
            public_url = self.client.storage \
                .from_(Config.STORAGE_BUCKET) \
                .get_public_url(filename)
            
            return public_url
            
        except Exception as e:
            logger.error(f"Upload hatası: {e}")
            return None
    
    def update_question(self, question_id: int, image_url: str, 
                       new_text: str = None, new_scenario: str = None) -> bool:
        """Soru güncelle (görsel URL + sadeleştirilmiş metin)"""
        try:
            update_data = {'image_url': image_url}
            
            if new_text:
                update_data['original_text'] = new_text
            
            if new_scenario:
                update_data['scenario_text'] = new_scenario
            
            self.client.table('question_bank') \
                .update(update_data) \
                .eq('id', question_id) \
                .execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Güncelleme hatası: {e}")
            return False


# ============== GEMİNİ ANALİZÖR ==============

class GeminiAnalyzer:
    """Gemini ile soru analizi, metin sadeleştirme ve kalite kontrolü"""
    
    ANALYSIS_PROMPT = """
Sen bir matematik eğitimi görsel tasarım uzmanısın. Sana verilen senaryo sorusunu analiz et.

🎯 TEMEL AMAÇ: Soru metnindeki tablo, veri listesi veya sayısal bilgileri GÖRSEL'e aktararak soru metnini SADELEŞTIRMEK.

═══════════════════════════════════════════════════════════════
📋 ANALİZ KRİTERLERİ
═══════════════════════════════════════════════════════════════

✅ GÖRSEL YAPILACAK DURUMLAR:
1. TABLO varsa (satır-sütun formatında veri)
2. VERİ LİSTESİ varsa (madde madde sayısal değerler)
3. KARŞILAŞTIRMA varsa (iki seçenek, firma, plan)
4. HAREKET/YOL problemi varsa (hız, mesafe, süre)
5. HAVUZ/MUSLUK problemi varsa (dolum, boşaltma)
6. YAŞ problemi varsa (zaman içinde değişim)

❌ GÖRSEL YAPILMAYACAK:
- Sadece düz metin, hikaye anlatımı
- Karmaşık formül/graf teorisi
- Geometrik şekil gerektiren (üçgen, kare vb.)

═══════════════════════════════════════════════════════════════
📝 METİN SADELEŞTİRME KURALLARI
═══════════════════════════════════════════════════════════════

Görsel oluşturduktan sonra soru metninden:
1. Tablo formatındaki veriyi SİL (görsel'de olacak)
2. Madde madde veri listesini SİL
3. Sayısal değerleri tekrarlamadan sadece referans ver
4. "Tabloda verilen...", "Yukarıdaki verilere göre..." gibi ifadeler kullan
5. Sorunun asıl sorusunu (ne hesaplanacak) KORU

ÖRNEK:
ÖNCEKİ METİN:
"Defne bakteri sayısını gözlemliyor.
Zaman (dk): 0, 20, 40, 60
Bakteri: 50, 100, 200, 400
5 saat sonra kaç bakteri olacak?"

SADELEŞTİRİLMİŞ METİN:
"Defne bakteri sayısının zamanla değişimini gözlemliyor. Tabloda verilen gözlem sonuçlarına göre, 5 saat sonra petri kabında yaklaşık kaç bakteri olacaktır?"

═══════════════════════════════════════════════════════════════
🎨 GÖRSEL TİPLERİ
═══════════════════════════════════════════════════════════════

"tablo" → Satır-sütun veri tablosu
"veri_kartlari" → Ayrı ayrı veri kartları
"karsilastirma" → İki seçenek yan yana
"hareket" → Yol/hareket diyagramı
"havuz" → Havuz/musluk diyagramı
"yas" → Zaman çizelgesi + kişiler
"genel" → Genel senaryo kartı

═══════════════════════════════════════════════════════════════
📊 JSON ÇIKTI FORMATI
═══════════════════════════════════════════════════════════════

{
  "gorsel_pisinilir": true,
  "gorsel_tipi": "tablo|veri_kartlari|karsilastirma|hareket|havuz|yas|genel",
  "baslik": "Görselin başlığı",
  "icon": "📊|📈|⚖️|🚗|🏊|👨‍👩‍👧|📋",
  
  "verilenler": [
    {"etiket": "Açıklayıcı etiket", "deger": "Sayısal değer", "renk": "blue|pink|green|orange"}
  ],
  
  "ozel_pisiniler": {
    // Görsel tipine göre detaylar - ASLA BOŞ OLMAMALI!
  },
  
  "sadellestirilmis_metin": "Görsele aktarılan veriler çıkarıldıktan sonraki yeni soru metni",
  "sadellestirilmis_senaryo": "Varsa sadeleştirilmiş senaryo metni (null olabilir)",
  
  "cikarilan_veriler": ["Tablo: Bakteri sayısı değişimi", "Liste: Zaman değerleri"],
  
  "kalite_degerlendirmesi": {
    "gorunum_puani": 8,
    "sadeleştirme_puani": 9,
    "anlam_butunlugu_puani": 8,
    "toplam_puan": 8.3,
    "onay": true,
    "aciklama": "Değişiklik uygun, tablo görselde daha anlaşılır"
  }
}

═══════════════════════════════════════════════════════════════
📊 TABLO TİPİ DETAYLARI
═══════════════════════════════════════════════════════════════

"ozel_pisiniler": {
  "tablo": {
    "tablo_baslik": "Bakteri Sayısının Zamana Göre Değişimi",
    "basliklar": ["Zaman (dk)", "Bakteri Sayısı"],
    "satirlar": [
      ["0", "50"],
      ["20", "100"],
      ["40", "200"],
      ["60", "400"]
    ],
    "kaynak_notu": "İlk 1 saatlik gözlem sonuçları"
  }
}

═══════════════════════════════════════════════════════════════
📈 VERİ KARTLARI TİPİ DETAYLARI
═══════════════════════════════════════════════════════════════

"ozel_pisiniler": {
  "veri_kartlari": {
    "kartlar": [
      {"etiket": "Başlangıç", "deger": "50", "birim": "bakteri", "icon": "🦠"},
      {"etiket": "Periyot", "deger": "20", "birim": "dakika", "icon": "⏱️"},
      {"etiket": "Hedef Süre", "deger": "5", "birim": "saat", "icon": "🎯", "highlight": true}
    ],
    "formul": "Bakteri = Başlangıç × 2^(periyot sayısı)"
  }
}

═══════════════════════════════════════════════════════════════
⚖️ KARŞILAŞTIRMA TİPİ DETAYLARI (ÇOK ÖNEMLİ!)
═══════════════════════════════════════════════════════════════

⚠️ KRİTİK: "secenekler" array'i MUTLAKA doldurulmalı ve her seçeneğin
"ozellikler" listesi ASLA boş olmamalı! Tüm sayısal veriler buraya eklenmeli!

"ozel_pisiniler": {
  "karsilastirma": {
    "secenekler": [
      {
        "isim": "A Modeli",
        "renk": "blue",
        "icon": "A",
        "ozellikler": [
          {"etiket": "Doğruluk Oranı", "deger": "%80"},
          {"etiket": "Hata Payı", "deger": "±%15"},
          {"etiket": "Fazla Tahmin", "deger": "%5"}
        ]
      },
      {
        "isim": "B Modeli", 
        "renk": "pink",
        "icon": "B",
        "ozellikler": [
          {"etiket": "Doğruluk Oranı", "deger": "%70"},
          {"etiket": "Tahmin Aralığı", "deger": "±1/5"},
          {"etiket": "Temel Yağış", "deger": "150 mm"}
        ]
      }
    ]
  }
}

ÖRNEK SORU: "A ve B modellerini karşılaştırıyorlar. A modeli %80 doğruluk, %15 hata, %5 fazla tahmin. B modeli 1/5 aralık. Temel yağış 150mm."

Bu soruda "secenekler" ASLA boş olamaz! Tüm veriler kartlara dağıtılmalı!

═══════════════════════════════════════════════════════════════

Şimdi aşağıdaki soruyu analiz et:

"""
    
    VALIDATION_PROMPT = """
Sen bir kalite kontrol uzmanısın. Yapılan değişikliği değerlendir.

ORİJİNAL SORU:
{original_text}

SADELEŞTİRİLMİŞ SORU:
{simplified_text}

GÖRSEL İÇERİĞİ:
{visual_content}

═══════════════════════════════════════════════════════════════
KALİTE KRİTERLERİ (Her biri 10 üzerinden)
═══════════════════════════════════════════════════════════════

1. GÖRÜNÜM UYGUNLUĞU (gorunum_puani):
   - Görsel tasarım profesyonel mi?
   - Veriler net ve okunaklı mı?
   - Renk ve tipografi uyumlu mu?

2. SADELEŞTİRME KALİTESİ (sadelestirme_puani):
   - Tekrarlayan bilgiler kaldırıldı mı?
   - Metin gereksiz yere uzun mu?
   - Görsel-metin dengesi iyi mi?

3. ANLAM BÜTÜNLÜĞÜ (anlam_butunlugu_puani):
   - Soru hâlâ anlaşılır mı?
   - Önemli bilgi kaybı var mı?
   - Öğrenci soruyu çözebilir mi?

═══════════════════════════════════════════════════════════════

JSON olarak yanıt ver:
{
  "gorunum_puani": 1-10,
  "sadelestirme_puani": 1-10,
  "anlam_butunlugu_puani": 1-10,
  "toplam_puan": ortalama,
  "onay": true/false (toplam >= 7 ise true),
  "aciklama": "Kısa değerlendirme",
  "iyilestirme_onerileri": ["Öneri 1", "Öneri 2"] // onay false ise
}
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
    
    def analyze_question(self, question_text: str, scenario_text: str = None) -> Optional[Dict]:
        """Soruyu analiz et ve sadeleştir"""
        try:
            full_text = question_text
            if scenario_text:
                full_text = f"SENARYO:\n{scenario_text}\n\nSORU:\n{question_text}"
            
            prompt = self.ANALYSIS_PROMPT + full_text
            
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
            
            # JSON parse
            result = json.loads(result_text)
            
            if not result.get('gorsel_pisinilir', False):
                logger.info(f"Görsel gerekmez: {result.get('aciklama', '')}")
                return None
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {e}")
            return None
        except Exception as e:
            logger.error(f"Analiz hatası: {e}")
            return None
    
    def validate_changes(self, original_text: str, simplified_text: str, 
                        visual_content: str) -> Dict:
        """Değişiklikleri doğrula ve puanla"""
        try:
            prompt = self.VALIDATION_PROMPT.format(
                original_text=original_text,
                simplified_text=simplified_text,
                visual_content=visual_content
            )
            
            if NEW_GENAI:
                response = self.client.models.generate_content(
                    model=Config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json"
                    )
                )
                result_text = response.text
            else:
                response = self.model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': 0.2,
                        'response_mime_type': 'application/json'
                    }
                )
                result_text = response.text
            
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Doğrulama hatası: {e}")
            return {
                'toplam_puan': 0,
                'onay': False,
                'aciklama': f'Doğrulama başarısız: {str(e)}'
            }


# ============== HTML RENDERER ==============

class HTMLRenderer:
    """Analiz sonucunu HTML'e çevir"""
    
    def __init__(self):
        pass
    
    def _get_base_css(self):
        return Template(HTMLTemplates.BASE_CSS).safe_substitute(width=Config.IMAGE_WIDTH)
    
    def _render_badges(self, verilenler: List[Dict]) -> str:
        """Badge HTML oluştur"""
        badges = []
        for v in verilenler[:4]:  # Max 4 badge
            color = HTMLTemplates.COLORS.get(v.get('renk', 'blue'), HTMLTemplates.COLORS['blue'])
            badges.append(f'''
                <span class="badge" style="background: {color['light']}; color: {color['dark']};">
                    {v.get('etiket', '')}: {v.get('deger', '')}
                </span>
            ''')
        return '\n'.join(badges)
    
    def render(self, analysis: Dict) -> Tuple[Optional[str], str]:
        """HTML oluştur, görsel içerik açıklamasını da döndür"""
        gorsel_tipi = analysis.get('gorsel_tipi', 'genel')
        
        renderers = {
            'tablo': self._render_tablo,
            'veri_kartlari': self._render_veri_kartlari,
            'karsilastirma': self._render_karsilastirma,
            'hareket': self._render_hareket,
            'havuz': self._render_havuz,
            'yas': self._render_yas,
            'genel': self._render_genel
        }
        
        renderer = renderers.get(gorsel_tipi, self._render_genel)
        
        try:
            html = renderer(analysis)
            visual_desc = self._get_visual_description(analysis)
            return html, visual_desc
        except Exception as e:
            logger.error(f"Render hatası ({gorsel_tipi}): {e}")
            return None, ""
    
    def _get_visual_description(self, analysis: Dict) -> str:
        """Görsel içeriğinin metin açıklaması"""
        gorsel_tipi = analysis.get('gorsel_tipi', 'genel')
        ozel = analysis.get('ozel_pisiniler', {})
        
        if gorsel_tipi == 'tablo':
            tablo = ozel.get('tablo', {})
            basliklar = tablo.get('basliklar', [])
            satirlar = tablo.get('satirlar', [])
            desc = f"Tablo: {' | '.join(basliklar)}\n"
            for satir in satirlar[:5]:
                desc += f"  {' | '.join(str(s) for s in satir)}\n"
            return desc
        
        elif gorsel_tipi == 'veri_kartlari':
            kartlar = ozel.get('veri_kartlari', {}).get('kartlar', [])
            desc = "Veri Kartları:\n"
            for k in kartlar:
                desc += f"  {k.get('etiket')}: {k.get('deger')} {k.get('birim', '')}\n"
            return desc
        
        elif gorsel_tipi == 'karsilastirma':
            secenekler = ozel.get('karsilastirma', {}).get('secenekler', [])
            desc = "Karşılaştırma:\n"
            for s in secenekler:
                desc += f"  {s.get('isim')}:\n"
                for oz in s.get('ozellikler', []):
                    desc += f"    - {oz.get('etiket')}: {oz.get('deger')}\n"
            return desc
        
        return f"Görsel Tipi: {gorsel_tipi}\nBaşlık: {analysis.get('baslik', '')}"
    
    def _render_tablo(self, analysis: Dict) -> str:
        """Tablo görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('tablo', {})
        basliklar = ozel.get('basliklar', [])
        satirlar = ozel.get('satirlar', [])
        colors = HTMLTemplates.COLORS['blue']
        
        # Boş veri kontrolü
        if not basliklar or not satirlar:
            logger.warning("Tablo verileri boş! Verilenlerden oluşturuluyor...")
            verilenler = analysis.get('verilenler', [])
            if verilenler:
                basliklar = ['Özellik', 'Değer']
                satirlar = [[v.get('etiket', ''), v.get('deger', '')] for v in verilenler]
            else:
                logger.error("Tablo için veri bulunamadı!")
                return None
        
        # Tablo HTML
        table_parts = ['<thead><tr>']
        for b in basliklar:
            table_parts.append(f'<th>{b}</th>')
        table_parts.append('</tr></thead><tbody>')
        
        for satir in satirlar:
            table_parts.append('<tr>')
            for hucre in satir:
                is_question = '?' in str(hucre)
                css = 'question-cell' if is_question else ''
                table_parts.append(f'<td class="{css}">{hucre}</td>')
            table_parts.append('</tr>')
        
        table_parts.append('</tbody>')
        
        # Kaynak notu
        source_note = ozel.get('kaynak_notu', '')
        source_note_html = f'<div class="source-note">📝 {source_note}</div>' if source_note else ''
        
        html = Template(HTMLTemplates.TABLO_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Veri Tablosu'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            color_primary=colors['primary'],
            color_dark=colors['dark'],
            color_light=colors['light'],
            tablo_baslik=ozel.get('tablo_baslik', 'Veri'),
            table_html='\n'.join(table_parts),
            source_note_html=source_note_html
        )
        
        return html
    
    def _render_veri_kartlari(self, analysis: Dict) -> str:
        """Veri kartları görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('veri_kartlari', {})
        kartlar = ozel.get('kartlar', [])
        colors = HTMLTemplates.COLORS['indigo']
        
        # Boş veri kontrolü
        if not kartlar:
            logger.warning("Veri kartları boş! Verilenlerden oluşturuluyor...")
            verilenler = analysis.get('verilenler', [])
            if verilenler:
                icons = ['📊', '📈', '🎯', '⏱️', '💰', '📏']
                kartlar = []
                for i, v in enumerate(verilenler):
                    kartlar.append({
                        'etiket': v.get('etiket', ''),
                        'deger': v.get('deger', ''),
                        'birim': '',
                        'icon': icons[i % len(icons)]
                    })
            else:
                logger.error("Veri kartları için veri bulunamadı!")
                return None
        
        # Kartlar HTML
        cards_html_parts = []
        for kart in kartlar:
            highlight = 'highlight' if kart.get('highlight') else ''
            cards_html_parts.append(f'''
                <div class="data-card {highlight}">
                    <div class="icon">{kart.get('icon', '📊')}</div>
                    <div class="label">{kart.get('etiket', '')}</div>
                    <div class="value">{kart.get('deger', '')}</div>
                    <div class="unit">{kart.get('birim', '')}</div>
                </div>
            ''')
        
        # Formül
        formul = ozel.get('formul', '')
        formula_html = ''
        if formul:
            formula_html = f'''
                <div class="formula-box">
                    <div class="formula">{formul}</div>
                </div>
            '''
        
        grid_cols = min(len(kartlar), 4)
        
        html = Template(HTMLTemplates.VERI_KARTLARI_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Veriler'),
            badges_html='',
            color_primary=colors['primary'],
            color_dark=colors['dark'],
            color_light=colors['light'],
            grid_cols=grid_cols,
            cards_html='\n'.join(cards_html_parts),
            formula_html=formula_html
        )
        
        return html
    
    def _render_karsilastirma(self, analysis: Dict) -> str:
        """Karşılaştırma görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('karsilastirma', {})
        secenekler = ozel.get('secenekler', [])
        
        # Boş seçenek kontrolü - eğer yoksa verilenlerden oluştur
        if not secenekler or len(secenekler) < 2:
            logger.warning("Karşılaştırma seçenekleri boş, verilenlerden oluşturuluyor...")
            verilenler = analysis.get('verilenler', [])
            karakterler = analysis.get('karakterler', [])
            
            # Verilenlerden iki grup oluştur
            secenekler = []
            if karakterler and len(karakterler) >= 2:
                for i, k in enumerate(karakterler[:2]):
                    secenekler.append({
                        'isim': k.get('isim', f'Model {chr(65+i)}'),
                        'renk': ['blue', 'pink'][i],
                        'ozellikler': []
                    })
            else:
                secenekler = [
                    {'isim': 'A Modeli', 'renk': 'blue', 'ozellikler': []},
                    {'isim': 'B Modeli', 'renk': 'pink', 'ozellikler': []}
                ]
            
            # Verilenleri dağıt
            for j, v in enumerate(verilenler):
                idx = j % 2
                secenekler[idx]['ozellikler'].append({
                    'etiket': v.get('etiket', ''),
                    'deger': v.get('deger', '')
                })
        
        # Hala boşsa, görseli oluşturma
        if not secenekler or all(not s.get('ozellikler') for s in secenekler):
            logger.error("Karşılaştırma verileri tamamen boş!")
            return None
        
        cards_html_parts = []
        color_order = ['blue', 'pink', 'green', 'orange']
        
        for i, secenek in enumerate(secenekler[:2]):
            color_name = secenek.get('renk', color_order[i % len(color_order)])
            colors = HTMLTemplates.COLORS.get(color_name, HTMLTemplates.COLORS['blue'])
            
            props_html = ''
            for oz in secenek.get('ozellikler', []):
                props_html += f'''
                    <div class="data-row">
                        <span class="data-label">{oz.get('etiket', '')}</span>
                        <span class="data-value" style="color: {colors['dark']}">{oz.get('deger', '')}</span>
                    </div>
                '''
            
            cards_html_parts.append(f'''
                <div class="compare-card" style="background: {colors['light']}; border-color: {colors['primary']}">
                    <h3 style="color: {colors['dark']}">
                        <span class="icon" style="background: {colors['primary']}">{secenek.get('icon', chr(65+i))}</span>
                        {secenek.get('isim', f'Seçenek {i+1}')}
                    </h3>
                    {props_html}
                </div>
            ''')
        
        html = Template(HTMLTemplates.KARSILASTIRMA_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Karşılaştırma'),
            badges_html='',
            cards_html='\n'.join(cards_html_parts),
            soru_metni=analysis.get('soru_metni', 'Hangisi daha avantajlı?')
        )
        
        return html
    
    def _render_hareket(self, analysis: Dict) -> str:
        """Hareket/yol görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('hareket', {})
        colors1 = HTMLTemplates.COLORS['blue']
        colors2 = HTMLTemplates.COLORS['green']
        
        # Basit yatay yol diyagramı
        araclar = ozel.get('araclar', [])
        noktalar = ozel.get('noktalar', [])
        mesafe = ozel.get('mesafe', '')
        
        diagram_html = f'''
            <div class="road road-horizontal" style="top: 50%; left: 50px; right: 50px; transform: translateY(-50%);">
            </div>
        '''
        
        # Başlangıç ve bitiş noktaları
        if noktalar:
            for i, nokta in enumerate(noktalar):
                pos = 'left: 30px;' if nokta.get('konum') == 'sol' else 'right: 30px;' if nokta.get('konum') == 'sag' else 'left: 50%;'
                diagram_html += f'''
                    <div class="info-label" style="{pos} top: 20px; background: white; color: #334155;">
                        📍 {nokta.get('isim', '')}
                    </div>
                '''
        
        # Araçlar
        if araclar:
            for i, arac in enumerate(araclar):
                color = colors1 if i == 0 else colors2
                pos = 'left: 80px;' if arac.get('konum') == 'sol' else 'right: 80px;'
                diagram_html += f'''
                    <div class="vehicle" style="{pos} top: 50%; transform: translateY(-50%); background: {color['primary']};">
                        🚗 {arac.get('isim', '')} ({arac.get('hiz', '')})
                    </div>
                '''
        
        # Mesafe etiketi
        if mesafe:
            diagram_html += f'''
                <div class="target-label" style="left: 50%; bottom: 30px; transform: translateX(-50%);">
                    📏 {mesafe}
                </div>
            '''
        
        html = Template(HTMLTemplates.HAREKET_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Hareket Problemi'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            color1_primary=colors1['primary'],
            color1_dark=colors1['dark'],
            color2_primary=colors2['primary'],
            color2_dark=colors2['dark'],
            diagram_html=diagram_html
        )
        
        return html
    
    def _render_havuz(self, analysis: Dict) -> str:
        """Havuz/musluk görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('havuz', {})
        
        havuz_kapasitesi = ozel.get('kapasite', '?')
        musluklar = ozel.get('musluklar', [])
        
        diagram_html = '<div class="pool"><span class="pool-label">' + str(havuz_kapasitesi) + '</span></div>'
        
        for i, musluk in enumerate(musluklar):
            tip = musluk.get('tip', 'dolum')
            pipe_class = 'fill-pipe' if tip == 'dolum' else 'drain-pipe'
            emoji = '🚰' if tip == 'dolum' else '🔻'
            
            diagram_html += f'''
                <div class="pipe {pipe_class}">
                    <div class="pipe-icon">
                        <span class="emoji">{emoji}</span>
                        <span class="name">{musluk.get('isim', f'Musluk {i+1}')}</span>
                    </div>
                    <div class="pipe-info">
                        <div class="label">Hız</div>
                        <div class="value">{musluk.get('hiz', '?')}</div>
                    </div>
                </div>
            '''
        
        html = Template(HTMLTemplates.HAVUZ_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Havuz Problemi'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            diagram_html=diagram_html
        )
        
        return html
    
    def _render_yas(self, analysis: Dict) -> str:
        """Yaş problemi görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('yas', {})
        colors = HTMLTemplates.COLORS['purple']
        
        kisiler = ozel.get('kisiler', [])
        zaman_noktalari = ozel.get('zaman_noktalari', [])
        iliskiler = ozel.get('iliskiler', [])
        
        # Zaman çizelgesi
        timeline_html = ''
        if zaman_noktalari:
            timeline_html = '''
                <div class="timeline">
                    <div class="timeline-line"></div>
                    <div class="timeline-points">
            '''
            for nokta in zaman_noktalari:
                timeline_html += f'''
                    <div class="timeline-point">
                        <div class="point-marker"></div>
                        <div class="point-label">{nokta}</div>
                    </div>
                '''
            timeline_html += '</div></div>'
        
        # Kişiler
        people_html = ''
        for kisi in kisiler:
            people_html += f'''
                <div class="person-card">
                    <div class="avatar">{kisi.get('avatar', '👤')}</div>
                    <div class="name">{kisi.get('isim', 'Kişi')}</div>
                    <div class="age">{kisi.get('yas', '?')}</div>
                    <div class="age-label">yaş</div>
                </div>
            '''
        
        # İlişkiler
        relations_html = ''
        for iliski in iliskiler:
            relations_html += f'''
                <div class="relation-box">
                    <div class="relation">{iliski}</div>
                </div>
            '''
        
        html = Template(HTMLTemplates.YAS_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Yaş Problemi'),
            badges_html='',
            color_primary=colors['primary'],
            color_dark=colors['dark'],
            color_light=colors['light'],
            timeline_html=timeline_html,
            people_html=people_html,
            relations_html=relations_html
        )
        
        return html
    
    def _render_genel(self, analysis: Dict) -> str:
        """Genel senaryo görseli"""
        colors = HTMLTemplates.COLORS['purple']
        karakterler = analysis.get('karakterler', [])
        verilenler = analysis.get('verilenler', [])
        
        # Karakterler
        chars_html = ''
        if karakterler:
            chars_html = '<div class="characters">'
            for k in karakterler:
                chars_html += f'''
                    <div class="character">
                        <span class="character-avatar">{k.get('avatar', '👤')}</span>
                        <span class="character-name">{k.get('isim', 'Kişi')}</span>
                    </div>
                '''
            chars_html += '</div>'
        
        # Bilgi kutuları
        info_items = []
        for v in verilenler:
            info_items.append(f'''
                <div class="info-item">
                    <span class="label">{v.get('etiket', '')}</span>
                    <span class="value">{v.get('deger', '')}</span>
                </div>
            ''')
        
        html = Template(HTMLTemplates.GENEL_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Problem'),
            badges_html='',
            color_primary=colors['primary'],
            color_dark=colors['dark'],
            color_light=colors['light'],
            characters_html=chars_html,
            icon=analysis.get('icon', '📊'),
            senaryo_baslik='Verilenler',
            info_items_html='\n'.join(info_items),
            soru_metni=analysis.get('soru_metni', 'Hesaplayınız.')
        )
        
        return html


# ============== HTML -> PNG ==============

class ImageConverter:
    """HTML'i PNG'ye çevir"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
    
    def start(self):
        """Playwright başlat"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        logger.info("Playwright başlatıldı")
    
    def stop(self):
        """Playwright kapat"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Playwright kapatıldı")
    
    def html_to_png(self, html: str) -> Optional[bytes]:
        """HTML'i PNG'ye çevir"""
        try:
            page = self.browser.new_page(viewport={
                'width': Config.IMAGE_WIDTH + 100,
                'height': Config.IMAGE_HEIGHT + 100
            })
            
            page.set_content(html)
            page.wait_for_load_state('networkidle')
            
            # Container elementini bul ve screenshot al
            container = page.query_selector('.container')
            if container:
                screenshot = container.screenshot(type='png')
            else:
                screenshot = page.screenshot(type='png', full_page=False)
            
            page.close()
            return screenshot
            
        except Exception as e:
            logger.error(f"Screenshot hatası: {e}")
            return None


# ============== ANA BOT ==============

class ScenarioBot:
    """Ana senaryo görsel botu v2.0"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.analyzer = GeminiAnalyzer()
        self.renderer = HTMLRenderer()
        self.converter = ImageConverter()
        
        self.stats = {
            'total': 0,
            'success': 0,
            'skipped': 0,
            'failed': 0,
            'rejected': 0,  # Kalite kontrolünden geçemeyenler
            'avg_quality': 0
        }
        self.quality_scores = []
    
    def run(self):
        """Botu çalıştır"""
        logger.info("="*60)
        logger.info("SENARYO GÖRSEL BOTU v2.0 BAŞLADI")
        logger.info("="*60)
        
        # Playwright başlat
        self.converter.start()
        
        try:
            batch_size = Config.TEST_BATCH_SIZE if Config.TEST_MODE else Config.BATCH_SIZE
            logger.info(f"Mod: {'TEST' if Config.TEST_MODE else 'PRODUCTION'}")
            logger.info(f"Batch: {batch_size}")
            logger.info(f"Kalite Eşiği: {Config.QUALITY_THRESHOLD}/10")
            
            questions = self.db.get_scenario_questions(batch_size)
            
            if not questions:
                logger.warning("İşlenecek soru bulunamadı!")
                return
            
            self.stats['total'] = len(questions)
            logger.info(f"Soru sayısı: {len(questions)}")
            
            for i, q in enumerate(questions):
                logger.info(f"\n--- Soru {i+1}/{len(questions)} (ID: {q['id']}) ---")
                self._process_question(q)
                time.sleep(1)
            
            self._report_results()
            
        finally:
            self.converter.stop()
    
    def _process_question(self, question: Dict):
        """Tek soru işle"""
        qid = question['id']
        original_text = question.get('original_text', '')
        scenario_text = question.get('scenario_text', '')
        
        if not original_text:
            logger.warning(f"#{qid}: Boş metin")
            self.stats['skipped'] += 1
            return
        
        # 1. Analiz ve sadeleştirme
        logger.info("Analiz ve sadeleştirme...")
        analysis = self.analyzer.analyze_question(original_text, scenario_text)
        
        if not analysis:
            logger.warning(f"#{qid}: Analiz başarısız veya görsel gerekmez")
            self.stats['skipped'] += 1
            return
        
        # 2. HTML oluştur
        gorsel_tipi = analysis.get('gorsel_tipi', 'genel')
        logger.info(f"Render ({gorsel_tipi})...")
        html, visual_desc = self.renderer.render(analysis)
        
        if not html:
            logger.error(f"#{qid}: Render başarısız")
            self.stats['failed'] += 1
            return
        
        # 3. Sadeleştirilmiş metinleri al
        simplified_text = analysis.get('sadellestirilmis_metin', original_text)
        simplified_scenario = analysis.get('sadellestirilmis_senaryo')
        
        # 4. Kalite kontrolü
        logger.info("Kalite kontrolü...")
        validation = analysis.get('kalite_degerlendirmesi', {})
        
        # Eğer analiz içinde yoksa, ayrıca doğrulama yap
        if not validation or 'toplam_puan' not in validation:
            validation = self.analyzer.validate_changes(
                original_text, 
                simplified_text, 
                visual_desc
            )
        
        quality_score = validation.get('toplam_puan', 0)
        is_approved = validation.get('onay', False)
        
        self.quality_scores.append(quality_score)
        logger.info(f"Kalite puanı: {quality_score}/10 - {'✅ Onaylandı' if is_approved else '❌ Reddedildi'}")
        
        if not is_approved:
            logger.warning(f"#{qid}: Kalite yetersiz - {validation.get('aciklama', '')}")
            self.stats['rejected'] += 1
            return
        
        # 5. PNG'ye çevir
        logger.info("PNG...")
        png_bytes = self.converter.html_to_png(html)
        
        if not png_bytes:
            logger.error(f"#{qid}: PNG başarısız")
            self.stats['failed'] += 1
            return
        
        # 6. Yükle
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"scenario/q_{qid}_{timestamp}.png"
        
        logger.info("Upload...")
        url = self.db.upload_image(png_bytes, filename)
        
        if not url:
            logger.error(f"#{qid}: Upload başarısız")
            self.stats['failed'] += 1
            return
        
        # 7. Veritabanını güncelle (görsel + sadeleştirilmiş metin)
        logger.info("Veritabanı güncelleniyor...")
        success = self.db.update_question(
            qid, 
            url,
            new_text=simplified_text if simplified_text != original_text else None,
            new_scenario=simplified_scenario
        )
        
        if success:
            logger.info(f"✅ #{qid}: BAŞARILI (Puan: {quality_score}/10)")
            if simplified_text != original_text:
                logger.info(f"   📝 Metin sadeleştirildi")
            self.stats['success'] += 1
        else:
            self.stats['failed'] += 1
    
    def _report_results(self):
        """Rapor"""
        logger.info("\n" + "="*60)
        logger.info("SONUÇ RAPORU")
        logger.info("="*60)
        logger.info(f"Toplam: {self.stats['total']}")
        logger.info(f"✅ Başarılı: {self.stats['success']}")
        logger.info(f"⏭️  Atlanan: {self.stats['skipped']}")
        logger.info(f"🚫 Reddedilen: {self.stats['rejected']}")
        logger.info(f"❌ Başarısız: {self.stats['failed']}")
        
        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"Başarı Oranı: %{rate:.1f}")
        
        if self.quality_scores:
            avg_quality = sum(self.quality_scores) / len(self.quality_scores)
            logger.info(f"Ortalama Kalite: {avg_quality:.1f}/10")


# ============== ÇALIŞTIR ==============

if __name__ == "__main__":
    try:
        bot = ScenarioBot()
        bot.run()
    except Exception as e:
        logger.error(f"Bot hatası: {e}")
        raise
