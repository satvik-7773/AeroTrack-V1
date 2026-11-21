import sys
import os
import re
import base64
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client

from data_ingestion.client import OpenSkyClient

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION (FULL-BLEED DARK TERMINAL)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AeroTrack Terminal // Aviation Finance, OEM & MRO Intelligence",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------------------------------------------------------
# SUPABASE & CLIENT INITIALIZATION
# -----------------------------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    client = OpenSkyClient()
except Exception:
    st.error("Unable to initialize AirLabs client. Verify AIRLABS_API_KEY in secrets.")
    st.stop()

# -----------------------------------------------------------------------------
# REFERENCE UNIVERSES (AVIATION EQUITIES, CARRIERS, OEMS, MRO HUBS)
# -----------------------------------------------------------------------------
WATCHLIST_ENTITIES = [
    {"ticker": "AER", "name": "AerCap Holdings N.V.", "category": "Lessors", "iata": None, "country": "IE/US"},
    {"ticker": "AL", "name": "Air Lease Corp.", "category": "Lessors", "iata": None, "country": "US"},
    {"ticker": "FTAI", "name": "FTAI Aviation Ltd.", "category": "Lessors", "iata": None, "country": "US"},
    {"ticker": "AIR.PA", "name": "Airbus SE", "category": "OEMs", "iata": None, "country": "EU"},
    {"ticker": "BA", "name": "Boeing Company", "category": "OEMs", "iata": None, "country": "US"},
    {"ticker": "ERJ", "name": "Embraer S.A.", "category": "OEMs", "iata": None, "country": "BR"},
    {"ticker": "DAL", "name": "Delta Air Lines", "category": "Airlines", "iata": "DL", "country": "US"},
    {"ticker": "UAL", "name": "United Airlines", "category": "Airlines", "iata": "UA", "country": "US"},
    {"ticker": "AAL", "name": "American Airlines", "category": "Airlines", "iata": "AA", "country": "US"},
    {"ticker": "LUV", "name": "Southwest Airlines", "category": "Airlines", "iata": "WN", "country": "US"},
    {"ticker": "RYAAY", "name": "Ryanair Holdings", "category": "Airlines", "iata": "FR", "country": "EU"},
    {"ticker": "LHA.DE", "name": "Lufthansa Group", "category": "Airlines", "iata": "LH", "country": "EU"},
    {"ticker": "IAG.L", "name": "IAG (British Airways)", "category": "Airlines", "iata": "BA", "country": "UK"},
    {"ticker": "INDIGO.NS", "name": "IndiGo (InterGlobe)", "category": "Airlines", "iata": "6E", "country": "IN"},
]

AIRLINE_FINANCIAL_BASELINES = {
    "DL": {"ticker": "DAL", "name": "Delta Air Lines", "rev_bn": 61.6, "net_profit_bn": 3.46, "op_margin": 9.7, "registered_fleet": 992, "avg_age_yrs": 14.8},
    "UA": {"ticker": "UAL", "name": "United Airlines", "rev_bn": 57.1, "net_profit_bn": 3.15, "op_margin": 8.9, "registered_fleet": 1004, "avg_age_yrs": 15.6},
    "AA": {"ticker": "AAL", "name": "American Airlines", "rev_bn": 54.2, "net_profit_bn": 0.85, "op_margin": 4.8, "registered_fleet": 977, "avg_age_yrs": 13.4},
    "WN": {"ticker": "LUV", "name": "Southwest Airlines", "rev_bn": 27.5, "net_profit_bn": 0.47, "op_margin": 2.4, "registered_fleet": 817, "avg_age_yrs": 11.9},
    "FR": {"ticker": "RYAAY", "name": "Ryanair Group", "rev_bn": 14.5, "net_profit_bn": 2.08, "op_margin": 14.9, "registered_fleet": 608, "avg_age_yrs": 9.1},
    "LH": {"ticker": "LHA.DE", "name": "Lufthansa Group", "rev_bn": 40.6, "net_profit_bn": 1.49, "op_margin": 4.4, "registered_fleet": 735, "avg_age_yrs": 13.2},
    "6E": {"ticker": "INDIGO.NS", "name": "IndiGo", "rev_bn": 9.3, "net_profit_bn": 0.98, "op_margin": 11.4, "registered_fleet": 415, "avg_age_yrs": 4.4},
    "BA": {"ticker": "IAG.L", "name": "British Airways (IAG)", "rev_bn": 34.7, "net_profit_bn": 2.95, "op_margin": 13.8, "registered_fleet": 601, "avg_age_yrs": 13.6},
    "AF": {"ticker": "AF.PA", "name": "Air France-KLM", "rev_bn": 34.1, "net_profit_bn": 0.52, "op_margin": 5.1, "registered_fleet": 566, "avg_age_yrs": 12.8},
    "TK": {"ticker": "THYAO.IS", "name": "Turkish Airlines", "rev_bn": 22.7, "net_profit_bn": 3.40, "op_margin": 11.6, "registered_fleet": 472, "avg_age_yrs": 9.4},
    "EK": {"ticker": "PRIVATE", "name": "Emirates", "rev_bn": 33.0, "net_profit_bn": 4.70, "op_margin": 15.1, "registered_fleet": 261, "avg_age_yrs": 10.5},
    "QR": {"ticker": "PRIVATE", "name": "Qatar Airways", "rev_bn": 22.2, "net_profit_bn": 1.67, "op_margin": 8.4, "registered_fleet": 254, "avg_age_yrs": 9.2},
    "SQ": {"ticker": "C6L.SI", "name": "Singapore Airlines", "rev_bn": 14.3, "net_profit_bn": 1.98, "op_margin": 14.3, "registered_fleet": 203, "avg_age_yrs": 7.4},
    "AC": {"ticker": "AC.TO", "name": "Air Canada", "rev_bn": 16.4, "net_profit_bn": 1.25, "op_margin": 5.7, "registered_fleet": 362, "avg_age_yrs": 12.6},
    "CZ": {"ticker": "1055.HK", "name": "China Southern", "rev_bn": 24.1, "net_profit_bn": -0.24, "op_margin": 1.2, "registered_fleet": 917, "avg_age_yrs": 9.5},
    "MU": {"ticker": "0670.HK", "name": "China Eastern", "rev_bn": 18.8, "net_profit_bn": -0.58, "op_margin": -0.8, "registered_fleet": 804, "avg_age_yrs": 9.1},
    "CA": {"ticker": "0753.HK", "name": "Air China", "rev_bn": 23.2, "net_profit_bn": -0.04, "op_margin": 1.6, "registered_fleet": 930, "avg_age_yrs": 9.8},
    "FX": {"ticker": "FDX", "name": "FedEx Express", "rev_bn": 87.7, "net_profit_bn": 4.33, "op_margin": 6.3, "registered_fleet": 698, "avg_age_yrs": 21.4},
    "5X": {"ticker": "UPS", "name": "UPS Airlines", "rev_bn": 91.1, "net_profit_bn": 5.78, "op_margin": 9.3, "registered_fleet": 292, "avg_age_yrs": 22.1},
}

OEM_BACKLOG_REFERENCE = [
    {"OEM": "Airbus", "Ticker": "AIR.PA", "Program": "A320neo Family", "Segment": "Narrowbody", "Backlog": 7190, "Annual_Delivery_Rate": 602, "Avg_List_Price_M": 115, "Key_Slots": "IndiGo, United, Wizz Air, Air India"},
    {"OEM": "Airbus", "Ticker": "AIR.PA", "Program": "A220 Family", "Segment": "Regional / NB", "Backlog": 512, "Annual_Delivery_Rate": 75, "Avg_List_Price_M": 91, "Key_Slots": "Delta, Air France, Breeze, JetBlue"},
    {"OEM": "Airbus", "Ticker": "AIR.PA", "Program": "A330neo Family", "Segment": "Widebody", "Backlog": 205, "Annual_Delivery_Rate": 32, "Avg_List_Price_M": 296, "Key_Slots": "Delta, Condor, Malaysia, ITA"},
    {"OEM": "Airbus", "Ticker": "AIR.PA", "Program": "A350 / A350F", "Segment": "Widebody", "Backlog": 738, "Annual_Delivery_Rate": 57, "Avg_List_Price_M": 338, "Key_Slots": "Emirates, Turkish, Air India, Delta"},
    {"OEM": "Boeing", "Ticker": "BA", "Program": "737 MAX Family", "Segment": "Narrowbody", "Backlog": 4760, "Annual_Delivery_Rate": 265, "Avg_List_Price_M": 122, "Key_Slots": "Ryanair, Southwest, United, Akasa"},
    {"OEM": "Boeing", "Ticker": "BA", "Program": "787 Dreamliner", "Segment": "Widebody", "Backlog": 790, "Annual_Delivery_Rate": 51, "Avg_List_Price_M": 292, "Key_Slots": "United, Riyadh Air, ANA, Lufthansa"},
    {"OEM": "Boeing", "Ticker": "BA", "Program": "777 / 777X / 777F", "Segment": "Widebody", "Backlog": 545, "Annual_Delivery_Rate": 14, "Avg_List_Price_M": 410, "Key_Slots": "Emirates, Qatar, Lufthansa, Ethiopian"},
    {"OEM": "Boeing", "Ticker": "BA", "Program": "767 / KC-46 / 767F", "Segment": "Widebody", "Backlog": 94, "Annual_Delivery_Rate": 18, "Avg_List_Price_M": 220, "Key_Slots": "FedEx, UPS"},
    {"OEM": "Embraer", "Ticker": "ERJ", "Program": "E-Jets E2 Family", "Segment": "Regional", "Backlog": 224, "Annual_Delivery_Rate": 47, "Avg_List_Price_M": 68, "Key_Slots": "Porter, Azul, KLM Cityhopper, Virgin"},
    {"OEM": "Embraer", "Ticker": "ERJ", "Program": "E175 (E1)", "Segment": "Regional", "Backlog": 176, "Annual_Delivery_Rate": 26, "Avg_List_Price_M": 54, "Key_Slots": "American Eagle, SkyWest, Republic"},
    {"OEM": "COMAC", "Ticker": "PRIVATE", "Program": "C919", "Segment": "Narrowbody", "Backlog": 1060, "Annual_Delivery_Rate": 16, "Avg_List_Price_M": 99, "Key_Slots": "China Eastern, Air China, China Southern"},
    {"OEM": "ATR", "Ticker": "AIR.PA", "Program": "ATR 42 / 72-600", "Segment": "Regional", "Backlog": 145, "Annual_Delivery_Rate": 36, "Avg_List_Price_M": 27, "Key_Slots": "IndiGo, Azul, Air Corsica, Cebu Pacific"},
]

MRO_HUBS = [
    {"hub": "SIN", "name": "Singapore Changi (ST Eng / SIAEC)", "lat": 1.364, "lon": 103.991, "specialty": "Airframe & LEAP/Trent"},
    {"hub": "HKG", "name": "Hong Kong (HAECO)", "lat": 22.308, "lon": 113.918, "specialty": "Heavy Widebody C/D-Check"},
    {"hub": "SNN", "name": "Shannon (Lufthansa Technik / IAC)", "lat": 52.702, "lon": -8.925, "specialty": "Lessor Transition & Paint"},
    {"hub": "IST", "name": "Istanbul (Turkish Technic)", "lat": 41.275, "lon": 28.751, "specialty": "Narrowbody & Widebody Heavy"},
    {"hub": "DXB", "name": "Dubai (Emirates Eng / ExecuJet)", "lat": 25.253, "lon": 55.365, "specialty": "A380 / 777 Heavy Base"},
    {"hub": "MZJ", "name": "Marana Pinal Airpark", "lat": 32.510, "lon": -111.325, "specialty": "Storage, Teardown & Preservation"},
    {"hub": "VCV", "name": "Victorville SCLA", "lat": 34.597, "lon": -117.383, "specialty": "Storage & Lessor Return"},
    {"hub": "FRA", "name": "Frankfurt (Lufthansa Technik)", "lat": 50.037, "lon": 8.562, "specialty": "Engine & Component Base"},
    {"hub": "ATL", "name": "Atlanta (Delta TechOps)", "lat": 33.640, "lon": -84.427, "specialty": "CFM / PW / GE Engine MRO"},
    {"hub": "XMN", "name": "Xiamen (HAECO / TAECO)", "lat": 24.544, "lon": 118.128, "specialty": "P2F Freighter Conversions"},
]

CARGO_CODES = {
    "FX", "FDX", "5X", "UPS", "5Y", "GTI", "PO", "PAC", "K4", "CKS", "CV", "CLX", "3S", "BOX",
    "RU", "ABW", "D0", "BCS", "ABR", "GEC", "SQC", "CK", "CKK", "KZ", "NCA", "MP", "MPH", "QT",
    "TAY", "LD", "AHK"
}

AIRPORT_MAP = {
    "ATL": "Atlanta", "DFW": "Dallas", "DEN": "Denver", "ORD": "Chicago", "LAX": "Los Angeles",
    "JFK": "New York", "LHR": "London", "HND": "Tokyo", "CDG": "Paris", "DXB": "Dubai",
    "DEL": "New Delhi", "BOM": "Mumbai", "FRA": "Frankfurt", "AMS": "Amsterdam", "MAD": "Madrid",
    "SIN": "Singapore", "HKG": "Hong Kong", "SYD": "Sydney", "YYZ": "Toronto", "IST": "Istanbul"
}

_AIRLINER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <path fill="#ffffff" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
</svg>"""
AIRLINER_ICON_URL = "data:image/svg+xml;base64," + base64.b64encode(_AIRLINER_SVG.encode("utf-8")).decode("ascii")

# -----------------------------------------------------------------------------
# EXCEPTIONAL DARK TERMINAL CSS + 60FPS ANIMATIONS (ZERO TOP BAR OBSTRUCTION)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    :root {
        --bg-canvas: #0D0E11;
        --bg-surface: #15171C;
        --bg-elevated: #1C1F26;
        --bg-hover: #242832;
        --border-subtle: rgba(255, 255, 255, 0.08);
        --border-bright: rgba(138, 180, 248, 0.35);
        --text-primary: #F1F5F9;
        --text-secondary: #94A3B8;
        --text-muted: #64748B;
        --green: #34D399;
        --green-bg: rgba(52, 211, 153, 0.14);
        --red: #FB7185;
        --red-bg: rgba(251, 113, 133, 0.14);
        --blue: #60A5FA;
        --blue-bg: rgba(96, 165, 250, 0.14);
        --amber: #FBBF24;
        --amber-bg: rgba(251, 191, 36, 0.14);
        --ease-out-expo: cubic-bezier(0.22, 1, 0.36, 1);
    }

    /* Completely remove Streamlit top bar so nothing blocks the upper canvas */
    header[data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    button[kind="header"],
    #MainMenu,
    footer {
        display: none !important;
        height: 0 !important;
        visibility: hidden !important;
    }

    /* Keyframes for smooth 60fps UI motion */
    @keyframes viewEnter {
        0% { opacity: 0; transform: translateY(12px) scale(0.992); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes staggerFade {
        0% { opacity: 0; transform: translateY(10px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    @keyframes drawSparkline {
        0% { stroke-dashoffset: 360; }
        100% { stroke-dashoffset: 0; }
    }
    @keyframes fadeFill {
        0% { opacity: 0; }
        100% { opacity: 1; }
    }
    @keyframes barExpand {
        0% { transform: scaleX(0); }
        100% { transform: scaleX(1); }
    }
    @keyframes pulseBeacon {
        0% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.65); }
        70% { box-shadow: 0 0 0 8px rgba(52, 211, 153, 0); }
        100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
    }
    @keyframes marqueeScroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    @keyframes shimmerSweep {
        0% { transform: translateX(-120%); }
        100% { transform: translateX(220%); }
    }

    .stApp {
        background: radial-gradient(circle at 18% 0%, rgba(30, 58, 138, 0.14), transparent 40%),
                    radial-gradient(circle at 88% 10%, rgba(16, 185, 129, 0.08), transparent 36%),
                    var(--bg-canvas);
        color: var(--text-primary);
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .block-container {
        padding: 1.05rem 1.85rem 2.75rem 1.85rem !important;
        max-width: 1640px;
    }

    /* Animated SVG sparklines */
    .spark-line {
        stroke-dasharray: 360;
        stroke-dashoffset: 360;
        animation: drawSparkline 1.05s var(--ease-out-expo) forwards;
    }
    .spark-area {
        opacity: 0;
        animation: fadeFill 0.9s ease 0.25s forwards;
    }

    /* Inputs & Dropdowns */
    div[data-baseweb="input"] > div,
    .stTextInput > div > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 999px !important;
        color: var(--text-primary) !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease, background-color 0.25s ease;
    }
    div[data-baseweb="select"] > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease;
    }
    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--blue) !important;
        box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.16) !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="input"] input {
        color: var(--text-primary) !important;
    }
    ul[data-baseweb="menu"] {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-bright) !important;
        border-radius: 12px !important;
    }
    li[role="option"] {
        color: var(--text-primary) !important;
        background-color: transparent !important;
        transition: background-color 0.15s ease;
    }
    li[role="option"]:hover {
        background-color: var(--bg-hover) !important;
    }
    label[data-testid="stWidgetLabel"] p {
        color: var(--text-secondary) !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }

    /* Sleek Pill Radio Navigation */
    div[role="radiogroup"] {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
    }
    div[role="radiogroup"] label {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 999px !important;
        padding: 0.36rem 0.95rem !important;
        margin: 0 !important;
        cursor: pointer !important;
        transition: transform 0.22s var(--ease-out-expo), background-color 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease !important;
    }
    div[role="radiogroup"] label:hover {
        background: var(--bg-hover) !important;
        border-color: rgba(255, 255, 255, 0.22) !important;
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
    }
    div[role="radiogroup"] label[data-checked="true"],
    div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(135deg, rgba(96, 165, 250, 0.22), rgba(52, 211, 153, 0.16)) !important;
        border-color: var(--blue) !important;
        box-shadow: 0 4px 14px rgba(96, 165, 250, 0.18) !important;
    }
    div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    div[role="radiogroup"] label p {
        color: var(--text-primary) !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
    }

    /* Buttons */
    div.stButton > button,
    div.stDownloadButton > button {
        background: var(--bg-elevated);
        color: var(--text-primary);
        border: 1px solid var(--border-subtle);
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.8rem;
        transition: transform 0.22s var(--ease-out-expo), border-color 0.22s ease, box-shadow 0.22s ease, background 0.22s ease;
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover {
        background: var(--bg-hover);
        border-color: var(--blue);
        color: #FFFFFF;
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    }

    /* Brand Header */
    .brand-wrap {
        display: flex;
        align-items: center;
        gap: 0.8rem;
    }
    .brand-icon {
        width: 40px;
        height: 40px;
        border-radius: 12px;
        background: linear-gradient(135deg, #2563EB, #10B981);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.35);
        transition: transform 0.35s var(--ease-out-expo);
    }
    .brand-icon:hover {
        transform: rotate(-8deg) scale(1.06);
    }
    .brand-name {
        font-size: 1.32rem;
        font-weight: 800;
        letter-spacing: -0.025em;
        color: #FFFFFF;
        line-height: 1.1;
    }
    .brand-sub {
        font-size: 0.72rem;
        color: var(--text-secondary);
        font-weight: 500;
    }
    .live-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.45rem;
        background: var(--green-bg);
        border: 1px solid rgba(52, 211, 153, 0.35);
        color: var(--green);
        border-radius: 999px;
        padding: 0.38rem 0.85rem;
        font-size: 0.73rem;
        font-weight: 600;
        font-family: 'IBM Plex Mono', monospace;
    }
    .live-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--green);
        animation: pulseBeacon 2s infinite;
    }

    /* Smooth Continuous Ticker Marquee */
    .ticker-shell {
        overflow: hidden;
        background: rgba(28, 31, 38, 0.72);
        backdrop-filter: blur(8px);
        border: 1px solid var(--border-subtle);
        border-radius: 999px;
        padding: 0.38rem 0;
        margin: 0.55rem 0 0.85rem 0;
        white-space: nowrap;
        position: relative;
    }
    .ticker-track {
        display: inline-flex;
        gap: 2rem;
        animation: marqueeScroll 36s linear infinite;
        will-change: transform;
    }
    .ticker-shell:hover .ticker-track {
        animation-play-state: paused;
    }
    .tick-item {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.75rem;
        color: var(--text-primary);
    }

    /* Left Watchlist Rail */
    .rail-box {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 18px;
        padding: 1rem 0.95rem 0.85rem 0.95rem;
        animation: viewEnter 0.45s var(--ease-out-expo) both;
    }
    .rail-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.65rem;
    }
    .rail-title {
        font-size: 0.96rem;
        font-weight: 700;
        color: #FFFFFF;
    }
    .rail-tag {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.68rem;
        color: var(--blue);
        background: var(--blue-bg);
        padding: 0.16rem 0.5rem;
        border-radius: 999px;
    }
    .watch-item {
        display: grid;
        grid-template-columns: 1.25fr 0.75fr 0.95fr;
        align-items: center;
        gap: 0.4rem;
        padding: 0.65rem 0.55rem;
        border-top: 1px solid var(--border-subtle);
        border-radius: 10px;
        transition: transform 0.22s var(--ease-out-expo), background-color 0.2s ease, box-shadow 0.2s ease;
        animation: staggerFade 0.4s var(--ease-out-expo) both;
    }
    .watch-item:hover {
        background: var(--bg-hover);
        transform: translateX(5px);
        box-shadow: inset 3px 0 0 var(--blue);
    }
    .w-sym { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; font-weight: 700; color: #FFFFFF; }
    .w-name { font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 108px; }
    .w-px { text-align: right; font-family: 'IBM Plex Mono', monospace; font-size: 0.79rem; font-weight: 600; color: var(--text-primary); }
    .w-chg { text-align: right; font-family: 'IBM Plex Mono', monospace; font-size: 0.71rem; font-weight: 600; }

    /* Animated KPI / Index Cards */
    .idx-card {
        position: relative;
        overflow: hidden;
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 1rem 1.1rem 0.7rem 1.1rem;
        transition: transform 0.28s var(--ease-out-expo), border-color 0.28s ease, box-shadow 0.28s ease;
        animation: staggerFade 0.5s var(--ease-out-expo) both;
        will-change: transform;
    }
    .idx-card::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 45%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.045), transparent);
        transform: translateX(-120%);
        pointer-events: none;
    }
    .idx-card:hover {
        transform: translateY(-4px);
        border-color: var(--border-bright);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
    }
    .idx-card:hover::after {
        animation: shimmerSweep 0.85s ease forwards;
    }
    .idx-kicker { font-size: 0.72rem; font-weight: 700; color: var(--text-secondary); letter-spacing: 0.05em; }
    .idx-big { font-size: 1.5rem; font-weight: 800; color: #FFFFFF; font-variant-numeric: tabular-nums; margin: 0.2rem 0; }
    .pill-up { background: var(--green-bg); color: var(--green); padding: 0.14rem 0.48rem; border-radius: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; font-weight: 700; }
    .pill-dn { background: var(--red-bg); color: var(--red); padding: 0.14rem 0.48rem; border-radius: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; font-weight: 700; }

    /* Spacious Hero & Section Cards */
    .glass-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 18px;
        padding: 1.2rem 1.35rem;
        margin-bottom: 1.1rem;
        transition: border-color 0.25s ease, transform 0.25s var(--ease-out-expo), box-shadow 0.25s ease;
        animation: viewEnter 0.45s var(--ease-out-expo) both;
    }
    .glass-card:hover {
        border-color: rgba(255, 255, 255, 0.16);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.32);
    }
    .sec-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 0.95rem 0 0.65rem 0;
        padding-bottom: 0.45rem;
        border-bottom: 1px solid var(--border-subtle);
    }
    .sec-title { font-size: 1rem; font-weight: 700; color: #FFFFFF; }
    .sec-sub { font-size: 0.74rem; color: var(--text-secondary); font-family: 'IBM Plex Mono', monospace; }

    /* Animated MRO / Utilization Bars */
    .mro-bar-wrap {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 0.9rem 1.05rem;
        transition: transform 0.22s var(--ease-out-expo), border-color 0.22s ease;
    }
    .mro-bar-wrap:hover {
        transform: translateY(-2px);
        border-color: var(--border-bright);
    }
    .mro-track {
        width: 100%;
        height: 8px;
        background: #272B35;
        border-radius: 999px;
        overflow: hidden;
        margin-top: 0.45rem;
    }
    .mro-fill {
        height: 100%;
        border-radius: 999px;
        transform-origin: left;
        animation: barExpand 0.9s var(--ease-out-expo) forwards;
    }

    /* Dedicated News Corner Cards */
    .news-tile {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 1.05rem 1.15rem;
        margin-bottom: 0.85rem;
        transition: transform 0.24s var(--ease-out-expo), border-color 0.24s ease, background-color 0.24s ease, box-shadow 0.24s ease;
        animation: staggerFade 0.45s var(--ease-out-expo) both;
    }
    .news-tile:hover {
        transform: translateY(-3px);
        background: var(--bg-elevated);
        border-color: var(--border-bright);
        box-shadow: 0 12px 26px rgba(0, 0, 0, 0.36);
    }
    .news-tile a {
        color: #F8FAFC;
        text-decoration: none;
        font-size: 0.95rem;
        font-weight: 700;
        line-height: 1.38;
        display: block;
        margin: 0.4rem 0;
        transition: color 0.18s ease;
    }
    .news-tile a:hover { color: var(--blue); }
    .news-snip { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.48; }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-canvas); }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--blue); }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# HELPERS & DATA INGESTION
# -----------------------------------------------------------------------------
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_airspace_sector(lat, lon):
    if 35 <= lat <= 70 and -15 <= lon <= 45:
        return "EUROPE"
    if 25 <= lat <= 60 and -130 <= lon <= -60:
        return "NORTH AMERICA"
    if 0 <= lat <= 50 and 100 <= lon <= 150:
        return "EAST ASIA & APAC"
    if 10 <= lat <= 35 and 35 <= lon <= 85:
        return "MIDDLE EAST & S. ASIA"
    if -50 <= lat <= 15 and -80 <= lon <= -35:
        return "LATIN AMERICA"
    if 15 <= lat <= 60 and -60 <= lon <= -15:
        return "NORTH ATLANTIC"
    if -50 <= lat <= 10 and 10 <= lon <= 50:
        return "AFRICA"
    if -45 <= lat <= -10 and 110 <= lon <= 160:
        return "OCEANIA"
    return "TRANSOCEANIC"


def classify_airframe_taxonomy(icao_code):
    code = str(icao_code).upper().strip()

    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N", "A332", "A333", "A338", "A339", "A359", "A35K", "A300", "A306", "A310", "A343", "A346", "A388", "BCS1", "BCS3"]:
        manufacturer = "Airbus"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM", "B772", "B773", "B77W", "B77L", "B778", "B779", "B788", "B789", "B78X", "B744", "B748", "B762", "B763", "B764", "B712", "B752", "B753", "MD11", "MD82", "MD83", "MD88", "DC10"]:
        manufacturer = "Boeing"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "E135", "E145", "E35L", "E55P", "E50P", "E550"]:
        manufacturer = "Embraer"
    elif code in ["CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "CL30", "CL35", "CL60", "GLEX", "GL5T", "GL7T"]:
        manufacturer = "Bombardier / MHI"
    elif code in ["AT43", "AT72", "AT42", "AT75", "AT76"]:
        manufacturer = "ATR"
    elif code in ["C919", "ARJ2"]:
        manufacturer = "COMAC"
    else:
        manufacturer = "Other"

    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N"]:
        family = "Airbus A320 Family"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM"]:
        family = "Boeing 737 Family"
    elif code in ["A332", "A333", "A338", "A339"]:
        family = "Airbus A330 Family"
    elif code in ["B772", "B773", "B77W", "B77L", "B778", "B779"]:
        family = "Boeing 777 Family"
    elif code in ["B788", "B789", "B78X"]:
        family = "Boeing 787 Family"
    elif code in ["A359", "A35K"]:
        family = "Airbus A350 Family"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "BCS1", "BCS3", "AT43", "AT72", "AT75", "AT76"]:
        family = "Regional Jet / Turboprop"
    elif code in ["B744", "B748", "B762", "B763", "B764", "MD11", "A300", "A306", "A310"]:
        family = "Dedicated Widebody / Freighter"
    elif code in ["GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "FA7X", "FA8X", "C750", "C680", "E55P", "LJ60", "LJ75", "PC24"]:
        family = "Business Jets"
    else:
        family = "Other / Unclassified"

    if family in ["Airbus A320 Family", "Boeing 737 Family"]:
        body_type = "Narrowbody"
    elif family in ["Airbus A330 Family", "Boeing 777 Family", "Boeing 787 Family", "Airbus A350 Family", "Dedicated Widebody / Freighter"]:
        body_type = "Widebody"
    elif family == "Regional Jet / Turboprop":
        body_type = "Regional"
    elif family == "Business Jets":
        body_type = "Business Jet"
    else:
        body_type = "Other"

    if code in ["A20N", "A21N", "A19N", "B38M", "B39M", "B3XM", "A338", "A339", "B788", "B789", "B78X", "A359", "A35K", "E290", "E295", "BCS1", "BCS3", "C919"]:
        generation = "Next-Gen"
    else:
        generation = "Legacy"

    return pd.Series([manufacturer, family, body_type, generation])


def build_svg_sparkline(values, color="#34D399", width=86, height=28, uid="sp"):
    clean = [float(v) for v in values if v is not None and not np.isnan(v)]
    if len(clean) < 2:
        clean = [1.0, 1.0]
    lo, hi = min(clean), max(clean)
    span = (hi - lo) if hi > lo else 1.0
    pts = []
    n = len(clean)
    for i, val in enumerate(clean):
        x = (i / (n - 1)) * width
        y = height - 3 - ((val - lo) / span) * (height - 6)
        pts.append(f"{x:.1f},{y:.1f}")
    poly_pts = " ".join(pts)
    area_pts = f"0,{height} {poly_pts} {width},{height}"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="g_{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.34"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.0"/>'
        f'</linearGradient></defs>'
        f'<polygon class="spark-area" points="{area_pts}" fill="url(#g_{uid})"/>'
        f'<polyline class="spark-line" points="{poly_pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def style_dark_chart(fig, height=330):
    fig.update_layout(
        height=height,
        paper_bgcolor="#15171C",
        plot_bgcolor="#111318",
        font=dict(color="#CBD5E1", family="Plus Jakarta Sans, sans-serif", size=12),
        margin=dict(l=16, r=18, t=38, b=18),
        transition={"duration": 550, "easing": "cubic-in-out"},
        hoverlabel=dict(
            bgcolor="#1C1F26",
            bordercolor="#60A5FA",
            font=dict(color="#FFFFFF", family="Plus Jakarta Sans, sans-serif", size=12),
        ),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False, linecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#94A3B8"))
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False, linecolor="rgba(255,255,255,0.1)", tickfont=dict(color="#94A3B8"))
    return fig


@st.cache_data(ttl=86400)
def fetch_airline_map(api_key):
    try:
        res = requests.get(f"https://airlabs.co/api/v9/airlines?api_key={api_key}", timeout=15)
        if res.status_code == 200:
            return {al.get("iata_code"): al.get("name") for al in res.json().get("response", []) if al.get("iata_code")}
    except Exception:
        pass
    return {}


@st.cache_data(ttl=20)
def fetch_live_commercial_fleet(api_key):
    rows = []
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={api_key}", timeout=18)
        if res.status_code == 200:
            for ac in res.json().get("response", []):
                if ac.get("lat") is None or ac.get("lng") is None:
                    continue
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN":
                    continue
                rows.append({
                    "icao24": hex_code,
                    "callsign": str(ac.get("flight_iata") or ac.get("flight_icao") or hex_code).strip(),
                    "flight_number": str(ac.get("flight_number") or "N/A").strip(),
                    "airline_code": str(ac.get("airline_iata") or "UNKN").upper().strip(),
                    "aircraft_type": str(ac.get("aircraft_icao") or "UNKN").upper().strip(),
                    "dep_iata": str(ac.get("dep_iata") or "UNKN").upper().strip(),
                    "arr_iata": str(ac.get("arr_iata") or "UNKN").upper().strip(),
                    "latitude": safe_float(ac.get("lat")),
                    "longitude": safe_float(ac.get("lng")),
                    "baro_altitude": safe_float(ac.get("alt")) * 3.28084,
                    "velocity": safe_float(ac.get("speed")),
                    "heading": safe_float(ac.get("dir")),
                    "vertical_rate": safe_float(ac.get("v_speed")),
                })
    except Exception:
        pass

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.drop_duplicates(subset=["icao24"]).reset_index(drop=True)
    df["sector"] = [get_airspace_sector(la, lo) for la, lo in zip(df["latitude"], df["longitude"])]
    df[["Manufacturer", "Family", "Body Type", "Generation"]] = df["aircraft_type"].apply(classify_airframe_taxonomy)
    df["is_cargo"] = df["airline_code"].isin(CARGO_CODES) | (df["Family"] == "Dedicated Widebody / Freighter")

    conditions = [
        df["baro_altitude"] < 2500,
        (df["vertical_rate"] > 2.5) & (df["baro_altitude"] < 28000),
        (df["vertical_rate"] < -2.5) & (df["baro_altitude"] < 28000),
        df["baro_altitude"] >= 28000,
    ]
    choices = ["Takeoff / Approach", "Climb", "Descent", "Cruise"]
    df["flight_phase"] = np.select(conditions, choices, default="En-Route")
    return df


@st.cache_data(ttl=60)
def fetch_supabase_history():
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(720).execute()
        hist_df = pd.DataFrame(res.data)
        if hist_df.empty:
            return pd.DataFrame()
        hist_df["ts"] = pd.to_datetime(hist_df["timestamp"], utc=True, errors="coerce")
        return hist_df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def _fetch_single_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/3.0)"}
    try:
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code != 200:
            return symbol, None
        result = r.json().get("chart", {}).get("result", [])
        if not result:
            return symbol, None
        meta = result[0].get("meta", {})
        closes = [c for c in result[0].get("indicators", {}).get("quote", [{}])[0].get("close", []) if c is not None]
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        prev = meta.get("chartPreviousClose") or (closes[-2] if len(closes) >= 2 else price)
        currency = meta.get("currency", "USD")
        pct = ((price - prev) / prev * 100.0) if (price and prev and prev > 0) else 0.0
        return symbol, {
            "price": round(float(price), 2) if price is not None else None,
            "pct_change": round(float(pct), 2),
            "currency": currency,
            "spark": closes[-20:] if closes else [1.0, 1.0],
        }
    except Exception:
        return symbol, None


@st.cache_data(ttl=900)
def fetch_watchlist_quotes(tickers):
    quotes = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch_single_quote, t) for t in tickers]
        for fut in as_completed(futures):
            sym, data = fut.result()
            if data:
                quotes[sym] = data
    return quotes


@st.cache_data(ttl=900)
def fetch_aviation_news():
    feeds = [
        ("Simple Flying", "https://simpleflying.com/feed/"),
        ("FlightGlobal", "https://www.flightglobal.com/rss"),
        ("Leeham News", "https://leehamnews.com/feed/"),
        ("AeroTime", "https://www.aerotime.aero/feed"),
    ]
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/3.0)"}
    for source_name, url in feeds:
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:8]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()[:16]
                desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()
                desc = html.unescape(desc)[:175]
                if not title or not link:
                    continue
                low = f"{title} {desc}".lower()
                if any(k in low for k in ["order", "deliver", "backlog", "airbus", "boeing", "embraer", "max", "a320", "a350", "787"]):
                    tag = "OEM & Backlog"
                elif any(k in low for k in ["mro", "maintenance", "engine", "leap", "gtf", "grounded", "aog", "check"]):
                    tag = "MRO & Engine"
                elif any(k in low for k in ["profit", "earnings", "lease", "lessor", "aercap", "revenue", "capacity", "fleet"]):
                    tag = "Finance & Leasing"
                else:
                    tag = "Market Brief"
                items.append({
                    "source": source_name,
                    "title": html.unescape(title),
                    "snippet": desc,
                    "link": link,
                    "published": pub,
                    "tag": tag,
                })
        except Exception:
            continue
    return items[:24]


def compute_airline_growth_from_history(hist_df, live_airline_counts):
    growth_map = {}
    if hist_df.empty or "regional_breakdown" not in hist_df.columns:
        return growth_map

    now_ts = hist_df["ts"].max()
    records = []
    for _, row in hist_df.iterrows():
        rb = row.get("regional_breakdown")
        if isinstance(rb, dict) and "__meta_airlines" in rb:
            records.append((row["ts"], rb["__meta_airlines"]))
    if not records:
        return growth_map

    _, first_counts = records[0]
    snap_24h = min(records, key=lambda x: abs((x[0] - (now_ts - pd.Timedelta(hours=24))).total_seconds()))[1]
    snap_30d = min(records, key=lambda x: abs((x[0] - (now_ts - pd.Timedelta(days=30))).total_seconds()))[1]

    for code, live_cnt in live_airline_counts.items():
        b24 = snap_24h.get(code)
        b30 = snap_30d.get(code)
        bmax = first_counts.get(code)
        growth_map[code] = {
            "d24": round(((live_cnt - b24) / b24) * 100, 1) if b24 and b24 > 0 else None,
            "d30": round(((live_cnt - b30) / b30) * 100, 1) if b30 and b30 > 0 else None,
            "dmax": round(((live_cnt - bmax) / bmax) * 100, 1) if bmax and bmax > 0 else None,
        }
    return growth_map


# -----------------------------------------------------------------------------
# LOAD DATA
# -----------------------------------------------------------------------------
airline_map = fetch_airline_map(client.api_key)
raw_df = fetch_live_commercial_fleet(client.api_key)
hist_df = fetch_supabase_history()
quotes_map = fetch_watchlist_quotes([e["ticker"] for e in WATCHLIST_ENTITIES])
news_items = fetch_aviation_news()

if raw_df.empty:
    st.error("Live commercial ADS-B feed returned no vectors. Verify AIRLABS_API_KEY or API rate quota.")
    st.stop()

live_airline_counts = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts().to_dict()
growth_map = compute_airline_growth_from_history(hist_df, live_airline_counts)
utc_now = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")

# -----------------------------------------------------------------------------
# TOP HEADER BAR (UNOBSTRUCTED AT TOP OF CANVAS)
# -----------------------------------------------------------------------------
top_l, top_m, top_r = st.columns([1.3, 2.3, 1.15], gap="medium")

with top_l:
    st.markdown(
        '<div class="brand-wrap">'
        '<div class="brand-icon">'
        '<svg width="21" height="21" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">'
        '<path fill="#FFFFFF" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>'
        '</svg>'
        '</div>'
        '<div><div class="brand-name">AeroTrack</div><div class="brand-sub">Aviation Finance, OEM &amp; MRO Terminal</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )

with top_m:
    search_query = st.text_input(
        "Terminal Search",
        placeholder="Search airline, OEM, ticker, tail hex, or airframe (e.g. DAL, A359, BA, 6E, AER)...",
        label_visibility="collapsed",
    )

with top_r:
    tr1, tr2 = st.columns([1.45, 0.75], gap="small")
    with tr1:
        st.markdown(f'<div class="live-pill"><span class="live-dot"></span>{utc_now}</div>', unsafe_allow_html=True)
    with tr2:
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

# Animated Live Ticker Marquee Strip
ticker_chips = [f'<span class="tick-item"><strong style="color:#60A5FA;">LIVE FLEET</strong> {len(raw_df):,} AC</span>']
for ent in WATCHLIST_ENTITIES:
    q = quotes_map.get(ent["ticker"])
    if q and q.get("price") is not None:
        p = q["pct_change"]
        clr = "#34D399" if p >= 0 else "#FB7185"
        arr = "▲" if p >= 0 else "▼"
        ticker_chips.append(
            f'<span class="tick-item"><strong>{ent["ticker"]}</strong> {q["price"]:,.2f} '
            f'<span style="color:{clr};">{p:+.2f}% {arr}</span></span>'
        )
ticker_html = "".join(ticker_chips)
st.markdown(f'<div class="ticker-shell"><div class="ticker-track">{ticker_html}{ticker_html}</div></div>', unsafe_allow_html=True)

# Top-Level Navigation Switcher (Cleanly separates Equity Dashboard, OEM, Digital Twin, News Corner)
nav_view = st.radio(
    "Primary Navigation",
    ["Equity & Fleet Dashboard", "OEM Backlog Corner", "Digital Twin & MRO", "News Corner"],
    horizontal=True,
    label_visibility="collapsed",
    key="primary_nav_radio",
)

st.markdown("<div style='height:0.55rem;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# SPACIOUS 2-PANE LAYOUT: LEFT WATCHLIST RAIL | WIDE MAIN WORKSPACE
# -----------------------------------------------------------------------------
col_watch, col_main = st.columns([0.92, 3.08], gap="large")

with col_watch:
    st.markdown(
        '<div class="rail-box"><div class="rail-head"><div class="rail-title">Market Watchlist</div><div class="rail-tag">LIVE 1M</div></div>',
        unsafe_allow_html=True,
    )
    wl_cat = st.radio(
        "Watchlist Filter",
        ["All", "Airlines", "Lessors", "OEMs"],
        horizontal=True,
        label_visibility="collapsed",
        key="wl_filter_radio",
    )
    filtered_wl = [e for e in WATCHLIST_ENTITIES if wl_cat == "All" or e["category"] == wl_cat]

    wl_rows = []
    for idx, item in enumerate(filtered_wl):
        tkr = item["ticker"]
        q = quotes_map.get(tkr)
        if q and q.get("price") is not None:
            sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(q["currency"], "")
            px_str = f"{sym}{q['price']:,.2f}"
            pct = q["pct_change"]
            clr = "#34D399" if pct >= 0 else "#FB7185"
            arr = "▲" if pct >= 0 else "▼"
            chg_str = f"{pct:+.2f}% {arr}"
            svg = build_svg_sparkline(q["spark"], color=clr, width=68, height=24, uid=f"w_{idx}")
        else:
            cnt = live_airline_counts.get(item["iata"], 0) if item["iata"] else 0
            px_str = f"{cnt} AC" if cnt else item["country"]
            clr = "#94A3B8"
            chg_str = item["category"]
            svg = build_svg_sparkline([1.0, 1.02, 1.01, 1.03], color="#60A5FA", width=68, height=24, uid=f"w_{idx}")

        delay = min(idx * 0.03, 0.4)
        wl_rows.append(
            f'<div class="watch-item" style="animation-delay:{delay:.2f}s;">'
            f'<div><div class="w-sym">{html.escape(tkr)}</div><div class="w-name">{html.escape(item["name"])}</div></div>'
            f'<div style="display:flex;justify-content:center;">{svg}</div>'
            f'<div><div class="w-px">{px_str}</div><div class="w-chg" style="color:{clr};">{chg_str}</div></div>'
            f'</div>'
        )
    st.markdown("".join(wl_rows) + "</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
    focus_choices = ["ALL (Global Universe)"] + [f"{e['ticker']} — {e['name']}" for e in filtered_wl]
    focus_pick = st.selectbox("Focus Entity", focus_choices)

# Compute Filtered Telemetry Frame
df = raw_df.copy()
if focus_pick != "ALL (Global Universe)":
    tkr_sel = focus_pick.split(" — ")[0].strip()
    ent = next((e for e in WATCHLIST_ENTITIES if e["ticker"] == tkr_sel), None)
    if ent:
        if ent.get("iata"):
            df = df[df["airline_code"] == ent["iata"]]
        elif ent["ticker"] == "AIR.PA":
            df = df[df["Manufacturer"] == "Airbus"]
        elif ent["ticker"] == "BA":
            df = df[df["Manufacturer"] == "Boeing"]
        elif ent["ticker"] == "ERJ":
            df = df[df["Manufacturer"] == "Embraer"]

if search_query.strip():
    q = search_query.strip().lower()
    df = df[
        df["callsign"].str.lower().str.contains(q, na=False)
        | df["icao24"].str.lower().str.contains(q, na=False)
        | df["airline_code"].str.lower().str.contains(q, na=False)
        | df["aircraft_type"].str.lower().str.contains(q, na=False)
        | df["Family"].str.lower().str.contains(q, na=False)
        | df["Manufacturer"].str.lower().str.contains(q, na=False)
    ]

# =============================================================================
# MAIN WORKSPACE BY TOP NAVIGATION SELECTION
# =============================================================================
with col_main:
    # =========================================================================
    # VIEW 1: EQUITY & FLEET DASHBOARD
    # =========================================================================
    if nav_view == "Equity & Fleet Dashboard":
        scope = st.radio(
            "Market Scope",
            ["Global", "NORTH AMERICA", "EUROPE", "EAST ASIA & APAC", "MIDDLE EAST & S. ASIA", "LATIN AMERICA", "Widebody", "Narrowbody", "Cargo"],
            horizontal=True,
            label_visibility="collapsed",
            key="eq_scope_pills",
        )

        scoped_df = df.copy()
        if scope in ["NORTH AMERICA", "EUROPE", "EAST ASIA & APAC", "MIDDLE EAST & S. ASIA", "LATIN AMERICA"]:
            scoped_df = scoped_df[scoped_df["sector"] == scope]
        elif scope == "Widebody":
            scoped_df = scoped_df[scoped_df["Body Type"] == "Widebody"]
        elif scope == "Narrowbody":
            scoped_df = scoped_df[scoped_df["Body Type"] == "Narrowbody"]
        elif scope == "Cargo":
            scoped_df = scoped_df[scoped_df["is_cargo"] == True]

        # Build Index Series
        total_series = hist_df["total_flights"].tail(24).tolist() if not hist_df.empty else [len(raw_df)]
        nb_series, wb_series, cg_series = [], [], []
        if not hist_df.empty and "regional_breakdown" in hist_df.columns:
            for rb in hist_df["regional_breakdown"].tail(24):
                if isinstance(rb, dict):
                    bt = rb.get("__meta_body_types", {})
                    if bt:
                        nb_series.append(bt.get("Narrowbody", 0))
                        wb_series.append(bt.get("Widebody", 0))
                    if "__meta_cargo_count" in rb:
                        cg_series.append(rb["__meta_cargo_count"])

        def _delta(series, curr):
            valid = [v for v in series if v and v > 0]
            if len(valid) >= 2:
                avg = np.mean(valid[:-1])
                return ((curr - avg) / avg) * 100.0 if avg > 0 else 0.0
            return 0.0

        c_tot = len(scoped_df)
        c_nb = int((scoped_df["Body Type"] == "Narrowbody").sum())
        c_wb = int((scoped_df["Body Type"] == "Widebody").sum())
        c_cg = int(scoped_df["is_cargo"].sum())

        cards = [
            ("ACTIVE COMMERCIAL FLEET", f"{c_tot:,}", _delta(total_series, len(raw_df)), total_series or [c_tot, c_tot], "c1"),
            ("NARROWBODY UTILIZATION", f"{c_nb:,}", _delta(nb_series, int((raw_df["Body Type"] == "Narrowbody").sum())), nb_series or [c_nb, c_nb], "c2"),
            ("WIDEBODY UTILIZATION", f"{c_wb:,}", _delta(wb_series, int((raw_df["Body Type"] == "Widebody").sum())), wb_series or [c_wb, c_wb], "c3"),
            ("DEDICATED FREIGHTERS", f"{c_cg:,}", _delta(cg_series, int(raw_df["is_cargo"].sum())), cg_series or [c_cg, c_cg], "c4"),
        ]

        k1, k2, k3, k4 = st.columns(4, gap="medium")
        for idx_i, (col, (kicker, big, dlt, ser, uid)) in enumerate(zip([k1, k2, k3, k4], cards)):
            up = dlt >= 0
            pcls = "pill-up" if up else "pill-dn"
            sp_clr = "#34D399" if up else "#FB7185"
            arr = "↑" if up else "↓"
            svg = build_svg_sparkline(ser, color=sp_clr, width=210, height=38, uid=uid)
            with col:
                st.markdown(
                    f'<div class="idx-card" style="animation-delay:{idx_i*0.06:.2f}s;">'
                    f'<div class="idx-kicker">{kicker}</div>'
                    f'<div class="idx-big">{big}</div>'
                    f'<div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.4rem;">'
                    f'<span class="{pcls}">{dlt:+.1f}% {arr}</span>'
                    f'<span style="font-size:0.71rem;color:#94A3B8;">vs 24h avg</span>'
                    f'</div><div>{svg}</div></div>',
                    unsafe_allow_html=True,
                )

        # Spacious Sub-Views inside Equity & Fleet so nothing looks packed
        sub_tab_1, sub_tab_2, sub_tab_3 = st.tabs([
            "Airline Fleet Growth & Financials",
            "Global Commercial Fleet Map (3D)",
            "Regional Capacity & HHI Benchmark",
        ])

        with sub_tab_1:
            screener_rows = []
            all_codes = sorted(
                set(list(AIRLINE_FINANCIAL_BASELINES.keys()) + list(raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts().head(25).index)),
                key=lambda c: live_airline_counts.get(c, 0),
                reverse=True,
            )
            for code in all_codes:
                sub = scoped_df[scoped_df["airline_code"] == code]
                live_cnt = len(sub)
                base = AIRLINE_FINANCIAL_BASELINES.get(code, {})
                tkr = base.get("ticker", "N/A")
                q = quotes_map.get(tkr, {})
                gr = growth_map.get(code, {})
                ng_pct = round(float((sub["Generation"] == "Next-Gen").mean() * 100), 1) if live_cnt > 0 else 0.0
                reg_fleet = base.get("registered_fleet")
                util_ratio = round((live_cnt / reg_fleet) * 100, 1) if (reg_fleet and reg_fleet > 0) else None

                screener_rows.append({
                    "IATA": code,
                    "Airline": base.get("name") or airline_map.get(code, code),
                    "Ticker": tkr,
                    "Stock Price": q.get("price"),
                    "1D Equity %": q.get("pct_change"),
                    "Live Airborne": live_cnt,
                    "Registered Fleet": reg_fleet,
                    "Active Lift %": util_ratio,
                    "Growth 24h %": gr.get("d24"),
                    "Growth 30D %": gr.get("d30"),
                    "Growth Max %": gr.get("dmax"),
                    "Next-Gen %": ng_pct,
                    "Revenue ($B)": base.get("rev_bn"),
                    "Net Profit ($B)": base.get("net_profit_bn"),
                    "Op Margin %": base.get("op_margin"),
                })

            scr_df = pd.DataFrame(screener_rows)
            st.dataframe(
                scr_df,
                use_container_width=True,
                hide_index=True,
                height=390,
                column_config={
                    "Stock Price": st.column_config.NumberColumn(format="%.2f"),
                    "1D Equity %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "Active Lift %": st.column_config.ProgressColumn("Active Lift %", min_value=0, max_value=100, format="%.1f%%"),
                    "Next-Gen %": st.column_config.ProgressColumn("Next-Gen %", min_value=0, max_value=100, format="%.1f%%"),
                    "Growth 24h %": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Growth 30D %": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Growth Max %": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Revenue ($B)": st.column_config.NumberColumn(format="$%.1fB"),
                    "Net Profit ($B)": st.column_config.NumberColumn(format="$%.2fB"),
                    "Op Margin %": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )

            ch1, ch2 = st.columns(2, gap="large")
            with ch1:
                fin_df = scr_df.dropna(subset=["Net Profit ($B)"]).head(12)
                fig_prof = px.bar(
                    fin_df,
                    x="Airline",
                    y="Net Profit ($B)",
                    color="Op Margin %",
                    color_continuous_scale=["#FB7185", "#FBBF24", "#34D399"],
                    title="Carrier Net Profit ($B) vs. Operating Margin",
                )
                style_dark_chart(fig_prof, height=320)
                fig_prof.update_layout(xaxis_title="", xaxis_tickangle=-25)
                st.plotly_chart(fig_prof, use_container_width=True)

            with ch2:
                if not hist_df.empty:
                    fig_tr = go.Figure()
                    fig_tr.add_trace(go.Scatter(
                        x=hist_df["ts"].tail(48),
                        y=hist_df["total_flights"].tail(48),
                        mode="lines",
                        line=dict(color="#60A5FA", width=2.6, shape="spline"),
                        fill="tozeroy",
                        fillcolor="rgba(96, 165, 250, 0.14)",
                        name="Active Fleet",
                    ))
                    style_dark_chart(fig_tr, height=320)
                    fig_tr.update_layout(title="Global Commercial Fleet Volume Trajectory")
                    st.plotly_chart(fig_tr, use_container_width=True)

        with sub_tab_2:
            if scoped_df.empty:
                st.info("No active commercial airframes match this filter.")
            else:
                def _body_rgb(row):
                    if row["is_cargo"]:
                        return [251, 191, 36, 235]
                    if row["Body Type"] == "Widebody":
                        return [96, 165, 250, 235]
                    if row["Body Type"] == "Narrowbody":
                        return [52, 211, 153, 225]
                    return [148, 163, 184, 200]

                map_df = scoped_df.copy()
                map_df["color"] = map_df.apply(_body_rgb, axis=1)
                map_df["angle"] = (360.0 - map_df["heading"].fillna(0.0)) % 360.0
                map_df["icon_size"] = np.where(map_df["Body Type"] == "Widebody", 21, 15)
                map_df["icon_data"] = [{
                    "url": AIRLINER_ICON_URL, "width": 128, "height": 128, "anchorX": 64, "anchorY": 64, "mask": True
                }] * len(map_df)
                map_df["alt_fmt"] = map_df["baro_altitude"].round(0).astype(int)
                map_df["spd_fmt"] = map_df["velocity"].round(0).astype(int)

                layer = pdk.Layer(
                    "IconLayer",
                    data=map_df,
                    get_icon="icon_data",
                    get_position="[longitude, latitude]",
                    get_size="icon_size",
                    size_scale=1,
                    size_min_pixels=10,
                    size_max_pixels=23,
                    get_angle="angle",
                    get_color="color",
                    billboard=False,
                    pickable=True,
                )
                st.pydeck_chart(
                    pdk.Deck(
                        layers=[layer],
                        initial_view_state=pdk.ViewState(latitude=25, longitude=10, zoom=1.5, pitch=36, bearing=0),
                        tooltip={
                            "html": "<div style='font-family:Plus Jakarta Sans,sans-serif;padding:6px;min-width:195px;'>"
                                    "<div style='font-weight:700;color:#FFF;font-size:13px;border-bottom:1px solid #334155;padding-bottom:3px;margin-bottom:4px;'>{callsign} ({icao24})</div>"
                                    "<div style='color:#CBD5E1;font-size:12px;'>{aircraft_type} · {Family}</div>"
                                    "<div style='color:#34D399;font-family:IBM Plex Mono,monospace;font-size:11px;margin-top:3px;'>ALT {alt_fmt} ft | SPD {spd_fmt} km/h</div>"
                                    "</div>",
                            "style": {"backgroundColor": "#15171C", "border": "1px solid #475569", "borderRadius": "10px"},
                        },
                        map_style="mapbox://styles/mapbox/dark-v11",
                    ),
                    use_container_width=True,
                )
                st.caption("Legend:  Emerald = Narrowbody  |  Blue = Widebody  |  Amber = Freighter / Cargo  |  Silver = Regional")

        with sub_tab_3:
            total_g = len(raw_df)
            reg_rows = []
            for sec_name, sec_df in raw_df.groupby("sector"):
                cnt = len(sec_df)
                c_counts = sec_df[~sec_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts()
                if not c_counts.empty:
                    props = c_counts / c_counts.sum()
                    hhi = round(float(sum(props ** 2) * 10000), 1)
                    conc = "Highly Concentrated" if hhi > 2500 else ("Moderately Concentrated" if hhi > 1500 else "Competitive")
                    top_c = f"{airline_map.get(c_counts.index[0], c_counts.index[0])} ({c_counts.index[0]})"
                else:
                    hhi, conc, top_c = 0.0, "Charter / Unscheduled", "N/A"
                reg_rows.append({
                    "Geographic Market": sec_name,
                    "Active Fleet": cnt,
                    "Global Share %": round((cnt / total_g) * 100, 1) if total_g else 0.0,
                    "Next-Gen %": round(float((sec_df["Generation"] == "Next-Gen").mean() * 100), 1),
                    "HHI Index": hhi,
                    "Market Structure": conc,
                    "Leading Operator": top_c,
                    "Top Family": sec_df["Family"].mode()[0],
                })
            st.dataframe(
                pd.DataFrame(reg_rows).sort_values("Active Fleet", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Global Share %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                    "Next-Gen %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                },
            )

    # =========================================================================
    # VIEW 2: OEM BACKLOG CORNER
    # =========================================================================
    elif nav_view == "OEM Backlog Corner":
        oem_df = pd.DataFrame(OEM_BACKLOG_REFERENCE)
        oem_df["Backlog_Years"] = (oem_df["Backlog"] / oem_df["Annual_Delivery_Rate"]).round(1)
        oem_df["Backlog_Value_Bn"] = ((oem_df["Backlog"] * oem_df["Avg_List_Price_M"]) / 1000.0).round(1)
        live_oems = raw_df[raw_df["Manufacturer"] != "Other"]["Manufacturer"].value_counts().to_dict()

        o1, o2, o3, o4 = st.columns(4, gap="medium")
        oem_cards = [
            ("AIRBUS FIRM BACKLOG", f"{int(oem_df[oem_df['OEM']=='Airbus']['Backlog'].sum()):,}", f"{live_oems.get('Airbus', 0):,} live airborne", "#60A5FA"),
            ("BOEING FIRM BACKLOG", f"{int(oem_df[oem_df['OEM']=='Boeing']['Backlog'].sum()):,}", f"{live_oems.get('Boeing', 0):,} live airborne", "#34D399"),
            ("EMBRAER FIRM BACKLOG", f"{int(oem_df[oem_df['OEM']=='Embraer']['Backlog'].sum()):,}", f"{live_oems.get('Embraer', 0):,} live airborne", "#FBBF24"),
            ("GROSS BOOK VALUE", f"${oem_df['Backlog_Value_Bn'].sum():,.0f}B", "List-price implied backlog", "#F1F5F9"),
        ]
        for idx_o, (col, (k, v, sub, clr)) in enumerate(zip([o1, o2, o3, o4], oem_cards)):
            with col:
                st.markdown(
                    f'<div class="idx-card" style="padding-bottom:0.95rem;animation-delay:{idx_o*0.06:.2f}s;">'
                    f'<div class="idx-kicker">{k}</div>'
                    f'<div class="idx-big" style="color:{clr};">{v}</div>'
                    f'<div style="font-size:0.74rem;color:#94A3B8;">{sub}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

        oc1, oc2 = st.columns([1.4, 1.0], gap="large")
        with oc1:
            fig_bl = px.bar(
                oem_df.sort_values("Backlog", ascending=True),
                x="Backlog",
                y="Program",
                color="OEM",
                orientation="h",
                text="Backlog_Years",
                color_discrete_map={"Airbus": "#60A5FA", "Boeing": "#34D399", "Embraer": "#FBBF24", "COMAC": "#FB7185", "ATR": "#94A3B8"},
                title="Program Backlog & Production Horizon (Years)",
            )
            fig_bl.update_traces(texttemplate="%{text}y", textposition="outside")
            style_dark_chart(fig_bl, height=390)
            fig_bl.update_layout(yaxis_title="", xaxis_title="Firm Unfilled Orders")
            st.plotly_chart(fig_bl, use_container_width=True)

        with oc2:
            in_svc = pd.DataFrame([{"OEM": k, "Airframes": v} for k, v in live_oems.items() if k in ["Airbus", "Boeing", "Embraer", "ATR", "COMAC"]])
            if not in_svc.empty:
                fig_sh = px.pie(
                    in_svc,
                    names="OEM",
                    values="Airframes",
                    hole=0.62,
                    color="OEM",
                    color_discrete_map={"Airbus": "#60A5FA", "Boeing": "#34D399", "Embraer": "#FBBF24", "COMAC": "#FB7185", "ATR": "#94A3B8"},
                    title="Live In-Service Fleet Share (ADS-B)",
                )
                fig_sh.update_traces(textinfo="label+percent", marker=dict(line=dict(color="#0D0E11", width=2)))
                style_dark_chart(fig_sh, height=390)
                fig_sh.update_layout(showlegend=False)
                st.plotly_chart(fig_sh, use_container_width=True)

        st.markdown('<div class="sec-head"><div class="sec-title">Delivery Slot Pipeline &amp; Production Cadence</div><div class="sec-sub">OFFICIAL OEM BASELINE</div></div>', unsafe_allow_html=True)
        st.dataframe(
            oem_df[["OEM", "Program", "Segment", "Backlog", "Annual_Delivery_Rate", "Backlog_Years", "Backlog_Value_Bn", "Key_Slots"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Backlog": st.column_config.NumberColumn("Firm Backlog", format="%d"),
                "Annual_Delivery_Rate": st.column_config.NumberColumn("Delivery Run-Rate", format="%d / yr"),
                "Backlog_Years": st.column_config.NumberColumn("Backlog Years", format="%.1f yrs"),
                "Backlog_Value_Bn": st.column_config.NumberColumn("Implied Value", format="$%.1fB"),
                "Key_Slots": "Key Slot Holders",
            },
        )

    # =========================================================================
    # VIEW 3: DIGITAL TWIN & MRO RADAR
    # =========================================================================
    elif nav_view == "Digital Twin & MRO":
        st.markdown(
            '<div class="glass-card" style="padding:1rem 1.25rem;">'
            '<div style="font-size:1rem;font-weight:700;color:#FFFFFF;">Live Airframe Digital Twin &amp; MRO Maintenance Radar</div>'
            '<div style="font-size:0.8rem;color:#94A3B8;margin-top:0.2rem;">Select any active commercial tail to inspect live kinematic flight phase, estimated A/C/D-check progression, and nearest global MRO/storage hub.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        sample_tails = df.sort_values("baro_altitude", ascending=False).head(100)
        tail_opts = [f"{r['callsign']} | {r['icao24']} | {r['aircraft_type']} ({r['airline_code']})" for _, r in sample_tails.iterrows()]

        if tail_opts:
            picked = st.selectbox("Select Active Tail Registration / ICAO Hex", tail_opts)
            hex_sel = picked.split("|")[1].strip()
            trow = df[df["icao24"] == hex_sel].iloc[0]

            hub_dists = [(h["hub"], h["name"], h["specialty"], float(haversine_km(trow["latitude"], trow["longitude"], h["lat"], h["lon"]))) for h in MRO_HUBS]
            near_hub = min(hub_dists, key=lambda x: x[3])
            al_info = AIRLINE_FINANCIAL_BASELINES.get(trow["airline_code"], {})
            est_age = al_info.get("avg_age_yrs", 4.6 if trow["Generation"] == "Next-Gen" else 13.8)
            a_prog = int((hash(hex_sel) % 72) + 20)
            c_prog = int(((est_age % 2.0) / 2.0) * 100)
            d_prog = int(min(100, (est_age / 8.0) * 100))

            dt1, dt2, dt3 = st.columns(3, gap="medium")
            with dt1:
                st.markdown(
                    f'<div class="idx-card" style="padding-bottom:1rem;">'
                    f'<div class="idx-kicker">DIGITAL TWIN IDENTITY</div>'
                    f'<div class="idx-big" style="font-size:1.2rem;">{trow["callsign"]} · {trow["icao24"]}</div>'
                    f'<div style="font-size:0.79rem;color:#CBD5E1;line-height:1.55;">'
                    f'Airframe: <strong>{trow["aircraft_type"]}</strong> ({trow["Family"]})<br/>'
                    f'OEM / Gen: <strong>{trow["Manufacturer"]}</strong> · {trow["Generation"]}<br/>'
                    f'Operator: <strong>{airline_map.get(trow["airline_code"], trow["airline_code"])}</strong>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with dt2:
                st.markdown(
                    f'<div class="idx-card" style="padding-bottom:1rem;">'
                    f'<div class="idx-kicker">LIVE KINEMATIC STATE</div>'
                    f'<div class="idx-big" style="font-size:1.2rem;color:#34D399;">{trow["flight_phase"].upper()}</div>'
                    f'<div style="font-size:0.79rem;color:#CBD5E1;font-family:IBM Plex Mono,monospace;line-height:1.55;">'
                    f'ALT: {trow["baro_altitude"]:,.0f} ft<br/>'
                    f'SPD: {trow["velocity"]:,.0f} km/h | HDG: {trow["heading"]:.0f}°<br/>'
                    f'SECTOR: {trow["sector"]}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with dt3:
                st.markdown(
                    f'<div class="idx-card" style="padding-bottom:1rem;">'
                    f'<div class="idx-kicker">MRO HUB &amp; FLEET AGE</div>'
                    f'<div class="idx-big" style="font-size:1.15rem;color:#FBBF24;">{near_hub[0]} ({near_hub[3]:,.0f} km)</div>'
                    f'<div style="font-size:0.78rem;color:#CBD5E1;line-height:1.55;">'
                    f'{near_hub[1]}<br/>'
                    f'Specialty: {near_hub[2]}<br/>'
                    f'Operator Avg Age: <strong>{est_age:.1f} yrs</strong>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height:0.55rem;'></div>", unsafe_allow_html=True)

            # Animated MRO Check Horizon Bars
            b1, b2, b3 = st.columns(3, gap="medium")
            for col, (lbl, pct_val, clr) in zip(
                [b1, b2, b3],
                [
                    ("A-Check Cycle (~600 FH)", a_prog, "#60A5FA"),
                    ("C-Check Window (~24 Months)", c_prog, "#34D399"),
                    ("Heavy D-Check Horizon (~8 Yrs)", d_prog, "#FBBF24"),
                ],
            ):
                with col:
                    st.markdown(
                        f'<div class="mro-bar-wrap">'
                        f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;font-weight:600;color:#E2E8F0;">'
                        f'<span>{lbl}</span><span style="color:{clr};font-family:IBM Plex Mono,monospace;">{pct_val}%</span></div>'
                        f'<div class="mro-track"><div class="mro-fill" style="width:{pct_val}%;background:{clr};"></div></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("<div style='height:0.65rem;'></div>", unsafe_allow_html=True)
        mc1, mc2 = st.columns([1.25, 1.0], gap="large")
        with mc1:
            mro_rows = []
            for hub in MRO_HUBS:
                dists = haversine_km(df["latitude"].values, df["longitude"].values, hub["lat"], hub["lon"])
                nearby = df[(dists <= 120.0) & (df["baro_altitude"] < 14000)]
                mro_rows.append({
                    "Hub": hub["hub"],
                    "MRO Facility": hub["name"],
                    "Specialty": hub["specialty"],
                    "Low-Alt Movements (<120km)": int(len(nearby)),
                    "Next-Gen %": f"{(nearby['Generation']=='Next-Gen').mean()*100:.0f}%" if len(nearby) > 0 else "0%",
                })
            st.markdown('<div class="sec-head"><div class="sec-title">Global MRO &amp; Storage Hub Traffic</div><div class="sec-sub">&lt;120 KM APPROACH</div></div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(mro_rows).sort_values("Low-Alt Movements (<120km)", ascending=False), use_container_width=True, hide_index=True, height=300)

        with mc2:
            gen_oem = df[df["Manufacturer"] != "Other"].groupby(["Manufacturer", "Generation"]).size().reset_index(name="Count")
            if not gen_oem.empty:
                fig_mro = px.bar(
                    gen_oem,
                    x="Manufacturer",
                    y="Count",
                    color="Generation",
                    barmode="stack",
                    color_discrete_map={"Next-Gen": "#34D399", "Legacy": "#475569"},
                    title="Engine MRO Base: Next-Gen vs. Legacy",
                )
                style_dark_chart(fig_mro, height=345)
                fig_mro.update_layout(xaxis_title="", legend=dict(orientation="h", y=1.08, x=0, title=None))
                st.plotly_chart(fig_mro, use_container_width=True)

    # =========================================================================
    # VIEW 4: DEDICATED NEWS CORNER
    # =========================================================================
    else:
        busiest_reg = raw_df["sector"].mode()[0] if not raw_df.empty else "NORTH AMERICA"
        top_al = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].mode()[0]
        top_al_name = airline_map.get(top_al, top_al)

        st.markdown(
            f'<div class="glass-card">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.45rem;">'
            f'<span style="font-size:0.74rem;font-weight:700;color:#60A5FA;letter-spacing:0.06em;">AVIATION MARKET WIRE &amp; BRIEFING</span>'
            f'<span class="rail-tag">{len(news_items)} LIVE STORIES</span>'
            f'</div>'
            f'<div style="font-size:1.08rem;font-weight:800;color:#FFFFFF;margin-bottom:0.35rem;">'
            f'{len(raw_df):,} active commercial airframes tracked worldwide · {top_al_name} ({top_al}) leads airborne lift'
            f'</div>'
            f'<div style="font-size:0.84rem;color:#CBD5E1;line-height:1.55;">'
            f'Highest sector density is currently concentrated in <strong>{busiest_reg}</strong>, with Next-Gen fleets accounting for '
            f'<strong>{(raw_df["Generation"]=="Next-Gen").mean()*100:.1f}%</strong> of global capacity. Filter curated industry reporting below by vertical.'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        news_cat = st.radio(
            "News Category",
            ["All Stories", "OEM & Backlog", "MRO & Engine", "Finance & Leasing", "Market Brief"],
            horizontal=True,
            label_visibility="collapsed",
            key="news_cat_pills",
        )

        shown_news = [n for n in news_items if news_cat == "All Stories" or n["tag"] == news_cat]

        if not shown_news:
            st.info("No articles matched that vertical in the current RSS window.")
        else:
            nc1, nc2 = st.columns(2, gap="medium")
            for idx_n, item in enumerate(shown_news):
                target_col = nc1 if idx_n % 2 == 0 else nc2
                tag_clr = (
                    "#60A5FA" if item["tag"] == "OEM & Backlog"
                    else ("#FBBF24" if item["tag"] == "MRO & Engine"
                          else ("#34D399" if item["tag"] == "Finance & Leasing" else "#CBD5E1"))
                )
                with target_col:
                    st.markdown(
                        f'<div class="news-tile" style="animation-delay:{min(idx_n*0.04, 0.35):.2f}s;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="font-size:0.7rem;font-weight:700;color:{tag_clr};font-family:IBM Plex Mono,monospace;">{item["tag"].upper()}</span>'
                        f'<span style="font-size:0.7rem;color:#64748B;">{html.escape(item["source"])} · {html.escape(item["published"])}</span>'
                        f'</div>'
                        f'<a href="{html.escape(item["link"])}" target="_blank">{html.escape(item["title"])}</a>'
                        f'<div class="news-snip">{html.escape(item["snippet"])}...</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
