import sys
import os
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
# PAGE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AeroTrack // Global Aviation Intelligence",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
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
# MODERN AURORA GLASSMORPHISM & ANIMATION CSS
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --bg-base: #060913;
        --glass-bg: rgba(15, 23, 42, 0.56);
        --glass-bg-hover: rgba(20, 30, 54, 0.72);
        --glass-border: rgba(148, 163, 184, 0.14);
        --glass-border-bright: rgba(56, 189, 248, 0.35);
        --accent-sky: #38bdf8;
        --accent-indigo: #818cf8;
        --accent-teal: #2dd4bf;
        --accent-amber: #fbbf24;
        --accent-rose: #fb7185;
        --text-main: #f1f5f9;
        --text-muted: #94a3b8;
    }

    /* Keyframe Animations */
    @keyframes auroraDrift {
        0%   { background-position: 0% 50%, 100% 0%, 50% 100%; }
        50%  { background-position: 100% 50%, 0% 100%, 50% 0%; }
        100% { background-position: 0% 50%, 100% 0%, 50% 100%; }
    }

    @keyframes fadeSlideUp {
        0% {
            opacity: 0;
            transform: translateY(14px) scale(0.99);
        }
        100% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    @keyframes shimmerBeam {
        0%   { transform: translateX(-100%); }
        100% { transform: translateX(200%); }
    }

    @keyframes liveRipple {
        0%   { transform: scale(0.9); opacity: 0.9; }
        70%  { transform: scale(2.1); opacity: 0; }
        100% { transform: scale(2.1); opacity: 0; }
    }

    /* Main App Canvas with Subtle Moving Aurora Mesh */
    .stApp {
        background-color: var(--bg-base);
        background-image:
            radial-gradient(circle at 12% 18%, rgba(56, 189, 248, 0.10) 0%, transparent 42%),
            radial-gradient(circle at 86% 12%, rgba(129, 140, 248, 0.10) 0%, transparent 40%),
            radial-gradient(circle at 55% 88%, rgba(45, 212, 191, 0.07) 0%, transparent 45%);
        background-size: 140% 140%;
        animation: auroraDrift 22s ease-in-out infinite;
        color: var(--text-main);
        font-family: 'Inter', sans-serif;
    }

    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] {
        background: rgba(6, 9, 19, 0.55);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    }

    .block-container {
        padding: 1.4rem 2.2rem 2.5rem 2.2rem;
        max-width: 100%;
    }

    /* Sidebar Glass Panel */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(10, 15, 29, 0.96) 0%, rgba(7, 11, 22, 0.98) 100%);
        border-right: 1px solid var(--glass-border);
        backdrop-filter: blur(16px);
    }

    /* Primary Buttons */
    div.stButton > button {
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.16), rgba(129, 140, 248, 0.18));
        color: #f8fafc;
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 10px;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 0.9rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        height: 44px;
        transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
    }
    div.stButton > button:hover {
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.32), rgba(129, 140, 248, 0.34));
        border-color: var(--accent-sky);
        transform: translateY(-1px);
        box-shadow: 0 8px 24px rgba(56, 189, 248, 0.22);
        color: #ffffff;
    }

    /* Hero Banner */
    .hero-shell {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.78) 0%, rgba(15, 23, 42, 0.48) 100%);
        backdrop-filter: blur(18px);
        border: 1px solid var(--glass-border);
        border-radius: 16px;
        padding: 1.25rem 1.65rem;
        margin-bottom: 1.25rem;
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
        animation: fadeSlideUp 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .hero-shell::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 45%;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--accent-sky), var(--accent-indigo), transparent);
        animation: shimmerBeam 5.5s ease-in-out infinite;
    }
    .brand-row {
        display: flex;
        align-items: center;
        gap: 0.85rem;
    }
    .brand-logo {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.35rem;
        box-shadow: 0 6px 20px rgba(56, 189, 248, 0.35);
    }
    .brand-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.85rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        background: linear-gradient(90deg, #ffffff 0%, #bae6fd 55%, #c7d2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        line-height: 1.1;
    }
    .brand-sub {
        font-size: 0.8rem;
        color: var(--text-muted);
        letter-spacing: 0.04em;
        margin-top: 0.2rem;
    }

    .hero-meta {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex-wrap: wrap;
    }
    .live-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        padding: 0.42rem 0.9rem;
        border-radius: 999px;
        background: rgba(45, 212, 191, 0.10);
        border: 1px solid rgba(45, 212, 191, 0.28);
        color: #5eead4;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        font-weight: 500;
    }
    .live-dot-wrap {
        position: relative;
        width: 9px;
        height: 9px;
    }
    .live-dot-core {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        background: #2dd4bf;
    }
    .live-dot-ring {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        background: #2dd4bf;
        animation: liveRipple 2s cubic-bezier(0.22, 1, 0.36, 1) infinite;
    }
    .author-pill {
        padding: 0.42rem 0.9rem;
        border-radius: 999px;
        background: rgba(148, 163, 184, 0.08);
        border: 1px solid var(--glass-border);
        color: #cbd5e1;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.74rem;
    }

    /* Bento KPI Cards */
    .kpi-card {
        position: relative;
        background: var(--glass-bg);
        backdrop-filter: blur(16px);
        border: 1px solid var(--glass-border);
        border-radius: 14px;
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.28s ease, box-shadow 0.28s ease, background 0.28s ease;
        animation: fadeSlideUp 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        background: var(--glass-bg-hover);
        border-color: var(--glass-border-bright);
        box-shadow: 0 14px 32px rgba(2, 6, 23, 0.55);
    }
    .kpi-card.delay-1 { animation-delay: 0.05s; }
    .kpi-card.delay-2 { animation-delay: 0.12s; }
    .kpi-card.delay-3 { animation-delay: 0.19s; }
    .kpi-card.delay-4 { animation-delay: 0.26s; }

    .kpi-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.55rem;
    }
    .kpi-label {
        font-size: 0.74rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-muted);
    }
    .kpi-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.68rem;
        padding: 0.16rem 0.5rem;
        border-radius: 6px;
        background: rgba(56, 189, 248, 0.12);
        color: var(--accent-sky);
    }
    .kpi-badge.amber { background: rgba(251, 191, 36, 0.12); color: var(--accent-amber); }
    .kpi-badge.rose  { background: rgba(251, 113, 133, 0.14); color: var(--accent-rose); }
    .kpi-badge.teal  { background: rgba(45, 212, 191, 0.12); color: var(--accent-teal); }

    .kpi-value {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2.15rem;
        font-weight: 700;
        line-height: 1.05;
        color: #ffffff;
    }
    .kpi-foot {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.73rem;
        color: var(--text-muted);
        margin-top: 0.5rem;
    }

    /* Macro Ribbon */
    .macro-ribbon {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
        gap: 0.75rem;
        background: rgba(15, 23, 42, 0.45);
        backdrop-filter: blur(14px);
        border: 1px solid var(--glass-border);
        border-radius: 14px;
        padding: 0.9rem 1.25rem;
        margin-bottom: 1.25rem;
        animation: fadeSlideUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.15s both;
    }
    .macro-item {
        border-right: 1px solid rgba(148, 163, 184, 0.1);
        padding-right: 0.75rem;
    }
    .macro-item:last-child {
        border-right: none;
    }
    .macro-k {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-muted);
        margin-bottom: 0.2rem;
    }
    .macro-v {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.02rem;
        font-weight: 600;
        color: #f8fafc;
    }

    /* Section Header */
    .section-head {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin: 0.5rem 0 0.9rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }
    .section-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.15rem;
        font-weight: 600;
        color: #f8fafc;
        letter-spacing: -0.01em;
    }
    .section-caption {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        color: var(--text-muted);
    }

    /* Glass Container Card for Family Spotlight */
    .spotlight-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 0.85rem;
        margin: 0.85rem 0 1.4rem 0;
    }
    .spotlight-box {
        background: linear-gradient(145deg, rgba(56, 189, 248, 0.08), rgba(129, 140, 248, 0.05));
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 12px;
        padding: 0.95rem 1.1rem;
        transition: transform 0.22s ease, border-color 0.22s ease;
    }
    .spotlight-box:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.48);
    }

    /* Pill Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
        background: rgba(15, 23, 42, 0.55);
        backdrop-filter: blur(12px);
        padding: 0.4rem;
        border-radius: 12px;
        border: 1px solid var(--glass-border);
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 0.88rem;
        font-weight: 600;
        color: var(--text-muted);
        border-radius: 8px;
        padding: 0.5rem 1.1rem;
        transition: all 0.2s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #f8fafc;
        background: rgba(148, 163, 184, 0.08);
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.22), rgba(129, 140, 248, 0.22)) !important;
        color: #ffffff !important;
        border: 1px solid rgba(56, 189, 248, 0.4) !important;
        box-shadow: 0 4px 16px rgba(56, 189, 248, 0.14);
    }

    /* Clean Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.25); border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent-sky); }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS (CORE LOGIC PRESERVED)
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
        apt_txt = f"{raw_apt} · {AIRPORT_MAP.get(raw_apt, 'Intl Hub')}"
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
# PLOTLY THEME HELPER
# -----------------------------------------------------------------------------
def style_plotly(fig, height=320):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15, 23, 42, 0.35)",
        font=dict(color="#cbd5e1", family="Inter, sans-serif", size=12),
        margin=dict(l=12, r=18, t=22, b=16),
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.95)",
            bordercolor="rgba(56, 189, 248, 0.45)",
            font=dict(color="#f8fafc", family="JetBrains Mono, monospace", size=12),
        ),
    )
    fig.update_xaxes(gridcolor="rgba(148, 163, 184, 0.08)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(148, 163, 184, 0.08)", zeroline=False)
    return fig

# -----------------------------------------------------------------------------
# FETCH LIVE DATA
# -----------------------------------------------------------------------------
dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)
dynamic_airline_map["MIL"] = "State / Military Operator"

raw_df = fetch_global_fusion(client.api_key)
macro = get_macro_intelligence(dynamic_airline_map)

if not raw_df.empty:
    # -------------------------------------------------------------------------
    # SIDEBAR WORKSPACE CONTROLS
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 0.4rem 0 0.8rem 0; border-bottom: 1px solid rgba(148,163,184,0.14); margin-bottom: 1rem;">
                <div style="font-family:'Space Grotesk',sans-serif; font-size:1.15rem; font-weight:700; color:#f8fafc;">
                    ✈️ Flight Deck Controls
                </div>
                <div style="font-size:0.75rem; color:#94a3b8; margin-top:0.15rem;">
                    Global telemetry filters &amp; viewport
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        class_filter = st.radio(
            "Asset Classification",
            ["ALL ASSETS", "CIVILIAN ONLY", "MILITARY ONLY", "FLAGGED ANOMALIES"],
        )

        sector_list = ["GLOBAL (ALL)"] + sorted(list(raw_df["sector"].unique()))
        region_filter = st.selectbox("Geographic Zone", sector_list)

        min_alt = int(raw_df["baro_altitude"].fillna(0).min())
        max_alt = int(raw_df["baro_altitude"].fillna(0).max())
        if min_alt >= max_alt:
            max_alt = min_alt + 1000
        alt_filter = st.slider(
            "Altitude Envelope (ft)",
            min_value=min_alt,
            max_value=max_alt,
            value=(min_alt, max_alt),
            step=1000,
        )

        search_query = st.text_input("Search Callsign / Hex / Carrier", placeholder="e.g. DAL, A359, 4ca...")

        st.markdown("---")
        map_pitch = st.toggle("3D Globe Perspective", value=True, help="Tilts the global map for atmospheric depth.")

        if st.button("✨ Refresh Global Telemetry", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Apply Filters
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

    # Compute KPI Metrics
    total_active = len(df)
    civilian_cnt = int((df["Classification"] == "CIVILIAN").sum())
    mil_cnt = int((df["military"] == True).sum())
    anom_cnt = int((df["Classification"] == "ANOMALY").sum())
    nextgen_pct = (df["Generation"] == "Next-Gen").mean() * 100 if total_active > 0 else 0.0
    avg_speed = df["velocity"].mean() if total_active > 0 else 0.0
    avg_alt = df["baro_altitude"].mean() if total_active > 0 else 0.0
    anom_rate = (anom_cnt / total_active * 100) if total_active > 0 else 0.0
    mil_rate = (mil_cnt / total_active * 100) if total_active > 0 else 0.0

    # -------------------------------------------------------------------------
    # HERO HEADER BANNER
    # -------------------------------------------------------------------------
    st.markdown(
        f"""
        <div class="hero-shell">
            <div class="brand-row">
                <div class="brand-logo">✈️</div>
                <div>
                    <div class="brand-title">AEROTRACK</div>
                    <div class="brand-sub">Global Aviation Telemetry, Fleet Taxonomy &amp; Airspace Analytics</div>
                </div>
            </div>
            <div class="hero-meta">
                <div class="live-pill">
                    <div class="live-dot-wrap">
                        <div class="live-dot-ring"></div>
                        <div class="live-dot-core"></div>
                    </div>
                    LIVE GLOBAL FUSION
                </div>
                <div class="author-pill">SATVIK GOYAL &bull; @satvik-7773</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # BENTO KPI ROW
    # -------------------------------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
            <div class="kpi-card delay-1">
                <div class="kpi-top">
                    <span class="kpi-label">Active Aircraft</span>
                    <span class="kpi-badge">{nextgen_pct:.1f}% Next-Gen</span>
                </div>
                <div class="kpi-value">{total_active:,}</div>
                <div class="kpi-foot">Avg Cruise: {avg_speed:,.0f} km/h · {avg_alt:,.0f} ft</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        civ_pct = (civilian_cnt / total_active * 100) if total_active > 0 else 0.0
        st.markdown(
            f"""
            <div class="kpi-card delay-2">
                <div class="kpi-top">
                    <span class="kpi-label">Commercial Fleet</span>
                    <span class="kpi-badge teal">{civ_pct:.1f}% Share</span>
                </div>
                <div class="kpi-value" style="color:#38bdf8;">{civilian_cnt:,}</div>
                <div class="kpi-foot">{df['airline_code'].nunique():,} active carrier codes</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
            <div class="kpi-card delay-3">
                <div class="kpi-top">
                    <span class="kpi-label">State &amp; Gov Flights</span>
                    <span class="kpi-badge amber">{mil_rate:.1f}% Share</span>
                </div>
                <div class="kpi-value" style="color:#fbbf24;">{mil_cnt:,}</div>
                <div class="kpi-foot">ADS-B Exchange + ICAO State fusion</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        st.markdown(
            f"""
            <div class="kpi-card delay-4">
                <div class="kpi-top">
                    <span class="kpi-label">Telemetry Anomalies</span>
                    <span class="kpi-badge rose">{anom_rate:.2f}% Rate</span>
                </div>
                <div class="kpi-value" style="color:#fb7185;">{anom_cnt:,}</div>
                <div class="kpi-foot">Altitude / envelope / speed flags</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # MACRO INTELLIGENCE RIBBON
    # -------------------------------------------------------------------------
    if macro:
        delta_val = float(macro["density_delta"].strip("%"))
        delta_color = "#2dd4bf" if delta_val >= 0 else "#fb7185"
        st.markdown(
            f"""
            <div class="macro-ribbon">
                <div class="macro-item">
                    <div class="macro-k">Global Asset Density</div>
                    <div class="macro-v">{macro['density']} <span style="color:{delta_color}; font-size:0.8rem; font-family:'JetBrains Mono',monospace;">{macro['density_delta']}</span></div>
                </div>
                <div class="macro-item">
                    <div class="macro-k">Macro Anomaly Index</div>
                    <div class="macro-v" style="color:#fb7185;">{macro['threat_pct']}</div>
                </div>
                <div class="macro-item">
                    <div class="macro-k">State / Gov Index</div>
                    <div class="macro-v" style="color:#fbbf24;">{macro['mil_pct']}</div>
                </div>
                <div class="macro-item">
                    <div class="macro-k">Busiest Zone</div>
                    <div class="macro-v" style="color:#38bdf8;">{macro['region']}</div>
                </div>
                <div class="macro-item">
                    <div class="macro-k">Busiest Global Hub</div>
                    <div class="macro-v" style="color:#c7d2fe;">{macro['airport']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # MAIN NAVIGATION TABS
    # -------------------------------------------------------------------------
    tab_map, tab_market, tab_family, tab_log = st.tabs([
        "🌐 Live Airspace & Trends",
        "📊 Fleet, Carriers & Cargo",
        "✈️ Airframes & Regions",
        "📋 Flight Intelligence Log",
    ])

    # =========================================================================
    # TAB 1: LIVE GLOBAL MAP + 24H VOLUME TRENDLINE
    # =========================================================================
    with tab_map:
        st.markdown(
            f"""
            <div class="section-head">
                <div class="section-title">Global Live Flight Map</div>
                <div class="section-caption">
                    <span style="color:#38bdf8;">● Commercial</span> &nbsp;&nbsp;
                    <span style="color:#fbbf24;">● State / Gov</span> &nbsp;&nbsp;
                    <span style="color:#fb7185;">● Anomaly</span> &nbsp;|&nbsp;
                    {len(df):,} plotted tracks
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if df.empty:
            st.info("No aircraft match your current filter selection.")
        else:
            def assign_core_color(cls):
                if cls == "ANOMALY":
                    return [251, 113, 133, 240]
                elif cls == "MILITARY":
                    return [251, 191, 36, 235]
                return [56, 189, 248, 175]

            def assign_halo_color(cls):
                if cls == "ANOMALY":
                    return [251, 113, 133, 75]
                elif cls == "MILITARY":
                    return [251, 191, 36, 65]
                return [56, 189, 248, 28]

            map_df = df.copy()
            map_df["core_color"] = map_df["Classification"].apply(assign_core_color)
            map_df["halo_color"] = map_df["Classification"].apply(assign_halo_color)
            map_df["baro_altitude_fmt"] = map_df["baro_altitude"].round(0).astype(int)
            map_df["velocity_fmt"] = map_df["velocity"].round(0).astype(int)

            halo_layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[longitude, latitude]",
                get_fill_color="halo_color",
                get_radius=18000,
                radius_min_pixels=6,
                radius_max_pixels=18,
                pickable=False,
            )
            core_layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[longitude, latitude]",
                get_fill_color="core_color",
                get_radius=4500,
                radius_min_pixels=2.5,
                radius_max_pixels=8,
                pickable=True,
            )

            st.pydeck_chart(
                pdk.Deck(
                    layers=[halo_layer, core_layer],
                    initial_view_state=pdk.ViewState(
                        latitude=22,
                        longitude=5,
                        zoom=1.55,
                        pitch=32 if map_pitch else 0,
                    ),
                    tooltip={
                        "html": """
                            <div style="font-family: 'Inter', sans-serif; padding: 4px 2px;">
                                <div style="font-weight:700; font-size:13px; color:#f8fafc; margin-bottom:3px;">
                                    {callsign} <span style="color:#94a3b8; font-weight:400;">({icao24})</span>
                                </div>
                                <div style="font-size:11px; color:#cbd5e1; margin-bottom:4px;">
                                    {aircraft_type} &bull; {Family} ({Generation})
                                </div>
                                <div style="font-family:'JetBrains Mono', monospace; font-size:11px; color:#38bdf8;">
                                    ALT {baro_altitude_fmt} ft &nbsp;|&nbsp; SPD {velocity_fmt} km/h
                                </div>
                                <div style="margin-top:4px; font-size:10px; font-weight:700; color:#fbbf24; letter-spacing:0.06em;">
                                    {Classification}
                                </div>
                            </div>
                        """,
                        "style": {
                            "backgroundColor": "rgba(15, 23, 42, 0.94)",
                            "border": "1px solid rgba(56, 189, 248, 0.35)",
                            "borderRadius": "10px",
                            "boxShadow": "0 10px 25px rgba(0,0,0,0.45)",
                        },
                    },
                    map_style="mapbox://styles/mapbox/dark-v11",
                ),
                use_container_width=True,
            )

        # 24-Hour Macro Trendline (Upgraded Spline Dual-Axis Area Chart)
        if macro and macro.get("history_df") is not None and not macro["history_df"].empty:
            hist = macro["history_df"]
            st.markdown(
                """
                <div class="section-head" style="margin-top: 1.4rem;">
                    <div class="section-title">24-Hour Global Flight &amp; Anomaly Volume Trend</div>
                    <div class="section-caption">SUPABASE TELEMETRY SNAPSHOTS</div>
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
                    line=dict(color="#38bdf8", width=2.8, shape="spline"),
                    fill="tozeroy",
                    fillcolor="rgba(56, 189, 248, 0.14)",
                ),
                secondary_y=False,
            )
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Active State / Gov Assets"],
                    name="State / Gov Assets",
                    mode="lines+markers",
                    line=dict(color="#fbbf24", width=2, shape="spline"),
                    marker=dict(size=5),
                ),
                secondary_y=True,
            )
            trend_fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Flagged Anomalies"],
                    name="Flagged Anomalies",
                    mode="lines+markers",
                    line=dict(color="#fb7185", width=2, shape="spline"),
                    marker=dict(size=5),
                ),
                secondary_y=True,
            )

            style_plotly(trend_fig, height=300)
            trend_fig.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified",
            )
            trend_fig.update_yaxes(title_text="Commercial Flights", secondary_y=False, title_font=dict(size=11, color="#38bdf8"))
            trend_fig.update_yaxes(title_text="State / Anomaly Count", secondary_y=True, showgrid=False, title_font=dict(size=11, color="#fbbf24"))
            st.plotly_chart(trend_fig, use_container_width=True)

    # =========================================================================
    # TAB 2: MARKET DOMINANCE, MANUFACTURERS, CARGO & FAMILIES
    # =========================================================================
    with tab_market:
        if df.empty:
            st.info("No aircraft data available for the selected filters.")
        else:
            r1_c1, r1_c2 = st.columns(2, gap="large")

            with r1_c1:
                st.markdown(
                    """
                    <div class="section-head">
                        <div class="section-title">Top 10 Global Airlines</div>
                        <div class="section-caption">ACTIVE AIRBORNE FLEET</div>
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
                        color_continuous_scale=["#0ea5e9", "#6366f1"],
                    )
                    fig_al.update_traces(textposition="outside", marker_line_width=0)
                    fig_al.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Aircraft")
                    style_plotly(fig_al, height=330)
                    st.plotly_chart(fig_al, use_container_width=True)
                else:
                    st.info("Insufficient commercial airline data in current filter.")

            with r1_c2:
                st.markdown(
                    """
                    <div class="section-head">
                        <div class="section-title">Manufacturer Market Share</div>
                        <div class="section-caption">OEM BREAKDOWN</div>
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
                        color_discrete_sequence=["#38bdf8", "#818cf8", "#2dd4bf", "#fbbf24", "#fb7185", "#a78bfa", "#60a5fa", "#34d399"],
                    )
                    fig_oem.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                        marker=dict(line=dict(color="#060913", width=2)),
                    )
                    style_plotly(fig_oem, height=330)
                    fig_oem.update_layout(showlegend=False)
                    st.plotly_chart(fig_oem, use_container_width=True)
                else:
                    st.info("No manufacturer classification data available.")

            r2_c1, r2_c2 = st.columns(2, gap="large")

            with r2_c1:
                st.markdown(
                    """
                    <div class="section-head">
                        <div class="section-title">Active Cargo Operators</div>
                        <div class="section-caption">FREIGHT &amp; LOGISTICS</div>
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
                        color_continuous_scale=["#f59e0b", "#fb7185"],
                    )
                    fig_cg.update_traces(textposition="outside", marker_line_width=0)
                    fig_cg.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Freighters")
                    style_plotly(fig_cg, height=330)
                    st.plotly_chart(fig_cg, use_container_width=True)
                else:
                    st.info("No dedicated cargo operators detected in current filter.")

            with r2_c2:
                st.markdown(
                    """
                    <div class="section-head">
                        <div class="section-title">Top Deployed Aircraft Families</div>
                        <div class="section-caption">AIRFRAME UTILIZATION</div>
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
                        color_continuous_scale=["#2dd4bf", "#38bdf8"],
                    )
                    fig_fm.update_traces(textposition="outside", marker_line_width=0)
                    fig_fm.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="Active Airframes")
                    style_plotly(fig_fm, height=330)
                    st.plotly_chart(fig_fm, use_container_width=True)
                else:
                    st.info("Insufficient airframe family data.")

            # Fleet Body-Type & Generation Split
            st.markdown(
                """
                <div class="section-head" style="margin-top: 0.75rem;">
                    <div class="section-title">Fleet Architecture &amp; Modernization Split</div>
                    <div class="section-caption">BODY CLASS &amp; GENERATION</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            b1, b2 = st.columns(2, gap="large")
            with b1:
                body_counts = df["Body Type"].value_counts().reset_index()
                body_counts.columns = ["Body Type", "Count"]
                fig_body = px.bar(
                    body_counts,
                    x="Body Type",
                    y="Count",
                    color="Body Type",
                    text="Count",
                    color_discrete_sequence=["#38bdf8", "#818cf8", "#2dd4bf", "#fbbf24", "#64748b"],
                )
                fig_body.update_traces(textposition="outside", marker_line_width=0)
                style_plotly(fig_body, height=250)
                fig_body.update_layout(showlegend=False, xaxis_title="", yaxis_title="Aircraft")
                st.plotly_chart(fig_body, use_container_width=True)

            with b2:
                gen_counts = df["Generation"].value_counts().reset_index()
                gen_counts.columns = ["Generation", "Count"]
                fig_gen = px.pie(
                    gen_counts,
                    names="Generation",
                    values="Count",
                    hole=0.65,
                    color="Generation",
                    color_discrete_map={"Next-Gen": "#2dd4bf", "Legacy": "#64748b"},
                )
                fig_gen.update_traces(
                    textinfo="percent+label",
                    marker=dict(line=dict(color="#060913", width=2)),
                )
                style_plotly(fig_gen, height=250)
                fig_gen.update_layout(showlegend=False)
                st.plotly_chart(fig_gen, use_container_width=True)

    # =========================================================================
    # TAB 3: AIRFRAME FAMILY SPOTLIGHT & REGIONAL CONCENTRATION
    # =========================================================================
    with tab_family:
        st.markdown(
            """
            <div class="section-head">
                <div class="section-title">Aircraft Asset Family Deep-Dive</div>
                <div class="section-caption">GLOBAL FLEET DEPLOYMENT PROFILE</div>
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

            top_op_code = fam_df[~fam_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].mode()[0] if fam_ops > 0 else "UNKN"
            top_op_name = dynamic_airline_map.get(top_op_code, top_op_code)

            st.markdown(
                f"""
                <div class="spotlight-grid">
                    <div class="spotlight-box">
                        <div class="macro-k">Active Assets</div>
                        <div style="font-family:'Space Grotesk',sans-serif; font-size:1.65rem; font-weight:700; color:#38bdf8;">
                            {fam_active:,} <span style="font-size:0.9rem; color:#94a3b8; font-weight:500;">({fam_share:.1f}% global)</span>
                        </div>
                    </div>
                    <div class="spotlight-box">
                        <div class="macro-k">Global Operators</div>
                        <div style="font-family:'Space Grotesk',sans-serif; font-size:1.65rem; font-weight:700; color:#f8fafc;">
                            {fam_ops} Airlines
                        </div>
                    </div>
                    <div class="spotlight-box">
                        <div class="macro-k">Dominant Region</div>
                        <div style="font-family:'Space Grotesk',sans-serif; font-size:1.25rem; font-weight:700; color:#fbbf24; margin-top:0.25rem;">
                            {top_fam_region}
                        </div>
                    </div>
                    <div class="spotlight-box">
                        <div class="macro-k">Primary Operator</div>
                        <div style="font-family:'Space Grotesk',sans-serif; font-size:1.2rem; font-weight:700; color:#2dd4bf; margin-top:0.25rem;">
                            {top_op_name} ({top_op_code})
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            fam_sec = fam_df["sector"].value_counts().reset_index()
            fam_sec.columns = ["Zone", "Flights"]
            fig_fsec = px.bar(
                fam_sec,
                x="Zone",
                y="Flights",
                text="Flights",
                color="Flights",
                color_continuous_scale=["#6366f1", "#38bdf8"],
                title=f"{selected_family} — Geographic Footprint",
            )
            fig_fsec.update_traces(textposition="outside", marker_line_width=0)
            style_plotly(fig_fsec, height=280)
            fig_fsec.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Active Flights")
            st.plotly_chart(fig_fsec, use_container_width=True)
        else:
            st.info("No classified aircraft families found in current data stream.")

        st.markdown(
            """
            <div class="section-head" style="margin-top: 1rem;">
                <div class="section-title">Regional Asset Concentration &amp; Market HHI</div>
                <div class="section-caption">COMPETITIVE DYNAMICS BY ZONE</div>
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

            regional_data.append({
                "Airspace Sector": sector_name,
                "Active Tracks": sec_tracks,
                "Deployment Share (%)": round(fleet_share_idx, 1),
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
                "Deployment Share (%)": st.column_config.ProgressColumn(
                    "Deployment Share",
                    min_value=0.0,
                    max_value=100.0,
                    format="%.1f%%",
                ),
            },
        )

    # =========================================================================
    # TAB 4: AIRCRAFT INTELLIGENCE LOG
    # =========================================================================
    with tab_log:
        st.markdown(
            f"""
            <div class="section-head">
                <div class="section-title">Live Aircraft Intelligence Log</div>
                <div class="section-caption">SORTED BY PRIORITY &amp; ALTITUDE &bull; {len(df):,} RECORDS</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        display_cols = [
            "Classification", "icao24", "callsign", "flight_number", "airline_code",
            "aircraft_type", "Family", "Body Type", "Generation", "sector",
            "baro_altitude", "velocity", "Threat_Reason",
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
                "aircraft_type": "Model Code",
                "Family": "Airframe Family",
                "Body Type": "Body Type",
                "Generation": "Gen",
                "sector": "Region",
                "baro_altitude": "Alt (ft)",
                "velocity": "Speed (km/h)",
                "Threat_Reason": "Flags",
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
            },
        )

        csv_bytes = df_full.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Export Filtered Telemetry (CSV)",
            data=csv_bytes,
            file_name="aerotrack_live_telemetry.csv",
            mime="text/csv",
        )

else:
    st.error("ERR_NO_DATA: Check tracking configuration parameters or API limits.")
