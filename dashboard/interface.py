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
# PAGE CONFIGURATION (SIDEBAR REMOVED)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AeroTrack // Aviation Operations & Fleet Telemetry",
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
# FLIGHTRADAR-STYLE JETLINER SVG ICON (BASE64 DATA URI FOR PYDECK ICONLAYER)
# -----------------------------------------------------------------------------
_AIRLINER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <path fill="#ffffff" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
</svg>"""
AIRLINER_ICON_URL = "data:image/svg+xml;base64," + base64.b64encode(_AIRLINER_SVG.encode("utf-8")).decode("ascii")

# -----------------------------------------------------------------------------
# LUFTHANSA TECHNIK / INDUSTRIAL AVIONICS STYLING & ANIMATIONS
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
        --bg-carbon: #0B0C0E;
        --bg-panel: #111317;
        --bg-elevated: #16191F;
        --bg-input: #1C2028;
        --border-hairline: #262B34;
        --border-active: #3F4654;
        --gold-primary: #FFB400;
        --gold-dim: rgba(255, 180, 0, 0.14);
        --titanium: #E5E7EB;
        --steel-muted: #8E95A2;
        --emerald-ok: #10B981;
        --copper-cargo: #F97316;
        --crimson-caution: #EF4444;
    }

    /* Hide Sidebar & Default Streamlit Chrome Completely */
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    button[kind="header"],
    #MainMenu,
    footer {
        display: none !important;
        visibility: hidden !important;
    }

    header[data-testid="stHeader"] {
        background: rgba(11, 12, 14, 0.85);
        border-bottom: 1px solid var(--border-hairline);
        height: 2.2rem;
    }

    /* Precision Keyframe Animations */
    @keyframes panelReveal {
        0%   { opacity: 0; transform: translateY(10px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    @keyframes horizonScan {
        0%   { transform: translateX(-100%); opacity: 0.2; }
        50%  { opacity: 1; }
        100% { transform: translateX(320%); opacity: 0.2; }
    }

    @keyframes signalEq {
        0%, 100% { transform: scaleY(0.35); opacity: 0.55; }
        50%      { transform: scaleY(1.0); opacity: 1.0; }
    }

    @keyframes barFill {
        0%   { transform: scaleX(0); }
        100% { transform: scaleX(1); }
    }

    @keyframes cautionPulse {
        0%, 100% { opacity: 1; }
        50%      { opacity: 0.45; }
    }

    /* Base App Canvas */
    .stApp {
        background-color: var(--bg-carbon);
        background-image:
            linear-gradient(rgba(255, 255, 255, 0.018) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.018) 1px, transparent 1px);
        background-size: 48px 48px;
        color: var(--titanium);
        font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        font-variant-numeric: tabular-nums;
    }

    .block-container {
        padding: 1.1rem 2rem 2.5rem 2rem;
        max-width: 100%;
    }

    /* Form Controls Restyled to Industrial Avionics */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        background-color: var(--bg-input) !important;
        border: 1px solid var(--border-hairline) !important;
        border-radius: 4px !important;
        color: var(--titanium) !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.82rem !important;
    }
    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="input"] > div:hover {
        border-color: var(--gold-primary) !important;
    }
    label[data-testid="stWidgetLabel"] p {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.68rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        color: var(--steel-muted) !important;
    }

    /* Action Buttons */
    div.stButton > button,
    div.stDownloadButton > button {
        background-color: var(--bg-input);
        color: var(--gold-primary);
        border: 1px solid rgba(255, 180, 0, 0.45);
        border-radius: 3px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.76rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        height: 40px;
        transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover {
        background-color: var(--gold-primary);
        color: #0B0C0E;
        border-color: var(--gold-primary);
        transform: translateY(-1px);
        box-shadow: 0 6px 18px rgba(255, 180, 0, 0.18);
    }

    /* Header Command Strip */
    .eng-header {
        position: relative;
        overflow: hidden;
        background: var(--bg-panel);
        border: 1px solid var(--border-hairline);
        border-top: 2px solid var(--gold-primary);
        border-radius: 4px;
        padding: 1.1rem 1.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        animation: panelReveal 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .eng-header::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 28%;
        height: 2px;
        background: linear-gradient(90deg, transparent, #FFF3C4, var(--gold-primary), transparent);
        animation: horizonScan 6s linear infinite;
    }
    .eng-brand-block {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .eng-mark {
        width: 40px;
        height: 40px;
        border: 1px solid rgba(255, 180, 0, 0.45);
        background: rgba(255, 180, 0, 0.08);
        border-radius: 3px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .eng-title {
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 1.55rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #FFFFFF;
        line-height: 1.1;
    }
    .eng-title span {
        color: var(--gold-primary);
        font-weight: 500;
        font-size: 0.95rem;
        letter-spacing: 0.14em;
        margin-left: 0.5rem;
    }
    .eng-sub {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.72rem;
        color: var(--steel-muted);
        letter-spacing: 0.09em;
        text-transform: uppercase;
        margin-top: 0.25rem;
    }

    /* Live Signal Equalizer Badge */
    .eng-status-group {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex-wrap: wrap;
    }
    .sys-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: var(--bg-elevated);
        border: 1px solid var(--border-hairline);
        padding: 0.42rem 0.8rem;
        border-radius: 3px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.72rem;
        letter-spacing: 0.06em;
        color: var(--titanium);
    }
    .eq-bars {
        display: inline-flex;
        align-items: flex-end;
        gap: 2px;
        height: 12px;
    }
    .eq-bar {
        width: 2.5px;
        height: 12px;
        background: var(--emerald-ok);
        transform-origin: bottom;
        animation: signalEq 1.2s ease-in-out infinite;
    }
    .eq-bar:nth-child(2) { animation-delay: 0.2s; height: 9px; }
    .eq-bar:nth-child(3) { animation-delay: 0.4s; height: 12px; }
    .eq-bar:nth-child(4) { animation-delay: 0.6s; height: 7px; }

    /* KPI Architectural Cards */
    .metric-tile {
        position: relative;
        background: var(--bg-panel);
        border: 1px solid var(--border-hairline);
        border-radius: 4px;
        padding: 1rem 1.15rem;
        margin-bottom: 0.9rem;
        overflow: hidden;
        transition: border-color 0.22s ease, transform 0.22s ease, background-color 0.22s ease;
        animation: panelReveal 0.55s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .metric-tile::after {
        content: "";
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        height: 2px;
        background: var(--gold-primary);
        transform: scaleX(0);
        transform-origin: left;
        transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
    }
    .metric-tile:hover {
        background: var(--bg-elevated);
        border-color: var(--border-active);
        transform: translateY(-2px);
    }
    .metric-tile:hover::after {
        transform: scaleX(1);
    }
    .metric-tile.caution::after { background: var(--crimson-caution); }
    .metric-tile.nominal::after { background: var(--emerald-ok); }
    .metric-tile.delay-1 { animation-delay: 0.04s; }
    .metric-tile.delay-2 { animation-delay: 0.10s; }
    .metric-tile.delay-3 { animation-delay: 0.16s; }
    .metric-tile.delay-4 { animation-delay: 0.22s; }

    .m-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.45rem;
    }
    .m-code {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.68rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: var(--steel-muted);
    }
    .m-tag {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.67rem;
        padding: 0.12rem 0.42rem;
        border-radius: 2px;
        border: 1px solid var(--border-hairline);
        color: var(--gold-primary);
        background: rgba(255, 180, 0, 0.08);
    }
    .m-tag.emerald { color: var(--emerald-ok); background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.25); }
    .m-tag.copper  { color: var(--copper-cargo); background: rgba(249, 115, 22, 0.08); border-color: rgba(249, 115, 22, 0.25); }
    .m-tag.crimson { color: var(--crimson-caution); background: rgba(239, 68, 68, 0.10); border-color: rgba(239, 68, 68, 0.3); }

    .m-val {
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 2.05rem;
        font-weight: 700;
        line-height: 1.05;
        color: #FFFFFF;
    }
    .m-sub {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.71rem;
        color: var(--steel-muted);
        margin-top: 0.45rem;
    }
    .m-bar-track {
        width: 100%;
        height: 3px;
        background: #20252E;
        margin-top: 0.55rem;
        border-radius: 1px;
        overflow: hidden;
    }
    .m-bar-fill {
        height: 100%;
        transform-origin: left;
        animation: barFill 0.9s cubic-bezier(0.16, 1, 0.3, 1) both;
    }

    /* Macro Strip */
    .macro-strip {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 0.75rem;
        background: var(--bg-panel);
        border: 1px solid var(--border-hairline);
        border-left: 3px solid var(--gold-primary);
        border-radius: 4px;
        padding: 0.8rem 1.15rem;
        margin-bottom: 1.1rem;
        animation: panelReveal 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.12s both;
    }
    .macro-cell {
        border-right: 1px solid var(--border-hairline);
        padding-right: 0.75rem;
    }
    .macro-cell:last-child { border-right: none; }
    .macro-k {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.64rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--steel-muted);
        margin-bottom: 0.2rem;
    }
    .macro-v {
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 0.96rem;
        font-weight: 600;
        color: #FFFFFF;
    }

    /* Section Headings */
    .sec-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid var(--border-hairline);
        padding-bottom: 0.45rem;
        margin: 0.5rem 0 0.85rem 0;
    }
    .sec-title {
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 0.98rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #FFFFFF;
    }
    .sec-ref {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        color: var(--steel-muted);
        letter-spacing: 0.06em;
    }

    /* Family Spotlight Grid */
    .mro-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 0.8rem;
        margin: 0.8rem 0 1.25rem 0;
    }
    .mro-box {
        background: var(--bg-panel);
        border: 1px solid var(--border-hairline);
        border-top: 2px solid var(--border-active);
        border-radius: 4px;
        padding: 0.9rem 1.05rem;
        transition: border-color 0.2s ease, transform 0.2s ease;
    }
    .mro-box:hover {
        border-top-color: var(--gold-primary);
        transform: translateY(-2px);
    }

    /* Tabs Styled Like Instrument Mode Selectors */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.35rem;
        background: var(--bg-panel);
        padding: 0.3rem;
        border: 1px solid var(--border-hairline);
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.76rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--steel-muted);
        border-radius: 3px;
        padding: 0.5rem 1.05rem;
        transition: all 0.18s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #FFFFFF;
        background: var(--bg-elevated);
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--gold-primary) !important;
        color: #0B0C0E !important;
        font-weight: 700 !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Clean Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-carbon); }
    ::-webkit-scrollbar-thumb { background: #2D333F; border-radius: 2px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--gold-primary); }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS (CORE LOGIC PRESERVED + HEADING EXTRACTION FOR AIRLINER ICONS)
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
        return "01. LOW / APPROACH (<10K FT)"
    if alt_ft < 28000:
        return "02. CLIMB / DESCENT (10K-28K)"
    if alt_ft < 36000:
        return "03. MID CRUISE (28K-36K)"
    if alt_ft <= 43000:
        return "04. HIGH CRUISE (36K-43K)"
    return "05. UPPER / STRATO (>43K FT)"

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
                    "flight_number": "MIL-OPS",
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
                        "flight_number": "MIL-OPS",
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
                reasons.append("TELEMETRY ANOMALY")
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
        apt_txt = f"{raw_apt} // {AIRPORT_MAP.get(raw_apt, 'Intl Hub')}"
        carrier_code = str(current.get("top_carrier", "UNKN")).upper()
        full_carrier_name = _airline_map.get(carrier_code, carrier_code)

        history_df = stats_df[["timestamp", "total_flights", "military_count", "threat_count"]].copy()
        history_df["timestamp"] = pd.to_datetime(history_df["timestamp"]).dt.strftime("%H:%M")
        history_df = history_df.set_index("timestamp").iloc[::-1]
        history_df.rename(
            columns={
                "total_flights": "Global Commercial Volume",
                "military_count": "Active State / Gov Assets",
                "threat_count": "Flagged Anomalies",
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
# PLOTLY INDUSTRIAL GRAPHITE CHART STYLING (ZERO BLUE / ZERO PURPLE)
# -----------------------------------------------------------------------------
def style_eng_chart(fig, height=320):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(17, 19, 23, 0.95)",
        plot_bgcolor="rgba(11, 12, 14, 0.85)",
        font=dict(color="#D1D5DB", family="IBM Plex Mono, monospace", size=11),
        margin=dict(l=14, r=20, t=26, b=16),
        transition={"duration": 500, "easing": "cubic-in-out"},
        hoverlabel=dict(
            bgcolor="#16191F",
            bordercolor="#FFB400",
            font=dict(color="#FFFFFF", family="IBM Plex Mono, monospace", size=11),
        ),
    )
    fig.update_xaxes(gridcolor="rgba(255, 255, 255, 0.05)", zeroline=False, linecolor="#262B34")
    fig.update_yaxes(gridcolor="rgba(255, 255, 255, 0.05)", zeroline=False, linecolor="#262B34")
    return fig

# -----------------------------------------------------------------------------
# DATA INGESTION
# -----------------------------------------------------------------------------
dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)
dynamic_airline_map["MIL"] = "State / Military Operator"

raw_df = fetch_global_fusion(client.api_key)
macro = get_macro_intelligence(dynamic_airline_map)
utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

if not raw_df.empty:
    # -------------------------------------------------------------------------
    # EXECUTIVE ENGINEERING HEADER
    # -------------------------------------------------------------------------
    st.markdown(
        f"""
        <div class="eng-header">
            <div class="eng-brand-block">
                <div class="eng-mark">
                    <svg width="22" height="22" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                        <path fill="#FFB400" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/>
                    </svg>
                </div>
                <div>
                    <div class="eng-title">AEROTRACK <span>FLEET TELEMETRY &amp; MRO INTELLIGENCE</span></div>
                    <div class="eng-sub">SYS.REF // GLOBAL ADS-B FUSION CORE &bull; AIRFRAME TAXONOMY &bull; ENVELOPE MONITORING</div>
                </div>
            </div>
            <div class="eng-status-group">
                <div class="sys-badge">
                    <div class="eq-bars">
                        <div class="eq-bar"></div>
                        <div class="eq-bar"></div>
                        <div class="eq-bar"></div>
                        <div class="eq-bar"></div>
                    </div>
                    STREAMING // {utc_now}
                </div>
                <div class="sys-badge">
                    SATVIK GOYAL &bull; @satvik-7773
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # INLINE OPERATIONS FILTER DECK (REPLACES SIDEBAR)
    # -------------------------------------------------------------------------
    f1, f2, f3, f4, f5 = st.columns([1.2, 1.4, 1.4, 1.3, 0.9], gap="small")

    with f1:
        class_filter = st.selectbox(
            "CLASSIFICATION",
            ["ALL ASSETS", "CIVILIAN ONLY", "MILITARY ONLY", "FLAGGED ANOMALIES"],
        )
    with f2:
        sector_list = ["GLOBAL (ALL)"] + sorted(list(raw_df["sector"].unique()))
        region_filter = st.selectbox("AIRSPACE SECTOR", sector_list)
    with f3:
        min_alt = int(raw_df["baro_altitude"].fillna(0).min())
        max_alt = int(raw_df["baro_altitude"].fillna(0).max())
        if min_alt >= max_alt:
            max_alt = min_alt + 1000
        alt_filter = st.slider(
            "ALTITUDE ENVELOPE (FT)",
            min_value=min_alt,
            max_value=max_alt,
            value=(min_alt, max_alt),
            step=1000,
        )
    with f4:
        search_query = st.text_input("CALLSIGN / HEX / ICAO TYPE", placeholder="FILTER E.G. DLH, A359, 3C6...")
    with f5:
        st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)
        if st.button("RESYNC FEED", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Apply Inline Filters
    df = raw_df.copy()
    if class_filter == "CIVILIAN ONLY":
        df = df[df["Classification"] == "CIVILIAN"]
    elif class_filter == "MILITARY ONLY":
        df = df[df["Classification"] == "MILITARY"]
    elif class_filter == "FLAGGED ANOMALIES":
        df = df[df["Classification"] == "ANOMALY"]

    if region_filter != "GLOBAL (ALL)":
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

    # Compute Operational KPIs
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
    active_airframes = df[df["aircraft_type"] != "UNKN"]["aircraft_type"].nunique() if total_active > 0 else 0

    # -------------------------------------------------------------------------
    # PRIMARY TELEMETRY KPI TILES
    # -------------------------------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
            <div class="metric-tile delay-1">
                <div class="m-head">
                    <span class="m-code">TRACKED AIRFRAMES</span>
                    <span class="m-tag emerald">NEXT-GEN {nextgen_pct:.1f}%</span>
                </div>
                <div class="m-val">{total_active:,}</div>
                <div class="m-sub">AVG CRUISE: {avg_speed:,.0f} KM/H &bull; FL{int(avg_alt/100):03d} &bull; {active_airframes} TYPES</div>
                <div class="m-bar-track"><div class="m-bar-fill" style="width:{min(nextgen_pct, 100):.1f}%; background:#10B981;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        st.markdown(
            f"""
            <div class="metric-tile delay-2">
                <div class="m-head">
                    <span class="m-code">COMMERCIAL OPERATIONS</span>
                    <span class="m-tag">{civ_pct:.1f}% SHARE</span>
                </div>
                <div class="m-val" style="color:#FFB400;">{civ_cnt:,}</div>
                <div class="m-sub">ACTIVE OPERATORS: {active_carriers:,} AIRLINE CODES</div>
                <div class="m-bar-track"><div class="m-bar-fill" style="width:{min(civ_pct, 100):.1f}%; background:#FFB400;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
            <div class="metric-tile delay-3">
                <div class="m-head">
                    <span class="m-code">STATE &amp; DEFENSE TRAFFIC</span>
                    <span class="m-tag copper">{mil_pct:.1f}% SHARE</span>
                </div>
                <div class="m-val" style="color:#F97316;">{mil_cnt:,}</div>
                <div class="m-sub">SOURCE: ADSB.LOL MIL + ICAO STATE REGISTRY</div>
                <div class="m-bar-track"><div class="m-bar-fill" style="width:{min(mil_pct * 3, 100):.1f}%; background:#F97316;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        st.markdown(
            f"""
            <div class="metric-tile caution delay-4">
                <div class="m-head">
                    <span class="m-code">ENVELOPE ANOMALIES</span>
                    <span class="m-tag crimson">{anom_pct:.2f}% RATE</span>
                </div>
                <div class="m-val" style="color:{'#EF4444' if anom_cnt > 0 else '#10B981'};">{anom_cnt:,}</div>
                <div class="m-sub">CEILING / OVERSPEED / TELEMETRY INTEGRITY</div>
                <div class="m-bar-track"><div class="m-bar-fill" style="width:{min(anom_pct * 10, 100):.1f}%; background:#EF4444;"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # MACRO INTELLIGENCE TELEMETRY STRIP
    # -------------------------------------------------------------------------
    if macro:
        delta_val = float(macro["density_delta"].strip("%"))
        delta_col = "#10B981" if delta_val >= 0 else "#EF4444"
        st.markdown(
            f"""
            <div class="macro-strip">
                <div class="macro-cell">
                    <div class="macro-k">GLOBAL ASSET DENSITY</div>
                    <div class="macro-v">{macro['density']} <span style="color:{delta_col}; font-family:'IBM Plex Mono',monospace; font-size:0.78rem;">[{macro['density_delta']}]</span></div>
                </div>
                <div class="macro-cell">
                    <div class="macro-k">MACRO ANOMALY INDEX</div>
                    <div class="macro-v" style="color:#EF4444;">{macro['threat_pct']}</div>
                </div>
                <div class="macro-cell">
                    <div class="macro-k">STATE / GOV INDEX</div>
                    <div class="macro-v" style="color:#F97316;">{macro['mil_pct']}</div>
                </div>
                <div class="macro-cell">
                    <div class="macro-k">PEAK TRAFFIC ZONE</div>
                    <div class="macro-v" style="color:#FFB400;">{macro['region']}</div>
                </div>
                <div class="macro-cell">
                    <div class="macro-k">PRIMARY GLOBAL HUB</div>
                    <div class="macro-v">{macro['airport']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # WORKSPACE NAVIGATION TABS
    # -------------------------------------------------------------------------
    tab_globe, tab_ops, tab_mro, tab_log = st.tabs([
        "01 // 3D GLOBAL TRAFFIC & TRENDS",
        "02 // OPERATORS, CARGO & ENVELOPE",
        "03 // AIRFRAME MRO & REGIONAL HHI",
        "04 // FLIGHT TELEMETRY LOG",
    ])

    # =========================================================================
    # TAB 1: 3D GLOBE WITH REAL AIRLINER MARKERS + 24H TRENDLINE
    # =========================================================================
    with tab_globe:
        st.markdown(
            f"""
            <div class="sec-bar">
                <div class="sec-title">3D Global Airspace Traffic — Live Vector Layer</div>
                <div class="sec-ref">
                    <span style="color:#FFB400;">COMMERCIAL</span> &bull;
                    <span style="color:#F97316;">STATE / MIL</span> &bull;
                    <span style="color:#EF4444;">ANOMALY</span> &nbsp;|&nbsp;
                    {len(df):,} ACTIVE AIRFRAMES
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if df.empty:
            st.info("No aircraft match the current filter criteria.")
        else:
            def assign_aircraft_color(cls):
                if cls == "ANOMALY":
                    return [239, 68, 68, 250]     # Caution Crimson
                elif cls == "MILITARY":
                    return [249, 115, 22, 240]    # Defense Copper
                return [255, 180, 0, 230]         # Lufthansa Aviation Gold

            map_df = df.copy()
            map_df["color"] = map_df["Classification"].apply(assign_aircraft_color)
            map_df["angle"] = (360.0 - map_df["heading"].fillna(0.0)) % 360.0
            map_df["icon_size"] = np.where(
                map_df["Classification"] == "ANOMALY",
                24,
                np.where(map_df["Classification"] == "MILITARY", 20, 16),
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
                size_max_pixels=26,
                get_angle="angle",
                get_color="color",
                billboard=False,
                pickable=True,
            )

            st.pydeck_chart(
                pdk.Deck(
                    layers=[airliner_layer],
                    initial_view_state=pdk.ViewState(
                        latitude=24,
                        longitude=8,
                        zoom=1.65,
                        pitch=42,
                        bearing=0,
                    ),
                    tooltip={
                        "html": """
                            <div style="font-family: 'IBM Plex Mono', monospace; padding: 6px 4px; min-width: 190px;">
                                <div style="display:flex; justify-content:space-between; border-bottom:1px solid #262B34; padding-bottom:4px; margin-bottom:5px;">
                                    <strong style="color:#FFB400; font-size:12px;">{callsign}</strong>
                                    <span style="color:#8E95A2; font-size:11px;">{icao24}</span>
                                </div>
                                <div style="color:#E5E7EB; font-size:11px; margin-bottom:4px;">
                                    {aircraft_type} &bull; {Family} ({Generation})
                                </div>
                                <div style="color:#9CA3AF; font-size:11px;">
                                    ALT: <span style="color:#FFFFFF;">{baro_altitude_fmt} FT</span> &nbsp;|&nbsp;
                                    SPD: <span style="color:#FFFFFF;">{velocity_fmt} KM/H</span>
                                </div>
                                <div style="color:#9CA3AF; font-size:11px; margin-top:2px;">
                                    HDG: <span style="color:#FFFFFF;">{heading_fmt}°</span> &nbsp;|&nbsp;
                                    STS: <span style="color:#FFB400; font-weight:600;">{Classification}</span>
                                </div>
                            </div>
                        """,
                        "style": {
                            "backgroundColor": "#111317",
                            "border": "1px solid #FFB400",
                            "borderRadius": "3px",
                            "boxShadow": "0 8px 24px rgba(0,0,0,0.65)",
                        },
                    },
                    map_style="mapbox://styles/mapbox/dark-v11",
                ),
                use_container_width=True,
            )

        # 24-Hour Global Flight & Anomaly Volume Trendline
        if macro and macro.get("history_df") is not None and not macro["history_df"].empty:
            hist = macro["history_df"]
            st.markdown(
                """
                <div class="sec-bar" style="margin-top: 1.25rem;">
                    <div class="sec-title">24-Hour Global Fleet Volume &amp; Anomaly Trendline</div>
                    <div class="sec-ref">HISTORICAL TELEMETRY SERIES // SUPABASE</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            trend_fig = make_subplots(specs=[[{"secondary_y": True}]])
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Global Commercial Volume"],
                    name="Global Commercial Volume",
                    mode="lines",
                    line=dict(color="#FFB400", width=2.5, shape="spline"),
                    fill="tozeroy",
                    fillcolor="rgba(255, 180, 0, 0.10)",
                ),
                secondary_y=False,
            )
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Active State / Gov Assets"],
                    name="State / Gov Assets",
                    mode="lines+markers",
                    line=dict(color="#E5E7EB", width=1.8, shape="spline"),
                    marker=dict(size=4),
                ),
                secondary_y=True,
            )
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Flagged Anomalies"],
                    name="Flagged Anomalies",
                    mode="lines+markers",
                    line=dict(color="#EF4444", width=1.8, shape="spline"),
                    marker=dict(size=4),
                ),
                secondary_y=True,
            )
            style_eng_chart(trend_fig, height=290)
            trend_fig.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified",
            )
            trend_fig.update_yaxes(title_text="Commercial Flights", secondary_y=False, title_font=dict(size=10, color="#FFB400"))
            trend_fig.update_yaxes(title_text="State / Anomalies", secondary_y=True, showgrid=False, title_font=dict(size=10, color="#E5E7EB"))
            st.plotly_chart(trend_fig, use_container_width=True)

    # =========================================================================
    # TAB 2: OPERATORS, CARGO, OEM SHARE & OPERATIONAL FLIGHT ENVELOPE
    # =========================================================================
    with tab_ops:
        if df.empty:
            st.info("No aircraft data available for the selected filters.")
        else:
            r1_c1, r1_c2 = st.columns(2, gap="medium")

            with r1_c1:
                st.markdown(
                    """
                    <div class="sec-bar">
                        <div class="sec-title">Top 10 Commercial Carriers</div>
                        <div class="sec-ref">ACTIVE AIRBORNE FLEET</div>
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
                        color_continuous_scale=["#78530A", "#D97706", "#FFB400"],
                    )
                    fig_al.update_traces(textposition="outside", marker_line_width=0)
                    style_eng_chart(fig_al, height=330)
                    fig_al.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Aircraft")
                    st.plotly_chart(fig_al, use_container_width=True)
                else:
                    st.info("Insufficient commercial airline data in current filter.")

            with r1_c2:
                st.markdown(
                    """
                    <div class="sec-bar">
                        <div class="sec-title">OEM Manufacturer Market Share</div>
                        <div class="sec-ref">GLOBAL FLEET DISTRIBUTION</div>
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
                        color_discrete_sequence=["#FFB400", "#E5E7EB", "#F97316", "#10B981", "#9CA3AF", "#D97706", "#52525B", "#EF4444"],
                    )
                    fig_oem.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                        marker=dict(line=dict(color="#111317", width=2)),
                    )
                    style_eng_chart(fig_oem, height=330)
                    fig_oem.update_layout(showlegend=False)
                    st.plotly_chart(fig_oem, use_container_width=True)
                else:
                    st.info("No manufacturer classification data available.")

            r2_c1, r2_c2 = st.columns(2, gap="medium")

            with r2_c1:
                st.markdown(
                    """
                    <div class="sec-bar">
                        <div class="sec-title">Active Cargo &amp; Freighter Operators</div>
                        <div class="sec-ref">DEDICATED LOGISTICS</div>
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
                        color_continuous_scale=["#7C2D12", "#EA580C", "#FB923C"],
                    )
                    fig_cg.update_traces(textposition="outside", marker_line_width=0)
                    style_eng_chart(fig_cg, height=330)
                    fig_cg.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Freighters")
                    st.plotly_chart(fig_cg, use_container_width=True)
                else:
                    st.info("No dedicated cargo operators detected in current filter.")

            with r2_c2:
                st.markdown(
                    """
                    <div class="sec-bar">
                        <div class="sec-title">Top 10 Deployed Aircraft Families</div>
                        <div class="sec-ref">AIRFRAME UTILIZATION</div>
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
                        color_continuous_scale=["#065F46", "#059669", "#10B981"],
                    )
                    fig_fm.update_traces(textposition="outside", marker_line_width=0)
                    style_eng_chart(fig_fm, height=330)
                    fig_fm.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Airframes")
                    st.plotly_chart(fig_fm, use_container_width=True)
                else:
                    st.info("Insufficient airframe family data.")

            # Additional Informative Aerospace Operations Row: Flight Envelope & Flight Level Bands
            r3_c1, r3_c2 = st.columns(2, gap="medium")

            with r3_c1:
                st.markdown(
                    """
                    <div class="sec-bar">
                        <div class="sec-title">Operational Flight Envelope (Speed vs. Altitude)</div>
                        <div class="sec-ref">ENVELOPE INTEGRITY ANALYSIS</div>
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
                        "CIVILIAN": "rgba(255, 180, 0, 0.50)",
                        "MILITARY": "#F97316",
                        "ANOMALY": "#EF4444",
                    },
                    hover_name="callsign",
                    hover_data=["icao24", "aircraft_type", "Threat_Reason"],
                    labels={"velocity": "Ground Speed (km/h)", "baro_altitude": "Barometric Altitude (ft)"},
                )
                style_eng_chart(fig_env, height=310)
                fig_env.update_layout(legend=dict(orientation="h", y=1.08, x=0, title=None))
                st.plotly_chart(fig_env, use_container_width=True)

            with r3_c2:
                st.markdown(
                    """
                    <div class="sec-bar">
                        <div class="sec-title">Vertical Airspace Distribution (Flight Level Bands)</div>
                        <div class="sec-ref">TRAFFIC STRATIFICATION</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                band_series = df["baro_altitude"].apply(get_altitude_band).value_counts().sort_index()
                band_df = band_series.reset_index()
                band_df.columns = ["Altitude Band", "Aircraft"]
                fig_band = px.bar(
                    band_df,
                    x="Altitude Band",
                    y="Aircraft",
                    text="Aircraft",
                    color="Aircraft",
                    color_continuous_scale=["#3F4654", "#D97706", "#FFB400"],
                )
                fig_band.update_traces(textposition="outside", marker_line_width=0)
                style_eng_chart(fig_band, height=310)
                fig_band.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Active Aircraft")
                st.plotly_chart(fig_band, use_container_width=True)

    # =========================================================================
    # TAB 3: AIRFRAME MRO TAXONOMY & REGIONAL CONCENTRATION (HHI)
    # =========================================================================
    with tab_mro:
        st.markdown(
            """
            <div class="sec-bar">
                <div class="sec-title">Airframe Family MRO &amp; Fleet Modernization Profile</div>
                <div class="sec-ref">ACTIVE ASSET FAMILY INSPECTOR</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        available_families = sorted([f for f in raw_df["Family"].unique() if f != "Other / Unclassified"])
        if available_families:
            selected_family = st.selectbox("SELECT AIRCRAFT ASSET FAMILY", available_families)
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
                <div class="mro-grid">
                    <div class="mro-box">
                        <div class="macro-k">ACTIVE AIRFRAMES</div>
                        <div style="font-size:1.55rem; font-weight:700; color:#FFB400;">
                            {fam_active:,} <span style="font-size:0.85rem; color:#8E95A2; font-weight:500;">({fam_share:.1f}% GLOBAL)</span>
                        </div>
                    </div>
                    <div class="mro-box">
                        <div class="macro-k">GLOBAL OPERATORS</div>
                        <div style="font-size:1.55rem; font-weight:700; color:#FFFFFF;">{fam_ops} AIRLINES</div>
                    </div>
                    <div class="mro-box">
                        <div class="macro-k">DOMINANT OPERATING ZONE</div>
                        <div style="font-size:1.15rem; font-weight:700; color:#E5E7EB; margin-top:0.25rem;">{top_fam_region}</div>
                    </div>
                    <div class="mro-box">
                        <div class="macro-k">PRIMARY OPERATOR / NEXT-GEN MIX</div>
                        <div style="font-size:1.05rem; font-weight:700; color:#10B981; margin-top:0.25rem;">
                            {top_op_name} ({top_op_code}) &bull; {fam_nextgen:.0f}% NG
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            mro_c1, mro_c2 = st.columns([1.4, 1.0], gap="medium")
            with mro_c1:
                fam_sec = fam_df["sector"].value_counts().reset_index()
                fam_sec.columns = ["Zone", "Flights"]
                fig_fsec = px.bar(
                    fam_sec,
                    x="Zone",
                    y="Flights",
                    text="Flights",
                    color="Flights",
                    color_continuous_scale=["#3F4654", "#D97706", "#FFB400"],
                    title=f"{selected_family.upper()} — GEOGRAPHIC DEPLOYMENT",
                )
                fig_fsec.update_traces(textposition="outside", marker_line_width=0)
                style_eng_chart(fig_fsec, height=285)
                fig_fsec.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Airframes")
                st.plotly_chart(fig_fsec, use_container_width=True)

            with mro_c2:
                oem_ng = raw_df[raw_df["Manufacturer"] != "Other / Unclassified"].groupby(["Manufacturer", "Generation"]).size().reset_index(name="Count")
                fig_ng = px.bar(
                    oem_ng,
                    x="Manufacturer",
                    y="Count",
                    color="Generation",
                    barmode="stack",
                    color_discrete_map={"Next-Gen": "#10B981", "Legacy": "#52525B"},
                    title="OEM FLEET MODERNIZATION (NEXT-GEN VS LEGACY)",
                )
                style_eng_chart(fig_ng, height=285)
                fig_ng.update_layout(xaxis_title="", yaxis_title="Airframes", legend=dict(orientation="h", y=1.08, x=0, title=None))
                st.plotly_chart(fig_ng, use_container_width=True)

        st.markdown(
            """
            <div class="sec-bar" style="margin-top: 0.75rem;">
                <div class="sec-title">Regional Asset Concentration &amp; Herfindahl-Hirschman Index (HHI)</div>
                <div class="sec-ref">SECTOR COMPETITIVE BENCHMARK</div>
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
                    conc_status = "HIGHLY CONCENTRATED"
                elif hhi > 1500:
                    conc_status = "MODERATELY CONCENTRATED"
                else:
                    conc_status = "HIGHLY COMPETITIVE"
                top_c = carrier_counts.index[0]
                top_c_str = f"{dynamic_airline_map.get(top_c, top_c)} ({top_c})"
            else:
                conc_status = "N/A (CHARTER / STATE)"
                top_c_str = "NONE / CHARTER"

            top_fam = sector_df["Family"].mode()[0] if not sector_df.empty else "UNKN"
            ng_share = (sector_df["Generation"] == "Next-Gen").mean() * 100 if sec_tracks > 0 else 0.0

            regional_data.append({
                "Airspace Sector": sector_name,
                "Active Tracks": sec_tracks,
                "Deployment Share (%)": round(fleet_share_idx, 1),
                "Next-Gen Mix (%)": round(ng_share, 1),
                "Market Concentration": conc_status,
                "Dominant Carrier": top_c_str,
                "Dominant Family": top_fam,
            })

        df_regional = pd.DataFrame(regional_data).sort_values(by="Active Tracks", ascending=False)
        st.dataframe(
            df_regional,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Active Tracks": st.column_config.NumberColumn("Active Tracks", format="%d"),
                "Deployment Share (%)": st.column_config.ProgressColumn("Global Share", min_value=0.0, max_value=100.0, format="%.1f%%"),
                "Next-Gen Mix (%)": st.column_config.ProgressColumn("Next-Gen %", min_value=0.0, max_value=100.0, format="%.1f%%"),
            },
        )

    # =========================================================================
    # TAB 4: LIVE FLIGHT TELEMETRY LOG
    # =========================================================================
    with tab_log:
        st.markdown(
            f"""
            <div class="sec-bar">
                <div class="sec-title">Aircraft Intelligence &amp; Telemetry Registry</div>
                <div class="sec-ref">PRIORITY SORTED &bull; {len(df):,} ACTIVE RECORDS</div>
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
                "Classification": "Status",
                "icao24": "Hex ID",
                "callsign": "Callsign",
                "flight_number": "Flight No.",
                "airline_code": "Carrier",
                "aircraft_type": "Model",
                "Family": "Airframe Family",
                "Body Type": "Body Class",
                "Generation": "Gen",
                "sector": "Region",
                "baro_altitude": "Alt (ft)",
                "velocity": "Speed (km/h)",
                "heading": "Hdg (deg)",
                "Threat_Reason": "Envelope Flags",
            },
            inplace=True,
        )

        if "Carrier" in df_full.columns:
            df_full.insert(
                df_full.columns.get_loc("Carrier") + 1,
                "Airline Name",
                df_full["Carrier"].map(dynamic_airline_map).fillna("Unknown / Charter"),
            )

        st.dataframe(
            df_full,
            use_container_width=True,
            hide_index=True,
            height=540,
            column_config={
                "Alt (ft)": st.column_config.NumberColumn("Alt (ft)", format="%,.0f"),
                "Speed (km/h)": st.column_config.NumberColumn("Speed (km/h)", format="%,.0f"),
                "Hdg (deg)": st.column_config.NumberColumn("Hdg (deg)", format="%.0f°"),
            },
        )

        csv_bytes = df_full.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="EXPORT FILTERED TELEMETRY (CSV)",
            data=csv_bytes,
            file_name="aerotrack_telemetry_export.csv",
            mime="text/csv",
        )

else:
    st.error("ERR_NO_DATA: Check tracking configuration parameters or API limits.")
