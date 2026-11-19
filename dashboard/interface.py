import sys
import os
import base64
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_ingestion.client import OpenSkyClient
from supabase import create_client

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION (NO SIDEBAR)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AeroTrack // Aviation Asset & Fleet Risk Intelligence",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------------------------------------------------------
# SUPABASE INITIALIZATION
# -----------------------------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

AIRPORT_MAP = {
    "ATL": "Atlanta", "DFW": "Dallas", "DEN": "Denver", "ORD": "Chicago", "LAX": "Los Angeles",
    "JFK": "New York", "LHR": "London", "HND": "Tokyo", "CDG": "Paris", "DXB": "Dubai",
    "DEL": "New Delhi", "BOM": "Mumbai", "FRA": "Frankfurt", "AMS": "Amsterdam", "MAD": "Madrid",
    "SIN": "Singapore", "HKG": "Hong Kong", "SYD": "Sydney", "YYZ": "Toronto", "IST": "Istanbul"
}

# -----------------------------------------------------------------------------
# COMMERCIAL AIRLINER SILHOUETTE ICON (BASE64 SVG FOR PYDECK ICONLAYER)
# -----------------------------------------------------------------------------
_AIRLINER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <path fill="#ffffff" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
</svg>"""
AIRLINER_ICON_URL = "data:image/svg+xml;base64," + base64.b64encode(_AIRLINER_SVG.encode("utf-8")).decode("ascii")

# -----------------------------------------------------------------------------
# EXECUTIVE CORPORATE STYLING (AVIATION FINANCE & LEASING GRADE)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    :root {
        --canvas-bg: #F5F6F8;
        --surface-white: #FFFFFF;
        --surface-tint: #F9FAFB;
        --border-light: #E4E7EC;
        --border-med: #D0D5DD;
        --ink-primary: #101828;
        --ink-secondary: #475467;
        --ink-muted: #667085;
        --corp-emerald: #0F5C4D;
        --corp-emerald-dark: #0A4237;
        --corp-emerald-soft: #ECFDF5;
        --corp-bronze: #B45309;
        --corp-bronze-soft: #FEF3C7;
        --corp-crimson: #B91C1C;
        --corp-crimson-soft: #FEF2F2;
    }

    /* Hide Sidebar & Default Streamlit Chrome */
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    button[kind="header"],
    #MainMenu,
    footer {
        display: none !important;
        visibility: hidden !important;
    }

    header[data-testid="stHeader"] {
        background: rgba(245, 246, 248, 0.85);
        backdrop-filter: blur(8px);
        border-bottom: 1px solid var(--border-light);
        height: 2rem;
    }

    /* Corporate Micro-Animations */
    @keyframes fadeInUp {
        0%   { opacity: 0; transform: translateY(10px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    @keyframes subtleSweep {
        0%   { transform: translateX(-100%); }
        100% { transform: translateX(350%); }
    }

    @keyframes livePulse {
        0%   { box-shadow: 0 0 0 0 rgba(15, 92, 77, 0.45); }
        70%  { box-shadow: 0 0 0 7px rgba(15, 92, 77, 0); }
        100% { box-shadow: 0 0 0 0 rgba(15, 92, 77, 0); }
    }

    @keyframes fillExpand {
        0%   { transform: scaleX(0); }
        100% { transform: scaleX(1); }
    }

    /* App Canvas */
    .stApp {
        background-color: var(--canvas-bg);
        color: var(--ink-primary);
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .block-container {
        padding: 1.2rem 2.4rem 3rem 2.4rem;
        max-width: 1480px;
    }

    /* Force Light Executive Styling on All Streamlit Inputs Regardless of Browser Theme */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        background-color: var(--surface-white) !important;
        border: 1px solid var(--border-med) !important;
        border-radius: 8px !important;
        color: var(--ink-primary) !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.86rem !important;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04) !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="input"] input {
        color: var(--ink-primary) !important;
    }
    ul[data-baseweb="menu"] {
        background-color: var(--surface-white) !important;
        border: 1px solid var(--border-light) !important;
    }
    li[role="option"] {
        color: var(--ink-primary) !important;
        background-color: var(--surface-white) !important;
    }
    li[role="option"]:hover {
        background-color: var(--surface-tint) !important;
    }
    label[data-testid="stWidgetLabel"] p {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: var(--ink-secondary) !important;
    }
    div[data-testid="stSlider"] > div {
        color: var(--ink-primary) !important;
    }

    /* Executive Action Buttons */
    div.stButton > button,
    div.stDownloadButton > button {
        background-color: var(--corp-emerald);
        color: #FFFFFF;
        border: 1px solid var(--corp-emerald);
        border-radius: 8px;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        height: 40px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.08);
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover {
        background-color: var(--corp-emerald-dark);
        border-color: var(--corp-emerald-dark);
        color: #FFFFFF;
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(15, 92, 77, 0.18);
    }

    /* Top Executive Header */
    .corp-header {
        position: relative;
        overflow: hidden;
        background: var(--surface-white);
        border: 1px solid var(--border-light);
        border-top: 3px solid var(--corp-emerald);
        border-radius: 12px;
        padding: 1.25rem 1.75rem;
        margin-bottom: 1.15rem;
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        box-shadow: 0 1px 3px rgba(16, 24, 40, 0.05), 0 10px 24px rgba(16, 24, 40, 0.03);
        animation: fadeInUp 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .corp-header::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 22%;
        height: 3px;
        background: linear-gradient(90deg, transparent, #D97706, transparent);
        animation: subtleSweep 7s ease-in-out infinite;
    }
    .corp-brand {
        display: flex;
        align-items: center;
        gap: 0.95rem;
    }
    .corp-monogram {
        width: 44px;
        height: 44px;
        border-radius: 10px;
        background: var(--corp-emerald);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 12px rgba(15, 92, 77, 0.22);
    }
    .corp-title {
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: var(--ink-primary);
        line-height: 1.15;
    }
    .corp-title span {
        font-weight: 500;
        color: var(--ink-muted);
        font-size: 0.98rem;
        margin-left: 0.55rem;
        padding-left: 0.65rem;
        border-left: 1px solid var(--border-med);
    }
    .corp-subtitle {
        font-size: 0.82rem;
        color: var(--ink-secondary);
        margin-top: 0.2rem;
    }

    .corp-meta {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex-wrap: wrap;
    }
    .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: var(--corp-emerald-soft);
        border: 1px solid #A7F3D0;
        color: var(--corp-emerald-dark);
        padding: 0.42rem 0.85rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 600;
    }
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--corp-emerald);
        animation: livePulse 2.2s infinite;
    }
    .author-chip {
        background: var(--surface-tint);
        border: 1px solid var(--border-light);
        color: var(--ink-secondary);
        padding: 0.42rem 0.85rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 500;
    }

    /* Executive KPI Cards */
    .exec-card {
        background: var(--surface-white);
        border: 1px solid var(--border-light);
        border-radius: 12px;
        padding: 1.15rem 1.3rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
        animation: fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .exec-card:hover {
        transform: translateY(-2px);
        border-color: var(--border-med);
        box-shadow: 0 10px 26px rgba(16, 24, 40, 0.07);
    }
    .exec-card.d1 { animation-delay: 0.04s; }
    .exec-card.d2 { animation-delay: 0.09s; }
    .exec-card.d3 { animation-delay: 0.14s; }
    .exec-card.d4 { animation-delay: 0.19s; }

    .exec-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.55rem;
    }
    .exec-label {
        font-size: 0.78rem;
        font-weight: 600;
        color: var(--ink-secondary);
    }
    .pill-tag {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 0.18rem 0.55rem;
        border-radius: 999px;
    }
    .pill-emerald { background: var(--corp-emerald-soft); color: var(--corp-emerald-dark); border: 1px solid #A7F3D0; }
    .pill-bronze  { background: var(--corp-bronze-soft); color: #92400E; border: 1px solid #FDE68A; }
    .pill-crimson { background: var(--corp-crimson-soft); color: var(--corp-crimson); border: 1px solid #FECACA; }
    .pill-neutral { background: var(--surface-tint); color: var(--ink-secondary); border: 1px solid var(--border-light); }

    .exec-value {
        font-size: 2.05rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: var(--ink-primary);
        font-variant-numeric: tabular-nums;
        line-height: 1.1;
    }
    .exec-foot {
        font-size: 0.76rem;
        color: var(--ink-muted);
        margin-top: 0.45rem;
    }
    .exec-bar-bg {
        width: 100%;
        height: 4px;
        background: #EEF0F4;
        border-radius: 999px;
        margin-top: 0.65rem;
        overflow: hidden;
    }
    .exec-bar-fill {
        height: 100%;
        border-radius: 999px;
        transform-origin: left;
        animation: fillExpand 0.85s cubic-bezier(0.16, 1, 0.3, 1) both;
    }

    /* Macro Portfolio Benchmark Bar */
    .macro-bar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
        gap: 0.85rem;
        background: var(--surface-white);
        border: 1px solid var(--border-light);
        border-radius: 12px;
        padding: 0.95rem 1.35rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
        animation: fadeInUp 0.55s cubic-bezier(0.16, 1, 0.3, 1) 0.12s both;
    }
    .macro-item {
        border-right: 1px solid var(--border-light);
        padding-right: 0.85rem;
    }
    .macro-item:last-child { border-right: none; }
    .macro-label {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--ink-muted);
        margin-bottom: 0.22rem;
    }
    .macro-num {
        font-size: 1.02rem;
        font-weight: 700;
        color: var(--ink-primary);
        font-variant-numeric: tabular-nums;
    }

    /* Section Headers */
    .sec-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        border-bottom: 1px solid var(--border-light);
        padding-bottom: 0.55rem;
        margin: 0.65rem 0 0.95rem 0;
    }
    .sec-h-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: var(--ink-primary);
        letter-spacing: -0.01em;
    }
    .sec-h-sub {
        font-size: 0.76rem;
        font-weight: 500;
        color: var(--ink-muted);
    }

    /* Family Spotlight Cards */
    .fleet-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 0.85rem;
        margin: 0.85rem 0 1.25rem 0;
    }
    .fleet-box {
        background: var(--surface-white);
        border: 1px solid var(--border-light);
        border-left: 3px solid var(--corp-emerald);
        border-radius: 10px;
        padding: 0.95rem 1.15rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .fleet-box:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(16, 24, 40, 0.06);
    }

    /* Corporate Navigation Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.35rem;
        background: var(--surface-white);
        padding: 0.38rem;
        border: 1px solid var(--border-light);
        border-radius: 10px;
        margin-bottom: 1.15rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.84rem;
        font-weight: 600;
        color: var(--ink-secondary);
        border-radius: 7px;
        padding: 0.52rem 1.1rem;
        transition: all 0.18s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--ink-primary);
        background: var(--surface-tint);
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--corp-emerald) !important;
        color: #FFFFFF !important;
        box-shadow: 0 2px 8px rgba(15, 92, 77, 0.22);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 7px; height: 7px; }
    ::-webkit-scrollbar-track { background: var(--canvas-bg); }
    ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--corp-emerald); }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS (CORE LOGIC PRESERVED + HEADING FOR AIRLINER MARKERS)
# -----------------------------------------------------------------------------
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def get_airspace_sector(lat, lon):
    if 35 <= lat <= 70 and -15 <= lon <= 45: return "EUROPEAN ZONE"
    if 25 <= lat <= 60 and -130 <= lon <= -60: return "NORTH AMERICAN ZONE"
    if 0 <= lat <= 50 and 100 <= lon <= 150: return "EAST ASIAN ZONE"
    if 10 <= lat <= 35 and 35 <= lon <= 85: return "MIDDLE EAST / S. ASIA ZONE"
    if -50 <= lat <= 15 and -80 <= lon <= -35: return "SOUTH AMERICAN ZONE"
    if 15 <= lat <= 60 and -60 <= lon <= -15: return "NORTH ATLANTIC ZONE"
    if -50 <= lat <= 10 and 10 <= lon <= 50: return "AFRICAN ZONE"
    if -45 <= lat <= -10 and 110 <= lon <= 160: return "OCEANIC / AUSTRALASIA ZONE"
    return "INTERNATIONAL WATERS"

def get_altitude_band(alt_ft):
    if alt_ft < 10000:
        return "Approach / Low (<10k ft)"
    if alt_ft < 28000:
        return "Climb / Descent (10k-28k ft)"
    if alt_ft < 36000:
        return "Mid Cruise (28k-36k ft)"
    if alt_ft <= 43000:
        return "High Cruise (36k-43k ft)"
    return "Upper Flight Level (>43k ft)"

def classify_airframe_taxonomy(icao_code):
    code = str(icao_code).upper().strip()

    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N", "A332", "A333", "A338", "A339", "A359", "A35K", "A300", "A310", "A343", "A346", "A388", "BCS1", "BCS3"]:
        manufacturer = "Airbus"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM", "B772", "B773", "B77W", "B77L", "B778", "B779", "B788", "B789", "B78X", "B744", "B748", "B762", "B763", "B764", "B712", "B752", "B753", "MD11", "MD82", "MD83", "MD88", "DC10"]:
        manufacturer = "Boeing / MD"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "E135", "E145", "E35L", "E55P", "E50P", "E550"]:
        manufacturer = "Embraer"
    elif code in ["CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "CL30", "CL35", "CL60", "GLEX", "GL5T", "GL7T"]:
        manufacturer = "Bombardier / MHI"
    elif code in ["GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "G280", "G150"]:
        manufacturer = "Gulfstream"
    elif code in ["C750", "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C", "C208"]:
        manufacturer = "Cessna / Textron"
    elif code in ["F900", "F9EX", "FA7X", "FA8X", "F2TH"]:
        manufacturer = "Dassault"
    elif code in ["AT43", "AT72", "AT42"]:
        manufacturer = "ATR"
    elif code in ["PC24", "PC12"]:
        manufacturer = "Pilatus"
    else:
        manufacturer = "Other / Unclassified"

    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N"]: family = "Airbus A320 Family"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM"]: family = "Boeing 737 Family"
    elif code in ["A332", "A333", "A338", "A339"]: family = "Airbus A330 Family"
    elif code in ["B772", "B773", "B77W", "B77L", "B778", "B779"]: family = "Boeing 777 Family"
    elif code in ["B788", "B789", "B78X"]: family = "Boeing 787 Family"
    elif code in ["A359", "A35K"]: family = "Airbus A350 Family"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "BCS1", "BCS3", "AT43", "AT72"]: family = "Regional Aircraft"
    elif code in ["B744", "B748", "B762", "B763", "B764", "MD11", "A300", "A310"]: family = "Legacy Widebody / Cargo"
    elif code in ["GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "FA7X", "FA8X", "C750", "C680", "E55P", "LJ60", "LJ75", "PC24"]: family = "Business Jets"
    else: family = "Other / Unclassified"

    if family in ["Airbus A320 Family", "Boeing 737 Family"]: body_type = "Narrowbody"
    elif family in ["Airbus A330 Family", "Boeing 777 Family", "Boeing 787 Family", "Airbus A350 Family", "Legacy Widebody / Cargo"]: body_type = "Widebody"
    elif family == "Regional Aircraft": body_type = "Regional"
    elif family == "Business Jets": body_type = "Business Jet"
    else: body_type = "Other"

    if code in ["A20N", "A21N", "A19N", "B38M", "B39M", "B3XM", "A338", "A339", "B788", "B789", "B78X", "A359", "A35K", "E290", "E295", "BCS1", "BCS3"]:
        generation = "Next-Gen"
    else:
        generation = "Legacy"

    return pd.Series([manufacturer, family, body_type, generation])

try:
    client = OpenSkyClient()
except Exception:
    st.stop()

@st.cache_data(ttl=86400)
def fetch_dynamic_airline_map(api_key):
    try:
        res = requests.get(f"https://airlabs.co/api/v9/airlines?api_key={api_key}", timeout=15)
        if res.status_code == 200:
            return {al.get("iata_code"): al.get("name") for al in res.json().get("response", []) if al.get("iata_code")}
    except Exception:
        pass
    return {}

@st.cache_data(ttl=15)
def fetch_global_fusion(api_key):
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []
    fallback_mil_icaos = {"AFX", "RRR", "CNV", "CFC", "GAF", "RFF", "ASY", "FCE", "AME", "IAM", "BAF", "NAF", "SVF", "SUI", "PLF", "ROF", "HAF", "TUAF", "MMF"}

    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack/1.1"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code:
                    continue
                military_watchlist[hex_code] = {"aircraft_type": str(ac.get("t", "")).strip()}
                military_tracks.append({
                    "icao24": hex_code,
                    "callsign": str(ac.get("flight", "")).strip(),
                    "flight_number": "GOV-OPS",
                    "latitude": float(ac.get("lat") or 0),
                    "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")),
                    "velocity": safe_float(ac.get("gs")) * 1.852,
                    "heading": safe_float(ac.get("track") if ac.get("track") is not None else ac.get("true_heading")),
                    "aircraft_type": str(ac.get("t", "")),
                    "airline_code": "MIL",
                    "military": True,
                    "Classification": "MILITARY",
                })
    except Exception:
        pass

    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={api_key}", timeout=15)
        for ac in (res.json().get("response", []) if res.status_code == 200 else []):
            try:
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None:
                    continue
                airline_icao = str(ac.get("airline_icao", "UNKN")).upper().strip()
                is_mil = (hex_code in military_watchlist) or (airline_icao in fallback_mil_icaos)

                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": float(ac.get("lat") or 0),
                    "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084,
                    "velocity": float(ac.get("speed") or 0),
                    "heading": safe_float(ac.get("dir")),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(),
                    "flight_number": str(ac.get("flight_number", "UNKN")),
                    "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip(),
                    "military": is_mil,
                    "Classification": "MILITARY" if is_mil else "CIVILIAN",
                }
                if is_mil and hex_code in military_watchlist:
                    tactical_grid[hex_code].update({
                        "aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN"),
                        "airline_code": "MIL",
                        "flight_number": "GOV-OPS",
                    })
            except Exception:
                continue
    except Exception:
        pass

    df = pd.DataFrame(list(tactical_grid.values()))
    mil_df = pd.DataFrame(military_tracks)
    if not mil_df.empty:
        df = pd.concat([df, mil_df[~mil_df["icao24"].isin(df["icao24"])]], ignore_index=True)
    if df.empty:
        return df

    if "heading" not in df.columns:
        df["heading"] = 0.0
    else:
        df["heading"] = df["heading"].fillna(0.0)

    if "Classification" not in df.columns:
        df["Classification"] = "CIVILIAN"
    else:
        df["Classification"] = df["Classification"].fillna("CIVILIAN")

    df["Threat_Reason"] = ""
    df["sector"] = df.apply(lambda r: get_airspace_sector(r["latitude"], r["longitude"]), axis=1)
    df[["Manufacturer", "Family", "Body Type", "Generation"]] = df["aircraft_type"].apply(classify_airframe_taxonomy)

    biz_jets = [
        "GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "GL5T", "GL7T", "G280", "G150",
        "CL30", "CL35", "CL60", "CRJ2", "F900", "F9EX", "FA7X", "FA8X", "F2TH", "C750",
        "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C",
        "E55P", "E50P", "E550", "E135", "E35L", "LJ60", "LJ75", "LJ70", "LJ45", "LJ40",
        "LJ35", "HDJT", "PC24",
    ]

    for idx, row in df.iterrows():
        try:
            vel = float(row.get("velocity", 0.0))
            alt = float(row.get("baro_altitude", 0.0))
            ac_type = str(row.get("aircraft_type", "")).upper()
            is_mil = row.get("military", False)
            reasons = []
            if alt < 15000 and vel > 850:
                reasons.append("LOW-ALT/HI-VEL")
            if alt > (49000 if ac_type in biz_jets else 45000):
                reasons.append("CEILING-BREACH")
            if (vel > 1250) or (vel > 1050 and alt < 28000):
                reasons.append("OVER-SPEED")
            if alt > 30000 and vel < 20:
                reasons.append("TELEMETRY EXCEPTION")
            if reasons:
                df.at[idx, "Threat_Reason"] = " | ".join(reasons)
                df.at[idx, "Classification"] = "ANOMALY"
            elif is_mil:
                df.at[idx, "Classification"] = "MILITARY"
        except Exception:
            pass

    return df

@st.cache_data(ttl=30)
def get_macro_intelligence(_airline_map):
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(24).execute()
        stats_df = pd.DataFrame(res.data)
        if stats_df.empty:
            return None

        current = stats_df.iloc[0]
        avg_flights = stats_df["total_flights"].mean() if len(stats_df) > 1 else current["total_flights"]
        curr_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0
        curr_mil_pct = (current["military_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0
        flight_delta = ((current["total_flights"] - avg_flights) / avg_flights) * 100 if avg_flights > 0 else 0

        raw_apt = str(current.get("busiest_airport", "DFW")).upper()
        apt_txt = f"{raw_apt} ({AIRPORT_MAP.get(raw_apt, 'Intl Hub')})"
        carrier_code = str(current.get("top_carrier", "UNKN")).upper()
        full_carrier_name = _airline_map.get(carrier_code, carrier_code)

        history_df = stats_df[["timestamp", "total_flights", "military_count", "threat_count"]].copy()
        history_df["timestamp"] = pd.to_datetime(history_df["timestamp"]).dt.strftime("%H:%M")
        history_df = history_df.set_index("timestamp").iloc[::-1]
        history_df.rename(
            columns={
                "total_flights": "Commercial Fleet Volume",
                "military_count": "Gov / Special Ops",
                "threat_count": "Operational Exceptions",
            },
            inplace=True,
        )

        return {
            "density": f"{int(current.get('total_flights', 0)):,}",
            "density_delta": f"{flight_delta:+.1f}%",
            "threat_pct": f"{curr_threat_pct:.1f}%",
            "mil_pct": f"{curr_mil_pct:.1f}%",
            "region": str(current.get("busiest_region", "NORTH AMERICAN SECTOR")).upper(),
            "airport": apt_txt,
            "top_carrier": f"{full_carrier_name} ({carrier_code})",
            "top_carrier_count": int(current.get("top_carrier_count", 0)),
            "top_frame": str(current.get("top_frame", "UNKN")).upper(),
            "top_frame_count": int(current.get("top_frame_count", 0)),
            "history_df": history_df,
        }
    except Exception:
        return None

# -----------------------------------------------------------------------------
# CORPORATE PLOTLY THEME HELPER (CLEAN WHITE PAPER, EMERALD / BRONZE / CRIMSON)
# -----------------------------------------------------------------------------
def style_corp_chart(fig, height=325):
    fig.update_layout(
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FAFBFD",
        font=dict(color="#344054", family="Plus Jakarta Sans, sans-serif", size=12),
        margin=dict(l=16, r=20, t=28, b=18),
        transition={"duration": 500, "easing": "cubic-in-out"},
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor="#0F5C4D",
            font=dict(color="#101828", family="Plus Jakarta Sans, sans-serif", size=12),
        ),
    )
    fig.update_xaxes(gridcolor="#EAECF0", zeroline=False, linecolor="#D0D5DD", tickfont=dict(color="#475467"))
    fig.update_yaxes(gridcolor="#EAECF0", zeroline=False, linecolor="#D0D5DD", tickfont=dict(color="#475467"))
    return fig

# -----------------------------------------------------------------------------
# DATA INGESTION
# -----------------------------------------------------------------------------
dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)
dynamic_airline_map["MIL"] = "State / Government Operator"

raw_df = fetch_global_fusion(client.api_key)
macro = get_macro_intelligence(dynamic_airline_map)
utc_now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

if not raw_df.empty:
    # -------------------------------------------------------------------------
    # EXECUTIVE CORPORATE HEADER
    # -------------------------------------------------------------------------
    st.markdown(
        f"""
        <div class="corp-header">
            <div class="corp-brand">
                <div class="corp-monogram">
                    <svg width="22" height="22" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                        <path fill="#ffffff" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
                    </svg>
                </div>
                <div>
                    <div class="corp-title">AeroTrack <span>Aviation Asset &amp; Portfolio Risk Intelligence</span></div>
                    <div class="corp-subtitle">Global Fleet Utilization, Lessee Market Concentration &amp; Operational Risk Analytics</div>
                </div>
            </div>
            <div class="corp-meta">
                <div class="status-chip">
                    <span class="status-dot"></span>
                    Live Market Feed &bull; {utc_now}
                </div>
                <div class="author-chip">Satvik Goyal &bull; @satvik-7773</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # INLINE PORTFOLIO FILTER BAR (NO SIDEBAR)
    # -------------------------------------------------------------------------
    f1, f2, f3, f4, f5 = st.columns([1.2, 1.35, 1.4, 1.35, 0.85], gap="small")

    with f1:
        class_filter = st.selectbox(
            "Asset Segment",
            ["ALL ASSETS", "COMMERCIAL ONLY", "STATE / GOV ONLY", "RISK EXCEPTIONS"],
        )
    with f2:
        sector_list = ["GLOBAL (ALL REGIONS)"] + sorted(list(raw_df["sector"].unique()))
        region_filter = st.selectbox("Geographic Market", sector_list)
    with f3:
        min_alt = int(raw_df["baro_altitude"].fillna(0).min())
        max_alt = int(raw_df["baro_altitude"].fillna(0).max())
        if min_alt >= max_alt:
            max_alt = min_alt + 1000
        alt_filter = st.slider(
            "Operating Altitude Band (ft)",
            min_value=min_alt,
            max_value=max_alt,
            value=(min_alt, max_alt),
            step=1000,
        )
    with f4:
        search_query = st.text_input("Filter Carrier, Registration or Type", placeholder="e.g. DLH, A359, B789, 3C6...")
    with f5:
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Apply Filters
    df = raw_df.copy()
    if class_filter == "COMMERCIAL ONLY":
        df = df[df["Classification"] == "CIVILIAN"]
    elif class_filter == "STATE / GOV ONLY":
        df = df[df["Classification"] == "MILITARY"]
    elif class_filter == "RISK EXCEPTIONS":
        df = df[df["Classification"] == "ANOMALY"]

    if region_filter != "GLOBAL (ALL REGIONS)":
        df = df[df["sector"] == region_filter]

    df = df[(df["baro_altitude"] >= alt_filter[0]) & (df["baro_altitude"] <= alt_filter[1])]

    if search_query.strip():
        q = search_query.strip().lower()
        df = df[
            df["callsign"].astype(str).str.lower().str.contains(q, na=False)
            | df["icao24"].astype(str).str.lower().str.contains(q, na=False)
            | df["airline_code"].astype(str).str.lower().str.contains(q, na=False)
            | df["aircraft_type"].astype(str).str.lower().str.contains(q, na=False)
        ]

    # Portfolio KPI Metrics
    total_active = len(df)
    civ_cnt = int((df["Classification"] == "CIVILIAN").sum())
    mil_cnt = int((df["military"] == True).sum())
    anom_cnt = int((df["Classification"] == "ANOMALY").sum())

    nextgen_pct = (df["Generation"] == "Next-Gen").mean() * 100 if total_active > 0 else 0.0
    civ_pct = (civ_cnt / total_active * 100) if total_active > 0 else 0.0
    mil_pct = (mil_cnt / total_active * 100) if total_active > 0 else 0.0
    anom_pct = (anom_cnt / total_active * 100) if total_active > 0 else 0.0

    avg_speed = df["velocity"].mean() if total_active > 0 else 0.0
    avg_alt = df["baro_altitude"].mean() if total_active > 0 else 0.0
    active_carriers = df[~df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].nunique() if total_active > 0 else 0
    widebody_pct = (df["Body Type"] == "Widebody").mean() * 100 if total_active > 0 else 0.0

    # -------------------------------------------------------------------------
    # EXECUTIVE KPI CARDS
    # -------------------------------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
            <div class="exec-card d1">
                <div class="exec-top">
                    <span class="exec-label">In-Service Active Fleet</span>
                    <span class="pill-tag pill-emerald">{nextgen_pct:.1f}% Next-Gen</span>
                </div>
                <div class="exec-value">{total_active:,}</div>
                <div class="exec-foot">Avg Cruise: {avg_speed:,.0f} km/h &bull; FL{int(avg_alt/100):03d} &bull; {widebody_pct:.1f}% Widebody</div>
                <div class="exec-bar-bg"><div class="exec-bar-fill" style="width:{min(nextgen_pct, 100):.1f}%; background:#0F5C4D;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        st.markdown(
            f"""
            <div class="exec-card d2">
                <div class="exec-top">
                    <span class="exec-label">Commercial Lessee Traffic</span>
                    <span class="pill-tag pill-neutral">{civ_pct:.1f}% Share</span>
                </div>
                <div class="exec-value">{civ_cnt:,}</div>
                <div class="exec-foot">{active_carriers:,} active commercial carrier codes worldwide</div>
                <div class="exec-bar-bg"><div class="exec-bar-fill" style="width:{min(civ_pct, 100):.1f}%; background:#344054;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
            <div class="exec-card d3">
                <div class="exec-top">
                    <span class="exec-label">Government &amp; Special Ops</span>
                    <span class="pill-tag pill-bronze">{mil_pct:.1f}% Share</span>
                </div>
                <div class="exec-value" style="color:#B45309;">{mil_cnt:,}</div>
                <div class="exec-foot">Non-commercial state, VIP &amp; sovereign fleet tracks</div>
                <div class="exec-bar-bg"><div class="exec-bar-fill" style="width:{min(mil_pct * 3, 100):.1f}%; background:#B45309;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        st.markdown(
            f"""
            <div class="exec-card d4">
                <div class="exec-top">
                    <span class="exec-label">Operational Risk Exceptions</span>
                    <span class="pill-tag pill-crimson">{anom_pct:.2f}% Rate</span>
                </div>
                <div class="exec-value" style="color:{'#B91C1C' if anom_cnt > 0 else '#0F5C4D'};">{anom_cnt:,}</div>
                <div class="exec-foot">Out-of-envelope ceiling, speed &amp; transponder flags</div>
                <div class="exec-bar-bg"><div class="exec-bar-fill" style="width:{min(anom_pct * 10, 100):.1f}%; background:#B91C1C;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # MACRO MARKET BENCHMARK STRIP
    # -------------------------------------------------------------------------
    if macro:
        delta_val = float(macro["density_delta"].strip("%"))
        delta_col = "#0F5C4D" if delta_val >= 0 else "#B91C1C"
        st.markdown(
            f"""
            <div class="macro-bar">
                <div class="macro-item">
                    <div class="macro-label">Global Flight Volume</div>
                    <div class="macro-num">{macro['density']} <span style="color:{delta_col}; font-size:0.82rem; font-weight:600;">({macro['density_delta']} vs 24h avg)</span></div>
                </div>
                <div class="macro-item">
                    <div class="macro-label">Portfolio Exception Rate</div>
                    <div class="macro-num" style="color:#B91C1C;">{macro['threat_pct']}</div>
                </div>
                <div class="macro-item">
                    <div class="macro-label">Sovereign / Non-Comm Index</div>
                    <div class="macro-num" style="color:#B45309;">{macro['mil_pct']}</div>
                </div>
                <div class="macro-item">
                    <div class="macro-label">Highest Utilization Market</div>
                    <div class="macro-num" style="color:#0F5C4D;">{macro['region']}</div>
                </div>
                <div class="macro-item">
                    <div class="macro-label">Busiest Hub Airport</div>
                    <div class="macro-num">{macro['airport']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # CORPORATE WORKSPACE TABS
    # -------------------------------------------------------------------------
    tab_globe, tab_exposure, tab_taxonomy, tab_register = st.tabs([
        "Global Fleet Map & Utilization Trend",
        "Lessee, OEM & Cargo Exposure",
        "Fleet Modernization & Regional HHI Risk",
        "Asset Utilization & Risk Register",
    ])

    # =========================================================================
    # TAB 1: 3D GLOBE WITH REAL AIRLINER MARKERS + 24H VOLUME TREND
    # =========================================================================
    with tab_globe:
        st.markdown(
            f"""
            <div class="sec-header">
                <div class="sec-h-title">Global In-Service Fleet Distribution (3D Perspective)</div>
                <div class="sec-h-sub">
                    <span style="color:#0F5C4D; font-weight:600;">Commercial Lessee</span> &nbsp;&bull;&nbsp;
                    <span style="color:#B45309; font-weight:600;">State / Sovereign</span> &nbsp;&bull;&nbsp;
                    <span style="color:#B91C1C; font-weight:600;">Operational Exception</span> &nbsp;|&nbsp;
                    {len(df):,} Active Aircraft
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if df.empty:
            st.info("No aircraft match the selected portfolio filters.")
        else:
            def assign_corp_color(cls):
                if cls == "ANOMALY":
                    return [185, 28, 28, 245]     # Crimson Risk
                elif cls == "MILITARY":
                    return [180, 83, 9, 235]      # Warm Bronze
                return [15, 92, 77, 220]          # Institutional Forest Emerald

            map_df = df.copy()
            map_df["color"] = map_df["Classification"].apply(assign_corp_color)
            map_df["angle"] = (360.0 - map_df["heading"].fillna(0.0)) % 360.0
            map_df["icon_size"] = np.where(
                map_df["Classification"] == "ANOMALY",
                23,
                np.where(map_df["Classification"] == "MILITARY", 19, 15),
            )
            map_df["icon_data"] = [
                {
                    "url": AIRLINER_ICON_URL,
                    "width": 128,
                    "height": 128,
                    "anchorX": 64,
                    "anchorY": 64,
                    "mask": True,
                }
            ] * len(map_df)
            map_df["baro_altitude_fmt"] = map_df["baro_altitude"].round(0).astype(int)
            map_df["velocity_fmt"] = map_df["velocity"].round(0).astype(int)
            map_df["heading_fmt"] = map_df["heading"].round(0).astype(int)

            airliner_layer = pdk.Layer(
                "IconLayer",
                data=map_df,
                get_icon="icon_data",
                get_position="[longitude, latitude]",
                get_size="icon_size",
                size_scale=1,
                size_min_pixels=11,
                size_max_pixels=25,
                get_angle="angle",
                get_color="color",
                billboard=False,
                pickable=True,
            )

            st.pydeck_chart(
                pdk.Deck(
                    layers=[airliner_layer],
                    initial_view_state=pdk.ViewState(
                        latitude=25,
                        longitude=10,
                        zoom=1.6,
                        pitch=38,
                        bearing=0,
                    ),
                    tooltip={
                        "html": """
                            <div style="font-family: 'Plus Jakarta Sans', sans-serif; padding: 6px 4px; min-width: 205px;">
                                <div style="display:flex; justify-content:space-between; border-bottom:1px solid #E4E7EC; padding-bottom:4px; margin-bottom:5px;">
                                    <strong style="color:#101828; font-size:13px;">{callsign}</strong>
                                    <span style="color:#667085; font-family:'IBM Plex Mono', monospace; font-size:11px;">{icao24}</span>
                                </div>
                                <div style="color:#344054; font-size:12px; font-weight:500; margin-bottom:4px;">
                                    {aircraft_type} &bull; {Family} ({Generation})
                                </div>
                                <div style="color:#475467; font-family:'IBM Plex Mono', monospace; font-size:11px;">
                                    ALT {baro_altitude_fmt} ft &nbsp;|&nbsp; SPD {velocity_fmt} km/h
                                </div>
                                <div style="color:#475467; font-family:'IBM Plex Mono', monospace; font-size:11px; margin-top:2px;">
                                    HDG {heading_fmt} deg &nbsp;|&nbsp; <strong style="color:#0F5C4D;">{Classification}</strong>
                                </div>
                            </div>
                        """,
                        "style": {
                            "backgroundColor": "#FFFFFF",
                            "border": "1px solid #D0D5DD",
                            "borderRadius": "8px",
                            "boxShadow": "0 10px 25px rgba(16, 24, 40, 0.14)",
                        },
                    },
                    map_style="mapbox://styles/mapbox/light-v11",
                ),
                use_container_width=True,
            )

        if macro and macro.get("history_df") is not None and not macro["history_df"].empty:
            hist = macro["history_df"]
            st.markdown(
                """
                <div class="sec-header" style="margin-top: 1.35rem;">
                    <div class="sec-h-title">24-Hour Global Fleet Utilization &amp; Exception Trend</div>
                    <div class="sec-h-sub">Historical Snapshot Series (Supabase)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            trend_fig = make_subplots(specs=[[{"secondary_y": True}]])
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Commercial Fleet Volume"],
                    name="Commercial Fleet Volume",
                    mode="lines",
                    line=dict(color="#0F5C4D", width=2.6, shape="spline"),
                    fill="tozeroy",
                    fillcolor="rgba(15, 92, 77, 0.10)",
                ),
                secondary_y=False,
            )
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Gov / Special Ops"],
                    name="Gov / Special Ops",
                    mode="lines+markers",
                    line=dict(color="#B45309", width=2, shape="spline"),
                    marker=dict(size=5),
                ),
                secondary_y=True,
            )
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Operational Exceptions"],
                    name="Operational Exceptions",
                    mode="lines+markers",
                    line=dict(color="#B91C1C", width=2, shape="spline"),
                    marker=dict(size=5),
                ),
                secondary_y=True,
            )
            style_corp_chart(trend_fig, height=295)
            trend_fig.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified",
            )
            trend_fig.update_yaxes(title_text="Commercial Fleet", secondary_y=False, title_font=dict(size=11, color="#0F5C4D"))
            trend_fig.update_yaxes(title_text="Special Ops / Exceptions", secondary_y=True, showgrid=False, title_font=dict(size=11, color="#B45309"))
            st.plotly_chart(trend_fig, use_container_width=True)

    # =========================================================================
    # TAB 2: LESSEE CONCENTRATION, OEM EXPOSURE, CARGO & RISK ENVELOPE
    # =========================================================================
    with tab_exposure:
        if df.empty:
            st.info("No aircraft data available for the selected filters.")
        else:
            r1_c1, r1_c2 = st.columns(2, gap="large")

            with r1_c1:
                st.markdown(
                    """
                    <div class="sec-header">
                        <div class="sec-h-title">Top 10 Global Airline Operators (Lessee Exposure)</div>
                        <div class="sec-h-sub">Active Airborne Fleet</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                top10_airlines = df[~df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts().head(10)
                if not top10_airlines.empty:
                    al_df = top10_airlines.reset_index()
                    al_df.columns = ["Code", "Flights"]
                    al_df["Carrier"] = al_df["Code"].map(lambda x: f"{dynamic_airline_map.get(x, x)} ({x})")
                    fig_al = px.bar(
                        al_df,
                        x="Flights",
                        y="Carrier",
                        orientation="h",
                        text="Flights",
                        color="Flights",
                        color_continuous_scale=["#6EE7B7", "#0F5C4D", "#064E3B"],
                    )
                    fig_al.update_traces(textposition="outside", marker_line_width=0)
                    style_corp_chart(fig_al, height=340)
                    fig_al.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Aircraft")
                    st.plotly_chart(fig_al, use_container_width=True)
                else:
                    st.info("Insufficient commercial airline data in current filter.")

            with r1_c2:
                st.markdown(
                    """
                    <div class="sec-header">
                        <div class="sec-h-title">OEM Manufacturer Market Share</div>
                        <div class="sec-h-sub">Portfolio Composition</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                manuf_share = df[df["Manufacturer"] != "Other / Unclassified"]["Manufacturer"].value_counts()
                if not manuf_share.empty:
                    man_df = manuf_share.reset_index()
                    man_df.columns = ["Manufacturer", "Count"]
                    fig_oem = px.pie(
                        man_df,
                        names="Manufacturer",
                        values="Count",
                        hole=0.62,
                        color_discrete_sequence=["#0F5C4D", "#344054", "#B45309", "#059669", "#667085", "#D97706", "#98A2B3", "#B91C1C"],
                    )
                    fig_oem.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                        marker=dict(line=dict(color="#FFFFFF", width=2)),
                    )
                    style_corp_chart(fig_oem, height=340)
                    fig_oem.update_layout(showlegend=False)
                    st.plotly_chart(fig_oem, use_container_width=True)
                else:
                    st.info("No manufacturer classification data available.")

            r2_c1, r2_c2 = st.columns(2, gap="large")

            with r2_c1:
                st.markdown(
                    """
                    <div class="sec-header">
                        <div class="sec-h-title">Dedicated Cargo &amp; Freighter Operators</div>
                        <div class="sec-h-sub">Air Freight Utilization</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                cargo_codes = [
                    "FX", "FDX", "5X", "UPS", "5Y", "GTI", "PO", "PAC", "K4", "CKS", "CV", "CLX", "3S", "BOX",
                    "RU", "ABW", "D0", "BCS", "ABR", "LH", "GEC", "SQC", "CK", "CKK", "KZ", "NCA", "CI", "CAL",
                    "BR", "EVA", "MP", "MPH", "QT", "TAY", "OOK", "LD", "AHK",
                ]
                cargo_df = df[(df["airline_code"].isin(cargo_codes)) | (df["Family"] == "Legacy Widebody / Cargo")]
                top_cargo = cargo_df[~cargo_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts().head(10)
                if not top_cargo.empty:
                    cg_df = top_cargo.reset_index()
                    cg_df.columns = ["Code", "Flights"]
                    cg_df["Operator"] = cg_df["Code"].map(lambda x: f"{dynamic_airline_map.get(x, x)} ({x})")
                    fig_cg = px.bar(
                        cg_df,
                        x="Flights",
                        y="Operator",
                        orientation="h",
                        text="Flights",
                        color="Flights",
                        color_continuous_scale=["#FDE68A", "#D97706", "#92400E"],
                    )
                    fig_cg.update_traces(textposition="outside", marker_line_width=0)
                    style_corp_chart(fig_cg, height=340)
                    fig_cg.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Freighters")
                    st.plotly_chart(fig_cg, use_container_width=True)
                else:
                    st.info("No dedicated cargo operators detected in current filter.")

            with r2_c2:
                st.markdown(
                    """
                    <div class="sec-header">
                        <div class="sec-h-title">Top 10 Deployed Aircraft Families</div>
                        <div class="sec-h-sub">Asset Class Demand</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                top10_fams = df[df["Family"] != "Other / Unclassified"]["Family"].value_counts().head(10)
                if not top10_fams.empty:
                    fm_df = top10_fams.reset_index()
                    fm_df.columns = ["Family", "Count"]
                    fig_fm = px.bar(
                        fm_df,
                        x="Count",
                        y="Family",
                        orientation="h",
                        text="Count",
                        color="Count",
                        color_continuous_scale=["#CBD5E1", "#475467", "#101828"],
                    )
                    fig_fm.update_traces(textposition="outside", marker_line_width=0)
                    style_corp_chart(fig_fm, height=340)
                    fig_fm.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Airframes")
                    st.plotly_chart(fig_fm, use_container_width=True)
                else:
                    st.info("Insufficient airframe family data.")

            r3_c1, r3_c2 = st.columns(2, gap="large")

            with r3_c1:
                st.markdown(
                    """
                    <div class="sec-header">
                        <div class="sec-h-title">Operational Risk Envelope (Speed vs. Altitude)</div>
                        <div class="sec-h-sub">Outlier &amp; Regime Dispersion</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                env_df = df.sample(n=min(len(df), 2500), random_state=42) if len(df) > 2500 else df
                fig_env = px.scatter(
                    env_df,
                    x="velocity",
                    y="baro_altitude",
                    color="Classification",
                    color_discrete_map={
                        "CIVILIAN": "rgba(15, 92, 77, 0.45)",
                        "MILITARY": "#B45309",
                        "ANOMALY": "#B91C1C",
                    },
                    hover_name="callsign",
                    hover_data=["icao24", "aircraft_type", "Threat_Reason"],
                    labels={"velocity": "Ground Speed (km/h)", "baro_altitude": "Barometric Altitude (ft)"},
                )
                style_corp_chart(fig_env, height=315)
                fig_env.update_layout(legend=dict(orientation="h", y=1.08, x=0, title=None))
                st.plotly_chart(fig_env, use_container_width=True)

            with r3_c2:
                st.markdown(
                    """
                    <div class="sec-header">
                        <div class="sec-h-title">Portfolio Body-Class Segmentation</div>
                        <div class="sec-h-sub">Narrowbody vs. Widebody vs. Regional</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                body_df = df["Body Type"].value_counts().reset_index()
                body_df.columns = ["Body Type", "Count"]
                fig_body = px.bar(
                    body_df,
                    x="Body Type",
                    y="Count",
                    color="Body Type",
                    text="Count",
                    color_discrete_sequence=["#0F5C4D", "#B45309", "#344054", "#667085", "#98A2B3"],
                )
                fig_body.update_traces(textposition="outside", marker_line_width=0)
                style_corp_chart(fig_body, height=315)
                fig_body.update_layout(showlegend=False, xaxis_title="", yaxis_title="Active Aircraft")
                st.plotly_chart(fig_body, use_container_width=True)

    # =========================================================================
    # TAB 3: FLEET MODERNIZATION, RESIDUAL-VALUE MIX & REGIONAL HHI RISK
    # =========================================================================
    with tab_taxonomy:
        st.markdown(
            """
            <div class="sec-header">
                <div class="sec-h-title">Aircraft Family Benchmark &amp; Lessor Utilization</div>
                <div class="sec-h-sub">Fleet Residual Value &amp; Geographic Dispersion</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        available_families = sorted([f for f in raw_df["Family"].unique() if f != "Other / Unclassified"])
        if available_families:
            selected_family = st.selectbox("Select Aircraft Asset Family", available_families)
            fam_df = raw_df[raw_df["Family"] == selected_family]
            fam_active = len(fam_df)
            fam_share = (fam_active / len(raw_df)) * 100 if len(raw_df) > 0 else 0.0
            fam_ops = fam_df[~fam_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].nunique()
            top_fam_region = fam_df["sector"].mode()[0] if not fam_df.empty else "N/A"
            fam_nextgen = (fam_df["Generation"] == "Next-Gen").mean() * 100 if fam_active > 0 else 0.0

            top_op_code = fam_df[~fam_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].mode()[0] if fam_ops > 0 else "UNKN"
            top_op_name = dynamic_airline_map.get(top_op_code, top_op_code)

            st.markdown(
                f"""
                <div class="fleet-grid">
                    <div class="fleet-box">
                        <div class="macro-label">Active In-Service Assets</div>
                        <div style="font-size:1.55rem; font-weight:800; color:#0F5C4D;">
                            {fam_active:,} <span style="font-size:0.85rem; color:#667085; font-weight:500;">({fam_share:.1f}% global)</span>
                        </div>
                    </div>
                    <div class="fleet-box">
                        <div class="macro-label">Active Airline Operators</div>
                        <div style="font-size:1.55rem; font-weight:800; color:#101828;">{fam_ops} Carriers</div>
                    </div>
                    <div class="fleet-box">
                        <div class="macro-label">Primary Operating Region</div>
                        <div style="font-size:1.1rem; font-weight:700; color:#101828; margin-top:0.25rem;">{top_fam_region}</div>
                    </div>
                    <div class="fleet-box">
                        <div class="macro-label">Top Operator &amp; Next-Gen Mix</div>
                        <div style="font-size:1.02rem; font-weight:700; color:#B45309; margin-top:0.25rem;">
                            {top_op_name} ({top_op_code}) &bull; {fam_nextgen:.0f}% NG
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            tx_c1, tx_c2 = st.columns([1.35, 1.0], gap="large")
            with tx_c1:
                fam_sec = fam_df["sector"].value_counts().reset_index()
                fam_sec.columns = ["Zone", "Flights"]
                fig_fsec = px.bar(
                    fam_sec,
                    x="Zone",
                    y="Flights",
                    text="Flights",
                    color="Flights",
                    color_continuous_scale=["#A7F3D0", "#0F5C4D"],
                    title=f"{selected_family} — Regional Utilization Footprint",
                )
                fig_fsec.update_traces(textposition="outside", marker_line_width=0)
                style_corp_chart(fig_fsec, height=295)
                fig_fsec.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Active Aircraft")
                st.plotly_chart(fig_fsec, use_container_width=True)

            with tx_c2:
                oem_ng = (
                    raw_df[raw_df["Manufacturer"] != "Other / Unclassified"]
                    .groupby(["Manufacturer", "Generation"])
                    .size()
                    .reset_index(name="Count")
                )
                fig_ng = px.bar(
                    oem_ng,
                    x="Manufacturer",
                    y="Count",
                    color="Generation",
                    barmode="stack",
                    color_discrete_map={"Next-Gen": "#0F5C4D", "Legacy": "#CBD5E1"},
                    title="OEM Modernization Mix (Next-Gen vs. Legacy)",
                )
                style_corp_chart(fig_ng, height=295)
                fig_ng.update_layout(xaxis_title="", yaxis_title="Aircraft", legend=dict(orientation="h", y=1.08, x=0, title=None))
                st.plotly_chart(fig_ng, use_container_width=True)

        st.markdown(
            """
            <div class="sec-header" style="margin-top: 0.75rem;">
                <div class="sec-h-title">Regional Asset Concentration &amp; Lessee HHI Risk Benchmark</div>
                <div class="sec-h-sub">Herfindahl-Hirschman Index by Aviation Market</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        total_global_tracks = len(raw_df)
        regional_data = []
        for sector_name, sector_df in raw_df.groupby("sector"):
            sec_tracks = len(sector_df)
            fleet_share_idx = (sec_tracks / total_global_tracks) * 100 if total_global_tracks > 0 else 0

            carrier_counts = sector_df[~sector_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts()
            if not carrier_counts.empty:
                c_props = carrier_counts / carrier_counts.sum()
                hhi = sum(c_props ** 2) * 10000
                if hhi > 2500:
                    conc_status = "Highly Concentrated"
                elif hhi > 1500:
                    conc_status = "Moderately Concentrated"
                else:
                    conc_status = "Highly Competitive"
                top_c = carrier_counts.index[0]
                top_c_str = f"{dynamic_airline_map.get(top_c, top_c)} ({top_c})"
            else:
                conc_status = "N/A (Charter / State)"
                top_c_str = "NONE / CHARTER"

            top_fam = sector_df["Family"].mode()[0] if not sector_df.empty else "UNKN"
            ng_share = (sector_df["Generation"] == "Next-Gen").mean() * 100 if sec_tracks > 0 else 0.0

            regional_data.append({
                "Geographic Market": sector_name,
                "Active Fleet": sec_tracks,
                "Global Share (%)": round(fleet_share_idx, 1),
                "Next-Gen Share (%)": round(ng_share, 1),
                "Concentration Risk (HHI)": conc_status,
                "Largest Operator": top_c_str,
                "Dominant Family": top_fam,
            })

        df_regional = pd.DataFrame(regional_data).sort_values(by="Active Fleet", ascending=False)
        st.dataframe(
            df_regional,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Active Fleet": st.column_config.NumberColumn("Active Fleet", format="%d"),
                "Global Share (%)": st.column_config.ProgressColumn("Global Share", min_value=0.0, max_value=100.0, format="%.1f%%"),
                "Next-Gen Share (%)": st.column_config.ProgressColumn("Next-Gen %", min_value=0.0, max_value=100.0, format="%.1f%%"),
            },
        )

    # =========================================================================
    # TAB 4: ASSET UTILIZATION & RISK REGISTER
    # =========================================================================
    with tab_register:
        st.markdown(
            f"""
            <div class="sec-header">
                <div class="sec-h-title">Live Aircraft Asset Utilization &amp; Risk Register</div>
                <div class="sec-h-sub">Sorted by Risk Priority &amp; Flight Level &bull; {len(df):,} Records</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        display_cols = [
            "Classification", "icao24", "callsign", "flight_number", "airline_code",
            "aircraft_type", "Family", "Body Type", "Generation", "sector",
            "baro_altitude", "velocity", "heading", "Threat_Reason",
        ]

        df_full = df[[c for c in display_cols if c in df.columns]].copy()

        if "Classification" in df_full.columns:
            df_full["_rank"] = df_full["Classification"].map({"ANOMALY": 0, "MILITARY": 1, "CIVILIAN": 2}).fillna(3)
            df_full = df_full.sort_values(by=["_rank", "baro_altitude"], ascending=[True, False]).drop(columns=["_rank"])

        df_full.rename(
            columns={
                "Classification": "Segment",
                "icao24": "ICAO Hex",
                "callsign": "Callsign",
                "flight_number": "Flight No.",
                "airline_code": "Carrier",
                "aircraft_type": "Type",
                "Family": "Airframe Family",
                "Body Type": "Body Class",
                "Generation": "Generation",
                "sector": "Market Region",
                "baro_altitude": "Altitude (ft)",
                "velocity": "Speed (km/h)",
                "heading": "Heading",
                "Threat_Reason": "Risk Flags",
            },
            inplace=True,
        )

        if "Carrier" in df_full.columns:
            df_full.insert(
                df_full.columns.get_loc("Carrier") + 1,
                "Operator Name",
                df_full["Carrier"].map(dynamic_airline_map).fillna("Unknown / Charter"),
            )

        st.dataframe(
            df_full,
            use_container_width=True,
            hide_index=True,
            height=540,
            column_config={
                "Altitude (ft)": st.column_config.NumberColumn("Altitude (ft)", format="%,.0f"),
                "Speed (km/h)": st.column_config.NumberColumn("Speed (km/h)", format="%,.0f"),
                "Heading": st.column_config.NumberColumn("Heading", format="%.0f deg"),
            },
        )

        csv_bytes = df_full.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Export Portfolio Register (CSV)",
            data=csv_bytes,
            file_name="aerotrack_portfolio_register.csv",
            mime="text/csv",
        )

else:
    st.error("ERR_NO_DATA: Check tracking configuration parameters or API limits.")
