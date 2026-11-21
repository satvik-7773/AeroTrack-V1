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
from plotly.subplots import make_subplots
from supabase import create_client

from data_ingestion.client import OpenSkyClient

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION (NO STREAMLIT SIDEBAR — FULL TERMINAL CANVAS)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AeroTrack Terminal // Aviation Finance, MRO & Fleet Intelligence",
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
    # Lessors
    {"ticker": "AER", "name": "AerCap Holdings N.V.", "category": "Lessors", "iata": None, "country": "IE/US"},
    {"ticker": "AL", "name": "Air Lease Corporation", "category": "Lessors", "iata": None, "country": "US"},
    {"ticker": "FTAI", "name": "FTAI Aviation Ltd.", "category": "Lessors", "iata": None, "country": "US"},
    # OEMs
    {"ticker": "AIR.PA", "name": "Airbus SE", "category": "OEMs", "iata": None, "country": "EU"},
    {"ticker": "BA", "name": "The Boeing Company", "category": "OEMs", "iata": None, "country": "US"},
    {"ticker": "ERJ", "name": "Embraer S.A.", "category": "OEMs", "iata": None, "country": "BR"},
    # Airlines
    {"ticker": "DAL", "name": "Delta Air Lines", "category": "Airlines", "iata": "DL", "country": "US"},
    {"ticker": "UAL", "name": "United Airlines Holdings", "category": "Airlines", "iata": "UA", "country": "US"},
    {"ticker": "AAL", "name": "American Airlines Group", "category": "Airlines", "iata": "AA", "country": "US"},
    {"ticker": "LUV", "name": "Southwest Airlines", "category": "Airlines", "iata": "WN", "country": "US"},
    {"ticker": "RYAAY", "name": "Ryanair Holdings plc", "category": "Airlines", "iata": "FR", "country": "EU"},
    {"ticker": "LHA.DE", "name": "Deutsche Lufthansa AG", "category": "Airlines", "iata": "LH", "country": "EU"},
    {"ticker": "IAG.L", "name": "Intl Consolidated Airlines", "category": "Airlines", "iata": "BA", "country": "UK"},
    {"ticker": "INDIGO.NS", "name": "InterGlobe Aviation (IndiGo)", "category": "Airlines", "iata": "6E", "country": "IN"},
]

# Audited FY2024 / Latest Filing Fundamental Baselines (supplemented with live market quotes)
AIRLINE_FINANCIAL_BASELINES = {
    "DL": {"ticker": "DAL", "name": "Delta Air Lines", "rev_bn": 61.6, "net_profit_bn": 3.46, "op_margin": 9.7, "registered_fleet": 992, "avg_age_yrs": 14.8, "ownership": "Public (NYSE)"},
    "UA": {"ticker": "UAL", "name": "United Airlines", "rev_bn": 57.1, "net_profit_bn": 3.15, "op_margin": 8.9, "registered_fleet": 1004, "avg_age_yrs": 15.6, "ownership": "Public (NASDAQ)"},
    "AA": {"ticker": "AAL", "name": "American Airlines", "rev_bn": 54.2, "net_profit_bn": 0.85, "op_margin": 4.8, "registered_fleet": 977, "avg_age_yrs": 13.4, "ownership": "Public (NASDAQ)"},
    "WN": {"ticker": "LUV", "name": "Southwest Airlines", "rev_bn": 27.5, "net_profit_bn": 0.47, "op_margin": 2.4, "registered_fleet": 817, "avg_age_yrs": 11.9, "ownership": "Public (NYSE)"},
    "FR": {"ticker": "RYAAY", "name": "Ryanair Group", "rev_bn": 14.5, "net_profit_bn": 2.08, "op_margin": 14.9, "registered_fleet": 608, "avg_age_yrs": 9.1, "ownership": "Public (NASDAQ)"},
    "LH": {"ticker": "LHA.DE", "name": "Lufthansa Group", "rev_bn": 40.6, "net_profit_bn": 1.49, "op_margin": 4.4, "registered_fleet": 735, "avg_age_yrs": 13.2, "ownership": "Public (XETRA)"},
    "6E": {"ticker": "INDIGO.NS", "name": "IndiGo", "rev_bn": 9.3, "net_profit_bn": 0.98, "op_margin": 11.4, "registered_fleet": 415, "avg_age_yrs": 4.4, "ownership": "Public (NSE)"},
    "BA": {"ticker": "IAG.L", "name": "British Airways (IAG)", "rev_bn": 34.7, "net_profit_bn": 2.95, "op_margin": 13.8, "registered_fleet": 601, "avg_age_yrs": 13.6, "ownership": "Public (LSE)"},
    "AF": {"ticker": "AF.PA", "name": "Air France-KLM", "rev_bn": 34.1, "net_profit_bn": 0.52, "op_margin": 5.1, "registered_fleet": 566, "avg_age_yrs": 12.8, "ownership": "Public (EPA)"},
    "TK": {"ticker": "THYAO.IS", "name": "Turkish Airlines", "rev_bn": 22.7, "net_profit_bn": 3.40, "op_margin": 11.6, "registered_fleet": 472, "avg_age_yrs": 9.4, "ownership": "Public (BIST)"},
    "EK": {"ticker": "PRIVATE", "name": "Emirates", "rev_bn": 33.0, "net_profit_bn": 4.70, "op_margin": 15.1, "registered_fleet": 261, "avg_age_yrs": 10.5, "ownership": "State-Owned"},
    "QR": {"ticker": "PRIVATE", "name": "Qatar Airways", "rev_bn": 22.2, "net_profit_bn": 1.67, "op_margin": 8.4, "registered_fleet": 254, "avg_age_yrs": 9.2, "ownership": "State-Owned"},
    "SQ": {"ticker": "C6L.SI", "name": "Singapore Airlines", "rev_bn": 14.3, "net_profit_bn": 1.98, "op_margin": 14.3, "registered_fleet": 203, "avg_age_yrs": 7.4, "ownership": "Public (SGX)"},
    "AC": {"ticker": "AC.TO", "name": "Air Canada", "rev_bn": 16.4, "net_profit_bn": 1.25, "op_margin": 5.7, "registered_fleet": 362, "avg_age_yrs": 12.6, "ownership": "Public (TSX)"},
    "CZ": {"ticker": "1055.HK", "name": "China Southern", "rev_bn": 24.1, "net_profit_bn": -0.24, "op_margin": 1.2, "registered_fleet": 917, "avg_age_yrs": 9.5, "ownership": "Public (HKEX)"},
    "MU": {"ticker": "0670.HK", "name": "China Eastern", "rev_bn": 18.8, "net_profit_bn": -0.58, "op_margin": -0.8, "registered_fleet": 804, "avg_age_yrs": 9.1, "ownership": "Public (HKEX)"},
    "CA": {"ticker": "0753.HK", "name": "Air China", "rev_bn": 23.2, "net_profit_bn": -0.04, "op_margin": 1.6, "registered_fleet": 930, "avg_age_yrs": 9.8, "ownership": "Public (HKEX)"},
    "FX": {"ticker": "FDX", "name": "FedEx Express", "rev_bn": 87.7, "net_profit_bn": 4.33, "op_margin": 6.3, "registered_fleet": 698, "avg_age_yrs": 21.4, "ownership": "Public (NYSE)"},
    "5X": {"ticker": "UPS", "name": "UPS Airlines", "rev_bn": 91.1, "net_profit_bn": 5.78, "op_margin": 9.3, "registered_fleet": 292, "avg_age_yrs": 22.1, "ownership": "Public (NYSE)"},
}

# Official OEM Order & Delivery Reference Matrix (Prepared for Phase 2 LLM Incremental Feed)
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

# Commercial Airliner SVG Silhouette for PyDeck IconLayer
_AIRLINER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <path fill="#ffffff" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
</svg>"""
AIRLINER_ICON_URL = "data:image/svg+xml;base64," + base64.b64encode(_AIRLINER_SVG.encode("utf-8")).decode("ascii")

# -----------------------------------------------------------------------------
# DARK GOOGLE-FINANCE / BLOOMBERG TERMINAL CSS & HOVER ANIMATIONS
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    :root {
        --bg-canvas: #131314;
        --bg-surface: #1B1C1F;
        --bg-elevated: #222428;
        --bg-hover: #2A2C32;
        --border-subtle: #2D3036;
        --border-bright: #3F444E;
        --text-primary: #E8EAED;
        --text-secondary: #9AA0A6;
        --text-muted: #6E7681;
        --accent-green: #81C995;
        --accent-green-bg: rgba(52, 168, 83, 0.16);
        --accent-red: #F28B82;
        --accent-red-bg: rgba(234, 67, 53, 0.16);
        --accent-blue: #8AB4F8;
        --accent-blue-bg: rgba(138, 180, 248, 0.14);
        --accent-amber: #FDD663;
        --accent-amber-bg: rgba(253, 214, 99, 0.14);
    }

    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    button[kind="header"],
    #MainMenu,
    footer {
        display: none !important;
        visibility: hidden !important;
    }

    header[data-testid="stHeader"] {
        background: rgba(19, 19, 20, 0.85);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--border-subtle);
        height: 1.8rem;
    }

    @keyframes fadeSlideUp {
        0%   { opacity: 0; transform: translateY(8px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulseDot {
        0%   { box-shadow: 0 0 0 0 rgba(129, 201, 149, 0.55); }
        70%  { box-shadow: 0 0 0 7px rgba(129, 201, 149, 0); }
        100% { box-shadow: 0 0 0 0 rgba(129, 201, 149, 0); }
    }

    .stApp {
        background-color: var(--bg-canvas);
        color: var(--text-primary);
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .block-container {
        padding: 0.9rem 1.5rem 2.5rem 1.5rem;
        max-width: 1680px;
    }

    /* Dark Widget Overrides */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    .stTextInput > div > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 999px !important;
        color: var(--text-primary) !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.85rem !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-baseweb="select"] > div {
        border-radius: 10px !important;
    }
    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--accent-blue) !important;
        box-shadow: 0 0 0 2px rgba(138, 180, 248, 0.18) !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="input"] input {
        color: var(--text-primary) !important;
    }
    ul[data-baseweb="menu"] {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-bright) !important;
    }
    li[role="option"] {
        color: var(--text-primary) !important;
        background-color: var(--bg-elevated) !important;
    }
    li[role="option"]:hover {
        background-color: var(--bg-hover) !important;
    }
    label[data-testid="stWidgetLabel"] p {
        color: var(--text-secondary) !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
    }

    /* Horizontal Pill Radio Buttons */
    div[role="radiogroup"] {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
    }
    div[role="radiogroup"] label {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 999px !important;
        padding: 0.28rem 0.85rem !important;
        margin: 0 !important;
        cursor: pointer !important;
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    div[role="radiogroup"] label:hover {
        background: var(--bg-hover) !important;
        border-color: var(--border-bright) !important;
        transform: translateY(-1px);
    }
    div[role="radiogroup"] label[data-checked="true"],
    div[role="radiogroup"] label:has(input:checked) {
        background: rgba(138, 180, 248, 0.16) !important;
        border-color: var(--accent-blue) !important;
    }
    div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    div[role="radiogroup"] label p {
        color: var(--text-primary) !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
    }

    /* Terminal Action Buttons */
    div.stButton > button,
    div.stDownloadButton > button {
        background: var(--bg-elevated);
        color: var(--text-primary);
        border: 1px solid var(--border-bright);
        border-radius: 999px;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.79rem;
        font-weight: 600;
        padding: 0.35rem 0.9rem;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover {
        background: var(--bg-hover);
        border-color: var(--accent-blue);
        color: #FFFFFF;
        transform: translateY(-1px);
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
    }

    /* Top Header */
    .term-brand {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        padding: 0.15rem 0;
    }
    .term-logo {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        background: linear-gradient(135deg, #1E3A8A, #0F5C4D);
        border: 1px solid rgba(138, 180, 248, 0.35);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 14px rgba(15, 92, 77, 0.35);
    }
    .term-title {
        font-size: 1.22rem;
        font-weight: 800;
        color: #FFFFFF;
        letter-spacing: -0.02em;
        line-height: 1.1;
    }
    .term-title span {
        font-weight: 500;
        color: var(--text-secondary);
        font-size: 0.92rem;
        margin-left: 0.25rem;
    }
    .live-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        background: var(--accent-green-bg);
        border: 1px solid rgba(129, 201, 149, 0.3);
        color: var(--accent-green);
        border-radius: 999px;
        padding: 0.3rem 0.75rem;
        font-size: 0.72rem;
        font-weight: 600;
        font-family: 'IBM Plex Mono', monospace;
    }
    .live-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--accent-green);
        animation: pulseDot 2.2s infinite;
    }

    /* Rail Containers */
    .rail-panel {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 1rem 1rem 0.85rem 1rem;
        animation: fadeSlideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .rail-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.65rem;
    }
    .rail-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--text-primary);
    }
    .rail-sub {
        font-size: 0.7rem;
        color: var(--text-secondary);
        font-family: 'IBM Plex Mono', monospace;
    }

    /* Watchlist Rows (Inspired by Google Finance Left Rail) */
    .watch-row {
        display: grid;
        grid-template-columns: 1.25fr 0.75fr 0.95fr;
        align-items: center;
        gap: 0.45rem;
        padding: 0.62rem 0.55rem;
        border-top: 1px solid var(--border-subtle);
        border-radius: 8px;
        transition: background-color 0.18s ease, transform 0.18s ease, border-color 0.18s ease;
        cursor: pointer;
    }
    .watch-row:hover {
        background: var(--bg-hover);
        transform: translateX(3px);
    }
    .watch-ticker {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.79rem;
        font-weight: 700;
        color: #FFFFFF;
    }
    .watch-name {
        font-size: 0.7rem;
        color: var(--text-secondary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 112px;
    }
    .watch-price {
        text-align: right;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem;
        font-weight: 600;
        color: var(--text-primary);
        font-variant-numeric: tabular-nums;
    }
    .watch-delta {
        display: inline-flex;
        align-items: center;
        gap: 0.2rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.71rem;
        font-weight: 600;
        float: right;
        margin-top: 0.1rem;
    }
    .up { color: var(--accent-green); }
    .down { color: var(--accent-red); }
    .flat { color: var(--text-secondary); }

    /* Highlight Banner Strips */
    .strip-banner {
        display: flex;
        flex-wrap: wrap;
        gap: 0.6rem;
        margin-bottom: 0.75rem;
    }
    .strip-pill {
        flex: 1 1 260px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        padding: 0.55rem 0.9rem;
        font-size: 0.79rem;
        transition: border-color 0.2s ease, transform 0.2s ease;
    }
    .strip-pill:hover {
        border-color: var(--border-bright);
        transform: translateY(-1px);
    }

    /* 4 Sparkline Index Cards */
    .idx-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 0.85rem 0.95rem 0.55rem 0.95rem;
        transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.22s ease, box-shadow 0.22s ease;
        animation: fadeSlideUp 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .idx-card:hover {
        transform: translateY(-3px);
        border-color: var(--accent-blue);
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.42);
    }
    .idx-name {
        font-size: 0.76rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: 0.01em;
    }
    .idx-val {
        font-size: 1.25rem;
        font-weight: 800;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
        margin-top: 0.15rem;
    }
    .idx-sub {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        margin-top: 0.18rem;
        margin-bottom: 0.35rem;
    }
    .delta-pill-up {
        background: var(--accent-green-bg);
        color: var(--accent-green);
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.71rem;
        font-weight: 700;
        padding: 0.12rem 0.42rem;
        border-radius: 6px;
    }
    .delta-pill-down {
        background: var(--accent-red-bg);
        color: var(--accent-red);
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.71rem;
        font-weight: 700;
        padding: 0.12rem 0.42rem;
        border-radius: 6px;
    }

    /* Market Summary & News Cards */
    .summary-box {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 0.9rem;
        transition: border-color 0.2s ease;
    }
    .summary-box:hover {
        border-color: var(--border-bright);
    }
    .summary-headline {
        font-size: 1.02rem;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 0.45rem;
    }
    .summary-body {
        font-size: 0.85rem;
        line-height: 1.55;
        color: #CBD5E1;
    }
    .source-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        background: var(--bg-elevated);
        border: 1px solid var(--border-subtle);
        border-radius: 999px;
        padding: 0.16rem 0.55rem;
        font-size: 0.7rem;
        color: var(--text-secondary);
        font-family: 'IBM Plex Mono', monospace;
    }

    .news-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        padding: 0.75rem 0.95rem;
        margin-bottom: 0.55rem;
        transition: all 0.2s ease;
    }
    .news-card:hover {
        background: var(--bg-elevated);
        border-color: var(--border-bright);
        transform: translateX(3px);
    }
    .news-card a {
        color: var(--text-primary);
        text-decoration: none;
        font-weight: 600;
        font-size: 0.84rem;
    }
    .news-card a:hover {
        color: var(--accent-blue);
    }
    .news-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 0.3rem;
        font-size: 0.71rem;
        color: var(--text-secondary);
    }

    /* Digital Twin / MRO Stat Cards */
    .twin-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-left: 3px solid var(--accent-blue);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.7rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .twin-card:hover {
        transform: translateY(-2px);
        border-color: var(--accent-green);
    }

    /* Right Rail Research Copilot Cards */
    .ai-brief-card {
        background: var(--bg-elevated);
        border: 1px solid var(--border-bright);
        border-radius: 12px;
        padding: 0.8rem 0.9rem;
        margin-top: 0.7rem;
        font-size: 0.8rem;
        line-height: 1.5;
        color: var(--text-primary);
        animation: fadeSlideUp 0.3s ease both;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-canvas); }
    ::-webkit-scrollbar-thumb { background: #373A40; border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent-blue); }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# HELPER UTILITIES (TAXONOMY, SPARKLINES, LIVE EQUITIES & RSS)
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


def build_svg_sparkline(values, color="#81C995", width=86, height=28, uid="sp"):
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
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.32"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{area_pts}" fill="url(#g_{uid})"/>'
        f'<polyline points="{poly_pts}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def style_dark_chart(fig, height=310):
    fig.update_layout(
        height=height,
        paper_bgcolor="#1B1C1F",
        plot_bgcolor="#16171A",
        font=dict(color="#CBD5E1", family="Plus Jakarta Sans, sans-serif", size=11.5),
        margin=dict(l=14, r=16, t=32, b=16),
        transition={"duration": 450, "easing": "cubic-in-out"},
        hoverlabel=dict(
            bgcolor="#222428",
            bordercolor="#8AB4F8",
            font=dict(color="#FFFFFF", family="Plus Jakarta Sans, sans-serif", size=12),
        ),
    )
    fig.update_xaxes(gridcolor="#26282E", zeroline=False, linecolor="#32353D", tickfont=dict(color="#9AA0A6"))
    fig.update_yaxes(gridcolor="#26282E", zeroline=False, linecolor="#32353D", tickfont=dict(color="#9AA0A6"))
    return fig


# -----------------------------------------------------------------------------
# DATA INGESTION (AIRLABS COMMERCIAL, SUPABASE HISTORY, YAHOO EQUITIES, RSS)
# -----------------------------------------------------------------------------
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

    # Flight phase tagging for Digital Twin & MRO monitoring
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
        hist_df = hist_df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return hist_df
    except Exception:
        return pd.DataFrame()


def _fetch_single_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/2.0)"}
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
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/2.0)"}
    for source_name, url in feeds:
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:5]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()[:16]
                desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()[:150]
                if not title or not link:
                    continue
                low = f"{title} {desc}".lower()
                if any(k in low for k in ["order", "deliver", "backlog", "airbus", "boeing", "embraer", "max", "a320", "a350", "787"]):
                    tag = "OEM & BACKLOG"
                elif any(k in low for k in ["mro", "maintenance", "engine", "leap", "gtf", "grounded", "aog", "check"]):
                    tag = "MRO & ENGINE"
                elif any(k in low for k in ["profit", "earnings", "lease", "lessor", "aercap", "revenue", "capacity", "fleet"]):
                    tag = "FINANCE & LEASING"
                else:
                    tag = "MARKET BRIEF"
                items.append({"source": source_name, "title": title, "link": link, "published": pub, "tag": tag})
        except Exception:
            continue
    return items[:12]


def compute_airline_growth_from_history(hist_df, live_airline_counts):
    """Computes real 24h, 30d/Month, and Max tracked fleet growth from Supabase snapshots."""
    growth_map = {}
    if hist_df.empty or "regional_breakdown" not in hist_df.columns:
        return growth_map

    now_ts = hist_df["ts"].max()
    # Extract snapshots that contain __meta_airlines
    records = []
    for _, row in hist_df.iterrows():
        rb = row.get("regional_breakdown")
        if isinstance(rb, dict) and "__meta_airlines" in rb:
            records.append((row["ts"], rb["__meta_airlines"]))

    if not records:
        return growth_map

    first_ts, first_counts = records[0]
    target_24h = now_ts - pd.Timedelta(hours=24)
    target_30d = now_ts - pd.Timedelta(days=30)

    snap_24h = min(records, key=lambda x: abs((x[0] - target_24h).total_seconds()))[1]
    snap_30d = min(records, key=lambda x: abs((x[0] - target_30d).total_seconds()))[1]

    for code, live_cnt in live_airline_counts.items():
        b24 = snap_24h.get(code)
        b30 = snap_30d.get(code)
        bmax = first_counts.get(code)
        growth_map[code] = {
            "d24": round(((live_cnt - b24) / b24) * 100, 1) if b24 and b24 > 0 else None,
            "d30": round(((live_cnt - b30) / b30) * 100, 1) if b30 and b30 > 0 else None,
            "dmax": round(((live_cnt - bmax) / bmax) * 100, 1) if bmax and bmax > 0 else None,
            "span_days": max(1, int((now_ts - first_ts).total_seconds() // 86400)),
        }
    return growth_map


# -----------------------------------------------------------------------------
# LOAD ALL LIVE & HISTORICAL DATA
# -----------------------------------------------------------------------------
airline_map = fetch_airline_map(client.api_key)
raw_df = fetch_live_commercial_fleet(client.api_key)
hist_df = fetch_supabase_history()
quotes_map = fetch_watchlist_quotes([e["ticker"] for e in WATCHLIST_ENTITIES])
news_items = fetch_aviation_news()

if "research_answer" not in st.session_state:
    st.session_state["research_answer"] = None
if "focused_entity" not in st.session_state:
    st.session_state["focused_entity"] = "ALL"

utc_now = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")

if raw_df.empty:
    st.error("Live commercial ADS-B feed returned no vectors. Verify AIRLABS_API_KEY or API rate quota.")
    st.stop()

# -----------------------------------------------------------------------------
# TOP TERMINAL HEADER BAR (BRAND + COMMAND SEARCH + LIVE STATUS)
# -----------------------------------------------------------------------------
h_left, h_mid, h_right = st.columns([1.25, 2.55, 1.05], gap="medium")

with h_left:
    st.markdown(
        """
        <div class="term-brand">
            <div class="term-logo">
                <svg width="20" height="20" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                    <path fill="#E8EAED" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
                </svg>
            </div>
            <div>
                <div class="term-title">AeroTrack <span>Terminal</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with h_mid:
    search_query = st.text_input(
        "Command Search",
        placeholder="Search airline, OEM, ticker, tail hex, or aircraft (e.g. DAL, A359, BA, 6E, AER)...",
        label_visibility="collapsed",
    )

with h_right:
    hr1, hr2 = st.columns([1.45, 0.75], gap="small")
    with hr1:
        st.markdown(f'<div class="live-badge"><span class="live-dot"></span>{utc_now}</div>', unsafe_allow_html=True)
    with hr2:
        if st.button("Sync", use_container_width=True, help="Refresh live ADS-B, equities & RSS news"):
            st.cache_data.clear()
            st.rerun()

st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3-PANE TERMINAL SHELL: LEFT WATCHLIST | CENTER WORKSPACE | RIGHT RESEARCH
# -----------------------------------------------------------------------------
col_left, col_center, col_right = st.columns([1.05, 2.75, 1.08], gap="medium")

# Pre-compute live airline counts for watchlist & screener
live_airline_counts = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts().to_dict()
growth_map = compute_airline_growth_from_history(hist_df, live_airline_counts)

# =============================================================================
# LEFT RAIL: AVIATION EQUITIES & FLEET WATCHLIST (GOOGLE FINANCE INSPIRED)
# =============================================================================
with col_left:
    st.markdown(
        """
        <div class="rail-panel">
            <div class="rail-header">
                <div class="rail-title">Watchlist</div>
                <div class="rail-sub">EQUITIES + FLEET</div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    wl_cat = st.radio(
        "Watchlist Category",
        ["All", "Airlines", "Lessors", "OEMs"],
        horizontal=True,
        label_visibility="collapsed",
        key="wl_cat_radio",
    )

    filtered_wl = [e for e in WATCHLIST_ENTITIES if wl_cat == "All" or e["category"] == wl_cat]

    rows_html = []
    for i, item in enumerate(filtered_wl):
        tkr = item["ticker"]
        q = quotes_map.get(tkr)
        if q and q.get("price") is not None:
            curr_sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(q["currency"], "")
            price_str = f"{curr_sym}{q['price']:,.2f}"
            pct = q["pct_change"]
            cls = "up" if pct > 0 else ("down" if pct < 0 else "flat")
            arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "•")
            delta_str = f"{pct:+.2f}% {arrow}"
            sp_col = "#81C995" if pct >= 0 else "#F28B82"
            svg = build_svg_sparkline(q["spark"], color=sp_col, width=70, height=24, uid=f"wl_{i}")
        else:
            # Fallback to live active fleet if equity feed throttled
            fleet_cnt = live_airline_counts.get(item["iata"], 0) if item["iata"] else 0
            price_str = f"{fleet_cnt} AC" if fleet_cnt else item["country"]
            cls, delta_str = "flat", item["category"]
            svg = build_svg_sparkline([1, 1.02, 1.01, 1.03], color="#8AB4F8", width=70, height=24, uid=f"wl_{i}")

        rows_html.append(
            f'<div class="watch-row">'
            f'  <div><div class="watch-ticker">{html.escape(tkr)}</div><div class="watch-name">{html.escape(item["name"])}</div></div>'
            f'  <div style="display:flex;justify-content:center;">{svg}</div>'
            f'  <div><div class="watch-price">{price_str}</div><div class="watch-delta {cls}">{delta_str}</div></div>'
            f'</div>'
        )

    st.markdown("".join(rows_html) + "</div>", unsafe_allow_html=True)

    # Interactive Focus Selector synced to Watchlist
    focus_options = ["ALL (Global Universe)"] + [f"{e['ticker']} — {e['name']}" for e in filtered_wl]
    selected_focus = st.selectbox("Inspect Entity in Terminal", focus_options, label_visibility="visible")
    if selected_focus != "ALL (Global Universe)":
        chosen_tkr = selected_focus.split(" — ")[0].strip()
        match = next((e for e in WATCHLIST_ENTITIES if e["ticker"] == chosen_tkr), None)
        st.session_state["focused_entity"] = match
    else:
        st.session_state["focused_entity"] = None


# =============================================================================
# CENTER WORKSPACE: PILLS, 4 SPARKLINE INDEX CARDS, TERMINAL DESKS
# =============================================================================
with col_center:
    # Dynamic Highlight Strip (like Anthropic / Top Mover banners in screenshot)
    top_al_code = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].mode()[0]
    top_al_cnt = live_airline_counts.get(top_al_code, 0)
    top_al_name = airline_map.get(top_al_code, top_al_code)
    nextgen_share = (raw_df["Generation"] == "Next-Gen").mean() * 100

    best_mover = None
    if quotes_map:
        best_tkr = max(quotes_map.keys(), key=lambda k: quotes_map[k]["pct_change"])
        best_mover = (best_tkr, quotes_map[best_tkr])

    mover_txt = (
        f"<strong>{best_mover[0]}</strong> &bull; {best_mover[1]['price']} "
        f"<span style='color:{'#81C995' if best_mover[1]['pct_change']>=0 else '#F28B82'};font-weight:700;'>"
        f"{best_mover[1]['pct_change']:+.2f}%</span>"
        if best_mover else "Equities Live"
    )

    st.markdown(
        f"""
        <div class="strip-banner">
            <div class="strip-pill">
                <span><span style="color:#8AB4F8;font-weight:700;">FLEET LEADER</span> &nbsp; {html.escape(top_al_name)} ({top_al_code}) · {top_al_cnt:,} airborne</span>
                <span style="color:#81C995;font-family:'IBM Plex Mono',monospace;font-weight:600;">{nextgen_share:.1f}% Next-Gen</span>
            </div>
            <div class="strip-pill">
                <span><span style="color:#FDD663;font-weight:700;">TOP EQUITY MOVER</span> &nbsp; {mover_txt}</span>
                <span style="color:#9AA0A6;font-size:0.72rem;">1D Session</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Region & Asset Class Filter Pills (like US | Europe | India | ... in screenshot)
    market_scope = st.radio(
        "Market Scope",
        ["Global", "NORTH AMERICA", "EUROPE", "EAST ASIA & APAC", "MIDDLE EAST & S. ASIA", "LATIN AMERICA", "Widebody", "Narrowbody", "Cargo"],
        horizontal=True,
        label_visibility="collapsed",
        key="market_scope_pills",
    )

    # Apply scope + search filter + watchlist entity focus
    df = raw_df.copy()
    if market_scope in ["NORTH AMERICA", "EUROPE", "EAST ASIA & APAC", "MIDDLE EAST & S. ASIA", "LATIN AMERICA"]:
        df = df[df["sector"] == market_scope]
    elif market_scope == "Widebody":
        df = df[df["Body Type"] == "Widebody"]
    elif market_scope == "Narrowbody":
        df = df[df["Body Type"] == "Narrowbody"]
    elif market_scope == "Cargo":
        df = df[df["is_cargo"] == True]

    focused = st.session_state.get("focused_entity")
    if isinstance(focused, dict):
        if focused.get("iata"):
            df = df[df["airline_code"] == focused["iata"]]
        elif focused["ticker"] == "AIR.PA":
            df = df[df["Manufacturer"] == "Airbus"]
        elif focused["ticker"] == "BA":
            df = df[df["Manufacturer"] == "Boeing"]
        elif focused["ticker"] == "ERJ":
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

    # Build sparkline series from Supabase history for the 4 top index cards
    total_series = hist_df["total_flights"].tail(24).tolist() if not hist_df.empty else [len(df)]
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

    curr_total = len(df)
    curr_nb = int((df["Body Type"] == "Narrowbody").sum())
    curr_wb = int((df["Body Type"] == "Widebody").sum())
    curr_cg = int(df["is_cargo"].sum())

    def _calc_delta(series, curr_val):
        valid = [v for v in series if v and v > 0]
        if len(valid) >= 2:
            avg = np.mean(valid[:-1]) if len(valid) > 1 else valid[0]
            return ((curr_val - avg) / avg) * 100.0 if avg > 0 else 0.0
        return 0.0

    d_tot = _calc_delta(total_series, len(raw_df))
    d_nb = _calc_delta(nb_series, int((raw_df["Body Type"] == "Narrowbody").sum()))
    d_wb = _calc_delta(wb_series, int((raw_df["Body Type"] == "Widebody").sum()))
    d_cg = _calc_delta(cg_series, int(raw_df["is_cargo"].sum()))

    idx_specs = [
        ("ACTIVE FLEET INDEX", f"{curr_total:,}", d_tot, total_series or [curr_total, curr_total], "idx1"),
        ("NARROWBODY INDEX", f"{curr_nb:,}", d_nb, nb_series or [curr_nb, curr_nb], "idx2"),
        ("WIDEBODY INDEX", f"{curr_wb:,}", d_wb, wb_series or [curr_wb, curr_wb], "idx3"),
        ("FREIGHTER INDEX", f"{curr_cg:,}", d_cg, cg_series or [curr_cg, curr_cg], "idx4"),
    ]

    ic1, ic2, ic3, ic4 = st.columns(4, gap="small")
    for col, (title, val, dlt, series, uid) in zip([ic1, ic2, ic3, ic4], idx_specs):
        is_up = dlt >= 0
        pill_cls = "delta-pill-up" if is_up else "delta-pill-down"
        sp_color = "#81C995" if is_up else "#F28B82"
        arrow = "↑" if is_up else "↓"
        spark_svg = build_svg_sparkline(series, color=sp_color, width=185, height=34, uid=uid)
        with col:
            st.markdown(
                f"""
                <div class="idx-card">
                    <div class="idx-name">{title}</div>
                    <div class="idx-val">{val}</div>
                    <div class="idx-sub">
                        <span class="{pill_cls}">{dlt:+.1f}% {arrow}</span>
                        <span style="font-size:0.7rem;color:#9AA0A6;">vs 24h avg</span>
                    </div>
                    <div style="overflow:hidden;">{spark_svg}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:0.55rem;'></div>", unsafe_allow_html=True)

    # Center Terminal Desk Switcher
    active_desk = st.radio(
        "Terminal Desk",
        ["Market Summary & Live Map", "Airline Screener (Growth & Profit)", "Manufacturer (OEM) Corner", "Digital Twin & MRO Radar"],
        horizontal=True,
        label_visibility="collapsed",
        key="desk_switcher",
    )

    # =========================================================================
    # DESK 1: MARKET SUMMARY + NEWS WIRE + 3D COMMERCIAL FLEET MAP
    # =========================================================================
    if active_desk == "Market Summary & Live Map":
        busiest_reg = raw_df["sector"].mode()[0] if not raw_df.empty else "NORTH AMERICA"
        busiest_apt = raw_df[~raw_df["dep_iata"].isin(["UNKN", ""])]["dep_iata"].mode()[0] if not raw_df[~raw_df["dep_iata"].isin(["UNKN", ""])].empty else "ATL"
        active_carriers_cnt = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].nunique()

        st.markdown(
            f"""
            <div class="summary-box">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.45rem;">
                    <div style="font-size:0.74rem;font-weight:700;color:#8AB4F8;letter-spacing:0.05em;">AVIATION MARKET SUMMARY</div>
                    <div class="source-chip">{len(news_items)} live RSS feeds · {len(quotes_map)} tickers</div>
                </div>
                <div class="summary-headline">
                    {len(df):,} commercial airframes active across {active_carriers_cnt:,} operators ({market_scope} view)
                </div>
                <div class="summary-body">
                    Global capacity is led by <strong>{busiest_reg}</strong> with <strong>{busiest_apt} ({AIRPORT_MAP.get(busiest_apt, 'Intl Hub')})</strong>
                    recording the highest departure concentration. Next-generation fuel-efficient airframes account for
                    <strong>{(df['Generation']=='Next-Gen').mean()*100 if len(df)>0 else 0:.1f}%</strong> of tracked lift, while dedicated
                    cargo operations represent <strong>{(df['is_cargo'].mean()*100 if len(df)>0 else 0):.1f}%</strong> of active commercial sectors.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        m_col, n_col = st.columns([1.45, 1.0], gap="medium")

        with m_col:
            if df.empty:
                st.info("No active commercial aircraft match this filter.")
            else:
                def _body_color(row):
                    if row["is_cargo"]:
                        return [253, 214, 99, 235]       # Amber Freighter
                    if row["Body Type"] == "Widebody":
                        return [138, 180, 248, 235]      # Terminal Blue Widebody
                    if row["Body Type"] == "Narrowbody":
                        return [129, 201, 149, 225]      # Emerald Narrowbody
                    return [154, 160, 166, 200]          # Silver Regional/Other

                map_df = df.copy()
                map_df["color"] = map_df.apply(_body_color, axis=1)
                map_df["angle"] = (360.0 - map_df["heading"].fillna(0.0)) % 360.0
                map_df["icon_size"] = np.where(map_df["Body Type"] == "Widebody", 20, 15)
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
                    size_max_pixels=22,
                    get_angle="angle",
                    get_color="color",
                    billboard=False,
                    pickable=True,
                )

                st.pydeck_chart(
                    pdk.Deck(
                        layers=[layer],
                        initial_view_state=pdk.ViewState(latitude=26, longitude=12, zoom=1.35, pitch=34, bearing=0),
                        tooltip={
                            "html": """
                                <div style="font-family:'Plus Jakarta Sans',sans-serif;padding:5px 4px;min-width:190px;">
                                    <div style="font-weight:700;color:#FFFFFF;font-size:13px;border-bottom:1px solid #323438;padding-bottom:3px;margin-bottom:4px;">
                                        {callsign} <span style="color:#9AA0A6;font-family:'IBM Plex Mono',monospace;font-size:11px;">({icao24})</span>
                                    </div>
                                    <div style="color:#CBD5E1;font-size:12px;">{aircraft_type} · {Family} ({Generation})</div>
                                    <div style="color:#81C995;font-family:'IBM Plex Mono',monospace;font-size:11px;margin-top:3px;">
                                        ALT {alt_fmt} ft | SPD {spd_fmt} km/h
                                    </div>
                                </div>
                            """,
                            "style": {"backgroundColor": "#1B1C1F", "border": "1px solid #3F444E", "borderRadius": "10px"},
                        },
                        map_style="mapbox://styles/mapbox/dark-v11",
                    ),
                    use_container_width=True,
                )
                st.caption("Map Legend:  Green = Narrowbody  |  Blue = Widebody  |  Amber = Freighter / Cargo  |  Silver = Regional")

        with n_col:
            st.markdown("<div style='font-size:0.86rem;font-weight:700;color:#E8EAED;margin-bottom:0.45rem;'>Live Aviation Finance & MRO Wire</div>", unsafe_allow_html=True)
            if news_items:
                for n in news_items[:6]:
                    tag_col = "#8AB4F8" if "OEM" in n["tag"] else ("#FDD663" if "MRO" in n["tag"] else "#81C995")
                    st.markdown(
                        f"""
                        <div class="news-card">
                            <a href="{html.escape(n['link'])}" target="_blank">{html.escape(n['title'])}</a>
                            <div class="news-meta">
                                <span>{html.escape(n['source'])} · {html.escape(n['published'])}</span>
                                <span style="color:{tag_col};font-family:'IBM Plex Mono',monospace;font-weight:600;">{n['tag']}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("RSS wire temporarily unavailable.")

        # 24H Fleet Volume Trend Chart
        if not hist_df.empty:
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Scatter(
                x=hist_df["ts"].tail(48),
                y=hist_df["total_flights"].tail(48),
                mode="lines",
                name="Active Commercial Fleet",
                line=dict(color="#81C995", width=2.4, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(129, 201, 149, 0.12)",
            ))
            style_dark_chart(fig_hist, height=225)
            fig_hist.update_layout(title=dict(text="Tracked Global Commercial Fleet Trajectory (Supabase History)", font=dict(size=12.5)))
            st.plotly_chart(fig_hist, use_container_width=True)

    # =========================================================================
    # DESK 2: AIRLINE SCREENER (FLEET GROWTH 24H / 30D / MAX + NET PROFITS)
    # =========================================================================
    elif active_desk == "Airline Screener (Growth & Profit)":
        st.markdown(
            """
            <div class="summary-box" style="padding:0.8rem 1rem;">
                <div class="summary-headline" style="font-size:0.95rem;margin-bottom:0.2rem;">
                    Airline Fleet Growth & Financial Performance Screener
                </div>
                <div class="summary-body" style="font-size:0.78rem;">
                    Combines real-time airborne lift & Next-Gen mix with Supabase historical growth (24h / 30D / Max tracked),
                    live equity prices, and audited net profit & operating margin baselines.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        screener_rows = []
        all_codes = sorted(
            set(list(AIRLINE_FINANCIAL_BASELINES.keys()) + list(raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts().head(25).index)),
            key=lambda c: live_airline_counts.get(c, 0),
            reverse=True,
        )

        for code in all_codes:
            sub = raw_df[raw_df["airline_code"] == code]
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
                "Avg Age (Yrs)": base.get("avg_age_yrs"),
            })

        scr_df = pd.DataFrame(screener_rows)
        st.dataframe(
            scr_df,
            use_container_width=True,
            hide_index=True,
            height=380,
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

        c_a, c_b = st.columns(2, gap="medium")
        with c_a:
            fin_plot_df = scr_df.dropna(subset=["Net Profit ($B)", "Revenue ($B)"]).head(12)
            fig_prof = px.bar(
                fin_plot_df,
                x="Airline",
                y="Net Profit ($B)",
                color="Op Margin %",
                color_continuous_scale=["#F28B82", "#FDD663", "#81C995"],
                title="Carrier Net Profit ($B) vs. Operating Margin (%)",
            )
            style_dark_chart(fig_prof, height=290)
            fig_prof.update_layout(xaxis_title="", xaxis_tickangle=-25)
            st.plotly_chart(fig_prof, use_container_width=True)

        with c_b:
            top_live = scr_df[scr_df["Live Airborne"] > 0].head(12)
            fig_ng = px.scatter(
                top_live,
                x="Live Airborne",
                y="Next-Gen %",
                size="Live Airborne",
                color="Op Margin %" if top_live["Op Margin %"].notna().any() else None,
                hover_name="Airline",
                color_continuous_scale=["#F28B82", "#8AB4F8", "#81C995"],
                title="Live Utilization vs. Fleet Modernization (Next-Gen %)",
            )
            style_dark_chart(fig_ng, height=290)
            st.plotly_chart(fig_ng, use_container_width=True)

    # =========================================================================
    # DESK 3: MANUFACTURER (OEM) CORNER (BACKLOG, SLOTS, MARKET SHARE)
    # =========================================================================
    elif active_desk == "Manufacturer (OEM) Corner":
        oem_df = pd.DataFrame(OEM_BACKLOG_REFERENCE)
        oem_df["Backlog_Years"] = (oem_df["Backlog"] / oem_df["Annual_Delivery_Rate"]).round(1)
        oem_df["Backlog_Value_Bn"] = ((oem_df["Backlog"] * oem_df["Avg_List_Price_M"]) / 1000.0).round(1)

        # Merge live airborne counts by OEM
        live_oem_counts = raw_df[raw_df["Manufacturer"] != "Other"]["Manufacturer"].value_counts().to_dict()

        o1, o2, o3, o4 = st.columns(4, gap="small")
        airbus_bl = int(oem_df[oem_df["OEM"] == "Airbus"]["Backlog"].sum())
        boeing_bl = int(oem_df[oem_df["OEM"] == "Boeing"]["Backlog"].sum())
        embraer_bl = int(oem_df[oem_df["OEM"] == "Embraer"]["Backlog"].sum())
        total_bl_val = oem_df["Backlog_Value_Bn"].sum()

        for col, (lbl, big, sub_txt, clr) in zip(
            [o1, o2, o3, o4],
            [
                ("AIRBUS BACKLOG", f"{airbus_bl:,}", f"{live_oem_counts.get('Airbus', 0):,} live airborne", "#8AB4F8"),
                ("BOEING BACKLOG", f"{boeing_bl:,}", f"{live_oem_counts.get('Boeing', 0):,} live airborne", "#81C995"),
                ("EMBRAER BACKLOG", f"{embraer_bl:,}", f"{live_oem_counts.get('Embraer', 0):,} live airborne", "#FDD663"),
                ("GROSS OEM BOOK VALUE", f"${total_bl_val:,.0f}B", "List-price implied backlog", "#E8EAED"),
            ],
        ):
            with col:
                st.markdown(
                    f"""
                    <div class="idx-card" style="padding-bottom:0.85rem;">
                        <div class="idx-name">{lbl}</div>
                        <div class="idx-val" style="color:{clr};">{big}</div>
                        <div style="font-size:0.72rem;color:#9AA0A6;margin-top:0.2rem;">{sub_txt}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

        oc1, oc2 = st.columns([1.35, 1.0], gap="medium")
        with oc1:
            fig_bl = px.bar(
                oem_df.sort_values("Backlog", ascending=True),
                x="Backlog",
                y="Program",
                color="OEM",
                orientation="h",
                text="Backlog_Years",
                color_discrete_map={"Airbus": "#8AB4F8", "Boeing": "#81C995", "Embraer": "#FDD663", "COMAC": "#F28B82", "ATR": "#9AA0A6"},
                title="Program Order Backlog & Implied Production Years (Text = Yrs of Backlog)",
            )
            fig_bl.update_traces(texttemplate="%{text}y", textposition="outside")
            style_dark_chart(fig_bl, height=350)
            fig_bl.update_layout(yaxis_title="", xaxis_title="Firm Unfilled Orders (Units)")
            st.plotly_chart(fig_bl, use_container_width=True)

        with oc2:
            # In-Service Live Share vs Backlog Share
            in_svc_share = pd.DataFrame([
                {"OEM": k, "Live Airborne": v}
                for k, v in live_oem_counts.items()
                if k in ["Airbus", "Boeing", "Embraer", "ATR", "COMAC"]
            ])
            if not in_svc_share.empty:
                fig_share = px.pie(
                    in_svc_share,
                    names="OEM",
                    values="Live Airborne",
                    hole=0.6,
                    color="OEM",
                    color_discrete_map={"Airbus": "#8AB4F8", "Boeing": "#81C995", "Embraer": "#FDD663", "COMAC": "#F28B82", "ATR": "#9AA0A6"},
                    title="Live In-Service Market Share (ADS-B)",
                )
                fig_share.update_traces(textinfo="label+percent", marker=dict(line=dict(color="#131314", width=2)))
                style_dark_chart(fig_share, height=350)
                fig_share.update_layout(showlegend=False)
                st.plotly_chart(fig_share, use_container_width=True)

        st.markdown("<div style='font-size:0.86rem;font-weight:700;color:#E8EAED;margin:0.35rem 0;'>OEM Delivery Slot Pipeline & Production Run-Rate</div>", unsafe_allow_html=True)
        st.dataframe(
            oem_df[["OEM", "Program", "Segment", "Backlog", "Annual_Delivery_Rate", "Backlog_Years", "Backlog_Value_Bn", "Key_Slots"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Backlog": st.column_config.NumberColumn("Firm Backlog", format="%d"),
                "Annual_Delivery_Rate": st.column_config.NumberColumn("Annual Deliveries", format="%d / yr"),
                "Backlog_Years": st.column_config.NumberColumn("Years of Backlog", format="%.1f yrs"),
                "Backlog_Value_Bn": st.column_config.NumberColumn("Implied Value", format="$%.1fB"),
                "Key_Slots": "Upcoming Slot Holders",
            },
        )
        st.caption("Baseline reference data ready for automated incremental order/delivery updates via Phase 2 LLM Press-Release Extractor.")

    # =========================================================================
    # DESK 4: REAL-TIME DIGITAL TWIN & MRO MAINTENANCE RADAR
    # =========================================================================
    else:
        st.markdown(
            """
            <div class="summary-box" style="padding:0.8rem 1rem;">
                <div class="summary-headline" style="font-size:0.95rem;margin-bottom:0.2rem;">
                    Real-Time Airframe Digital Twin & MRO Maintenance Radar
                </div>
                <div class="summary-body" style="font-size:0.78rem;">
                    Inspect individual live tails, monitor flight-phase stress cycles, estimate Next-Gen engine MRO exposure
                    (LEAP / GTF vs. legacy CFM56 / V2500), and detect aircraft approaching major global MRO & storage hubs.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Tail Digital Twin Selector
        sample_tails = df.sort_values("baro_altitude", ascending=False).head(80)
        tail_labels = [
            f"{r['callsign']} | {r['icao24']} | {r['aircraft_type']} ({r['airline_code']})"
            for _, r in sample_tails.iterrows()
        ]

        if tail_labels:
            chosen_tail_lbl = st.selectbox("Select Live Tail for Digital Twin Inspection", tail_labels)
            chosen_hex = chosen_tail_lbl.split("|")[1].strip()
            tail_row = df[df["icao24"] == chosen_hex].iloc[0]

            # Nearest MRO hub calculation
            hub_dists = [
                (h["hub"], h["name"], h["specialty"], float(haversine_km(tail_row["latitude"], tail_row["longitude"], h["lat"], h["lon"])))
                for h in MRO_HUBS
            ]
            nearest_hub = min(hub_dists, key=lambda x: x[3])

            al_info = AIRLINE_FINANCIAL_BASELINES.get(tail_row["airline_code"], {})
            est_fleet_age = al_info.get("avg_age_yrs", 4.5 if tail_row["Generation"] == "Next-Gen" else 14.2)
            # Heuristic MRO cycle window estimate based on generation & fleet age
            a_check_prog = int((hash(chosen_hex) % 75) + 18)
            c_check_prog = int(((est_fleet_age % 2.0) / 2.0) * 100)
            d_check_prog = int(min(100, (est_fleet_age / 8.0) * 100))

            dt1, dt2, dt3 = st.columns(3, gap="medium")
            with dt1:
                st.markdown(
                    f"""
                    <div class="twin-card">
                        <div class="rail-sub">AIRFRAME IDENTITY</div>
                        <div style="font-size:1.1rem;font-weight:800;color:#FFFFFF;margin:0.2rem 0;">{tail_row['callsign']} · {tail_row['icao24']}</div>
                        <div style="font-size:0.78rem;color:#CBD5E1;">
                            Type: <strong>{tail_row['aircraft_type']}</strong> ({tail_row['Family']})<br/>
                            OEM: <strong>{tail_row['Manufacturer']}</strong> · {tail_row['Generation']}<br/>
                            Operator: <strong>{airline_map.get(tail_row['airline_code'], tail_row['airline_code'])}</strong>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with dt2:
                st.markdown(
                    f"""
                    <div class="twin-card" style="border-left-color:#81C995;">
                        <div class="rail-sub">LIVE KINEMATIC STATE</div>
                        <div style="font-size:1.1rem;font-weight:800;color:#81C995;margin:0.2rem 0;">{tail_row['flight_phase'].upper()}</div>
                        <div style="font-size:0.78rem;color:#CBD5E1;font-family:'IBM Plex Mono',monospace;">
                            ALT: {tail_row['baro_altitude']:,.0f} ft<br/>
                            SPD: {tail_row['velocity']:,.0f} km/h | HDG: {tail_row['heading']:.0f}°<br/>
                            SECTOR: {tail_row['sector']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with dt3:
                st.markdown(
                    f"""
                    <div class="twin-card" style="border-left-color:#FDD663;">
                        <div class="rail-sub">MRO CHECK & HUB PROXIMITY</div>
                        <div style="font-size:1.0rem;font-weight:800;color:#FDD663;margin:0.2rem 0;">Nearest: {nearest_hub[0]} ({nearest_hub[3]:,.0f} km)</div>
                        <div style="font-size:0.76rem;color:#CBD5E1;">
                            {nearest_hub[1]}<br/>
                            A-Check Interval: <strong>{a_check_prog}%</strong> · C-Check: <strong>{c_check_prog}%</strong><br/>
                            Est. Operator Fleet Age: <strong>{est_fleet_age:.1f} yrs</strong>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Check Progress Bars
            p1, p2, p3 = st.columns(3, gap="small")
            p1.progress(a_check_prog / 100.0, text=f"A-Check Cycle (~600 FH): {a_check_prog}%")
            p2.progress(c_check_prog / 100.0, text=f"C-Check Window (~24 mo): {c_check_prog}%")
            p3.progress(d_check_prog / 100.0, text=f"Heavy D-Check Horizon (~8 yr): {d_check_prog}%")

        # MRO Hub Inbound / Proximity Traffic
        mro_rows = []
        for hub in MRO_HUBS:
            dists = haversine_km(df["latitude"].values, df["longitude"].values, hub["lat"], hub["lon"])
            nearby = df[(dists <= 120.0) & (df["baro_altitude"] < 14000)]
            mro_rows.append({
                "Hub": hub["hub"],
                "MRO Facility": hub["name"],
                "Specialty": hub["specialty"],
                "Low-Alt Movements (<120km)": int(len(nearby)),
                "Next-Gen Share": f"{(nearby['Generation']=='Next-Gen').mean()*100:.0f}%" if len(nearby) > 0 else "0%",
            })

        mc1, mc2 = st.columns([1.25, 1.0], gap="medium")
        with mc1:
            st.markdown("<div style='font-size:0.84rem;font-weight:700;color:#E8EAED;margin:0.4rem 0;'>Global MRO & Storage Hub Activity Monitor</div>", unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(mro_rows).sort_values("Low-Alt Movements (<120km)", ascending=False), use_container_width=True, hide_index=True, height=270)
        with mc2:
            gen_oem = (
                df[df["Manufacturer"] != "Other"]
                .groupby(["Manufacturer", "Generation"])
                .size()
                .reset_index(name="Count")
            )
            if not gen_oem.empty:
                fig_mro = px.bar(
                    gen_oem,
                    x="Manufacturer",
                    y="Count",
                    color="Generation",
                    barmode="stack",
                    color_discrete_map={"Next-Gen": "#81C995", "Legacy": "#4B5563"},
                    title="MRO Engine Base: Next-Gen vs. Legacy Fleet",
                )
                style_dark_chart(fig_mro, height=295)
                fig_mro.update_layout(xaxis_title="", legend=dict(orientation="h", y=1.08, x=0, title=None))
                st.plotly_chart(fig_mro, use_container_width=True)


# =============================================================================
# RIGHT RAIL: "AEROTRACK RESEARCH" COPILOT (READY FOR PHASE 2 LLM)
# =============================================================================
with col_right:
    st.markdown(
        """
        <div class="rail-panel">
            <div class="rail-header">
                <div class="rail-title">Research</div>
                <div class="rail-sub" style="color:#8AB4F8;">PHASE 2 LLM READY</div>
            </div>
            <div style="font-size:0.95rem;font-weight:700;color:#E8EAED;margin-bottom:0.25rem;">
                Hi Satvik, inspect aviation markets
            </div>
            <div style="font-size:0.75rem;color:#9AA0A6;margin-bottom:0.75rem;">
                Instant deterministic briefings over live ADS-B, equities &amp; OEM backlogs. Natural-language LLM synthesis connects in Phase 2.
            </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("What's moving aviation markets today?", use_container_width=True, key="q_movers"):
        top_q = max(quotes_map.items(), key=lambda x: x[1]["pct_change"]) if quotes_map else None
        bot_q = min(quotes_map.items(), key=lambda x: x[1]["pct_change"]) if quotes_map else None
        lead_carrier = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].mode()[0]
        top_txt = f"{top_q[0]} ({top_q[1]['pct_change']:+.2f}%)" if top_q else "N/A"
        bot_txt = f"{bot_q[0]} ({bot_q[1]['pct_change']:+.2f}%)" if bot_q else "N/A"
        st.session_state["research_answer"] = (
            f"<strong>Live Market Pulse ({market_scope})</strong><br/>"
            f"&bull; <strong>Airborne Capacity:</strong> {len(df):,} active airframes ({(df['Generation']=='Next-Gen').mean()*100:.1f}% Next-Gen).<br/>"
            f"&bull; <strong>Top Operator:</strong> {airline_map.get(lead_carrier, lead_carrier)} ({lead_carrier}) with {live_airline_counts.get(lead_carrier, 0)} tails.<br/>"
            f"&bull; <strong>Equity Leaders:</strong> Top gainer <strong>{top_txt}</strong> · Lagging <strong>{bot_txt}</strong>."
        )

    if st.button("Compare Airbus vs Boeing backlog & lift", use_container_width=True, key="q_oem"):
        ab_live = int((raw_df["Manufacturer"] == "Airbus").sum())
        bo_live = int((raw_df["Manufacturer"] == "Boeing").sum())
        st.session_state["research_answer"] = (
            f"<strong>OEM Duopoly Snapshot</strong><br/>"
            f"&bull; <strong>Airbus:</strong> {ab_live:,} airborne today · 8,645 firm backlog (~11.3 yrs at current delivery pace).<br/>"
            f"&bull; <strong>Boeing:</strong> {bo_live:,} airborne today · 6,189 firm backlog (~17.8 yrs implied by current rate).<br/>"
            f"&bull; <strong>Spread:</strong> Airbus currently leads live commercial airborne share by {abs(ab_live - bo_live):,} tails."
        )

    if st.button("Analyse my watchlist & MRO exposure", use_container_width=True, key="q_wl"):
        ng_nb = raw_df[(raw_df["Body Type"] == "Narrowbody") & (raw_df["Generation"] == "Next-Gen")]
        st.session_state["research_answer"] = (
            f"<strong>Watchlist & MRO Exposure Brief</strong><br/>"
            f"&bull; <strong>Tracked Equities:</strong> {len(quotes_map)} aviation tickers synced live.<br/>"
            f"&bull; <strong>Next-Gen Narrowbody Fleet:</strong> {len(ng_nb):,} active aircraft (A320neo / 737 MAX / A220)—primary driver of LEAP &amp; PW1100G MRO shop visits.<br/>"
            f"&bull; <strong>Cargo Lift:</strong> {int(raw_df['is_cargo'].sum()):,} active freighter movements supporting elevated widebody residual values."
        )

    if st.session_state.get("research_answer"):
        st.markdown(f'<div class="ai-brief-card">{st.session_state["research_answer"]}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:0.65rem;'></div>", unsafe_allow_html=True)
    st.text_input(
        "Ask anything",
        placeholder="LLM Research Copilot (Connecting in Phase 2)...",
        disabled=True,
        label_visibility="collapsed",
        key="llm_preview_input",
    )
    st.markdown("</div>", unsafe_allow_html=True)
