import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import pydeck as pdk
from data_ingestion.client import OpenSkyClient
from supabase import create_client

# =====================================================================
# GLOBAL CONFIGURATION 
# =====================================================================
st.set_page_config(page_title="AeroTrack // Intelligence", layout="wide", initial_sidebar_state="collapsed")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

AIRPORT_MAP = {
    "ATL": "Atlanta", "DFW": "Dallas", "DEN": "Denver", "ORD": "Chicago", "LAX": "Los Angeles", 
    "JFK": "New York", "LHR": "London", "HND": "Tokyo", "CDG": "Paris", "DXB": "Dubai", 
    "DEL": "New Delhi", "BOM": "Mumbai", "FRA": "Frankfurt", "AMS": "Amsterdam", "MAD": "Madrid",
    "SIN": "Singapore", "HKG": "Hong Kong", "SYD": "Sydney", "YYZ": "Toronto", "IST": "Istanbul"
}

st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { padding: 1.5rem 2rem; max-width: 100%; }
    .main { background-color: #000000; color: #e0e0e0; font-family: 'SF Mono', Consolas, monospace; }
    div.stButton > button:first-child {
        background-color: transparent; color: #fff; border: 2px solid #333; 
        border-radius: 0px; font-family: inherit; font-size: 15px; font-weight: bold; height: 45px;
    }
    div.stButton > button:first-child:hover { border-color: #fff; color: #fff; background: rgba(255,255,255,0.1); }
    .stDataFrame { border: none !important; font-size: 16px !important; }
    </style>
    """, unsafe_allow_html=True)

def safe_float(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default

# =====================================================================
# DATA MANAGEMENT ENGINE
# =====================================================================
try: client = OpenSkyClient()
except Exception: st.stop()

@st.cache_data(ttl=86400) 
def fetch_dynamic_airline_map(api_key):
    try:
        res = requests.get(f"https://airlabs.co/api/v9/airlines?api_key={api_key}", timeout=15)
        if res.status_code == 200:
            return {al.get("iata_code"): al.get("name") for al in res.json().get("response", []) if al.get("iata_code")}
    except Exception: pass
    return {}

@st.cache_data(ttl=15)
def fetch_live_fleet_snapshot(api_key):
    tactical_grid = {}
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={api_key}", timeout=15)
        for ac in (res.json().get("response", []) if res.status_code == 200 else []):
            try:
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                tactical_grid[hex_code] = {
                    "icao24": hex_code, 
                    "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": float(ac.get("lat") or 0), 
                    "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084, 
                    "velocity": float(ac.get("speed") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(), 
                    "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip()
                }
            except Exception: continue
    except Exception: pass
    return pd.DataFrame(list(tactical_grid.values()))

@st.cache_data(ttl=30)
def get_historical_macro_intel(airline_map):
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(1).execute()
        if not res.data: return None
        current = res.data[0]
        
        raw_apt = str(current.get('busiest_airport', 'DFW')).upper()
        apt_txt = f"{raw_apt} ({AIRPORT_MAP.get(raw_apt, 'Intl Hub')})"
        
        raw_g_carrier = str(current.get('top_global_carrier', 'UNKN')).upper()
        g_carrier_txt = f"{raw_g_carrier} ({airline_map.get(raw_g_carrier, 'Commercial Operator')})"
        
        # Safely parse the JSON payload in case Supabase returns it as a string
        raw_payload = current.get('intelligence_payload', {})
        if isinstance(raw_payload, str):
            try: raw_payload = json.loads(raw_payload)
            except json.JSONDecodeError: raw_payload = {}

        return {
            "density": f"{int(current.get('total_flights', 0)):,}",
            "busiest_region": str(current.get('busiest_region', 'NORTH AMERICAN SECTOR')).upper(),
            "busiest_airport": apt_txt,
            "global_carrier": g_carrier_txt,
            "global_airframe": str(current.get('top_global_airframe', 'A320')).upper(),
            "regional_payload": raw_payload
        }
    except Exception: return None

# =====================================================================
# INTERFACE PRESENTATION LAYOUT
# =====================================================================
dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)
df = fetch_live_fleet_snapshot(client.api_key)
macro = get_historical_macro_intel(dynamic_airline_map)

if not df.empty:
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 15px;">
        <div>
            <div style="font-size: 13px; color: #666; letter-spacing: 2px; font-weight: bold;">STRATEGIC MATRIX INFRASTRUCTURE</div>
            <div style="font-size: 30px; font-weight: bold; color: #fff; letter-spacing: -0.5px;">AEROTRACK // ASSET INTEL</div>
        </div>
        <div>
            <div style="font-size: 13px; color: #666; letter-spacing: 2px; font-weight: bold;">LIVE_TRACKS</div>
            <div style="font-size: 30px; font-weight: bold; color: #00ffcc; text-align: right;">{len(df):,}</div>
        </div>
        <div style="font-size: 13px; color: #555; text-align: right; line-height: 1.4;">
            ASSET CAPITAL UTILIZATION ENGINES<br>SYSTEM SNAPSHOT LAYER // AUTH: SATVIK-7773
        </div>
    </div>
    """, unsafe_allow_html=True)

    if macro:
        st.markdown(f"""
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 15px; background-color: rgba(255,255,255,0.02); padding: 15px; border: 1px solid #222; margin-bottom: 20px; font-size: 13px;">
            <div>
                <span style="color:#666; font-weight:bold;">VOLUME INDEX</span><br>
                • Active Aircraft: <span style="color:#fff; font-weight:bold;">{macro['density']} units</span><br>
                • Peak Hub Footprint: <span style="color:#ffaa00; font-weight:bold;">{macro['busiest_airport']}</span>
            </div>
            <div>
                <span style="color:#666; font-weight:bold;">GLOBAL MARKET LEADER</span><br>
                • Top Carrier (Active Fleet): <span style="color:#00ffcc; font-weight:bold;">{macro['global_carrier']}</span>
            </div>
            <div>
                <span style="color:#666; font-weight:bold;">GLOBAL FLEET STANDARD</span><br>
                • Top Airframe Type: <span style="color:#00ffcc; font-weight:bold;">{macro['global_airframe']}</span>
            </div>
            <div>
                <span style="color:#666; font-weight:bold;">REGIONAL DENSITY PEAK</span><br>
                • Highest Traffic Sector: <span style="color:#ff3333; font-weight:bold;">{macro['busiest_region']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='font-size: 15px; color: #fff; font-weight: bold; margin-bottom: 8px;'>REGIONAL SECTOR OPERATOR EXPOSURE PROFILE</div>", unsafe_allow_html=True)
        
        reg_data = []
        if isinstance(macro.get('regional_payload'), dict):
            for s_name, s_vals in macro['regional_payload'].items():
                c_code = s_vals.get('top_carrier', 'UNKN')
                reg_data.append({
                    "Airspace Sector Zone": s_name,
                    "Dominant Operator Code": c_code,
                    "Operator Corporate Title": dynamic_airline_map.get(c_code, "Commercial Operator / Non-Scheduled"),
                    "Dominant Airframe Model Class": s_vals.get('top_airframe', 'UNKN')
                })
            
            if reg_data:
                st.dataframe(pd.DataFrame(reg_data), use_container_width=True, hide_index=True)
            else:
                st.info("Awaiting structural layout configurations from Database...")
        else:
            st.error("JSON payload decode error. Verify Supabase schema is set to JSONB.")
    else:
        st.markdown("<div style='color: #666; font-size: 12px; margin-bottom: 20px;'>AWAITING RE-RUN SIGNALS FROM BACKGROUND WORKER CORE...</div>", unsafe_allow_html=True)

    layer = pdk.Layer(
        'ScatterplotLayer',
        data=df,
        get_position='[longitude, latitude]',
        get_fill_color=[0, 255, 204, 70],
        get_radius=4000,
        radius_min_pixels=2.5,
        radius_max_pixels=8,
        pickable=True
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer], 
        initial_view_state=pdk.ViewState(latitude=22, longitude=10, zoom=1.3, pitch=0), 
        tooltip={"html": "<b>Asset ID:</b> {icao24}<br><b>Registration:</b> {callsign}<br><b>Airframe:</b> {aircraft_type}<br><b>Carrier:</b> {airline_code}<br><b>Altitude:</b> FL{baro_altitude:.0f} | <b>Speed:</b> {velocity:.0f} km/h", "style": {"backgroundColor": "#000", "color": "#fff", "fontFamily": "monospace", "fontSize": "13px", "border": "1px solid #333"}},
        map_style="mapbox://styles/mapbox/dark-v11"
    ), use_container_width=True)

    st.write("")
    if st.button("RUN GLOBAL PORTFOLIO SWEEP", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("<br><div style='font-size: 16px; color: #fff; margin-bottom: 8px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>RAW ASSET UTILIZATION MATRIX</div>", unsafe_allow_html=True)
    
    display_cols = ["icao24", "callsign", "airline_code", "aircraft_type", "baro_altitude", "velocity"]
    df_full = df[display_cols].copy()
    df_full = df_full.sort_values(by=["airline_code", "baro_altitude"], ascending=[True, False])

    df_full.rename(columns={
        "icao24": "Hex Frame ID", "callsign": "Flight Registration", 
        "airline_code": "Carrier Code", "aircraft_type": "Airframe Model",
        "baro_altitude": "Altitude (ft)", "velocity": "Ground Speed (km/h)"
    }, inplace=True)
    
    if "Carrier Code" in df_full.columns:
        c_idx = df_full.columns.get_loc("Carrier Code")
        df_full.insert(c_idx + 1, "Airline Operating Title", df_full["Carrier Code"].map(dynamic_airline_map).fillna("Private Air Asset / Non-Scheduled"))

    st.dataframe(df_full, use_container_width=True, hide_index=True)
else:
    st.error("ERR_NO_STREAM: Tracking pipeline validation required.")
