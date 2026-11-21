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
# PAGE CONFIGURATION (UNOBSTRUCTED FULL-CANVAS CORPORATE TERMINAL)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AeroTrack // Institutional Aviation Finance & Fleet Terminal",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    client = OpenSkyClient()
except Exception:
    st.error("Unable to initialize AirLabs client. Verify AIRLABS_API_KEY in secrets.")
    st.stop()

# -----------------------------------------------------------------------------
# INSTITUTIONAL EQUITY, AIRLINE, OEM, AIRFRAME SPEC & MRO UNIVERSES
# -----------------------------------------------------------------------------
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
# CORPORATE TERMINAL CSS (INTER FONT ONLY + HOVER ZOOM + SMOOTH ANIMATIONS)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap');

    :root {
        --bg-canvas: #0B0D12;
        --bg-surface: #13161E;
        --bg-elevated: #1A1E29;
        --bg-hover: #212635;
        --border-subtle: rgba(255, 255, 255, 0.085);
        --border-glow: rgba(96, 165, 250, 0.45);
        --text-primary: #F8FAFC;
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
        --ease: cubic-bezier(0.22, 1, 0.36, 1);
    }

    /* Hide Streamlit header/toolbar completely so nothing blocks top canvas */
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

    @keyframes viewFadeScale {
        0% { opacity: 0; transform: translateY(14px) scale(0.985); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes staggerZoom {
        0% { opacity: 0; transform: translateY(10px) scale(0.97); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes drawSpark {
        0% { stroke-dashoffset: 400; }
        100% { stroke-dashoffset: 0; }
    }
    @keyframes fadeArea {
        0% { opacity: 0; }
        100% { opacity: 1; }
    }
    @keyframes expandBar {
        0% { transform: scaleX(0); }
        100% { transform: scaleX(1); }
    }
    @keyframes pulseDot {
        0% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.65); }
        70% { box-shadow: 0 0 0 8px rgba(52, 211, 153, 0); }
        100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
    }
    @keyframes marquee {
        0% { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    @keyframes radarScan {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(250%); }
    }

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        font-variant-numeric: tabular-nums;
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 0%, rgba(37, 99, 235, 0.14), transparent 38%),
            radial-gradient(circle at 86% 6%, rgba(16, 185, 129, 0.09), transparent 34%),
            var(--bg-canvas);
        color: var(--text-primary);
    }

    .block-container {
        padding: 1rem 1.85rem 2.75rem 1.85rem !important;
        max-width: 1640px;
    }

    /* Animated Sparklines */
    .spark-line { stroke-dasharray: 400; stroke-dashoffset: 400; animation: drawSpark 1.1s var(--ease) forwards; }
    .spark-area { opacity: 0; animation: fadeArea 0.8s ease 0.25s forwards; }

    /* Inputs & Selectboxes */
    div[data-baseweb="input"] > div,
    .stTextInput > div > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 999px !important;
        color: var(--text-primary) !important;
        transition: all 0.25s var(--ease);
    }
    div[data-baseweb="select"] > div {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
        transition: all 0.25s var(--ease);
    }
    div[data-baseweb="input"] > div:hover,
    div[data-baseweb="select"] > div:hover {
        border-color: rgba(255, 255, 255, 0.22) !important;
        transform: scale(1.008);
    }
    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--blue) !important;
        box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.18) !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="input"] input {
        color: var(--text-primary) !important;
        font-family: 'Inter', sans-serif !important;
    }
    ul[data-baseweb="menu"] {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-glow) !important;
        border-radius: 12px !important;
    }
    li[role="option"] { color: var(--text-primary) !important; }
    li[role="option"]:hover { background-color: var(--bg-hover) !important; }
    label[data-testid="stWidgetLabel"] p {
        color: var(--text-secondary) !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
    }

    /* Pill Radio Controls with Hover Zoom */
    div[role="radiogroup"] { display: flex; flex-wrap: wrap; gap: 0.48rem; }
    div[role="radiogroup"] label {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 999px !important;
        padding: 0.42rem 1.05rem !important;
        margin: 0 !important;
        cursor: pointer !important;
        transition: transform 0.24s var(--ease), background-color 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease !important;
    }
    div[role="radiogroup"] label:hover {
        background: var(--bg-hover) !important;
        border-color: rgba(255, 255, 255, 0.25) !important;
        transform: translateY(-2px) scale(1.035);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
    }
    div[role="radiogroup"] label[data-checked="true"],
    div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(135deg, rgba(96, 165, 250, 0.25), rgba(52, 211, 153, 0.18)) !important;
        border-color: var(--blue) !important;
        box-shadow: 0 6px 18px rgba(96, 165, 250, 0.2) !important;
    }
    div[role="radiogroup"] label > div:first-child { display: none !important; }
    div[role="radiogroup"] label p {
        color: var(--text-primary) !important;
        font-size: 0.81rem !important;
        font-weight: 600 !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* Corporate Tabs with Hover Lift */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
        background: var(--bg-surface);
        padding: 0.35rem;
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        margin: 0.8rem 0 1rem 0;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Inter', sans-serif;
        font-size: 0.83rem;
        font-weight: 600;
        color: var(--text-secondary);
        border-radius: 10px;
        padding: 0.5rem 1.05rem;
        transition: all 0.22s var(--ease);
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #FFFFFF;
        background: var(--bg-hover);
        transform: scale(1.025);
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2563EB, #0F766E) !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3);
    }
    .stTabs [data-baseweb="tab-highlight"] { display: none !important; }

    /* Global Button Styling + Watchlist Card Buttons (Hover Enlargement) */
    div.stButton > button,
    div.stDownloadButton > button {
        background: var(--bg-surface);
        color: var(--text-primary);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        font-weight: 600;
        line-height: 1.38;
        transition: transform 0.25s var(--ease), background-color 0.22s ease, border-color 0.22s ease, box-shadow 0.25s ease;
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover {
        background: var(--bg-hover);
        border-color: var(--blue);
        color: #FFFFFF;
        transform: translateY(-2px) scale(1.028);
        box-shadow: 0 12px 26px rgba(0, 0, 0, 0.45);
        z-index: 10;
    }

    /* Watchlist Rail specific sleek row buttons */
    .wl-wrap div.stButton > button {
        width: 100%;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 0.58rem 0.78rem !important;
        white-space: pre-line !important;
        background: rgba(26, 30, 41, 0.72) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        margin-bottom: -0.35rem !important;
    }
    .wl-wrap div.stButton > button:hover {
        background: #23293A !important;
        border-color: var(--blue) !important;
        transform: translateX(4px) scale(1.032) !important;
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.5), inset 3px 0 0 var(--blue) !important;
    }

    /* Animated Chart & Table Frames with Hover Zoom */
    div[data-testid="stPlotlyChart"],
    div[data-testid="stDataFrame"] {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 0.45rem;
        transition: transform 0.28s var(--ease), border-color 0.25s ease, box-shadow 0.28s ease;
        animation: viewFadeScale 0.48s var(--ease) both;
    }
    div[data-testid="stPlotlyChart"]:hover,
    div[data-testid="stDataFrame"]:hover {
        transform: scale(1.012);
        border-color: rgba(96, 165, 250, 0.38);
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.45);
    }

    /* Brand & Header */
    .brand-wrap { display: flex; align-items: center; gap: 0.85rem; }
    .brand-icon {
        width: 42px; height: 42px; border-radius: 12px;
        background: linear-gradient(135deg, #2563EB, #059669);
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.35);
        transition: transform 0.3s var(--ease);
    }
    .brand-icon:hover { transform: scale(1.08) rotate(-6deg); }
    .brand-name { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.025em; color: #FFFFFF; line-height: 1.1; }
    .brand-sub { font-size: 0.74rem; color: var(--text-secondary); font-weight: 500; }
    .live-pill {
        display: inline-flex; align-items: center; justify-content: center; gap: 0.48rem;
        background: var(--green-bg); border: 1px solid rgba(52, 211, 153, 0.35);
        color: var(--green); border-radius: 999px; padding: 0.42rem 0.9rem;
        font-size: 0.74rem; font-weight: 600;
    }
    .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); animation: pulseDot 2s infinite; }

    /* Live Ticker Marquee */
    .ticker-shell {
        overflow: hidden; background: rgba(26, 30, 41, 0.75);
        backdrop-filter: blur(10px); border: 1px solid var(--border-subtle);
        border-radius: 999px; padding: 0.4rem 0; margin: 0.6rem 0 0.9rem 0; white-space: nowrap;
    }
    .ticker-track { display: inline-flex; gap: 2.1rem; animation: marquee 38s linear infinite; will-change: transform; }
    .ticker-shell:hover .ticker-track { animation-play-state: paused; }
    .tick-item { display: inline-flex; align-items: center; gap: 0.42rem; font-size: 0.76rem; color: var(--text-primary); }

    /* Index & KPI Cards with Hover Enlargement */
    .idx-card {
        position: relative; overflow: hidden;
        background: var(--bg-surface); border: 1px solid var(--border-subtle);
        border-radius: 16px; padding: 1.05rem 1.15rem 0.75rem 1.15rem;
        transition: transform 0.28s var(--ease), border-color 0.25s ease, box-shadow 0.28s ease;
        animation: staggerZoom 0.48s var(--ease) both;
        will-change: transform;
    }
    .idx-card:hover {
        transform: translateY(-4px) scale(1.032);
        border-color: var(--border-glow);
        box-shadow: 0 18px 38px rgba(0, 0, 0, 0.52);
        z-index: 12;
    }
    .idx-kicker { font-size: 0.72rem; font-weight: 700; color: var(--text-secondary); letter-spacing: 0.04em; text-transform: uppercase; }
    .idx-big { font-size: 1.55rem; font-weight: 800; color: #FFFFFF; margin: 0.22rem 0; letter-spacing: -0.02em; }
    .pill-up { background: var(--green-bg); color: var(--green); padding: 0.14rem 0.5rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }
    .pill-dn { background: var(--red-bg); color: var(--red); padding: 0.14rem 0.5rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }

    /* Glass Panels, Equity Tear-Sheet & Airframe Blueprint Showcase */
    .glass-card {
        background: var(--bg-surface); border: 1px solid var(--border-subtle);
        border-radius: 18px; padding: 1.25rem 1.4rem; margin-bottom: 1.05rem;
        transition: transform 0.28s var(--ease), border-color 0.25s ease, box-shadow 0.28s ease;
        animation: viewFadeScale 0.46s var(--ease) both;
    }
    .glass-card:hover {
        transform: scale(1.008);
        border-color: rgba(96, 165, 250, 0.35);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.44);
    }

    .stat-mini {
        background: var(--bg-elevated); border: 1px solid var(--border-subtle);
        border-radius: 13px; padding: 0.78rem 0.92rem;
        transition: transform 0.24s var(--ease), border-color 0.22s ease, box-shadow 0.24s ease;
    }
    .stat-mini:hover {
        transform: translateY(-3px) scale(1.03);
        border-color: var(--blue);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
    }
    .stat-k { font-size: 0.69rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
    .stat-v { font-size: 1.1rem; font-weight: 800; color: #FFFFFF; margin-top: 0.18rem; }

    /* Airframe Technical Render Stage */
    .render-stage {
        position: relative; overflow: hidden;
        background: radial-gradient(circle at 50% 45%, rgba(37, 99, 235, 0.16), rgba(15, 23, 42, 0.85));
        border: 1px solid rgba(96, 165, 250, 0.28);
        border-radius: 18px; padding: 1.25rem;
        transition: transform 0.3s var(--ease), box-shadow 0.3s ease;
        animation: viewFadeScale 0.5s var(--ease) both;
    }
    .render-stage:hover {
        transform: scale(1.018);
        box-shadow: 0 18px 40px rgba(37, 99, 235, 0.18);
    }
    .render-stage::after {
        content: ""; position: absolute; top: 0; left: 0; width: 35%; height: 100%;
        background: linear-gradient(90deg, transparent, rgba(96, 165, 250, 0.09), transparent);
        animation: radarScan 4.5s ease-in-out infinite;
        pointer-events: none;
    }

    /* Animated MRO Check Bars */
    .mro-bar-wrap {
        background: var(--bg-surface); border: 1px solid var(--border-subtle);
        border-radius: 14px; padding: 0.92rem 1.05rem;
        transition: transform 0.24s var(--ease), border-color 0.22s ease;
    }
    .mro-bar-wrap:hover { transform: translateY(-3px) scale(1.028); border-color: var(--border-glow); }
    .mro-track { width: 100%; height: 8px; background: #262B38; border-radius: 999px; overflow: hidden; margin-top: 0.45rem; }
    .mro-fill { height: 100%; border-radius: 999px; transform-origin: left; animation: expandBar 0.95s var(--ease) forwards; }

    /* News Cards with Hover Zoom */
    .news-tile {
        background: var(--bg-surface); border: 1px solid var(--border-subtle);
        border-radius: 16px; padding: 1.1rem 1.2rem; margin-bottom: 0.9rem;
        transition: transform 0.26s var(--ease), border-color 0.24s ease, background-color 0.24s ease, box-shadow 0.26s ease;
        animation: staggerZoom 0.45s var(--ease) both;
    }
    .news-tile:hover {
        transform: translateY(-4px) scale(1.022);
        background: var(--bg-elevated);
        border-color: var(--border-glow);
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.45);
    }
    .news-tile a { color: #F8FAFC; text-decoration: none; font-size: 0.96rem; font-weight: 700; line-height: 1.4; display: block; margin: 0.42rem 0; }
    .news-tile a:hover { color: var(--blue); }
    .news-snip { font-size: 0.81rem; color: var(--text-secondary); line-height: 1.5; }

    .sec-head { display: flex; justify-content: space-between; align-items: center; margin: 1rem 0 0.7rem 0; padding-bottom: 0.45rem; border-bottom: 1px solid var(--border-subtle); }
    .sec-title { font-size: 1.02rem; font-weight: 700; color: #FFFFFF; }
    .sec-sub { font-size: 0.74rem; color: var(--text-secondary); font-weight: 600; }

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--bg-canvas); }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--blue); }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# HELPERS, RETINA AIRFRAME SVG RENDERS & DATA LOADERS
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


def build_svg_sparkline(values, color="#34D399", width=190, height=36, uid="sp"):
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
        f'<polyline class="spark-line" points="{poly_pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def build_airframe_blueprint_svg(body_type, is_cargo, ac_code):
    """High-resolution vector airframe side + planform technical render for Digital Twin inspection."""
    accent = "#FBBF24" if is_cargo else ("#60A5FA" if body_type == "Widebody" else ("#34D399" if body_type == "Narrowbody" else "#A78BFA"))
    cabin_windows = "".join(
        f'<rect x="{125 + i*11}" y="99" width="5" height="4" rx="1" fill="#0B0D12" opacity="0.85"/>'
        for i in range(22 if body_type == "Widebody" else (16 if body_type == "Narrowbody" else 11))
    )
    if is_cargo:
        cabin_windows = '<rect x="145" y="96" width="58" height="10" rx="2" fill="#FBBF24" opacity="0.28" stroke="#FBBF24" stroke-width="0.9"/>'

    nose_label = "CARGO MAIN DECK" if is_cargo else f"{body_type.upper()} PROFILE"
    return (
        f'<svg viewBox="0 0 520 215" width="100%" xmlns="http://www.w3.org/2000/svg">'
        f'<defs>'
        f'  <linearGradient id="fuselageGrad" x1="0" y1="0" x2="0" y2="1">'
        f'    <stop offset="0%" stop-color="#E2E8F0"/>'
        f'    <stop offset="55%" stop-color="#94A3B8"/>'
        f'    <stop offset="100%" stop-color="#475569"/>'
        f'  </linearGradient>'
        f'  <linearGradient id="wingGrad" x1="0" y1="0" x2="1" y2="1">'
        f'    <stop offset="0%" stop-color="{accent}" stop-opacity="0.75"/>'
        f'    <stop offset="100%" stop-color="#1E293B" stop-opacity="0.9"/>'
        f'  </linearGradient>'
        f'  <pattern id="bpGrid" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'    <path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(96,165,250,0.12)" stroke-width="0.8"/>'
        f'  </pattern>'
        f'</defs>'
        f'<rect width="520" height="215" rx="12" fill="url(#bpGrid)"/>'
        # Technical callout lines
        f'<line x1="25" y1="158" x2="495" y2="158" stroke="rgba(148,163,184,0.28)" stroke-dasharray="4 4"/>'
        f'<line x1="265" y1="30" x2="265" y2="178" stroke="{accent}" stroke-opacity="0.35" stroke-dasharray="3 3"/>'
        # Vertical stabilizer
        f'<path d="M 392 92 L 456 26 L 478 26 L 444 96 Z" fill="url(#wingGrad)" stroke="{accent}" stroke-width="1.2"/>'
        # Horizontal stabilizer
        f'<path d="M 426 111 L 474 103 L 480 110 L 434 118 Z" fill="#64748B" stroke="#CBD5E1" stroke-width="0.8"/>'
        # Main fuselage
        f'<path d="M 52 114 C 54 96, 82 88, 120 88 L 400 90 C 425 91, 452 98, 466 107 C 452 118, 424 123, 398 124 L 118 124 C 76 124, 52 121, 52 114 Z" fill="url(#fuselageGrad)" stroke="#E2E8F0" stroke-width="1.1"/>'
        # Cockpit windshield
        f'<path d="M 74 97 L 95 95 L 98 103 L 72 103 Z" fill="#0F172A" stroke="{accent}" stroke-width="1"/>'
        # Windows / Cargo Door
        f'{cabin_windows}'
        # Swept Wing + Winglet
        f'<path d="M 218 113 L 315 142 L 326 138 L 266 112 Z" fill="url(#wingGrad)" stroke="{accent}" stroke-width="1.1"/>'
        f'<path d="M 315 142 L 328 128 L 333 130 L 324 143 Z" fill="{accent}"/>'
        # High-Bypass Turbofan Engine Nacelle
        f'<rect x="208" y="121" width="44" height="20" rx="8" fill="#1E293B" stroke="{accent}" stroke-width="1.4"/>'
        f'<ellipse cx="211" cy="131" rx="4" ry="9" fill="#0B0D12" stroke="#E2E8F0" stroke-width="1"/>'
        # Sensor telemetry pins
        f'<circle cx="84" cy="100" r="3.5" fill="{accent}"/>'
        f'<circle cx="230" cy="131" r="3.5" fill="#34D399"/>'
        f'<circle cx="448" cy="46" r="3.5" fill="#FBBF24"/>'
        # Crisp Labels (Inter font)
        f'<text x="20" y="24" fill="{accent}" font-family="Inter, sans-serif" font-size="11" font-weight="700">{html.escape(ac_code)} · {nose_label}</text>'
        f'<text x="20" y="196" fill="#94A3B8" font-family="Inter, sans-serif" font-size="10.5" font-weight="600">AVIONICS &amp; RADOME</text>'
        f'<text x="210" y="196" fill="#34D399" font-family="Inter, sans-serif" font-size="10.5" font-weight="600">PROPULSION / WINGBOX</text>'
        f'<text x="395" y="196" fill="#FBBF24" font-family="Inter, sans-serif" font-size="10.5" font-weight="600">EMPENNAGE &amp; APU</text>'
        f'</svg>'
    )


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def style_dark_chart(fig, height=345):
    fig.update_layout(
        height=height,
        paper_bgcolor="#13161E",
        plot_bgcolor="#0F1219",
        font=dict(color="#E2E8F0", family="Inter, Plus Jakarta Sans, sans-serif", size=12),
        title_font=dict(size=14, color="#FFFFFF", family="Inter, sans-serif"),
        margin=dict(l=18, r=20, t=44, b=20),
        transition={"duration": 650, "easing": "cubic-in-out"},
        hoverlabel=dict(
            bgcolor="#1A1E29",
            bordercolor="#60A5FA",
            font=dict(color="#FFFFFF", family="Inter, sans-serif", size=12),
        ),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.055)", zeroline=False, linecolor="rgba(255,255,255,0.12)", tickfont=dict(color="#94A3B8"))
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.055)", zeroline=False, linecolor="rgba(255,255,255,0.12)", tickfont=dict(color="#94A3B8"))
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
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/4.0)"}
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
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/4.0)"}
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
        sdf = pd.DataFrame({
            "date": pd.to_datetime(ts, unit="s", utc=True),
            "open": q.get("open", []),
            "high": q.get("high", []),
            "low": q.get("low", []),
            "close": q.get("close", []),
            "volume": q.get("volume", []),
        }).dropna(subset=["close"])
        return sdf, meta
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
    headers = {"User-Agent": "Mozilla/5.0 (AeroTrackTerminal/4.0)"}
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


def compute_airline_growth_from_history(hist_df, live_airline_counts):
    growth_map = {}
    if hist_df.empty or "regional_breakdown" not in hist_df.columns:
        return growth_map
    now_ts = hist_df["ts"].max()
    records = [(row["ts"], row["regional_breakdown"]["__meta_airlines"]) for _, row in hist_df.iterrows() if isinstance(row.get("regional_breakdown"), dict) and "__meta_airlines" in row["regional_breakdown"]]
    if not records:
        return growth_map
    _, first_counts = records[0]
    snap_24h = min(records, key=lambda x: abs((x[0] - (now_ts - pd.Timedelta(hours=24))).total_seconds()))[1]
    snap_30d = min(records, key=lambda x: abs((x[0] - (now_ts - pd.Timedelta(days=30))).total_seconds()))[1]
    for code, live_cnt in live_airline_counts.items():
        b24, b30, bmax = snap_24h.get(code), snap_30d.get(code), first_counts.get(code)
        growth_map[code] = {
            "d24": round(((live_cnt - b24) / b24) * 100, 1) if b24 and b24 > 0 else None,
            "d30": round(((live_cnt - b30) / b30) * 100, 1) if b30 and b30 > 0 else None,
            "dmax": round(((live_cnt - bmax) / bmax) * 100, 1) if bmax and bmax > 0 else None,
        }
    return growth_map


# -----------------------------------------------------------------------------
# SESSION STATE & NAVIGATION CALLBACKS
# -----------------------------------------------------------------------------
if "primary_nav_radio" not in st.session_state:
    st.session_state["primary_nav_radio"] = "Equity & Fleet Dashboard"
if "selected_stock" not in st.session_state:
    st.session_state["selected_stock"] = None


def open_stock(ticker_sym):
    st.session_state["selected_stock"] = ticker_sym
    st.session_state["primary_nav_radio"] = "Equity & Fleet Dashboard"


def close_stock():
    st.session_state["selected_stock"] = None


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
# TOP HEADER BAR + LIVE TICKER MARQUEE + TOP SECTION NAVIGATION
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
        '<div><div class="brand-name">AeroTrack</div><div class="brand-sub">Institutional Aviation Finance &amp; Fleet Intelligence</div></div>'
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

ticker_chips = [f'<span class="tick-item"><strong style="color:#60A5FA;">GLOBAL FLEET</strong> {len(raw_df):,} Airborne</span>']
for ent in WATCHLIST_ENTITIES:
    q = quotes_map.get(ent["ticker"])
    if q and q.get("price") is not None:
        p = q["pct_change"]
        clr = "#34D399" if p >= 0 else "#FB7185"
        arr = "▲" if p >= 0 else "▼"
        ticker_chips.append(
            f'<span class="tick-item"><strong>{ent["ticker"]}</strong> {q["price"]:,.2f} '
            f'<span style="color:{clr};font-weight:700;">{p:+.2f}% {arr}</span></span>'
        )
ticker_html = "".join(ticker_chips)
st.markdown(f'<div class="ticker-shell"><div class="ticker-track">{ticker_html}{ticker_html}</div></div>', unsafe_allow_html=True)

nav_view = st.radio(
    "Primary Navigation",
    ["Equity & Fleet Dashboard", "OEM Backlog Corner", "Digital Twin & MRO", "News Corner"],
    horizontal=True,
    label_visibility="collapsed",
    key="primary_nav_radio",
)

st.markdown("<div style='height:0.55rem;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# SPACIOUS 2-PANE LAYOUT: CLICKABLE WATCHLIST RAIL | WIDE WORKSPACE
# -----------------------------------------------------------------------------
col_watch, col_main = st.columns([0.92, 3.08], gap="large")

with col_watch:
    st.markdown(
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.45rem;">'
        '<span style="font-size:0.96rem;font-weight:700;color:#FFFFFF;">Equity Watchlist</span>'
        '<span style="font-size:0.7rem;color:#60A5FA;background:rgba(96,165,250,0.14);padding:0.15rem 0.55rem;border-radius:999px;font-weight:600;">CLICK TO OPEN</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    wl_cat = st.radio("Watchlist Filter", ["All", "Airlines", "Lessors", "OEMs"], horizontal=True, label_visibility="collapsed", key="wl_filter_radio")
    filtered_wl = [e for e in WATCHLIST_ENTITIES if wl_cat == "All" or e["category"] == wl_cat]

    st.markdown('<div class="wl-wrap">', unsafe_allow_html=True)
    for idx_w, item in enumerate(filtered_wl):
        tkr = item["ticker"]
        q = quotes_map.get(tkr)
        if q and q.get("price") is not None:
            sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(q["currency"], "")
            pct = q["pct_change"]
            arr = "▲" if pct >= 0 else "▼"
            label_txt = f"{tkr}  ·  {sym}{q['price']:,.2f}   {arr} {pct:+.2f}%\n{item['name']}  ({item['exchange']})"
        else:
            cnt = live_airline_counts.get(item["iata"], 0) if item["iata"] else 0
            extra = f"{cnt} active" if cnt else item["exchange"]
            label_txt = f"{tkr}  ·  {extra}\n{item['name']}"

        st.button(
            label_txt,
            key=f"wl_btn_{tkr}_{idx_w}",
            on_click=open_stock,
            args=(tkr,),
            use_container_width=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

# Apply Search Filter
df = raw_df.copy()
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
# MAIN WORKSPACE
# =============================================================================
with col_main:
    # =========================================================================
    # VIEW 1: EQUITY & FLEET DASHBOARD (WITH CLICK-TO-OPEN STOCK TEAR-SHEET)
    # =========================================================================
    if nav_view == "Equity & Fleet Dashboard":
        sel_tkr = st.session_state.get("selected_stock")

        # --- OPEN STOCK DETAIL TEAR-SHEET WHEN CLICKED ---
        if sel_tkr:
            ent = next((e for e in WATCHLIST_ENTITIES if e["ticker"] == sel_tkr), None)
            q_live = quotes_map.get(sel_tkr, {})
            fund = EQUITY_FUNDAMENTALS.get(sel_tkr, {})

            top_back_1, top_back_2 = st.columns([3.4, 1.0])
            with top_back_1:
                rng_choice = st.radio("Chart Horizon", ["1mo", "3mo", "6mo", "1y"], index=3, horizontal=True, label_visibility="collapsed", key="stock_rng_radio")
            with top_back_2:
                st.button("← All Markets & Fleet", on_click=close_stock, use_container_width=True)

            sdf, meta = fetch_stock_detail_history(sel_tkr, rng=rng_choice)
            curr_sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(q_live.get("currency", meta.get("currency", "USD")), "$")
            live_px = q_live.get("price") or (round(float(sdf["close"].iloc[-1]), 2) if not sdf.empty else None)
            pct_1d = q_live.get("pct_change", 0.0)
            vol_today = q_live.get("volume", 0)
            exch_name = q_live.get("exchange") or (ent["exchange"] if ent else "Global Exchange")
            hi_52 = q_live.get("high_52") or (float(sdf["high"].max()) if not sdf.empty else None)
            lo_52 = q_live.get("low_52") or (float(sdf["low"].min()) if not sdf.empty else None)

            px_str = f"{curr_sym}{live_px:,.2f}" if live_px is not None else "N/A"
            badge_cls = "pill-up" if pct_1d >= 0 else "pill-dn"
            arr = "▲" if pct_1d >= 0 else "▼"
            vol_str = f"{vol_today:,}" if vol_today else "N/A"
            rng_52_str = f"{curr_sym}{lo_52:,.2f} – {curr_sym}{hi_52:,.2f}" if (hi_52 and lo_52) else "N/A"

            st.markdown(
                f'<div class="glass-card">'
                f'<div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-start;gap:1rem;">'
                f'  <div>'
                f'    <div style="display:flex;align-items:center;gap:0.6rem;">'
                f'      <span style="font-size:1.55rem;font-weight:800;color:#FFFFFF;">{html.escape(ent["name"] if ent else sel_tkr)}</span>'
                f'      <span style="background:rgba(96,165,250,0.16);color:#60A5FA;padding:0.2rem 0.65rem;border-radius:999px;font-size:0.75rem;font-weight:700;">{html.escape(sel_tkr)} · {html.escape(exch_name)}</span>'
                f'    </div>'
                f'    <div style="font-size:0.83rem;color:#94A3B8;margin-top:0.3rem;">{html.escape(fund.get("fleet_note", "Aviation Equity Instrument"))}</div>'
                f'  </div>'
                f'  <div style="text-align:right;">'
                f'    <div style="font-size:2.1rem;font-weight:800;color:#FFFFFF;line-height:1.05;">{px_str}</div>'
                f'    <div style="margin-top:0.35rem;"><span class="{badge_cls}">{arr} {pct_1d:+.2f}% (1D)</span></div>'
                f'  </div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Financial & Trading Metrics Row (Hover Zoom Tiles)
            m_cols = st.columns(6, gap="small")
            fin_metrics = [
                ("Market Cap", fund.get("mkt_cap", "N/A")),
                ("Daily Volume", vol_str),
                ("52W Range", rng_52_str),
                ("Revenue (TTM)", fund.get("rev_ttm", "N/A")),
                ("Net Income", fund.get("net_inc", "N/A")),
                ("Op Margin / P/E", f"{fund.get('op_margin', 'N/A')} · {fund.get('pe', 'N/A')}"),
            ]
            for col, (mk, mv) in zip(m_cols, fin_metrics):
                with col:
                    st.markdown(
                        f'<div class="stat-mini"><div class="stat-k">{mk}</div><div class="stat-v">{html.escape(str(mv))}</div></div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:0.65rem;'></div>", unsafe_allow_html=True)

            # Interactive Price + 20D SMA + Volume Subplot
            if not sdf.empty:
                sdf["sma20"] = sdf["close"].rolling(20).mean()
                line_clr = "#34D399" if sdf["close"].iloc[-1] >= sdf["close"].iloc[0] else "#FB7185"
                fill_clr = "rgba(52, 211, 153, 0.14)" if line_clr == "#34D399" else "rgba(251, 113, 133, 0.14)"
                vol_clrs = ["#34D399" if c >= o else "#FB7185" for o, c in zip(sdf["open"].fillna(sdf["close"]), sdf["close"])]

                fig_stk = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.74, 0.26])
                fig_stk.add_trace(go.Scatter(x=sdf["date"], y=sdf["close"], mode="lines", name="Close", line=dict(color=line_clr, width=2.6), fill="tozeroy", fillcolor=fill_clr), row=1, col=1)
                fig_stk.add_trace(go.Scatter(x=sdf["date"], y=sdf["sma20"], mode="lines", name="20D SMA", line=dict(color="#60A5FA", width=1.6, dash="dot")), row=1, col=1)
                fig_stk.add_trace(go.Bar(x=sdf["date"], y=sdf["volume"], name="Volume", marker_color=vol_clrs, opacity=0.75), row=2, col=1)
                style_dark_chart(fig_stk, height=400)
                fig_stk.update_layout(title=f"{sel_tkr} — Price Action, 20-Day Moving Average & Trading Volume ({rng_choice.upper()})", hovermode="x unified", legend=dict(orientation="h", y=1.06, x=1, xanchor="right"))
                st.plotly_chart(fig_stk, use_container_width=True)

            # Live Airborne Fleet Context if entity is an Airline or OEM
            ent_iata = ent.get("iata") if ent else None
            if ent_iata:
                al_live = raw_df[raw_df["airline_code"] == ent_iata]
                st.markdown(f'<div class="sec-head"><div class="sec-title">Live Airborne Fleet Telemetry — {html.escape(ent["name"])} ({len(al_live):,} active)</div><div class="sec-sub">REAL-TIME UTILIZATION</div></div>', unsafe_allow_html=True)
                if not al_live.empty:
                    c1, c2 = st.columns(2, gap="large")
                    with c1:
                        fam_ct = al_live["Family"].value_counts().reset_index()
                        fam_ct.columns = ["Family", "Aircraft"]
                        fig_af = px.pie(fam_ct, names="Family", values="Aircraft", hole=0.62, color_discrete_sequence=["#60A5FA", "#34D399", "#FBBF24", "#A78BFA", "#FB7185"], title="Live Active Airframe Mix")
                        fig_af.update_traces(textinfo="label+percent", pull=[0.04] + [0]*(len(fam_ct)-1), marker=dict(line=dict(color="#0B0D12", width=2)))
                        fig_af.add_annotation(text=f"<b>{len(al_live)}</b><br>Airborne", x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#FFFFFF"))
                        style_dark_chart(fig_af, height=310)
                        fig_af.update_layout(showlegend=False)
                        st.plotly_chart(fig_af, use_container_width=True)
                    with c2:
                        sec_ct = al_live["sector"].value_counts().reset_index()
                        sec_ct.columns = ["Region", "Aircraft"]
                        fig_sc = px.bar(sec_ct, x="Aircraft", y="Region", orientation="h", text="Aircraft", color="Aircraft", color_continuous_scale=["#1E3A8A", "#60A5FA", "#34D399"], title="Regional Deployment Footprint")
                        fig_sc.update_traces(textposition="outside")
                        style_dark_chart(fig_sc, height=310)
                        fig_sc.update_layout(coloraxis_showscale=False, yaxis=dict(categoryorder="total ascending", title=""))
                        st.plotly_chart(fig_sc, use_container_width=True)

        # --- DEFAULT GLOBAL EQUITY & FLEET DASHBOARD ---
        else:
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
                arr = "▲" if up else "▼"
                svg = build_svg_sparkline(ser, color=sp_clr, width=215, height=38, uid=uid)
                with col:
                    st.markdown(
                        f'<div class="idx-card" style="animation-delay:{idx_i*0.06:.2f}s;">'
                        f'<div class="idx-kicker">{kicker}</div>'
                        f'<div class="idx-big">{big}</div>'
                        f'<div style="display:flex;align-items:center;gap:0.45rem;margin-bottom:0.45rem;">'
                        f'<span class="{pcls}">{arr} {dlt:+.1f}%</span>'
                        f'<span style="font-size:0.72rem;color:#94A3B8;">vs 24h avg</span>'
                        f'</div><div>{svg}</div></div>',
                        unsafe_allow_html=True,
                    )

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
                    height=385,
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
                        text="Net Profit ($B)",
                        color_continuous_scale=["#FB7185", "#FBBF24", "#34D399"],
                        title="Carrier Net Profit ($B) & Operating Margin (%)",
                    )
                    fig_prof.update_traces(texttemplate="$%{text:.2f}B", textposition="outside")
                    style_dark_chart(fig_prof, height=345)
                    fig_prof.update_layout(xaxis_title="", xaxis_tickangle=-25)
                    st.plotly_chart(fig_prof, use_container_width=True)

                with ch2:
                    body_ct = scoped_df["Body Type"].value_counts().reset_index()
                    body_ct.columns = ["Segment", "Count"]
                    fig_bd = px.pie(
                        body_ct,
                        names="Segment",
                        values="Count",
                        hole=0.64,
                        color_discrete_sequence=["#34D399", "#60A5FA", "#FBBF24", "#A78BFA", "#64748B"],
                        title="Global Active Fleet Composition by Body Class",
                    )
                    fig_bd.update_traces(
                        textinfo="label+percent",
                        pull=[0.04] + [0] * (len(body_ct) - 1),
                        marker=dict(line=dict(color="#0B0D12", width=2.5)),
                    )
                    fig_bd.add_annotation(text=f"<b>{len(scoped_df):,}</b><br>Active Tails", x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#FFFFFF"))
                    style_dark_chart(fig_bd, height=345)
                    fig_bd.update_layout(showlegend=False)
                    st.plotly_chart(fig_bd, use_container_width=True)

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
                    map_df["icon_data"] = [{"url": AIRLINER_ICON_URL, "width": 128, "height": 128, "anchorX": 64, "anchorY": 64, "mask": True}] * len(map_df)
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
                            initial_view_state=pdk.ViewState(latitude=25, longitude=10, zoom=1.55, pitch=36, bearing=0),
                            tooltip={
                                "html": "<div style='font-family:Inter,sans-serif;padding:6px;min-width:195px;'>"
                                        "<div style='font-weight:700;color:#FFF;font-size:13px;border-bottom:1px solid #334155;padding-bottom:3px;margin-bottom:4px;'>{callsign} ({icao24})</div>"
                                        "<div style='color:#CBD5E1;font-size:12px;'>{aircraft_type} · {Family}</div>"
                                        "<div style='color:#34D399;font-size:11px;font-weight:600;margin-top:3px;'>Altitude {alt_fmt} ft · Speed {spd_fmt} km/h</div>"
                                        "</div>",
                                "style": {"backgroundColor": "#13161E", "border": "1px solid #475569", "borderRadius": "10px"},
                            },
                            map_style="mapbox://styles/mapbox/dark-v11",
                        ),
                        use_container_width=True,
                    )
                    st.caption("Map Legend:  Emerald = Narrowbody  |  Blue = Widebody  |  Amber = Freighter / Cargo  |  Silver = Regional")

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
    # VIEW 2: OEM BACKLOG, UPCOMING DELIVERIES & PROBABLE DELIVERY SLOTS
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
            ("NEXT 12M DELIVERIES", f"{int(oem_df['Next_12M_Deliveries'].sum()):,}", "Projected global OEM output", "#FBBF24"),
            ("GROSS BACKLOG VALUE", f"${oem_df['Backlog_Value_Bn'].sum():,.0f}B", "Implied catalog book value", "#F8FAFC"),
        ]
        for idx_o, (col, (k, v, sub, clr)) in enumerate(zip([o1, o2, o3, o4], oem_cards)):
            with col:
                st.markdown(
                    f'<div class="idx-card" style="padding-bottom:1rem;animation-delay:{idx_o*0.06:.2f}s;">'
                    f'<div class="idx-kicker">{k}</div>'
                    f'<div class="idx-big" style="color:{clr};">{v}</div>'
                    f'<div style="font-size:0.75rem;color:#94A3B8;">{sub}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:0.65rem;'></div>", unsafe_allow_html=True)

        oc1, oc2 = st.columns([1.35, 1.0], gap="large")
        with oc1:
            fig_bl = px.bar(
                oem_df.sort_values("Backlog", ascending=True),
                x="Backlog",
                y="Program",
                color="OEM",
                orientation="h",
                text="Backlog_Years",
                color_discrete_map={"Airbus": "#60A5FA", "Boeing": "#34D399", "Embraer": "#FBBF24", "COMAC": "#FB7185", "ATR": "#94A3B8"},
                title="Order Backlog & Implied Production Horizon (Years)",
            )
            fig_bl.update_traces(texttemplate="%{text} yrs", textposition="outside")
            style_dark_chart(fig_bl, height=390)
            fig_bl.update_layout(yaxis_title="", xaxis_title="Firm Unfilled Orders (Units)")
            st.plotly_chart(fig_bl, use_container_width=True)

        with oc2:
            in_svc = pd.DataFrame([{"OEM": k, "Airframes": v} for k, v in live_oems.items() if k in ["Airbus", "Boeing", "Embraer", "ATR", "COMAC"]])
            if not in_svc.empty:
                fig_sh = px.pie(
                    in_svc,
                    names="OEM",
                    values="Airframes",
                    hole=0.64,
                    color="OEM",
                    color_discrete_map={"Airbus": "#60A5FA", "Boeing": "#34D399", "Embraer": "#FBBF24", "COMAC": "#FB7185", "ATR": "#94A3B8"},
                    title="Live In-Service Market Share (ADS-B)",
                )
                fig_sh.update_traces(textinfo="label+percent", pull=[0.04] + [0]*(len(in_svc)-1), marker=dict(line=dict(color="#0B0D12", width=2.5)))
                fig_sh.add_annotation(text=f"<b>{in_svc['Airframes'].sum():,}</b><br>Live Fleet", x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#FFFFFF"))
                style_dark_chart(fig_sh, height=390)
                fig_sh.update_layout(showlegend=False)
                st.plotly_chart(fig_sh, use_container_width=True)

        # Upcoming Deliveries & Probable Available Delivery Slots Section
        st.markdown(
            '<div class="sec-head">'
            '<div class="sec-title">Upcoming Deliveries &amp; Probable Available Delivery Slots by Aircraft Type</div>'
            '<div class="sec-sub">DIRECT OEM VS. LESSOR SECONDARY AVAILABILITY</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        slot_c1, slot_c2 = st.columns([1.25, 1.0], gap="large")
        with slot_c1:
            st.dataframe(
                oem_df[["OEM", "Program", "Segment", "Monthly_Rate", "Next_12M_Deliveries", "Direct_Slot_Window", "Lessor_Slot", "Key_Slots"]],
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config={
                    "Monthly_Rate": st.column_config.NumberColumn("Rate / Mo", format="%d / mo"),
                    "Next_12M_Deliveries": st.column_config.NumberColumn("Next 12M Deliveries", format="%d units"),
                    "Direct_Slot_Window": "Probable Direct OEM Slot",
                    "Lessor_Slot": "Probable Lessor Slot",
                    "Key_Slots": "Primary Upcoming Recipients",
                },
            )

        with slot_c2:
            fig_slot = px.bar(
                oem_df.sort_values("Direct_Slot_Year", ascending=True),
                x="Direct_Slot_Year",
                y="Program",
                color="OEM",
                orientation="h",
                text="Direct_Slot_Window",
                color_discrete_map={"Airbus": "#60A5FA", "Boeing": "#34D399", "Embraer": "#FBBF24", "COMAC": "#FB7185", "ATR": "#94A3B8"},
                title="Probable Next Open Direct OEM Delivery Slot",
            )
            fig_slot.update_traces(textposition="outside")
            style_dark_chart(fig_slot, height=380)
            fig_slot.update_xaxes(range=[2025, 2033], title="Earliest Probable Direct Slot Year")
            fig_slot.update_yaxes(title="")
            st.plotly_chart(fig_slot, use_container_width=True)

    # =========================================================================
    # VIEW 3: DIGITAL TWIN & MRO (AIRFRAME RENDER TOP -> MRO HUBS AT BOTTOM)
    # =========================================================================
    elif nav_view == "Digital Twin & MRO":
        sample_tails = df.sort_values("baro_altitude", ascending=False).head(100)
        tail_opts = [f"{r['callsign']} | {r['icao24']} | {r['aircraft_type']} ({r['airline_code']})" for _, r in sample_tails.iterrows()]

        if tail_opts:
            picked = st.selectbox("Select Live Commercial Tail for Digital Twin & MRO Inspection", tail_opts)
            hex_sel = picked.split("|")[1].strip()
            trow = df[df["icao24"] == hex_sel].iloc[0]

            specs = AIRFRAME_TECH_SPECS.get(
                trow["Family"],
                {"engines": "High-Bypass Turbofan", "seats": "Commercial Config", "range_km": "6,000+ km", "mtow_t": "78+ t", "cruise": "Mach 0.78", "cmv_m": "$42M – $85M", "lease_k": "$280k – $550k/mo"},
            )
            al_info = AIRLINE_FINANCIAL_BASELINES.get(trow["airline_code"], {})
            est_age = al_info.get("avg_age_yrs", 4.6 if trow["Generation"] == "Next-Gen" else 13.8)
            a_prog = int((hash(hex_sel) % 72) + 20)
            c_prog = int(((est_age % 2.0) / 2.0) * 100)
            d_prog = int(min(100, (est_age / 8.0) * 100))

            # --- TOP HERO: AIRFRAME TECHNICAL RENDER + FULL AIRCRAFT INTELLIGENCE ---
            hero_l, hero_r = st.columns([1.25, 1.35], gap="large")
            with hero_l:
                svg_render = build_airframe_blueprint_svg(trow["Body Type"], bool(trow["is_cargo"]), trow["aircraft_type"])
                st.markdown(
                    f'<div class="render-stage">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.55rem;">'
                    f'<span style="font-size:0.74rem;font-weight:700;color:#60A5FA;letter-spacing:0.05em;">DIGITAL TWIN SCHEMATIC</span>'
                    f'<span style="font-size:0.74rem;font-weight:700;color:#34D399;">{trow["flight_phase"].upper()}</span>'
                    f'</div>'
                    f'{svg_render}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            with hero_r:
                op_name = airline_map.get(trow["airline_code"], trow["airline_code"])
                st.markdown(
                    f'<div class="glass-card" style="margin-bottom:0.75rem;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                    f'  <div>'
                    f'    <div style="font-size:1.38rem;font-weight:800;color:#FFFFFF;">{html.escape(str(trow["callsign"]))} · {html.escape(str(trow["aircraft_type"]))}</div>'
                    f'    <div style="font-size:0.83rem;color:#94A3B8;margin-top:0.15rem;">{html.escape(trow["Manufacturer"])} · {html.escape(trow["Family"])} · Operated by <strong style="color:#E2E8F0;">{html.escape(op_name)}</strong></div>'
                    f'  </div>'
                    f'  <span class="pill-up">{trow["Generation"]}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                s1, s2, s3 = st.columns(3, gap="small")
                spec_tiles = [
                    ("ICAO Hex / Reg", trow["icao24"]),
                    ("Altitude / Speed", f"{trow['baro_altitude']:,.0f} ft · {trow['velocity']:,.0f} km/h"),
                    ("Est. Fleet Age", f"{est_age:.1f} Years"),
                    ("Powerplant Options", specs["engines"]),
                    ("Range / MTOW", f"{specs['range_km']} · {specs['mtow_t']}"),
                    ("Est. CMV / Lease", f"{specs['cmv_m']} · {specs['lease_k']}"),
                ]
                for idx_s, (sk, sv) in enumerate(spec_tiles):
                    target_c = [s1, s2, s3][idx_s % 3]
                    with target_c:
                        st.markdown(
                            f'<div class="stat-mini" style="margin-bottom:0.55rem;">'
                            f'<div class="stat-k">{sk}</div>'
                            f'<div class="stat-v" style="font-size:0.9rem;">{html.escape(str(sv))}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            # MRO Check Horizon Bars
            st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3, gap="medium")
            for col, (lbl, pct_val, clr) in zip(
                [b1, b2, b3],
                [
                    ("A-Check Cycle (~600 Flight Hours)", a_prog, "#60A5FA"),
                    ("C-Check Window (~24 Months)", c_prog, "#34D399"),
                    ("Heavy D-Check Structural Horizon (~8 Years)", d_prog, "#FBBF24"),
                ],
            ):
                with col:
                    st.markdown(
                        f'<div class="mro-bar-wrap">'
                        f'<div style="display:flex;justify-content:space-between;font-size:0.8rem;font-weight:600;color:#E2E8F0;">'
                        f'<span>{lbl}</span><span style="color:{clr};font-weight:700;">{pct_val}%</span></div>'
                        f'<div class="mro-track"><div class="mro-fill" style="width:{pct_val}%;background:{clr};"></div></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Engine Base Chart
            gen_oem = df[df["Manufacturer"] != "Other"].groupby(["Manufacturer", "Generation"]).size().reset_index(name="Count")
            if not gen_oem.empty:
                st.markdown("<div style='height:0.45rem;'></div>", unsafe_allow_html=True)
                fig_mro = px.bar(
                    gen_oem,
                    x="Manufacturer",
                    y="Count",
                    color="Generation",
                    barmode="stack",
                    text="Count",
                    color_discrete_map={"Next-Gen": "#34D399", "Legacy": "#475569"},
                    title="Global Engine & Airframe MRO Base: Next-Gen vs. Legacy Active Fleet",
                )
                style_dark_chart(fig_mro, height=295)
                fig_mro.update_layout(xaxis_title="", legend=dict(orientation="h", y=1.08, x=1, xanchor="right", title=None))
                st.plotly_chart(fig_mro, use_container_width=True)

            # --- BOTTOM SECTION: NEAREST MRO HUB & GLOBAL MRO HUB LIST ---
            hub_dists = [(h["hub"], h["name"], h["specialty"], float(haversine_km(trow["latitude"], trow["longitude"], h["lat"], h["lon"]))) for h in MRO_HUBS]
            near_hub = min(hub_dists, key=lambda x: x[3])

            st.markdown('<div class="sec-head"><div class="sec-title">Nearest MRO Base &amp; Global Maintenance Hub Monitor</div><div class="sec-sub">DIVERSION &amp; SCHEDULED SHOP-VISIT PROXIMITY</div></div>', unsafe_allow_html=True)

            st.markdown(
                f'<div class="glass-card" style="padding:1rem 1.25rem;">'
                f'<div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:0.8rem;">'
                f'  <div>'
                f'    <div style="font-size:0.72rem;font-weight:700;color:#FBBF24;text-transform:uppercase;letter-spacing:0.05em;">Nearest MRO Facility to {html.escape(str(trow["callsign"]))}</div>'
                f'    <div style="font-size:1.15rem;font-weight:800;color:#FFFFFF;margin-top:0.15rem;">{near_hub[0]} — {html.escape(near_hub[1])}</div>'
                f'    <div style="font-size:0.82rem;color:#94A3B8;margin-top:0.15rem;">Capability: {html.escape(near_hub[2])}</div>'
                f'  </div>'
                f'  <div style="text-align:right;">'
                f'    <div style="font-size:1.45rem;font-weight:800;color:#FBBF24;">{near_hub[3]:,.0f} km</div>'
                f'    <div style="font-size:0.75rem;color:#94A3B8;">Great-circle distance</div>'
                f'  </div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

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
            st.dataframe(pd.DataFrame(mro_rows).sort_values("Low-Alt Movements (<120km)", ascending=False), use_container_width=True, hide_index=True, height=300)

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
            f'<span style="font-size:0.74rem;font-weight:700;color:#60A5FA;letter-spacing:0.05em;">AVIATION MARKET WIRE &amp; BRIEFING</span>'
            f'<span style="background:rgba(96,165,250,0.14);color:#60A5FA;padding:0.18rem 0.65rem;border-radius:999px;font-size:0.72rem;font-weight:700;">{len(news_items)} LIVE STORIES</span>'
            f'</div>'
            f'<div style="font-size:1.12rem;font-weight:800;color:#FFFFFF;margin-bottom:0.35rem;">'
            f'{len(raw_df):,} active commercial airframes tracked worldwide · {html.escape(top_al_name)} ({top_al}) leads airborne lift'
            f'</div>'
            f'<div style="font-size:0.85rem;color:#CBD5E1;line-height:1.55;">'
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
                        f'<span style="font-size:0.71rem;font-weight:700;color:{tag_clr};text-transform:uppercase;">{item["tag"]}</span>'
                        f'<span style="font-size:0.72rem;color:#64748B;">{html.escape(item["source"])} · {html.escape(item["published"])}</span>'
                        f'</div>'
                        f'<a href="{html.escape(item["link"])}" target="_blank">{html.escape(item["title"])}</a>'
                        f'<div class="news-snip">{html.escape(item["snippet"])}...</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
