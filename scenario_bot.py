"""
Senaryo Görsel Botu (PISA/Problem)
==================================
Supabase'deki senaryo tabanlı soruları (PISA, hareket, maliyet, havuz, yaş) tarar,
Gemini ile analiz eder, HTML template'lerden profesyonel infografikler üretir.

GitHub Actions ile çalışır.
Günde 3 seans, her seansta 30 soru işler.
"""

import os
import json
import time
import logging
import base64
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any
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
    GEMINI_MODEL = 'gemini-2.0-flash'
    
    # Storage
    STORAGE_BUCKET = 'questions-images'
    
    # İşlem limitleri
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '30'))  # Varsayılan 30 soru
    TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    TEST_BATCH_SIZE = 10
    
    # Görsel ayarları
    IMAGE_WIDTH = 900
    IMAGE_HEIGHT = 600


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
    
    # ==================== YOL/HAREKET PROBLEMİ ====================
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
            
            .intersection {
                position: absolute;
                width: 70px;
                height: 70px;
                background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 5;
            }
            
            .intersection-icon {
                width: 45px;
                height: 45px;
                background: white;
                border-radius: 50%;
                display: flex;
                justify-content: center;
                align-items: center;
                font-size: 22px;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);
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
            
            .clock {
                position: absolute;
                width: 75px;
                height: 75px;
                background: white;
                border-radius: 50%;
                border: 4px solid;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
                z-index: 20;
            }
            
            .clock-time {
                font-size: 18px;
                font-weight: 800;
            }
            
            .clock-label {
                font-size: 10px;
                color: #64748b;
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
            
            .arrow {
                position: absolute;
                z-index: 8;
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
    
    # ==================== MALİYET/KARŞILAŞTIRMA ====================
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
    
    # ==================== HAVUZ/MUSLUK PROBLEMİ ====================
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
            
            .arrow-down {
                font-size: 20px;
                color: #22c55e;
            }
            
            .arrow-up {
                font-size: 20px;
                color: #ef4444;
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
                ${pipes_html}
                
                <div class="pool">
                    <span class="pool-label">${havuz_bilgi}</span>
                </div>
            </div>
            
            <div class="question-box" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 3px solid #f59e0b; border-radius: 16px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #92400e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; font-weight: 700;">❓ Soru</div>
                <div style="font-size: 18px; font-weight: 800; color: #78350f;">${soru_metni}</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== YAŞ PROBLEMİ / TIMELINE ====================
    YAS_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .timeline-container {
                padding: 30px 20px;
                background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
                border-radius: 16px;
                margin-bottom: 20px;
            }
            
            .timeline {
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: relative;
                padding: 40px 0;
            }
            
            .timeline::before {
                content: '';
                position: absolute;
                top: 50%;
                left: 10%;
                right: 10%;
                height: 4px;
                background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
                border-radius: 2px;
                transform: translateY(-50%);
            }
            
            .time-point {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 10px;
                z-index: 1;
            }
            
            .time-dot {
                width: 20px;
                height: 20px;
                background: white;
                border: 4px solid #22c55e;
                border-radius: 50%;
            }
            
            .time-label {
                background: white;
                padding: 8px 16px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 14px;
                color: #166534;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            
            .persons-container {
                display: flex;
                justify-content: center;
                gap: 30px;
                margin-top: 20px;
            }
            
            .person-card {
                background: white;
                border-radius: 16px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
                min-width: 140px;
            }
            
            .person-avatar {
                font-size: 40px;
                margin-bottom: 10px;
            }
            
            .person-name {
                font-size: 16px;
                font-weight: 700;
                color: #1e293b;
                margin-bottom: 8px;
            }
            
            .person-age {
                font-size: 14px;
                color: #64748b;
            }
            
            .person-age strong {
                color: #166534;
                font-size: 18px;
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
            
            <div class="timeline-container">
                <div class="timeline">
                    ${timeline_html}
                </div>
            </div>
            
            <div class="persons-container">
                ${persons_html}
            </div>
            
            <div class="question-box" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 3px solid #f59e0b; border-radius: 16px; padding: 20px; text-align: center; margin-top: 20px;">
                <div style="font-size: 12px; color: #92400e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; font-weight: 700;">❓ Soru</div>
                <div style="font-size: 18px; font-weight: 800; color: #78350f;">${soru_metni}</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== TABLO/VERİ ====================
    TABLO_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .data-table {
                width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
                margin-bottom: 20px;
            }
            
            .data-table th {
                background: linear-gradient(135deg, ${color_primary} 0%, ${color_dark} 100%);
                color: white;
                padding: 14px 16px;
                font-weight: 700;
                font-size: 14px;
                text-align: left;
            }
            
            .data-table td {
                padding: 12px 16px;
                border-bottom: 1px solid #e2e8f0;
                font-size: 14px;
            }
            
            .data-table tr:nth-child(even) {
                background: #f8fafc;
            }
            
            .data-table tr:last-child td {
                border-bottom: none;
            }
            
            .data-table tr:hover {
                background: ${color_light};
            }
            
            .highlight-cell {
                font-weight: 700;
                color: ${color_dark};
            }
            
            .question-cell {
                background: #fef3c7 !important;
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
            
            <table class="data-table">
                ${table_html}
            </table>
            
            <div class="question-box" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 3px solid #f59e0b; border-radius: 16px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #92400e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; font-weight: 700;">❓ Soru</div>
                <div style="font-size: 18px; font-weight: 800; color: #78350f;">${soru_metni}</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # ==================== GENEL PISA/SENARYO ====================
    GENEL_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            ${base_css}
            
            .scenario-box {
                background: linear-gradient(135deg, ${color_light} 0%, white 100%);
                border: 3px solid ${color_primary};
                border-radius: 18px;
                padding: 24px;
                margin-bottom: 20px;
            }
            
            .scenario-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 16px;
            }
            
            .scenario-icon {
                width: 50px;
                height: 50px;
                background: linear-gradient(135deg, ${color_primary} 0%, ${color_dark} 100%);
                border-radius: 14px;
                display: flex;
                justify-content: center;
                align-items: center;
                font-size: 24px;
            }
            
            .scenario-title {
                font-size: 18px;
                font-weight: 800;
                color: ${color_dark};
            }
            
            .info-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 12px;
            }
            
            .info-item {
                background: white;
                padding: 14px 18px;
                border-radius: 12px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
            }
            
            .info-item .label {
                font-size: 13px;
                color: #64748b;
                font-weight: 600;
            }
            
            .info-item .value {
                font-size: 16px;
                font-weight: 800;
                color: ${color_dark};
            }
            
            .characters {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin: 20px 0;
                flex-wrap: wrap;
            }
            
            .character {
                display: flex;
                align-items: center;
                gap: 10px;
                background: white;
                padding: 12px 18px;
                border-radius: 30px;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
            }
            
            .character-avatar {
                font-size: 28px;
            }
            
            .character-name {
                font-weight: 700;
                color: #1e293b;
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
            
            ${characters_html}
            
            <div class="scenario-box">
                <div class="scenario-header">
                    <div class="scenario-icon">${icon}</div>
                    <div class="scenario-title">${senaryo_baslik}</div>
                </div>
                <div class="info-grid">
                    ${info_items_html}
                </div>
            </div>
            
            <div class="question-box" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 3px solid #f59e0b; border-radius: 16px; padding: 20px; text-align: center;">
                <div style="font-size: 12px; color: #92400e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; font-weight: 700;">❓ Soru</div>
                <div style="font-size: 18px; font-weight: 800; color: #78350f;">${soru_metni}</div>
            </div>
        </div>
    </body>
    </html>
    """


# ============== VERİTABANI İŞLEMLERİ ==============

class DatabaseManager:
    """Supabase veritabanı işlemleri"""
    
    def __init__(self):
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise ValueError("SUPABASE_URL ve SUPABASE_KEY gerekli!")
        
        self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        logger.info("Supabase bağlantısı kuruldu")
    
    def get_scenario_questions(self, limit: int) -> List[Dict]:
        """Senaryo tabanlı soruları çek"""
        try:
            # scenario_text dolu olan ve image_url boş olan sorular
            response = self.client.table('question_bank').select('*').is_('image_url', 'null').eq('is_active', True).not_.is_('scenario_text', 'null').limit(limit).execute()
            
            questions = response.data
            logger.info(f"{len(questions)} senaryo sorusu bulundu")
            return questions
            
        except Exception as e:
            logger.error(f"Soru çekme hatası: {e}")
            
            # Alternatif: Uzun metinli soruları çek
            try:
                response = self.client.table('question_bank').select('*').is_('image_url', 'null').eq('is_active', True).limit(limit * 2).execute()
                
                # Manuel filtreleme - uzun sorular veya anahtar kelimeler
                keywords = ['yolculuk', 'hareket', 'hız', 'maliyet', 'fiyat', 'havuz', 'musluk',
                           'yaş', 'yıl önce', 'yıl sonra', 'tablo', 'grafik', 'karşılaştır',
                           'firma', 'şirket', 'proje', 'bütçe', 'inşaat', 'üretim']
                
                filtered = []
                for q in response.data:
                    text = (q.get('original_text') or '').lower()
                    scenario = q.get('scenario_text')
                    
                    # Senaryo var veya uzun metin veya anahtar kelime
                    if scenario or len(text) > 400 or any(kw in text for kw in keywords):
                        filtered.append(q)
                        if len(filtered) >= limit:
                            break
                
                logger.info(f"{len(filtered)} senaryo sorusu bulundu (manuel filtreleme)")
                return filtered
                
            except Exception as e2:
                logger.error(f"Alternatif sorgu hatası: {e2}")
                return []
    
    def update_image_url(self, question_id: int, image_url: str) -> bool:
        """Soru kaydına görsel URL'i ekle"""
        try:
            self.client.table('question_bank').update({
                'image_url': image_url
            }).eq('id', question_id).execute()
            
            logger.info(f"Soru #{question_id} güncellendi")
            return True
        except Exception as e:
            logger.error(f"Güncelleme hatası: {e}")
            return False
    
    def upload_image(self, image_bytes: bytes, filename: str) -> Optional[str]:
        """Görseli Storage'a yükle"""
        try:
            self.client.storage.from_(Config.STORAGE_BUCKET).upload(
                path=filename,
                file=image_bytes,
                file_options={"content-type": "image/png"}
            )
            
            public_url = self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
            logger.info(f"Görsel yüklendi: {filename}")
            return public_url
            
        except Exception as e:
            if 'Duplicate' in str(e) or 'already exists' in str(e):
                try:
                    self.client.storage.from_(Config.STORAGE_BUCKET).update(
                        path=filename,
                        file=image_bytes,
                        file_options={"content-type": "image/png"}
                    )
                    return self.client.storage.from_(Config.STORAGE_BUCKET).get_public_url(filename)
                except:
                    pass
            logger.error(f"Yükleme hatası: {e}")
            return None


# ============== GEMİNİ ANALİZ ==============

class GeminiAnalyzer:
    """Gemini ile senaryo analizi"""
    
    ANALYSIS_PROMPT = """Sen bir eğitim materyali tasarımcısısın.

GÖREV: Verilen matematik sorusunu analiz et ve infografik görsel için gerekli bilgileri JSON formatında çıkar.

ÖNEMLİ KURALLAR:
1. Sadece VERİLENLERİ çıkar - ÇÖZÜMÜ YAPMA!
2. Bilinmeyenleri "?" ile işaretle
3. Sorudaki isimleri ve değerleri aynen kullan
4. Türkçe karakterleri düzgün kullan

DESTEKLENEN GÖRSEL TİPLERİ:
- hareket: Yol, hız, zaman problemleri (otobüs, araba, yürüme)
- karsilastirma: İki seçenek karşılaştırma (maliyet, fiyat)
- havuz: Havuz, musluk, dolum/boşaltım
- yas: Yaş problemleri, timeline
- tablo: Veri tablosu gerektiren
- genel: Diğer senaryo bazlı problemler

JSON ÇIKTI FORMATI:
{
  "gorsel_pisinilir": true/false,
  "neden": "Eğer görsel gerekmiyorsa neden",
  "gorsel_tipi": "hareket|karsilastirma|havuz|yas|tablo|genel",
  "baslik": "Görsel başlığı (kısa ve öz)",
  "icon": "📊 veya 🚗 veya 🏊 gibi emoji",
  "karakterler": [
    {"isim": "Efe", "avatar": "👨", "rol": "Kuzey Hattı"},
    {"isim": "Kaan", "avatar": "👦", "rol": "Batı Hattı"}
  ],
  "verilenler": [
    {"etiket": "Efe'nin yolculuk süresi", "deger": "15 dakika", "renk": "blue"},
    {"etiket": "Kaan'ın yolculuk süresi", "deger": "20 dakika", "renk": "red"}
  ],
  "ozel_pisiniler": {
    "hareket": {
      "yollar": [
        {"isim": "Kuzey Hattı", "yon": "dikey", "renk": "blue"},
        {"isim": "Batı Hattı", "yon": "yatay", "renk": "red"}
      ],
      "araclar": [
        {"isim": "Efe", "hat": "Kuzey Hattı", "sure": "15 dk", "saat": "10:00"},
        {"isim": "Kaan", "hat": "Batı Hattı", "sure": "20 dk", "saat": "?"}
      ],
      "hedef": "Buluşma Noktası"
    },
    "karsilastirma": {
      "secenekler": [
        {"isim": "A Malzemesi", "pisiniler": [{"etiket": "Birim fiyat", "deger": "50 TL/m²"}]},
        {"isim": "B Malzemesi", "pisiniler": [{"etiket": "Birim fiyat", "deger": "80 TL/m²"}]}
      ]
    },
    "havuz": {
      "havuz_hacmi": "1000 litre",
      "musluklar": [
        {"isim": "A Musluğu", "tip": "dolum", "sure": "5 saatte doldurur"},
        {"isim": "B Musluğu", "tip": "bosaltma", "sure": "8 saatte boşaltır"}
      ]
    },
    "yas": {
      "zaman_noktalari": ["5 yıl önce", "Şimdi", "3 yıl sonra"],
      "kisiler": [
        {"isim": "Baba", "avatar": "👨", "yas_simdi": "40"},
        {"isim": "Oğul", "avatar": "👦", "yas_simdi": "?"}
      ]
    },
    "tablo": {
      "basliklar": ["Ürün", "Fiyat", "Miktar"],
      "satirlar": [
        ["Elma", "5 TL/kg", "3 kg"],
        ["Armut", "8 TL/kg", "2 kg"]
      ]
    }
  },
  "soru_metni": "Kısa ve net soru ifadesi (ne sorulduğu)"
}

SORU:
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
        """Soruyu analiz et"""
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
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                response_text = response.text
            else:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                response_text = response.text
            
            result = json.loads(response_text)
            
            if not result.get('gorsel_pisinilir', True):
                logger.info(f"Görsel gerekmez: {result.get('neden', '')}")
                return None
            
            logger.info(f"Analiz OK: {result.get('gorsel_tipi', 'genel')}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {e}")
            return None
        except Exception as e:
            logger.error(f"Analiz hatası: {e}")
            return None


# ============== HTML RENDERER ==============

class HTMLRenderer:
    """HTML template'den görsel oluştur"""
    
    def __init__(self):
        self.templates = HTMLTemplates()
    
    def render(self, analysis: Dict) -> Optional[str]:
        """Analiz sonucuna göre HTML oluştur"""
        try:
            gorsel_tipi = analysis.get('gorsel_tipi', 'genel')
            
            if gorsel_tipi == 'hareket':
                return self._render_hareket(analysis)
            elif gorsel_tipi == 'karsilastirma':
                return self._render_karsilastirma(analysis)
            elif gorsel_tipi == 'havuz':
                return self._render_havuz(analysis)
            elif gorsel_tipi == 'yas':
                return self._render_yas(analysis)
            elif gorsel_tipi == 'tablo':
                return self._render_tablo(analysis)
            else:
                return self._render_genel(analysis)
                
        except Exception as e:
            logger.error(f"Render hatası: {e}")
            return None
    
    def _get_base_css(self) -> str:
        """Base CSS'i width ile birlikte döndür"""
        return Template(HTMLTemplates.BASE_CSS).safe_substitute(width=Config.IMAGE_WIDTH)
    
    def _render_badges(self, verilenler: List[Dict]) -> str:
        """Badge HTML'i oluştur"""
        colors = HTMLTemplates.COLORS
        badges = []
        
        for i, v in enumerate(verilenler[:4]):  # Max 4 badge
            renk = v.get('renk', 'blue')
            if renk not in colors:
                renk = 'blue'
            c = colors[renk]
            
            badges.append(f'''
                <span class="badge" style="background: linear-gradient(135deg, {c['light']} 0%, white 100%); 
                      color: {c['dark']}; border: 2px solid {c['primary']};">
                    {v.get('etiket', '')}: <strong>{v.get('deger', '')}</strong>
                </span>
            ''')
        
        return '\n'.join(badges)
    
    def _render_hareket(self, analysis: Dict) -> str:
        """Hareket/yol problemi görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('hareket', {})
        colors = HTMLTemplates.COLORS
        
        # Yolları ve araçları çiz
        araclar = ozel.get('araclar', [])
        
        # Renkleri belirle
        color1 = colors.get('blue', colors['blue'])
        color2 = colors.get('red', colors['red'])
        
        # Diagram HTML
        diagram_parts = []
        
        # Dikey yol
        diagram_parts.append(f'''
            <div class="road road-vertical" style="left: 50%; top: 0; height: 220px; transform: translateX(-50%);"></div>
        ''')
        
        # Yatay yol  
        diagram_parts.append(f'''
            <div class="road road-horizontal" style="left: 0; top: 185px; width: 380px;"></div>
        ''')
        
        # Kavşak
        diagram_parts.append(f'''
            <div class="intersection" style="left: 50%; top: 185px; transform: translateX(-50%);">
                <div class="intersection-icon">📍</div>
            </div>
        ''')
        
        # Araçlar ve etiketler
        if len(araclar) >= 1:
            a1 = araclar[0]
            diagram_parts.append(f'''
                <div class="vehicle" style="left: 50%; top: 30px; transform: translateX(-50%); 
                     background: linear-gradient(180deg, {color1['primary']} 0%, {color1['dark']} 100%);">
                    🚌 {a1.get('isim', 'Kişi 1')}
                </div>
                <div class="info-label" style="right: 60px; top: 100px; background: {color1['light']}; 
                     color: {color1['dark']}; border: 2px solid {color1['primary']};">
                    ⏱ {a1.get('sure', '')}
                </div>
                <div class="clock" style="right: 50px; top: 20px; border-color: {color1['primary']};">
                    <span class="clock-time" style="color: {color1['dark']};">{a1.get('saat', '10:00')}</span>
                    <span class="clock-label">Hareket</span>
                </div>
            ''')
        
        if len(araclar) >= 2:
            a2 = araclar[1]
            saat2 = a2.get('saat', '?')
            is_unknown = saat2 == '?' or saat2 == ''
            
            diagram_parts.append(f'''
                <div class="vehicle" style="left: 40px; top: 198px; 
                     background: linear-gradient(90deg, {color2['primary']} 0%, {color2['dark']} 100%);">
                    🚌 {a2.get('isim', 'Kişi 2')}
                </div>
                <div class="info-label" style="left: 60px; top: 270px; background: {color2['light']}; 
                     color: {color2['dark']}; border: 2px solid {color2['primary']};">
                    ⏱ {a2.get('sure', '')}
                </div>
                <div class="clock" style="left: 40px; bottom: 20px; border-color: {color2['primary']};">
                    <span class="{'question-mark' if is_unknown else 'clock-time'}" 
                          style="color: {color2['dark']};">{'?' if is_unknown else saat2}</span>
                    {'<span class="clock-label">Hareket</span>' if not is_unknown else ''}
                </div>
            ''')
        
        # Hedef etiketi
        hedef = ozel.get('hedef', 'Buluşma Noktası')
        diagram_parts.append(f'''
            <div class="target-label" style="left: 50%; bottom: 10px; transform: translateX(-50%);">
                📍 {hedef}
            </div>
        ''')
        
        html = Template(HTMLTemplates.HAREKET_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Hareket Problemi'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            color1_primary=color1['primary'],
            color1_dark=color1['dark'],
            color2_primary=color2['primary'],
            color2_dark=color2['dark'],
            diagram_html='\n'.join(diagram_parts)
        )
        
        return html
    
    def _render_karsilastirma(self, analysis: Dict) -> str:
        """Karşılaştırma görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('karsilastirma', {})
        secenekler = ozel.get('secenekler', [])
        colors = HTMLTemplates.COLORS
        
        color_pairs = [('blue', 'pink'), ('green', 'orange'), ('purple', 'teal')]
        
        cards_html = []
        for i, secenek in enumerate(secenekler[:2]):
            renk_key = color_pairs[i % len(color_pairs)][i]
            c = colors.get(renk_key, colors['blue'])
            
            ozellikler = secenek.get('pisiniler', [])
            rows = []
            for oz in ozellikler:
                rows.append(f'''
                    <div class="data-row">
                        <span class="data-label">{oz.get('etiket', '')}</span>
                        <span class="data-value" style="color: {c['dark']};">{oz.get('deger', '')}</span>
                    </div>
                ''')
            
            cards_html.append(f'''
                <div class="compare-card" style="background: linear-gradient(135deg, {c['light']} 0%, white 100%); 
                     border-color: {c['primary']};">
                    <h3 style="color: {c['dark']};">
                        <span class="icon" style="background: {c['primary']};">{chr(65+i)}</span>
                        {secenek.get('isim', f'Seçenek {chr(65+i)}')}
                    </h3>
                    {''.join(rows)}
                </div>
            ''')
        
        html = Template(HTMLTemplates.KARSILASTIRMA_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Karşılaştırma'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            cards_html='\n'.join(cards_html),
            soru_metni=analysis.get('soru_metni', 'Hangi seçenek daha uygun?')
        )
        
        return html
    
    def _render_havuz(self, analysis: Dict) -> str:
        """Havuz/musluk görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('havuz', {})
        musluklar = ozel.get('musluklar', [])
        
        pipes_html = []
        for m in musluklar:
            tip = m.get('tip', 'dolum')
            css_class = 'fill-pipe' if tip == 'dolum' else 'drain-pipe'
            emoji = '🚿' if tip == 'dolum' else '🔻'
            arrow = '⬇️' if tip == 'dolum' else '⬆️'
            
            pipes_html.append(f'''
                <div class="pipe {css_class}">
                    <div class="pipe-icon">
                        <span class="emoji">{emoji}</span>
                        <span class="name">{m.get('isim', 'Musluk')}</span>
                    </div>
                    <div class="arrow-{'down' if tip == 'dolum' else 'up'}">{arrow}</div>
                    <div class="pipe-info">
                        <div class="label">Süre</div>
                        <div class="value">{m.get('sure', '?')}</div>
                    </div>
                </div>
            ''')
        
        html = Template(HTMLTemplates.HAVUZ_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Havuz Problemi'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            pipes_html='\n'.join(pipes_html),
            havuz_bilgi=ozel.get('havuz_hacmi', 'Havuz'),
            soru_metni=analysis.get('soru_metni', 'Havuz ne kadar sürede dolar?')
        )
        
        return html
    
    def _render_yas(self, analysis: Dict) -> str:
        """Yaş problemi görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('yas', {})
        zaman_noktalari = ozel.get('zaman_noktalari', ['Geçmiş', 'Şimdi', 'Gelecek'])
        kisiler = ozel.get('kisiler', [])
        
        # Timeline
        timeline_html = []
        for z in zaman_noktalari:
            timeline_html.append(f'''
                <div class="time-point">
                    <div class="time-label">{z}</div>
                    <div class="time-dot"></div>
                </div>
            ''')
        
        # Kişiler
        persons_html = []
        for k in kisiler:
            yas = k.get('yas_simdi', '?')
            yas_display = f'<span class="question-mark">?</span>' if yas == '?' else f'<strong>{yas}</strong> yaşında'
            
            persons_html.append(f'''
                <div class="person-card">
                    <div class="person-avatar">{k.get('avatar', '👤')}</div>
                    <div class="person-name">{k.get('isim', 'Kişi')}</div>
                    <div class="person-age">{yas_display}</div>
                </div>
            ''')
        
        html = Template(HTMLTemplates.YAS_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Yaş Problemi'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            timeline_html='\n'.join(timeline_html),
            persons_html='\n'.join(persons_html),
            soru_metni=analysis.get('soru_metni', 'Yaşları kaçtır?')
        )
        
        return html
    
    def _render_tablo(self, analysis: Dict) -> str:
        """Tablo görseli"""
        ozel = analysis.get('ozel_pisiniler', {}).get('tablo', {})
        basliklar = ozel.get('basliklar', [])
        satirlar = ozel.get('satirlar', [])
        colors = HTMLTemplates.COLORS['blue']
        
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
        
        html = Template(HTMLTemplates.TABLO_TEMPLATE).safe_substitute(
            base_css=self._get_base_css(),
            width=Config.IMAGE_WIDTH,
            baslik=analysis.get('baslik', 'Veri Tablosu'),
            badges_html=self._render_badges(analysis.get('verilenler', [])),
            color_primary=colors['primary'],
            color_dark=colors['dark'],
            color_light=colors['light'],
            table_html='\n'.join(table_parts),
            soru_metni=analysis.get('soru_metni', 'Tabloya göre hesaplayın.')
        )
        
        return html
    
    def _render_genel(self, analysis: Dict) -> str:
        """Genel senaryo görseli"""
        colors = HTMLTemplates.COLORS['purple']
        karakterler = analysis.get('karakterler', [])
        verilenler = analysis.get('verilenler', [])
        
        # Karakterler
        chars_html = []
        if karakterler:
            chars_html.append('<div class="characters">')
            for k in karakterler:
                chars_html.append(f'''
                    <div class="character">
                        <span class="character-avatar">{k.get('avatar', '👤')}</span>
                        <span class="character-name">{k.get('isim', 'Kişi')}</span>
                    </div>
                ''')
            chars_html.append('</div>')
        
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
            characters_html='\n'.join(chars_html),
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
    """Ana senaryo görsel botu"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.analyzer = GeminiAnalyzer()
        self.renderer = HTMLRenderer()
        self.converter = ImageConverter()
        
        self.stats = {
            'total': 0,
            'success': 0,
            'skipped': 0,
            'failed': 0
        }
    
    def run(self):
        """Botu çalıştır"""
        logger.info("="*60)
        logger.info("SENARYO GÖRSEL BOTU BAŞLADI")
        logger.info("="*60)
        
        # Playwright başlat
        self.converter.start()
        
        try:
            batch_size = Config.TEST_BATCH_SIZE if Config.TEST_MODE else Config.BATCH_SIZE
            logger.info(f"Mod: {'TEST' if Config.TEST_MODE else 'PRODUCTION'}")
            logger.info(f"Batch: {batch_size}")
            
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
        text = question.get('original_text', '')
        scenario = question.get('scenario_text', '')
        
        if not text:
            logger.warning(f"#{qid}: Boş metin")
            self.stats['skipped'] += 1
            return
        
        # 1. Analiz
        logger.info("Analiz...")
        analysis = self.analyzer.analyze_question(text, scenario)
        
        if not analysis:
            logger.warning(f"#{qid}: Analiz başarısız")
            self.stats['skipped'] += 1
            return
        
        # 2. HTML oluştur
        logger.info(f"Render ({analysis.get('gorsel_tipi', 'genel')})...")
        html = self.renderer.render(analysis)
        
        if not html:
            logger.error(f"#{qid}: Render başarısız")
            self.stats['failed'] += 1
            return
        
        # 3. PNG'ye çevir
        logger.info("PNG...")
        png_bytes = self.converter.html_to_png(html)
        
        if not png_bytes:
            logger.error(f"#{qid}: PNG başarısız")
            self.stats['failed'] += 1
            return
        
        # 4. Yükle
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"scenario/q_{qid}_{timestamp}.png"
        
        logger.info("Upload...")
        url = self.db.upload_image(png_bytes, filename)
        
        if not url:
            logger.error(f"#{qid}: Upload başarısız")
            self.stats['failed'] += 1
            return
        
        # 5. Güncelle
        if self.db.update_image_url(qid, url):
            logger.info(f"✅ #{qid}: BAŞARILI")
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
        logger.info(f"❌ Başarısız: {self.stats['failed']}")
        
        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            logger.info(f"Oran: %{rate:.1f}")


# ============== ÇALIŞTIR ==============

if __name__ == "__main__":
    try:
        bot = ScenarioBot()
        bot.run()
    except Exception as e:
        logger.error(f"Bot hatası: {e}")
        raise
