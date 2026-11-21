import sys
import os
import re
import html
import zlib
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

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="AeroTrack | Aviation Finance & Fleet Intelligence",
    page_icon="✈",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    client = OpenSkyClient()
except Exception:
    st.error("Unable to initialize AirLabs client. Verify AIRLABS_API_KEY in secrets.")
    st.stop()

# =============================================================================
# REFERENCE DATA
# =============================================================================
WATCHLIST_ENTITIES = [
    {"ticker": "AER", "name": "AerCap Holdings N.V.", "category": "Lessors", "iata": None, "exchange": "NYSE", "country": "IE / US"},
    {"ticker": "AL", "name": "Air Lease Corp.", "category": "Lessors", "iata": None, "exchange": "NYSE", "country": "US"},
    {"ticker": "FTAI", "name": "FTAI Aviation Ltd.", "category": "Lessors", "iata": None, "exchange": "NASDAQ", "country": "US"},
    {"ticker": "AIR.PA", "name": "Airbus SE", "category": "OEMs", "iata": None, "exchange": "Euronext Paris", "country": "EU"},
    {"ticker": "BA", "name": "The Boeing Company", "category": "OEMs", "iata": None, "exchange": "NYSE", "country": "US"},
    {"ticker": "ERJ", "name": "Embraer S.A.", "category": "OEMs", "iata": None, "exchange": "NYSE / B3", "country": "BR"},
    {"ticker": "DAL", "name": "Delta Air Lines", "category": "Airlines", "iata": "DL", "exchange": "NYSE", "country": "US"},
    {"ticker": "UAL", "name": "United Airlines Holdings", "category": "Airlines", "iata": "UA", "exchange": "NASDAQ", "country": "US"},
    {"ticker": "AAL", "name": "American Airlines Group", "category": "Airlines", "iata": "AA", "exchange": "NASDAQ", "country": "US"},
    {"ticker": "LUV", "name": "Southwest Airlines", "category": "Airlines", "iata": "WN", "exchange": "NYSE", "country": "US"},
    {"ticker": "RYAAY", "name": "Ryanair Holdings plc", "category": "Airlines", "iata": "FR", "exchange": "NASDAQ", "country": "EU"},
    {"ticker": "LHA.DE", "name": "Deutsche Lufthansa AG", "category": "Airlines", "iata": "LH", "exchange": "XETRA", "country": "DE"},
    {"ticker": "IAG.L", "name": "Intl Consolidated Airlines", "category": "Airlines", "iata": "BA", "exchange": "LSE", "country": "UK"},
    {"ticker": "INDIGO.NS", "name": "InterGlobe Aviation (IndiGo)", "category": "Airlines", "iata": "6E", "exchange": "NSE India", "country": "IN"},
]

EQUITY_FUNDAMENTALS = {
    "AER": {"mkt_cap": "$18.4B", "rev_ttm": "$7.9B", "net_inc": "$2.1B", "op_margin": "54.2%", "pe": "9.1x", "ev_ebitda": "8.4x", "fleet_note": "1,700+ owned/managed aircraft; world's largest commercial lessor."},
    "AL": {"mkt_cap": "$5.3B", "rev_ttm": "$2.7B", "net_inc": "$0.42B", "op_margin": "46.8%", "pe": "12.4x", "ev_ebitda": "10.2x", "fleet_note": "470+ owned fleet with 280+ Next-Gen OEM orderbook."},
    "FTAI": {"mkt_cap": "$14.6B", "rev_ttm": "$1.7B", "net_inc": "$0.34B", "op_margin": "31.5%", "pe": "38.2x", "ev_ebitda": "19.8x", "fleet_note": "CFM56 / V2500 PMA & modular engine MRO leasing leader."},
    "AIR.PA": {"mkt_cap": "€129.5B", "rev_ttm": "€69.2B", "net_inc": "€4.2B", "op_margin": "8.1%", "pe": "29.4x", "ev_ebitda": "14.6x", "fleet_note": "8,645 commercial aircraft firm backlog across A220/A320neo/A330neo/A350."},
    "BA": {"mkt_cap": "$112.8B", "rev_ttm": "$66.5B", "net_inc": "-$11.8B", "op_margin": "-14.2%", "pe": "N/M", "ev_ebitda": "N/M", "fleet_note": "6,189 commercial backlog; 737 MAX & 787 production recovery focus."},
    "ERJ": {"mkt_cap": "$7.8B", "rev_ttm": "$6.4B", "net_inc": "$0.35B", "op_margin": "9.2%", "pe": "21.6x", "ev_ebitda": "11.5x", "fleet_note": "Strong E195-E2 commercial & executive jet backlog expansion."},
    "DAL": {"mkt_cap": "$38.2B", "rev_ttm": "$61.6B", "net_inc": "$3.46B", "op_margin": "9.7%", "pe": "10.8x", "ev_ebitda": "6.1x", "fleet_note": "992 mainline aircraft; Delta TechOps third-party MRO powerhouse."},
    "UAL": {"mkt_cap": "$29.4B", "rev_ttm": "$57.1B", "net_inc": "$3.15B", "op_margin": "8.9%", "pe": "8.9x", "ev_ebitda": "5.4x", "fleet_note": "1,004 mainline aircraft with heavy 787 & A321neo United Next orderbook."},
    "AAL": {"mkt_cap": "$9.8B", "rev_ttm": "$54.2B", "net_inc": "$0.85B", "op_margin": "4.8%", "pe": "11.2x", "ev_ebitda": "6.3x", "fleet_note": "977 mainline aircraft; youngest legacy US carrier fleet profile."},
    "LUV": {"mkt_cap": "$18.9B", "rev_ttm": "$27.5B", "net_inc": "$0.47B", "op_margin": "2.4%", "pe": "34.1x", "ev_ebitda": "8.7x", "fleet_note": "All-Boeing 737 single-type operator transitioning to 737 MAX 7/8."},
    "RYAAY": {"mkt_cap": "$22.6B", "rev_ttm": "$14.5B", "net_inc": "$2.08B", "op_margin": "14.9%", "pe": "11.4x", "ev_ebitda": "6.2x", "fleet_note": "608 aircraft fleet; Europe's lowest unit-cost ultra-LCC operator."},
    "LHA.DE": {"mkt_cap": "€8.1B", "rev_ttm": "€37.6B", "net_inc": "€1.38B", "op_margin": "4.4%", "pe": "6.1x", "ev_ebitda": "3.9x", "fleet_note": "735 group aircraft + Lufthansa Technik global MRO subsidiary."},
    "IAG.L": {"mkt_cap": "£15.8B", "rev_ttm": "€32.1B", "net_inc": "€2.73B", "op_margin": "13.8%", "pe": "6.4x", "ev_ebitda": "4.1x", "fleet_note": "601 aircraft across British Airways, Iberia, Aer Lingus & Vueling."},
    "INDIGO.NS": {"mkt_cap": "₹1.82T", "rev_ttm": "₹785B", "net_inc": "₹81.7B", "op_margin": "11.4%", "pe": "22.3x", "ev_ebitda": "9.8x", "fleet_note": "415 active aircraft + 950+ A320neo/A321XLR/A350 backlog."},
}

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
    {"OEM": "Airbus", "Program": "A320neo / A321neo", "Segment": "Narrowbody", "Backlog": 7190, "Annual_Delivery_Rate": 620, "Monthly_Rate": 54, "Next_12M_Deliveries": 650, "Direct_Slot_Window": "Q4 2030", "Direct_Slot_Year": 2030.8, "Lessor_Slot": "Q3 2026 (AerCap / ALC)", "Avg_List_Price_M": 118, "Key_Slots": "IndiGo, United, Wizz Air, Air India"},
    {"OEM": "Airbus", "Program": "A220-100 / -300", "Segment": "Regional / NB", "Backlog": 512, "Annual_Delivery_Rate": 78, "Monthly_Rate": 7, "Next_12M_Deliveries": 88, "Direct_Slot_Window": "Q3 2027", "Direct_Slot_Year": 2027.6, "Lessor_Slot": "Q4 2026 (Azorra / ALC)", "Avg_List_Price_M": 91, "Key_Slots": "Delta, Air France, Breeze, JetBlue"},
    {"OEM": "Airbus", "Program": "A330-900neo", "Segment": "Widebody", "Backlog": 205, "Annual_Delivery_Rate": 36, "Monthly_Rate": 3, "Next_12M_Deliveries": 40, "Direct_Slot_Window": "Q2 2027", "Direct_Slot_Year": 2027.3, "Lessor_Slot": "Q1 2026 (Avolon / BOC)", "Avg_List_Price_M": 296, "Key_Slots": "Delta, Condor, Malaysia, ITA"},
    {"OEM": "Airbus", "Program": "A350-900 / -1000 / F", "Segment": "Widebody", "Backlog": 738, "Annual_Delivery_Rate": 62, "Monthly_Rate": 6, "Next_12M_Deliveries": 72, "Direct_Slot_Window": "Q1 2029", "Direct_Slot_Year": 2029.1, "Lessor_Slot": "Q2 2027 (AerCap / DAE)", "Avg_List_Price_M": 338, "Key_Slots": "Emirates, Turkish, Air India, Delta"},
    {"OEM": "Boeing", "Program": "737 MAX 8 / 9 / 10", "Segment": "Narrowbody", "Backlog": 4760, "Annual_Delivery_Rate": 340, "Monthly_Rate": 34, "Next_12M_Deliveries": 410, "Direct_Slot_Window": "Q2 2029", "Direct_Slot_Year": 2029.3, "Lessor_Slot": "Q2 2026 (SMBC / AerCap)", "Avg_List_Price_M": 122, "Key_Slots": "Ryanair, Southwest, United, Akasa"},
    {"OEM": "Boeing", "Program": "787-9 / -10 Dreamliner", "Segment": "Widebody", "Backlog": 790, "Annual_Delivery_Rate": 68, "Monthly_Rate": 6, "Next_12M_Deliveries": 84, "Direct_Slot_Window": "Q4 2028", "Direct_Slot_Year": 2028.8, "Lessor_Slot": "Q1 2027 (AerCap / ALC)", "Avg_List_Price_M": 292, "Key_Slots": "United, Riyadh Air, ANA, Lufthansa"},
    {"OEM": "Boeing", "Program": "777X / 777F", "Segment": "Widebody", "Backlog": 545, "Annual_Delivery_Rate": 22, "Monthly_Rate": 2, "Next_12M_Deliveries": 30, "Direct_Slot_Window": "Q3 2030", "Direct_Slot_Year": 2030.6, "Lessor_Slot": "Limited (Direct OEM Only)", "Avg_List_Price_M": 410, "Key_Slots": "Emirates, Qatar, Lufthansa, Ethiopian"},
    {"OEM": "Boeing", "Program": "767-300F / KC-46", "Segment": "Freighter", "Backlog": 94, "Annual_Delivery_Rate": 20, "Monthly_Rate": 2, "Next_12M_Deliveries": 22, "Direct_Slot_Window": "Q1 2027", "Direct_Slot_Year": 2027.1, "Lessor_Slot": "P2F Conversions Available", "Avg_List_Price_M": 220, "Key_Slots": "FedEx, UPS"},
    {"OEM": "Embraer", "Program": "E190-E2 / E195-E2", "Segment": "Regional", "Backlog": 224, "Annual_Delivery_Rate": 52, "Monthly_Rate": 4, "Next_12M_Deliveries": 60, "Direct_Slot_Window": "Q4 2027", "Direct_Slot_Year": 2027.8, "Lessor_Slot": "Q2 2026 (AerCap / Azorra)", "Avg_List_Price_M": 68, "Key_Slots": "Porter, Azul, KLM Cityhopper, Virgin"},
    {"OEM": "Embraer", "Program": "E175 (E1)", "Segment": "Regional", "Backlog": 176, "Annual_Delivery_Rate": 30, "Monthly_Rate": 3, "Next_12M_Deliveries": 34, "Direct_Slot_Window": "Q2 2027", "Direct_Slot_Year": 2027.3, "Lessor_Slot": "Q3 2026 (Nordic / Chorus)", "Avg_List_Price_M": 54, "Key_Slots": "American Eagle, SkyWest, Republic"},
    {"OEM": "COMAC", "Program": "C919", "Segment": "Narrowbody", "Backlog": 1060, "Annual_Delivery_Rate": 24, "Monthly_Rate": 2, "Next_12M_Deliveries": 32, "Direct_Slot_Window": "Q4 2031", "Direct_Slot_Year": 2031.8, "Lessor_Slot": "Domestic Chinese Lessors", "Avg_List_Price_M": 99, "Key_Slots": "China Eastern, Air China, China Southern"},
    {"OEM": "ATR", "Program": "ATR 42 / 72-600", "Segment": "Regional", "Backlog": 145, "Annual_Delivery_Rate": 38, "Monthly_Rate": 3, "Next_12M_Deliveries": 42, "Direct_Slot_Window": "Q1 2027", "Direct_Slot_Year": 2027.1, "Lessor_Slot": "Q2 2026 (NAC / Abelo)", "Avg_List_Price_M": 27, "Key_Slots": "IndiGo, Azul, Air Corsica, Cebu Pacific"},
]

AIRFRAME_TECH_SPECS = {
    "Airbus A320 Family": {"engines": "CFM LEAP-1A / PW1100G / CFM56-5B", "seats": "150 – 220 Pax", "range_km": "6,100 – 8,700 km", "mtow_t": "79 – 97 t", "cruise": "Mach 0.78", "cmv_m": "$48M – $64M", "lease_k": "$310k – $430k/mo"},
    "Boeing 737 Family": {"engines": "CFM LEAP-1B / CFM56-7B", "seats": "162 – 210 Pax", "range_km": "5,600 – 6,570 km", "mtow_t": "79 – 88 t", "cruise": "Mach 0.79", "cmv_m": "$45M – $59M", "lease_k": "$295k – $410k/mo"},
    "Airbus A350 Family": {"engines": "Rolls-Royce Trent XWB-84 / XWB-97", "seats": "300 – 410 Pax", "range_km": "15,000 – 16,100 km", "mtow_t": "280 – 319 t", "cruise": "Mach 0.85", "cmv_m": "$145M – $178M", "lease_k": "$980k – $1.25M/mo"},
    "Boeing 787 Family": {"engines": "GE GEnx-1B / Rolls-Royce Trent 1000", "seats": "248 – 330 Pax", "range_km": "13,530 – 14,140 km", "mtow_t": "228 – 254 t", "cruise": "Mach 0.85", "cmv_m": "$128M – $162M", "lease_k": "$890k – $1.15M/mo"},
    "Boeing 777 Family": {"engines": "GE90-115B / GE9X (777-9)", "seats": "312 – 426 Pax", "range_km": "13,650 – 15,840 km", "mtow_t": "347 – 351 t", "cruise": "Mach 0.84", "cmv_m": "$68M – $172M", "lease_k": "$520k – $1.20M/mo"},
    "Airbus A330 Family": {"engines": "RR Trent 7000 / Trent 700 / PW4000", "seats": "257 – 300 Pax", "range_km": "11,750 – 13,334 km", "mtow_t": "242 – 251 t", "cruise": "Mach 0.82", "cmv_m": "$52M – $112M", "lease_k": "$410k – $820k/mo"},
    "Regional Jet / Turboprop": {"engines": "PW1900G / GE CF34 / PW127XT", "seats": "70 – 146 Pax", "range_km": "1,500 – 4,800 km", "mtow_t": "23 – 62 t", "cruise": "Mach 0.74 – 0.80", "cmv_m": "$21M – $42M", "lease_k": "$155k – $285k/mo"},
    "Dedicated Widebody / Freighter": {"engines": "GEnx-2B / CF6-80C2 / PW4062", "seats": "100 – 137 t Payload", "range_km": "8,000 – 10,400 km", "mtow_t": "187 – 448 t", "cruise": "Mach 0.82 – 0.85", "cmv_m": "$58M – $195M", "lease_k": "$480k – $1.35M/mo"},
}

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
    "TAY", "LD", "AHK",
}

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
SECTOR_SCOPES = ["NORTH AMERICA", "EUROPE", "EAST ASIA & APAC", "MIDDLE EAST & S. ASIA", "LATIN AMERICA"]

# Design tokens (kept in Python so charts and CSS stay in sync)
C = {
    "bg": "#070A10", "panel": "#0D121B", "panel2": "#121927", "line": "rgba(148,163,184,0.13)",
    "text": "#E7ECF4", "muted": "#8896AB", "dim": "#5B6A80",
    "accent": "#5B9DFF", "pos": "#2FBF8F", "neg": "#EF6470", "gold": "#D9A94A", "violet": "#9A8CF2",
}
CHART_COLORS = [C["accent"], C["pos"], C["gold"], C["violet"], C["neg"], "#64748B"]
OEM_COLORS = {"Airbus": C["accent"], "Boeing": C["pos"], "Embraer": C["gold"], "COMAC": C["neg"], "ATR": "#94A3B8"}

# =============================================================================
# DESIGN SYSTEM (CSS)
# =============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    :root {
        --bg: #070A10; --panel: #0D121B; --panel-2: #121927; --panel-3: #18202F;
        --line: rgba(148,163,184,0.13); --line-strong: rgba(148,163,184,0.26);
        --text: #E7ECF4; --muted: #8896AB; --dim: #5B6A80;
        --accent: #5B9DFF; --accent-soft: rgba(91,157,255,0.13);
        --pos: #2FBF8F; --pos-soft: rgba(47,191,143,0.13);
        --neg: #EF6470; --neg-soft: rgba(239,100,112,0.13);
        --gold: #D9A94A; --gold-soft: rgba(217,169,74,0.13);
        --ease: cubic-bezier(0.2, 0.8, 0.2, 1);
        --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    }

    /* ---------- chrome removal ---------- */
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
    [data-testid="stStatusWidget"], [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"], #MainMenu, footer { display: none !important; }

    /* ---------- motion ---------- */
    @keyframes fadeUp   { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
    @keyframes fadeIn   { from { opacity: 0; } to { opacity: 1; } }
    @keyframes draw     { from { stroke-dashoffset: 400; } to { stroke-dashoffset: 0; } }
    @keyframes growX    { from { transform: scaleX(0); } to { transform: scaleX(1); } }
    @keyframes pulse    { 0% { box-shadow: 0 0 0 0 rgba(47,191,143,.55); } 70% { box-shadow: 0 0 0 7px rgba(47,191,143,0); } 100% { box-shadow: 0 0 0 0 rgba(47,191,143,0); } }
    @keyframes marquee  { from { transform: translateX(0); } to { transform: translateX(-50%); } }
    @keyframes sweep    { from { transform: translateX(-120%); } to { transform: translateX(320%); } }
    @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }
    .stApp {
        background:
            radial-gradient(1100px 520px at 8% -8%, rgba(91,157,255,0.09), transparent 60%),
            radial-gradient(900px 480px at 100% 0%, rgba(47,191,143,0.05), transparent 60%),
            var(--bg);
        color: var(--text);
    }
    .block-container { padding: 1.1rem 2rem 3rem 2rem !important; max-width: 1760px; }
    .num { font-family: var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }

    /* ---------- sidebar rail ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0A0F18 0%, #080C13 100%) !important;
        border-right: 1px solid var(--line);
        min-width: 318px !important; max-width: 318px !important;
    }
    section[data-testid="stSidebar"] > div { padding-top: 0.4rem; }
    section[data-testid="stSidebar"] .block-container { padding: 1rem 1rem 2rem 1rem !important; }

    .brand { display: flex; align-items: center; gap: .75rem; padding: .35rem .25rem 1rem .25rem; }
    .brand-mark {
        width: 38px; height: 38px; border-radius: 10px; display: grid; place-items: center;
        background: linear-gradient(145deg, #3B82F6, #0EA5A4);
        box-shadow: 0 8px 22px rgba(59,130,246,.28), inset 0 1px 0 rgba(255,255,255,.25);
    }
    .brand-name { font-size: 1.12rem; font-weight: 800; letter-spacing: -0.02em; color: #fff; line-height: 1.05; }
    .brand-tag { font-size: .66rem; color: var(--muted); font-weight: 500; letter-spacing: .02em; margin-top: 2px; }

    .rail-label {
        font-size: .64rem; font-weight: 700; color: var(--dim); letter-spacing: .12em; text-transform: uppercase;
        padding: .9rem .3rem .45rem .3rem; display: flex; justify-content: space-between; align-items: center;
    }
    .rail-label .hint { color: var(--accent); letter-spacing: .06em; }

    /* vertical nav (sidebar radio) */
    section[data-testid="stSidebar"] div[role="radiogroup"] { display: flex; flex-direction: column; gap: 3px; }
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        width: 100%; background: transparent !important; border: 1px solid transparent !important; border-radius: 9px !important;
        padding: .58rem .8rem !important; margin: 0 !important; cursor: pointer;
        transition: background .2s var(--ease), border-color .2s var(--ease), transform .2s var(--ease);
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: var(--panel-2) !important; transform: translateX(2px); }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(90deg, rgba(91,157,255,.16), rgba(91,157,255,.03)) !important;
        border-color: rgba(91,157,255,.30) !important; box-shadow: inset 3px 0 0 var(--accent);
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none !important; }
    section[data-testid="stSidebar"] div[role="radiogroup"] label p { font-size: .84rem !important; font-weight: 600 !important; color: #C9D3E2 !important; }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p { color: #fff !important; }

    /* watchlist filter (horizontal segmented) is rendered through .seg-scope wrapper */
    .seg-scope div[role="radiogroup"] { flex-direction: row !important; gap: 4px !important; background: var(--panel); padding: 3px; border: 1px solid var(--line); border-radius: 10px; }
    .seg-scope div[role="radiogroup"] label { flex: 1; justify-content: center; text-align: center; padding: .34rem .2rem !important; }
    .seg-scope div[role="radiogroup"] label:hover { transform: none !important; }
    .seg-scope div[role="radiogroup"] label p { font-size: .72rem !important; text-align: center; width: 100%; }

    /* watchlist rows */
    .wl div.stButton > button {
        width: 100%; text-align: left !important; justify-content: flex-start !important; white-space: pre-line !important;
        padding: .55rem .75rem !important; margin-bottom: -.4rem; background: var(--panel) !important;
        border: 1px solid var(--line) !important; border-radius: 10px !important; color: var(--text) !important;
        font-size: .76rem !important; line-height: 1.45 !important; font-weight: 500 !important;
        transition: border-color .2s var(--ease), background .2s var(--ease), transform .2s var(--ease), box-shadow .2s var(--ease);
    }
    .wl div.stButton > button:hover {
        background: var(--panel-2) !important; border-color: rgba(91,157,255,.5) !important;
        transform: translateX(3px); box-shadow: inset 3px 0 0 var(--accent), 0 8px 18px rgba(0,0,0,.35);
    }
    .wl div.stButton > button p { font-family: var(--mono); font-size: .74rem; }

    /* ---------- generic controls ---------- */
    div[data-baseweb="input"] > div {
        background: var(--panel) !important; border: 1px solid var(--line) !important; border-radius: 10px !important;
        transition: border-color .2s var(--ease), box-shadow .2s var(--ease);
    }
    div[data-baseweb="input"] > div:focus-within { border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(91,157,255,.16) !important; }
    div[data-baseweb="input"] input { color: var(--text) !important; font-size: .86rem !important; }
    div[data-baseweb="select"] > div { background: var(--panel) !important; border: 1px solid var(--line) !important; border-radius: 10px !important; }
    ul[data-baseweb="menu"] { background: var(--panel-2) !important; border: 1px solid var(--line-strong) !important; border-radius: 10px !important; }
    li[role="option"]:hover { background: var(--panel-3) !important; }
    label[data-testid="stWidgetLabel"] p { color: var(--muted) !important; font-size: .68rem !important; font-weight: 700 !important; letter-spacing: .08em !important; text-transform: uppercase !important; }

    /* main-area chip radios */
    .main div[role="radiogroup"], section.main div[role="radiogroup"], div[data-testid="stMain"] div[role="radiogroup"] { display: flex; flex-wrap: wrap; gap: .4rem; }
    div[data-testid="stMain"] div[role="radiogroup"] label {
        background: var(--panel) !important; border: 1px solid var(--line) !important; border-radius: 8px !important;
        padding: .36rem .85rem !important; margin: 0 !important; cursor: pointer;
        transition: background .2s var(--ease), border-color .2s var(--ease), transform .2s var(--ease);
    }
    div[data-testid="stMain"] div[role="radiogroup"] label:hover { background: var(--panel-2) !important; border-color: var(--line-strong) !important; transform: translateY(-1px); }
    div[data-testid="stMain"] div[role="radiogroup"] label:has(input:checked) { background: var(--accent-soft) !important; border-color: rgba(91,157,255,.55) !important; }
    div[data-testid="stMain"] div[role="radiogroup"] label > div:first-child { display: none !important; }
    div[data-testid="stMain"] div[role="radiogroup"] label p { font-size: .76rem !important; font-weight: 600 !important; color: #C9D3E2 !important; }
    div[data-testid="stMain"] div[role="radiogroup"] label:has(input:checked) p { color: #fff !important; }

    /* buttons */
    div[data-testid="stMain"] div.stButton > button, div.stDownloadButton > button {
        background: var(--panel-2); color: var(--text); border: 1px solid var(--line); border-radius: 9px;
        font-size: .78rem; font-weight: 600; padding: .45rem .9rem;
        transition: border-color .2s var(--ease), background .2s var(--ease), transform .2s var(--ease), box-shadow .2s var(--ease);
    }
    div[data-testid="stMain"] div.stButton > button:hover { border-color: var(--accent); background: var(--panel-3); transform: translateY(-1px); box-shadow: 0 8px 18px rgba(0,0,0,.35); color: #fff; }

    /* tabs: underline style */
    .stTabs [data-baseweb="tab-list"] { gap: 1.6rem; border-bottom: 1px solid var(--line); background: transparent; padding: 0; margin: .4rem 0 1rem 0; }
    .stTabs [data-baseweb="tab"] { background: transparent; padding: .7rem 0 !important; font-size: .84rem; font-weight: 600; color: var(--muted); height: auto; transition: color .2s var(--ease); }
    .stTabs [data-baseweb="tab"]:hover { color: #fff; }
    .stTabs [aria-selected="true"] { color: #fff !important; }
    .stTabs [data-baseweb="tab-highlight"] { background: var(--accent) !important; height: 2px !important; }
    .stTabs [data-baseweb="tab-border"] { display: none; }

    /* bordered containers = panels */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--panel); border: 1px solid var(--line) !important; border-radius: 14px !important;
        animation: fadeUp .5s var(--ease) both; transition: border-color .25s var(--ease);
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color: var(--line-strong) !important; }
    div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; animation: fadeIn .5s var(--ease) both; }

    /* ---------- command bar / page header ---------- */
    .status-pill {
        display: flex; align-items: center; justify-content: center; gap: .5rem; height: 38px;
        background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
        font-size: .72rem; font-weight: 600; color: #C9D3E2; white-space: nowrap;
    }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--pos); animation: pulse 2s infinite; }
    .page-head { display: flex; justify-content: space-between; align-items: flex-end; margin: .9rem 0 1rem 0; animation: fadeUp .45s var(--ease) both; }
    .page-title { font-size: 1.55rem; font-weight: 800; letter-spacing: -0.03em; color: #fff; line-height: 1.1; }
    .page-sub { font-size: .8rem; color: var(--muted); margin-top: .3rem; }
    .crumb { font-size: .66rem; font-weight: 700; color: var(--accent); letter-spacing: .12em; text-transform: uppercase; margin-bottom: .35rem; }

    /* ticker */
    .ticker { overflow: hidden; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); background: rgba(13,18,27,.7); white-space: nowrap; padding: .42rem 0; margin: .7rem 0 0 0; }
    .ticker-track { display: inline-flex; gap: 2.4rem; animation: marquee 55s linear infinite; will-change: transform; }
    .ticker:hover .ticker-track { animation-play-state: paused; }
    .tick { display: inline-flex; gap: .5rem; align-items: baseline; font-size: .72rem; color: #C9D3E2; }
    .tick b { color: #fff; font-weight: 700; }
    .tick .px { font-family: var(--mono); color: #fff; }

    /* ---------- KPI cards ---------- */
    .kpi {
        position: relative; overflow: hidden; background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
        padding: 1rem 1.1rem .8rem 1.1rem; animation: fadeUp .5s var(--ease) both;
        transition: transform .25s var(--ease), border-color .25s var(--ease), box-shadow .25s var(--ease);
    }
    .kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--kc, var(--accent)); opacity: .9; }
    .kpi:hover { transform: translateY(-3px); border-color: var(--line-strong); box-shadow: 0 16px 34px rgba(0,0,0,.42); }
    .kpi-k { font-size: .66rem; font-weight: 700; color: var(--muted); letter-spacing: .1em; text-transform: uppercase; }
    .kpi-v { font-family: var(--mono); font-size: 1.85rem; font-weight: 600; color: #fff; letter-spacing: -0.04em; margin: .3rem 0 .25rem 0; }
    .kpi-s { font-size: .72rem; color: var(--muted); }
    .chg { display: inline-flex; align-items: center; gap: .25rem; font-family: var(--mono); font-size: .72rem; font-weight: 600; padding: .12rem .45rem; border-radius: 6px; }
    .chg.up { color: var(--pos); background: var(--pos-soft); }
    .chg.dn { color: var(--neg); background: var(--neg-soft); }
    .spark-line { stroke-dasharray: 400; stroke-dashoffset: 400; animation: draw 1.2s var(--ease) .1s forwards; }
    .spark-area { opacity: 0; animation: fadeIn .9s ease .35s forwards; }

    /* ---------- metric tiles ---------- */
    .tile { background: var(--panel-2); border: 1px solid var(--line); border-radius: 11px; padding: .75rem .9rem; height: 100%; animation: fadeUp .5s var(--ease) both; transition: border-color .2s var(--ease), transform .2s var(--ease); }
    .tile:hover { border-color: rgba(91,157,255,.45); transform: translateY(-2px); }
    .tile-k { font-size: .62rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .1em; }
    .tile-v { font-family: var(--mono); font-size: .98rem; font-weight: 600; color: #fff; margin-top: .25rem; letter-spacing: -0.02em; }

    /* section header */
    .sec { display: flex; justify-content: space-between; align-items: baseline; margin: 1.35rem 0 .7rem 0; }
    .sec-t { font-size: .98rem; font-weight: 700; color: #fff; letter-spacing: -0.01em; }
    .sec-s { font-size: .66rem; font-weight: 700; color: var(--dim); letter-spacing: .1em; text-transform: uppercase; }

    /* hero card */
    .hero { background: linear-gradient(135deg, var(--panel-2), var(--panel)); border: 1px solid var(--line); border-radius: 16px; padding: 1.3rem 1.5rem; margin-bottom: 1rem; animation: fadeUp .5s var(--ease) both; }
    .badge { display: inline-block; font-size: .68rem; font-weight: 700; padding: .18rem .6rem; border-radius: 6px; letter-spacing: .04em; background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(91,157,255,.28); }
    .badge.gold { background: var(--gold-soft); color: var(--gold); border-color: rgba(217,169,74,.3); }
    .badge.pos { background: var(--pos-soft); color: var(--pos); border-color: rgba(47,191,143,.3); }

    /* schematic */
    .stage { position: relative; overflow: hidden; border: 1px solid rgba(91,157,255,.25); border-radius: 16px; padding: 1rem 1.1rem;
        background: radial-gradient(circle at 50% 40%, rgba(91,157,255,.12), rgba(8,12,19,.95)); animation: fadeUp .5s var(--ease) both; }
    .stage::after { content: ""; position: absolute; inset: 0 auto 0 0; width: 28%; background: linear-gradient(90deg, transparent, rgba(91,157,255,.08), transparent); animation: sweep 5.5s ease-in-out infinite; pointer-events: none; }

    /* progress */
    .bar { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: .9rem 1rem; transition: border-color .2s var(--ease), transform .2s var(--ease); animation: fadeUp .5s var(--ease) both; }
    .bar:hover { border-color: var(--line-strong); transform: translateY(-2px); }
    .bar-row { display: flex; justify-content: space-between; font-size: .76rem; font-weight: 600; color: #C9D3E2; }
    .bar-track { height: 6px; background: #1C2433; border-radius: 99px; overflow: hidden; margin-top: .55rem; }
    .bar-fill { height: 100%; border-radius: 99px; transform-origin: left; animation: growX 1s var(--ease) both; }

    /* news */
    .news { background: var(--panel); border: 1px solid var(--line); border-radius: 13px; padding: 1rem 1.15rem; margin-bottom: .85rem; animation: fadeUp .5s var(--ease) both; transition: transform .25s var(--ease), border-color .25s var(--ease), background .25s var(--ease); }
    .news:hover { transform: translateY(-3px); background: var(--panel-2); border-color: rgba(91,157,255,.4); }
    .news a { display: block; color: #F1F5F9; text-decoration: none; font-weight: 650; font-size: .93rem; line-height: 1.4; margin: .45rem 0; }
    .news a:hover { color: var(--accent); }
    .news-meta { display: flex; justify-content: space-between; font-size: .66rem; letter-spacing: .08em; font-weight: 700; text-transform: uppercase; }
    .news-snip { font-size: .8rem; color: var(--muted); line-height: 1.55; }

    ::-webkit-scrollbar { width: 7px; height: 7px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #263043; border-radius: 99px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# HELPERS
# =============================================================================
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


def build_svg_sparkline(values, color, width=230, height=40, uid="sp"):
    clean = [float(v) for v in values if v is not None and not np.isnan(v)]
    if len(clean) < 2:
        clean = [1.0, 1.0]
    lo, hi = min(clean), max(clean)
    span = (hi - lo) if hi > lo else 1.0
    n = len(clean)
    pts = [f"{(i / (n - 1)) * width:.1f},{height - 4 - ((v - lo) / span) * (height - 8):.1f}" for i, v in enumerate(clean)]
    poly = " ".join(pts)
    area = f"0,{height} {poly} {width},{height}"
    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="g_{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.30"/><stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon class="spark-area" points="{area}" fill="url(#g_{uid})"/>'
        f'<polyline class="spark-line" points="{poly}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>'
    )


def build_airframe_blueprint_svg(body_type, is_cargo, ac_code):
    accent = C["gold"] if is_cargo else (C["accent"] if body_type == "Widebody" else (C["pos"] if body_type == "Narrowbody" else C["violet"]))
    n_win = 22 if body_type == "Widebody" else (16 if body_type == "Narrowbody" else 11)
    windows = "".join(f'<rect x="{125 + i * 11}" y="99" width="5" height="4" rx="1" fill="#070A10" opacity="0.85"/>' for i in range(n_win))
    if is_cargo:
        windows = f'<rect x="145" y="96" width="58" height="10" rx="2" fill="{accent}" opacity="0.28" stroke="{accent}" stroke-width="0.9"/>'
    label = "CARGO MAIN DECK" if is_cargo else f"{body_type.upper()} PROFILE"
    return (
        f'<svg viewBox="0 0 520 215" width="100%" xmlns="http://www.w3.org/2000/svg">'
        f'<defs>'
        f'<linearGradient id="fus" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#E2E8F0"/><stop offset="55%" stop-color="#94A3B8"/><stop offset="100%" stop-color="#475569"/></linearGradient>'
        f'<linearGradient id="wng" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{accent}" stop-opacity="0.75"/><stop offset="100%" stop-color="#1E293B" stop-opacity="0.9"/></linearGradient>'
        f'<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(91,157,255,0.10)" stroke-width="0.8"/></pattern>'
        f'</defs>'
        f'<rect width="520" height="215" rx="10" fill="url(#grid)"/>'
        f'<line x1="25" y1="158" x2="495" y2="158" stroke="rgba(148,163,184,0.25)" stroke-dasharray="4 4"/>'
        f'<line x1="265" y1="30" x2="265" y2="178" stroke="{accent}" stroke-opacity="0.3" stroke-dasharray="3 3"/>'
        f'<path d="M 392 92 L 456 26 L 478 26 L 444 96 Z" fill="url(#wng)" stroke="{accent}" stroke-width="1.2"/>'
        f'<path d="M 426 111 L 474 103 L 480 110 L 434 118 Z" fill="#64748B" stroke="#CBD5E1" stroke-width="0.8"/>'
        f'<path d="M 52 114 C 54 96, 82 88, 120 88 L 400 90 C 425 91, 452 98, 466 107 C 452 118, 424 123, 398 124 L 118 124 C 76 124, 52 121, 52 114 Z" fill="url(#fus)" stroke="#E2E8F0" stroke-width="1.1"/>'
        f'<path d="M 74 97 L 95 95 L 98 103 L 72 103 Z" fill="#0F172A" stroke="{accent}" stroke-width="1"/>'
        f'{windows}'
        f'<path d="M 218 113 L 315 142 L 326 138 L 266 112 Z" fill="url(#wng)" stroke="{accent}" stroke-width="1.1"/>'
        f'<path d="M 315 142 L 328 128 L 333 130 L 324 143 Z" fill="{accent}"/>'
        f'<rect x="208" y="121" width="44" height="20" rx="8" fill="#1E293B" stroke="{accent}" stroke-width="1.4"/>'
        f'<ellipse cx="211" cy="131" rx="4" ry="9" fill="#070A10" stroke="#E2E8F0" stroke-width="1"/>'
        f'<circle cx="84" cy="100" r="3.5" fill="{accent}"/><circle cx="230" cy="131" r="3.5" fill="{C["pos"]}"/><circle cx="448" cy="46" r="3.5" fill="{C["gold"]}"/>'
        f'<text x="20" y="24" fill="{accent}" font-family="Inter, sans-serif" font-size="11" font-weight="700">{html.escape(ac_code)} · {label}</text>'
        f'<text x="20" y="196" fill="#8896AB" font-family="Inter, sans-serif" font-size="10" font-weight="600">AVIONICS &amp; RADOME</text>'
        f'<text x="210" y="196" fill="{C["pos"]}" font-family="Inter, sans-serif" font-size="10" font-weight="600">PROPULSION / WINGBOX</text>'
        f'<text x="395" y="196" fill="{C["gold"]}" font-family="Inter, sans-serif" font-size="10" font-weight="600">EMPENNAGE &amp; APU</text>'
        f'</svg>'
    )


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def style_chart(fig, height=340):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=CHART_COLORS,
        font=dict(color="#C9D3E2", family="Inter, sans-serif", size=12),
        title=dict(font=dict(size=13, color="#FFFFFF", family="Inter, sans-serif"), x=0.01, xanchor="left"),
        margin=dict(l=14, r=16, t=46, b=14),
        transition={"duration": 600, "easing": "cubic-in-out"},
        hoverlabel=dict(bgcolor="#121927", bordercolor="#5B9DFF", font=dict(color="#FFFFFF", family="Inter, sans-serif", size=12)),
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.08)", zeroline=False, linecolor="rgba(148,163,184,0.18)", tickfont=dict(color="#8896AB", size=11))
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.08)", zeroline=False, linecolor="rgba(148,163,184,0.18)", tickfont=dict(color="#8896AB", size=11))
    return fig


def donut(df_in, names, values, title, center_label, height=330, color_map=None):
    fig = px.pie(df_in, names=names, values=values, hole=0.68, title=title,
                 color=names if color_map else None, color_discrete_map=color_map,
                 color_discrete_sequence=CHART_COLORS)
    fig.update_traces(textinfo="percent", textfont=dict(size=11, color="#fff"), marker=dict(line=dict(color="#0D121B", width=3)), sort=False)
    fig.add_annotation(text=f"<b>{int(df_in[values].sum()):,}</b><br><span style='font-size:11px;color:#8896AB'>{center_label}</span>",
                       x=0.5, y=0.5, showarrow=False, font=dict(size=20, color="#FFFFFF"))
    style_chart(fig, height)
    fig.update_layout(legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center", font=dict(size=11)))
    return fig


def page_header(crumb, title, sub):
    st.markdown(
        f'<div class="page-head"><div><div class="crumb">{html.escape(crumb)}</div>'
        f'<div class="page-title">{html.escape(title)}</div><div class="page-sub">{html.escape(sub)}</div></div></div>',
        unsafe_allow_html=True,
    )


def section(title, sub=""):
    st.markdown(f'<div class="sec"><div class="sec-t">{title}</div><div class="sec-s">{sub}</div></div>', unsafe_allow_html=True)


def tile(k, v, delay=0.0, small=False):
    size = "font-size:.82rem;" if small else ""
    return f'<div class="tile" style="animation-delay:{delay:.2f}s;"><div class="tile-k">{html.escape(str(k))}</div><div class="tile-v" style="{size}">{html.escape(str(v))}</div></div>'


# =============================================================================
# DATA LOADERS
# =============================================================================
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

    df_ = pd.DataFrame(rows)
    if df_.empty:
        return df_

    df_ = df_.drop_duplicates(subset=["icao24"]).reset_index(drop=True)
    df_["sector"] = [get_airspace_sector(la, lo) for la, lo in zip(df_["latitude"], df_["longitude"])]
    df_[["Manufacturer", "Family", "Body Type", "Generation"]] = df_["aircraft_type"].apply(classify_airframe_taxonomy)
    df_["is_cargo"] = df_["airline_code"].isin(CARGO_CODES) | (df_["Family"] == "Dedicated Widebody / Freighter")

    conditions = [
        df_["baro_altitude"] < 2500,
        (df_["vertical_rate"] > 2.5) & (df_["baro_altitude"] < 28000),
        (df_["vertical_rate"] < -2.5) & (df_["baro_altitude"] < 28000),
        df_["baro_altitude"] >= 28000,
    ]
    df_["flight_phase"] = np.select(conditions, ["Takeoff / Approach", "Climb", "Descent", "Cruise"], default="En-Route")
    return df_


@st.cache_data(ttl=60)
def fetch_supabase_history():
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(720).execute()
        hist = pd.DataFrame(res.data)
        if hist.empty:
            return pd.DataFrame()
        hist["ts"] = pd.to_datetime(hist["timestamp"], utc=True, errors="coerce")
        return hist.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def _fetch_single_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/5.0)"}
    try:
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code != 200:
            return symbol, None
        result = r.json().get("chart", {}).get("result", [])
        if not result:
            return symbol, None
        meta = result[0].get("meta", {})
        q0 = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in q0.get("close", []) if c is not None]
        vols = [v for v in q0.get("volume", []) if v is not None]
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        prev = meta.get("chartPreviousClose") or (closes[-2] if len(closes) >= 2 else price)
        pct = ((price - prev) / prev * 100.0) if (price and prev and prev > 0) else 0.0
        return symbol, {
            "price": round(float(price), 2) if price is not None else None,
            "prev_close": round(float(prev), 2) if prev is not None else None,
            "pct_change": round(float(pct), 2),
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
            "volume": int(meta.get("regularMarketVolume") or (vols[-1] if vols else 0)),
            "high_52": meta.get("fiftyTwoWeekHigh"),
            "low_52": meta.get("fiftyTwoWeekLow"),
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
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
def fetch_stock_detail_history(symbol, rng="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/5.0)"}
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code != 200:
            return pd.DataFrame(), {}
        res = r.json().get("chart", {}).get("result", [])
        if not res:
            return pd.DataFrame(), {}
        meta = res[0].get("meta", {})
        ts = res[0].get("timestamp", [])
        q = res[0].get("indicators", {}).get("quote", [{}])[0]
        sdf_ = pd.DataFrame({
            "date": pd.to_datetime(ts, unit="s", utc=True),
            "open": q.get("open", []), "high": q.get("high", []), "low": q.get("low", []),
            "close": q.get("close", []), "volume": q.get("volume", []),
        }).dropna(subset=["close"])
        return sdf_, meta
    except Exception:
        return pd.DataFrame(), {}


@st.cache_data(ttl=900)
def fetch_aviation_news():
    feeds = [
        ("Simple Flying", "https://simpleflying.com/feed/"),
        ("FlightGlobal", "https://www.flightglobal.com/rss"),
        ("Leeham News", "https://leehamnews.com/feed/"),
        ("AeroTime", "https://www.aerotime.aero/feed"),
    ]
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/5.0)"}
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
                desc = html.unescape(re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip())[:180]
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
                items.append({"source": source_name, "title": html.unescape(title), "snippet": desc, "link": link, "published": pub, "tag": tag})
        except Exception:
            continue
    return items[:24]


def compute_airline_growth_from_history(hist, live_counts):
    growth = {}
    if hist.empty or "regional_breakdown" not in hist.columns:
        return growth
    now_ts = hist["ts"].max()
    records = [(row["ts"], row["regional_breakdown"]["__meta_airlines"]) for _, row in hist.iterrows()
               if isinstance(row.get("regional_breakdown"), dict) and "__meta_airlines" in row["regional_breakdown"]]
    if not records:
        return growth
    first_counts = records[0][1]
    snap_24h = min(records, key=lambda x: abs((x[0] - (now_ts - pd.Timedelta(hours=24))).total_seconds()))[1]
    snap_30d = min(records, key=lambda x: abs((x[0] - (now_ts - pd.Timedelta(days=30))).total_seconds()))[1]
    for code, live_cnt in live_counts.items():
        b24, b30, bmax = snap_24h.get(code), snap_30d.get(code), first_counts.get(code)
        growth[code] = {
            "d24": round(((live_cnt - b24) / b24) * 100, 1) if b24 and b24 > 0 else None,
            "d30": round(((live_cnt - b30) / b30) * 100, 1) if b30 and b30 > 0 else None,
            "dmax": round(((live_cnt - bmax) / bmax) * 100, 1) if bmax and bmax > 0 else None,
        }
    return growth


# =============================================================================
# SESSION STATE
# =============================================================================
NAV_ITEMS = ["Markets & Fleet", "OEM Backlog", "Digital Twin & MRO", "News Wire"]
if "primary_nav_radio" not in st.session_state:
    st.session_state["primary_nav_radio"] = NAV_ITEMS[0]
if "selected_stock" not in st.session_state:
    st.session_state["selected_stock"] = None


def open_stock(ticker_sym):
    st.session_state["selected_stock"] = ticker_sym
    st.session_state["primary_nav_radio"] = NAV_ITEMS[0]


def close_stock():
    st.session_state["selected_stock"] = None


# =============================================================================
# LOAD DATA
# =============================================================================
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

# =============================================================================
# SIDEBAR RAIL: BRAND, NAVIGATION, WATCHLIST
# =============================================================================
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">'
        '<svg width="20" height="20" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg"><path fill="#fff" d="M64 6 C67 6 69 12 69 22 L69 46 L116 74 L116 84 L69 68 L69 98 L88 112 L88 120 L64 113 L40 120 L40 112 L59 98 L59 68 L12 84 L12 74 L59 46 L59 22 C59 12 61 6 64 6 Z"/></svg>'
        '</div><div><div class="brand-name">AeroTrack</div><div class="brand-tag">AVIATION FINANCE &amp; FLEET INTELLIGENCE</div></div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="rail-label">Workspace</div>', unsafe_allow_html=True)
    nav_view = st.radio("Navigation", NAV_ITEMS, label_visibility="collapsed", key="primary_nav_radio")

    st.markdown('<div class="rail-label">Equity Watchlist<span class="hint">CLICK TO OPEN</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="seg-scope">', unsafe_allow_html=True)
    wl_cat = st.radio("Watchlist Filter", ["All", "Airlines", "Lessors", "OEMs"], horizontal=True, label_visibility="collapsed", key="wl_filter_radio")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="wl">', unsafe_allow_html=True)
    for idx_w, item in enumerate([e for e in WATCHLIST_ENTITIES if wl_cat == "All" or e["category"] == wl_cat]):
        tkr = item["ticker"]
        q = quotes_map.get(tkr)
        if q and q.get("price") is not None:
            sym = CURRENCY_SYMBOLS.get(q["currency"], "")
            pct = q["pct_change"]
            arr = "▲" if pct >= 0 else "▼"
            label_txt = f"{tkr}   {sym}{q['price']:,.2f}   {arr} {pct:+.2f}%\n{item['name']}"
        else:
            cnt = live_airline_counts.get(item["iata"], 0) if item["iata"] else 0
            label_txt = f"{tkr}   {f'{cnt} airborne' if cnt else item['exchange']}\n{item['name']}"
        st.button(label_txt, key=f"wl_btn_{tkr}_{idx_w}", on_click=open_stock, args=(tkr,), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# COMMAND BAR + TICKER
# =============================================================================
cb1, cb2, cb3 = st.columns([3.2, 1.25, 0.65], gap="small")
with cb1:
    search_query = st.text_input(
        "Search",
        placeholder="Search callsign, ICAO hex, airline code, aircraft type or manufacturer  —  e.g. DL, A359, 6E, Boeing",
        label_visibility="collapsed",
    )
with cb2:
    st.markdown(f'<div class="status-pill"><span class="status-dot"></span><span class="num">{utc_now}</span></div>', unsafe_allow_html=True)
with cb3:
    if st.button("Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

chips = [f'<span class="tick"><b style="color:{C["accent"]};">AIRBORNE</b><span class="px">{len(raw_df):,}</span></span>']
for ent in WATCHLIST_ENTITIES:
    q = quotes_map.get(ent["ticker"])
    if q and q.get("price") is not None:
        p = q["pct_change"]
        clr = C["pos"] if p >= 0 else C["neg"]
        chips.append(f'<span class="tick"><b>{ent["ticker"]}</b><span class="px">{q["price"]:,.2f}</span>'
                     f'<span style="color:{clr};font-family:var(--mono);font-weight:600;">{"▲" if p >= 0 else "▼"} {p:+.2f}%</span></span>')
tick_html = "".join(chips)
st.markdown(f'<div class="ticker"><div class="ticker-track">{tick_html}{tick_html}</div></div>', unsafe_allow_html=True)

# apply search filter
df = raw_df.copy()
if search_query.strip():
    sq = search_query.strip().lower()
    mask = pd.Series(False, index=df.index)
    for col in ["callsign", "icao24", "airline_code", "aircraft_type", "Family", "Manufacturer"]:
        mask |= df[col].str.lower().str.contains(sq, na=False, regex=False)
    df = df[mask]

# =============================================================================
# VIEW 1: MARKETS & FLEET
# =============================================================================
if nav_view == NAV_ITEMS[0]:
    sel_tkr = st.session_state.get("selected_stock")

    # ---------- equity tear-sheet ----------
    if sel_tkr:
        ent = next((e for e in WATCHLIST_ENTITIES if e["ticker"] == sel_tkr), None)
        q_live = quotes_map.get(sel_tkr, {})
        fund = EQUITY_FUNDAMENTALS.get(sel_tkr, {})

        page_header(f"Equity · {ent['category'] if ent else 'Instrument'}", ent["name"] if ent else sel_tkr, fund.get("fleet_note", "Aviation equity instrument"))

        bar_l, bar_r = st.columns([3.4, 1.0])
        with bar_l:
            rng_choice = st.radio("Horizon", ["1mo", "3mo", "6mo", "1y"], index=3, horizontal=True, label_visibility="collapsed", key="stock_rng_radio")
        with bar_r:
            st.button("← Back to Markets", on_click=close_stock, use_container_width=True)

        sdf, meta = fetch_stock_detail_history(sel_tkr, rng=rng_choice)
        curr_sym = CURRENCY_SYMBOLS.get(q_live.get("currency", meta.get("currency", "USD")), "$")
        live_px = q_live.get("price") or (round(float(sdf["close"].iloc[-1]), 2) if not sdf.empty else None)
        pct_1d = q_live.get("pct_change", 0.0)
        vol_today = q_live.get("volume", 0)
        exch_name = q_live.get("exchange") or (ent["exchange"] if ent else "Global Exchange")
        hi_52 = q_live.get("high_52") or (float(sdf["high"].max()) if not sdf.empty else None)
        lo_52 = q_live.get("low_52") or (float(sdf["low"].min()) if not sdf.empty else None)
        px_str = f"{curr_sym}{live_px:,.2f}" if live_px is not None else "N/A"
        up = pct_1d >= 0
        rng_str = f"{curr_sym}{lo_52:,.2f} – {curr_sym}{hi_52:,.2f}" if (hi_52 and lo_52) else "N/A"

        st.markdown(
            f'<div class="hero"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;">'
            f'<div><span class="badge">{html.escape(sel_tkr)} · {html.escape(exch_name)}</span>'
            f'<div style="font-size:.78rem;color:var(--muted);margin-top:.6rem;">Last updated {utc_now}</div></div>'
            f'<div style="text-align:right;"><div class="num" style="font-size:2.4rem;font-weight:600;color:#fff;line-height:1;">{px_str}</div>'
            f'<div style="margin-top:.5rem;"><span class="chg {"up" if up else "dn"}">{"▲" if up else "▼"} {pct_1d:+.2f}% 1D</span></div></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        metrics = [
            ("Market Cap", fund.get("mkt_cap", "N/A")), ("Volume", f"{vol_today:,}" if vol_today else "N/A"),
            ("52W Range", rng_str), ("Revenue TTM", fund.get("rev_ttm", "N/A")),
            ("Net Income", fund.get("net_inc", "N/A")), ("Op Margin", fund.get("op_margin", "N/A")),
            ("P/E", fund.get("pe", "N/A")), ("EV / EBITDA", fund.get("ev_ebitda", "N/A")),
        ]
        mc = st.columns(8, gap="small")
        for i, (col, (mk, mv)) in enumerate(zip(mc, metrics)):
            with col:
                st.markdown(tile(mk, mv, i * 0.04, small=(mk == "52W Range")), unsafe_allow_html=True)

        st.markdown("<div style='height:.9rem;'></div>", unsafe_allow_html=True)

        if not sdf.empty:
            sdf = sdf.copy()
            sdf["sma20"] = sdf["close"].rolling(20).mean()
            line_clr = C["pos"] if sdf["close"].iloc[-1] >= sdf["close"].iloc[0] else C["neg"]
            fill_clr = "rgba(47,191,143,0.10)" if line_clr == C["pos"] else "rgba(239,100,112,0.10)"
            vol_clrs = [C["pos"] if c >= o else C["neg"] for o, c in zip(sdf["open"].fillna(sdf["close"]), sdf["close"])]
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.76, 0.24])
            fig.add_trace(go.Scatter(x=sdf["date"], y=sdf["close"], mode="lines", name="Close", line=dict(color=line_clr, width=2.2), fill="tozeroy", fillcolor=fill_clr), row=1, col=1)
            fig.add_trace(go.Scatter(x=sdf["date"], y=sdf["sma20"], mode="lines", name="20D SMA", line=dict(color=C["accent"], width=1.4, dash="dot")), row=1, col=1)
            fig.add_trace(go.Bar(x=sdf["date"], y=sdf["volume"], name="Volume", marker_color=vol_clrs, opacity=0.6), row=2, col=1)
            style_chart(fig, 430)
            ymin = float(sdf["close"].min()) * 0.97
            fig.update_yaxes(range=[ymin, float(sdf["close"].max()) * 1.02], row=1, col=1)
            fig.update_layout(title=f"{sel_tkr} · Price, 20-Day SMA & Volume ({rng_choice.upper()})", hovermode="x unified",
                              legend=dict(orientation="h", y=1.08, x=1, xanchor="right"))
            with st.container(border=True):
                st.plotly_chart(fig, use_container_width=True)

        ent_iata = ent.get("iata") if ent else None
        if ent_iata:
            al_live = raw_df[raw_df["airline_code"] == ent_iata]
            section(f"Live Fleet Telemetry · {html.escape(ent['name'])}", f"{len(al_live):,} AIRBORNE NOW")
            if not al_live.empty:
                c1, c2 = st.columns(2, gap="medium")
                with c1:
                    fam = al_live["Family"].value_counts().reset_index()
                    fam.columns = ["Family", "Aircraft"]
                    with st.container(border=True):
                        st.plotly_chart(donut(fam, "Family", "Aircraft", "Active Airframe Mix", "Airborne", 330), use_container_width=True)
                with c2:
                    sec_ct = al_live["sector"].value_counts().reset_index()
                    sec_ct.columns = ["Region", "Aircraft"]
                    fig_sc = px.bar(sec_ct, x="Aircraft", y="Region", orientation="h", text="Aircraft", title="Regional Deployment Footprint")
                    fig_sc.update_traces(textposition="outside", marker_color=C["accent"], marker_line_width=0)
                    style_chart(fig_sc, 330)
                    fig_sc.update_layout(yaxis=dict(categoryorder="total ascending", title=""), xaxis_title="")
                    with st.container(border=True):
                        st.plotly_chart(fig_sc, use_container_width=True)

    # ---------- default dashboard ----------
    else:
        page_header("Markets & Fleet", "Global Fleet & Equity Overview", "Live ADS-B fleet utilisation alongside carrier financials and sector structure.")

        scope = st.radio("Scope", ["Global"] + SECTOR_SCOPES + ["Widebody", "Narrowbody", "Cargo"],
                         horizontal=True, label_visibility="collapsed", key="eq_scope_pills")

        scoped_df = df.copy()
        if scope in SECTOR_SCOPES:
            scoped_df = scoped_df[scoped_df["sector"] == scope]
        elif scope in ("Widebody", "Narrowbody"):
            scoped_df = scoped_df[scoped_df["Body Type"] == scope]
        elif scope == "Cargo":
            scoped_df = scoped_df[scoped_df["is_cargo"]]

        total_series = hist_df["total_flights"].tail(24).tolist() if (not hist_df.empty and "total_flights" in hist_df.columns) else [len(raw_df)]
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
            ("Active Commercial Fleet", f"{c_tot:,}", _delta(total_series, len(raw_df)), total_series or [c_tot, c_tot], "k1", C["accent"]),
            ("Narrowbody Utilisation", f"{c_nb:,}", _delta(nb_series, int((raw_df['Body Type'] == 'Narrowbody').sum())), nb_series or [c_nb, c_nb], "k2", C["pos"]),
            ("Widebody Utilisation", f"{c_wb:,}", _delta(wb_series, int((raw_df['Body Type'] == 'Widebody').sum())), wb_series or [c_wb, c_wb], "k3", C["violet"]),
            ("Dedicated Freighters", f"{c_cg:,}", _delta(cg_series, int(raw_df["is_cargo"].sum())), cg_series or [c_cg, c_cg], "k4", C["gold"]),
        ]
        for i, (col, (kk, big, dlt, ser, uid, kc)) in enumerate(zip(st.columns(4, gap="small"), cards)):
            up = dlt >= 0
            with col:
                st.markdown(
                    f'<div class="kpi" style="--kc:{kc};animation-delay:{i * 0.07:.2f}s;">'
                    f'<div class="kpi-k">{kk}</div><div class="kpi-v">{big}</div>'
                    f'<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem;">'
                    f'<span class="chg {"up" if up else "dn"}">{"▲" if up else "▼"} {dlt:+.1f}%</span><span class="kpi-s">vs 24h avg</span></div>'
                    f'{build_svg_sparkline(ser, C["pos"] if up else C["neg"], uid=uid)}</div>',
                    unsafe_allow_html=True,
                )

        t1, t2, t3 = st.tabs(["Carrier Screener", "Fleet Map", "Regional Structure"])

        with t1:
            rows = []
            all_codes = sorted(
                set(list(AIRLINE_FINANCIAL_BASELINES.keys()) + list(raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts().head(25).index)),
                key=lambda c: live_airline_counts.get(c, 0), reverse=True,
            )
            for code in all_codes:
                sub = scoped_df[scoped_df["airline_code"] == code]
                live_cnt = len(sub)
                base = AIRLINE_FINANCIAL_BASELINES.get(code, {})
                tkr = base.get("ticker", "N/A")
                q = quotes_map.get(tkr, {})
                gr = growth_map.get(code, {})
                reg_fleet = base.get("registered_fleet")
                rows.append({
                    "IATA": code, "Airline": base.get("name") or airline_map.get(code, code), "Ticker": tkr,
                    "Price": q.get("price"), "1D %": q.get("pct_change"),
                    "Airborne": live_cnt, "Registered": reg_fleet,
                    "Active Lift %": round((live_cnt / reg_fleet) * 100, 1) if reg_fleet else None,
                    "Δ 24h %": gr.get("d24"), "Δ 30D %": gr.get("d30"), "Δ Max %": gr.get("dmax"),
                    "Next-Gen %": round(float((sub["Generation"] == "Next-Gen").mean() * 100), 1) if live_cnt > 0 else 0.0,
                    "Revenue ($B)": base.get("rev_bn"), "Net Profit ($B)": base.get("net_profit_bn"), "Op Margin %": base.get("op_margin"),
                })
            scr = pd.DataFrame(rows)
            st.dataframe(
                scr, use_container_width=True, hide_index=True, height=390,
                column_config={
                    "Price": st.column_config.NumberColumn(format="%.2f"),
                    "1D %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "Active Lift %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                    "Next-Gen %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                    "Δ 24h %": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Δ 30D %": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Δ Max %": st.column_config.NumberColumn(format="%+.1f%%"),
                    "Revenue ($B)": st.column_config.NumberColumn(format="$%.1fB"),
                    "Net Profit ($B)": st.column_config.NumberColumn(format="$%.2fB"),
                    "Op Margin %": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
            st.markdown("<div style='height:.8rem;'></div>", unsafe_allow_html=True)
            ch1, ch2 = st.columns(2, gap="medium")
            with ch1:
                fin = scr.dropna(subset=["Net Profit ($B)"]).head(12)
                fig_p = px.bar(fin, x="Airline", y="Net Profit ($B)", color="Op Margin %", text="Net Profit ($B)",
                               color_continuous_scale=[C["neg"], C["gold"], C["pos"]], title="Net Profit ($B) & Operating Margin")
                fig_p.update_traces(texttemplate="$%{text:.2f}B", textposition="outside", marker_line_width=0)
                style_chart(fig_p, 360)
                fig_p.update_layout(xaxis_title="", xaxis_tickangle=-30, coloraxis_colorbar=dict(thickness=8, len=0.7, title=None))
                with st.container(border=True):
                    st.plotly_chart(fig_p, use_container_width=True)
            with ch2:
                body = scoped_df["Body Type"].value_counts().reset_index()
                body.columns = ["Segment", "Count"]
                with st.container(border=True):
                    st.plotly_chart(donut(body, "Segment", "Count", "Active Fleet by Body Class", "Active Tails", 360), use_container_width=True)

        with t2:
            if scoped_df.empty:
                st.info("No active commercial airframes match this filter.")
            else:
                def _rgb(row):
                    if row["is_cargo"]:
                        return [217, 169, 74, 235]
                    if row["Body Type"] == "Widebody":
                        return [91, 157, 255, 235]
                    if row["Body Type"] == "Narrowbody":
                        return [47, 191, 143, 225]
                    return [148, 163, 184, 200]

                m = scoped_df.copy()
                m["color"] = m.apply(_rgb, axis=1)
                m["alt_fmt"] = m["baro_altitude"].round(0).astype(int)
                m["spd_fmt"] = m["velocity"].round(0).astype(int)
                m["radius"] = np.where(m["Body Type"] == "Widebody", 52000, 36000)

                layer = pdk.Layer(
                    "ScatterplotLayer", data=m, get_position="[longitude, latitude]", get_fill_color="color",
                    get_radius="radius", radius_min_pixels=2.5, radius_max_pixels=7, pickable=True, opacity=0.9,
                )
                with st.container(border=True):
                    st.pydeck_chart(
                        pdk.Deck(
                            layers=[layer],
                            initial_view_state=pdk.ViewState(latitude=25, longitude=10, zoom=1.5, pitch=0),
                            tooltip={
                                "html": "<div style='font-family:Inter,sans-serif;padding:4px;min-width:190px;'>"
                                        "<div style='font-weight:700;color:#fff;font-size:13px;border-bottom:1px solid #334155;padding-bottom:3px;margin-bottom:4px;'>{callsign} · {icao24}</div>"
                                        "<div style='color:#CBD5E1;font-size:12px;'>{aircraft_type} · {Family}</div>"
                                        "<div style='color:#2FBF8F;font-size:11px;font-weight:600;margin-top:3px;'>{alt_fmt} ft · {spd_fmt} km/h</div></div>",
                                "style": {"backgroundColor": "#0D121B", "border": "1px solid #334155", "borderRadius": "8px"},
                            },
                            map_provider="carto", map_style="dark",
                        ),
                        use_container_width=True, height=560,
                    )
                st.markdown(
                    f'<div style="display:flex;gap:1.4rem;font-size:.74rem;color:var(--muted);margin-top:.5rem;">'
                    f'<span><span style="color:{C["pos"]};">●</span> Narrowbody</span><span><span style="color:{C["accent"]};">●</span> Widebody</span>'
                    f'<span><span style="color:{C["gold"]};">●</span> Freighter</span><span><span style="color:#94A3B8;">●</span> Regional / Other</span>'
                    f'<span style="margin-left:auto;" class="num">{len(m):,} tracked</span></div>',
                    unsafe_allow_html=True,
                )

        with t3:
            total_g = len(raw_df)
            reg_rows = []
            for sec_name, sec_df in raw_df.groupby("sector"):
                cnt = len(sec_df)
                cc = sec_df[~sec_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts()
                if not cc.empty:
                    props = cc / cc.sum()
                    hhi = round(float(sum(props ** 2) * 10000), 1)
                    conc = "Highly Concentrated" if hhi > 2500 else ("Moderately Concentrated" if hhi > 1500 else "Competitive")
                    top_c = f"{airline_map.get(cc.index[0], cc.index[0])} ({cc.index[0]})"
                else:
                    hhi, conc, top_c = 0.0, "Charter / Unscheduled", "N/A"
                reg_rows.append({
                    "Market": sec_name, "Active Fleet": cnt,
                    "Global Share %": round((cnt / total_g) * 100, 1) if total_g else 0.0,
                    "Next-Gen %": round(float((sec_df["Generation"] == "Next-Gen").mean() * 100), 1),
                    "HHI": hhi, "Structure": conc, "Leading Operator": top_c, "Top Family": sec_df["Family"].mode()[0],
                })
            st.dataframe(
                pd.DataFrame(reg_rows).sort_values("Active Fleet", ascending=False),
                use_container_width=True, hide_index=True,
                column_config={
                    "Global Share %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                    "Next-Gen %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                },
            )

# =============================================================================
# VIEW 2: OEM BACKLOG
# =============================================================================
elif nav_view == NAV_ITEMS[1]:
    page_header("OEM Backlog", "Order Book, Production & Delivery Slots", "Firm backlog, implied production horizon and probable open delivery slots by programme.")

    oem_df = pd.DataFrame(OEM_BACKLOG_REFERENCE)
    oem_df["Backlog_Years"] = (oem_df["Backlog"] / oem_df["Annual_Delivery_Rate"]).round(1)
    oem_df["Backlog_Value_Bn"] = ((oem_df["Backlog"] * oem_df["Avg_List_Price_M"]) / 1000.0).round(1)
    live_oems = raw_df[raw_df["Manufacturer"] != "Other"]["Manufacturer"].value_counts().to_dict()

    kp = [
        ("Airbus Firm Backlog", f"{int(oem_df[oem_df['OEM'] == 'Airbus']['Backlog'].sum()):,}", f"{live_oems.get('Airbus', 0):,} live airborne", C["accent"]),
        ("Boeing Firm Backlog", f"{int(oem_df[oem_df['OEM'] == 'Boeing']['Backlog'].sum()):,}", f"{live_oems.get('Boeing', 0):,} live airborne", C["pos"]),
        ("Next 12M Deliveries", f"{int(oem_df['Next_12M_Deliveries'].sum()):,}", "Projected global OEM output", C["gold"]),
        ("Gross Backlog Value", f"${oem_df['Backlog_Value_Bn'].sum():,.0f}B", "Implied at list price", C["violet"]),
    ]
    for i, (col, (k, v, s, kc)) in enumerate(zip(st.columns(4, gap="small"), kp)):
        with col:
            st.markdown(f'<div class="kpi" style="--kc:{kc};animation-delay:{i * 0.07:.2f}s;"><div class="kpi-k">{k}</div><div class="kpi-v">{v}</div><div class="kpi-s">{s}</div></div>', unsafe_allow_html=True)

    st.markdown("<div style='height:.9rem;'></div>", unsafe_allow_html=True)
    oc1, oc2 = st.columns([1.4, 1.0], gap="medium")
    with oc1:
        fig_bl = px.bar(oem_df.sort_values("Backlog"), x="Backlog", y="Program", color="OEM", orientation="h", text="Backlog_Years",
                        color_discrete_map=OEM_COLORS, title="Firm Backlog & Implied Production Horizon (years)")
        fig_bl.update_traces(texttemplate="%{text} yrs", textposition="outside", marker_line_width=0)
        style_chart(fig_bl, 400)
        fig_bl.update_layout(yaxis_title="", xaxis_title="Unfilled firm orders", legend=dict(orientation="h", y=1.1, x=1, xanchor="right", title=None))
        with st.container(border=True):
            st.plotly_chart(fig_bl, use_container_width=True)
    with oc2:
        in_svc = pd.DataFrame([{"OEM": k, "Airframes": v} for k, v in live_oems.items() if k in OEM_COLORS])
        if not in_svc.empty:
            with st.container(border=True):
                st.plotly_chart(donut(in_svc, "OEM", "Airframes", "Live In-Service Share (ADS-B)", "Live Fleet", 400, OEM_COLORS), use_container_width=True)

    section("Upcoming Deliveries & Probable Delivery Slots", "DIRECT OEM VS LESSOR SECONDARY")
    sc1, sc2 = st.columns([1.3, 1.0], gap="medium")
    with sc1:
        st.dataframe(
            oem_df[["OEM", "Program", "Segment", "Monthly_Rate", "Next_12M_Deliveries", "Direct_Slot_Window", "Lessor_Slot", "Key_Slots"]],
            use_container_width=True, hide_index=True, height=400,
            column_config={
                "Monthly_Rate": st.column_config.NumberColumn("Rate / Mo", format="%d / mo"),
                "Next_12M_Deliveries": st.column_config.NumberColumn("Next 12M", format="%d units"),
                "Direct_Slot_Window": "Direct OEM Slot", "Lessor_Slot": "Lessor Slot", "Key_Slots": "Primary Recipients",
            },
        )
    with sc2:
        fig_s = px.bar(oem_df.sort_values("Direct_Slot_Year"), x="Direct_Slot_Year", y="Program", color="OEM", orientation="h",
                       text="Direct_Slot_Window", color_discrete_map=OEM_COLORS, title="Next Open Direct OEM Delivery Slot")
        fig_s.update_traces(textposition="outside", marker_line_width=0)
        style_chart(fig_s, 400)
        fig_s.update_xaxes(range=[2025, 2034], title="Earliest probable slot (year)")
        fig_s.update_yaxes(title="")
        fig_s.update_layout(showlegend=False)
        with st.container(border=True):
            st.plotly_chart(fig_s, use_container_width=True)

# =============================================================================
# VIEW 3: DIGITAL TWIN & MRO
# =============================================================================
elif nav_view == NAV_ITEMS[2]:
    page_header("Digital Twin & MRO", "Airframe Inspection & Maintenance Proximity", "Select a live tail to view its schematic, indicative economics, check horizons and nearest MRO base.")

    sample_tails = df.sort_values("baro_altitude", ascending=False).head(100)
    tail_opts = [f"{r['callsign']} | {r['icao24']} | {r['aircraft_type']} ({r['airline_code']})" for _, r in sample_tails.iterrows()]

    if not tail_opts:
        st.info("No live tails match the current search.")
    else:
        picked = st.selectbox("Live commercial tail", tail_opts)
        hex_sel = picked.split("|")[1].strip()
        trow = df[df["icao24"] == hex_sel].iloc[0]

        specs = AIRFRAME_TECH_SPECS.get(trow["Family"], {"engines": "High-Bypass Turbofan", "seats": "Commercial Config", "range_km": "6,000+ km", "mtow_t": "78+ t", "cruise": "Mach 0.78", "cmv_m": "$42M – $85M", "lease_k": "$280k – $550k/mo"})
        al_info = AIRLINE_FINANCIAL_BASELINES.get(trow["airline_code"], {})
        est_age = al_info.get("avg_age_yrs", 4.6 if trow["Generation"] == "Next-Gen" else 13.8)
        a_prog = int((zlib.crc32(hex_sel.encode()) % 72) + 20)  # deterministic across reruns
        c_prog = int(((est_age % 2.0) / 2.0) * 100)
        d_prog = int(min(100, (est_age / 8.0) * 100))
        op_name = airline_map.get(trow["airline_code"], trow["airline_code"])

        hl, hr = st.columns([1.2, 1.4], gap="medium")
        with hl:
            st.markdown(
                f'<div class="stage"><div style="display:flex;justify-content:space-between;margin-bottom:.5rem;">'
                f'<span style="font-size:.66rem;font-weight:700;color:{C["accent"]};letter-spacing:.12em;">DIGITAL TWIN SCHEMATIC</span>'
                f'<span class="badge pos">{html.escape(trow["flight_phase"].upper())}</span></div>'
                f'{build_airframe_blueprint_svg(trow["Body Type"], bool(trow["is_cargo"]), trow["aircraft_type"])}</div>',
                unsafe_allow_html=True,
            )
        with hr:
            st.markdown(
                f'<div class="hero" style="padding:1.1rem 1.3rem;margin-bottom:.8rem;"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">'
                f'<div><div style="font-size:1.4rem;font-weight:800;color:#fff;letter-spacing:-.02em;">{html.escape(str(trow["callsign"]))} · {html.escape(str(trow["aircraft_type"]))}</div>'
                f'<div style="font-size:.8rem;color:var(--muted);margin-top:.25rem;">{html.escape(trow["Manufacturer"])} · {html.escape(trow["Family"])} · {html.escape(op_name)}</div></div>'
                f'<span class="badge {"pos" if trow["Generation"] == "Next-Gen" else "gold"}">{trow["Generation"]}</span></div></div>',
                unsafe_allow_html=True,
            )
            tiles = [
                ("ICAO Hex", trow["icao24"]), ("Altitude / Speed", f"{trow['baro_altitude']:,.0f} ft · {trow['velocity']:,.0f} km/h"),
                ("Est. Fleet Age", f"{est_age:.1f} yrs"), ("Powerplant", specs["engines"]),
                ("Range / MTOW", f"{specs['range_km']} · {specs['mtow_t']}"), ("Est. CMV / Lease", f"{specs['cmv_m']} · {specs['lease_k']}"),
            ]
            tcols = st.columns(3, gap="small")
            for i, (k, v) in enumerate(tiles):
                with tcols[i % 3]:
                    st.markdown(tile(k, v, i * 0.04, small=True) + "<div style='height:.5rem;'></div>", unsafe_allow_html=True)

        section("Maintenance Check Horizons", "INDICATIVE · MODELLED FROM FLEET AGE")
        for i, (col, (lbl, pv, clr)) in enumerate(zip(st.columns(3, gap="small"), [
            ("A-Check (~600 FH)", a_prog, C["accent"]), ("C-Check (~24 mo)", c_prog, C["pos"]), ("D-Check Structural (~8 yr)", d_prog, C["gold"]),
        ])):
            with col:
                st.markdown(
                    f'<div class="bar" style="animation-delay:{i * 0.07:.2f}s;"><div class="bar-row"><span>{lbl}</span><span class="num" style="color:{clr};">{pv}%</span></div>'
                    f'<div class="bar-track"><div class="bar-fill" style="width:{pv}%;background:{clr};animation-delay:{0.2 + i * 0.1:.1f}s;"></div></div></div>',
                    unsafe_allow_html=True,
                )

        gen_oem = df[df["Manufacturer"] != "Other"].groupby(["Manufacturer", "Generation"]).size().reset_index(name="Count")
        if not gen_oem.empty:
            st.markdown("<div style='height:.9rem;'></div>", unsafe_allow_html=True)
            fig_m = px.bar(gen_oem, x="Manufacturer", y="Count", color="Generation", barmode="stack", text="Count",
                           color_discrete_map={"Next-Gen": C["pos"], "Legacy": "#475569"}, title="MRO Demand Base · Next-Gen vs Legacy Active Fleet")
            fig_m.update_traces(marker_line_width=0)
            style_chart(fig_m, 300)
            fig_m.update_layout(xaxis_title="", legend=dict(orientation="h", y=1.12, x=1, xanchor="right", title=None))
            with st.container(border=True):
                st.plotly_chart(fig_m, use_container_width=True)

        hub_d = [(h["hub"], h["name"], h["specialty"], float(haversine_km(trow["latitude"], trow["longitude"], h["lat"], h["lon"]))) for h in MRO_HUBS]
        nh = min(hub_d, key=lambda x: x[3])
        section("Nearest MRO Base & Global Hub Monitor", "DIVERSION & SHOP-VISIT PROXIMITY")
        st.markdown(
            f'<div class="hero" style="padding:1.05rem 1.3rem;"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;">'
            f'<div><div style="font-size:.64rem;font-weight:700;color:{C["gold"]};letter-spacing:.12em;text-transform:uppercase;">Nearest facility to {html.escape(str(trow["callsign"]))}</div>'
            f'<div style="font-size:1.12rem;font-weight:800;color:#fff;margin-top:.2rem;">{nh[0]} — {html.escape(nh[1])}</div>'
            f'<div style="font-size:.8rem;color:var(--muted);margin-top:.15rem;">Capability: {html.escape(nh[2])}</div></div>'
            f'<div style="text-align:right;"><div class="num" style="font-size:1.7rem;font-weight:600;color:{C["gold"]};">{nh[3]:,.0f} km</div>'
            f'<div style="font-size:.72rem;color:var(--muted);">great-circle distance</div></div></div></div>',
            unsafe_allow_html=True,
        )

        mro_rows = []
        for hub in MRO_HUBS:
            d = haversine_km(df["latitude"].values, df["longitude"].values, hub["lat"], hub["lon"])
            nb = df[(d <= 120.0) & (df["baro_altitude"] < 14000)]
            mro_rows.append({
                "Hub": hub["hub"], "MRO Facility": hub["name"], "Specialty": hub["specialty"],
                "Low-Alt Movements (<120km)": int(len(nb)),
                "Next-Gen Share": f"{(nb['Generation'] == 'Next-Gen').mean() * 100:.0f}%" if len(nb) > 0 else "0%",
            })
        st.dataframe(pd.DataFrame(mro_rows).sort_values("Low-Alt Movements (<120km)", ascending=False), use_container_width=True, hide_index=True, height=320)

# =============================================================================
# VIEW 4: NEWS WIRE
# =============================================================================
else:
    page_header("News Wire", "Aviation Market Briefing", "Curated trade reporting across OEMs, MRO, leasing and capital markets.")

    busiest = raw_df["sector"].mode()[0]
    top_al = raw_df[~raw_df["airline_code"].isin(["UNKN", ""])]["airline_code"].mode()[0]
    top_name = airline_map.get(top_al, top_al)
    st.markdown(
        f'<div class="hero"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem;">'
        f'<span style="font-size:.66rem;font-weight:700;color:{C["accent"]};letter-spacing:.12em;">MARKET SNAPSHOT</span>'
        f'<span class="badge">{len(news_items)} STORIES</span></div>'
        f'<div style="font-size:1.1rem;font-weight:800;color:#fff;margin-bottom:.35rem;letter-spacing:-.01em;">'
        f'{len(raw_df):,} commercial airframes airborne · {html.escape(top_name)} ({html.escape(top_al)}) leads lift</div>'
        f'<div style="font-size:.84rem;color:#B6C2D4;line-height:1.6;">Airspace density is highest over <b style="color:#fff;">{html.escape(busiest)}</b>; '
        f'Next-Gen aircraft account for <b style="color:#fff;">{(raw_df["Generation"] == "Next-Gen").mean() * 100:.1f}%</b> of the live fleet.</div></div>',
        unsafe_allow_html=True,
    )

    news_cat = st.radio("Category", ["All Stories", "OEM & Backlog", "MRO & Engine", "Finance & Leasing", "Market Brief"],
                        horizontal=True, label_visibility="collapsed", key="news_cat_pills")
    shown = [n for n in news_items if news_cat == "All Stories" or n["tag"] == news_cat]
    tag_clr = {"OEM & Backlog": C["accent"], "MRO & Engine": C["gold"], "Finance & Leasing": C["pos"]}

    st.markdown("<div style='height:.5rem;'></div>", unsafe_allow_html=True)
    if not shown:
        st.info("No articles matched that category in the current feed window.")
    else:
        n1, n2 = st.columns(2, gap="medium")
        for i, item in enumerate(shown):
            clr = tag_clr.get(item["tag"], "#94A3B8")
            with (n1 if i % 2 == 0 else n2):
                st.markdown(
                    f'<div class="news" style="animation-delay:{min(i * 0.04, 0.4):.2f}s;">'
                    f'<div class="news-meta"><span style="color:{clr};">{html.escape(item["tag"])}</span>'
                    f'<span style="color:var(--dim);">{html.escape(item["source"])} · {html.escape(item["published"])}</span></div>'
                    f'<a href="{html.escape(item["link"])}" target="_blank" rel="noopener">{html.escape(item["title"])}</a>'
                    f'<div class="news-snip">{html.escape(item["snippet"])}…</div></div>',
                    unsafe_allow_html=True,
                )
