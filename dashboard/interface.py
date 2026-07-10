import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import pydeck as pdk
from data_ingestion.client import OpenSkyClient
from supabase import create_client

# =====================================================================
# GLOBAL CONFIGURATION & MASTER DATA DICTIONARIES
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
def fetch_global_fusion(api_key):
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []

    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack/1.0"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code: continue
                military_watchlist[hex_code] = {"aircraft_type": str(ac.get("t", "")).strip()}
                military_tracks.append({
                    "icao24": hex_code, "callsign": str(ac.get("flight", "")).strip(),
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")), "velocity": safe_float(ac.get("gs")) * 1.852,
                    "aircraft_type": str(ac.get("t", "")), "airline_code": "MIL", "military": True, "Classification": "MILITARY"
                })
    except Exception: pass

    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={api_key}", timeout=15)
        for ac in (res.json().get("response", []) if res.status_code == 200 else []):
            try:
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                tactical_grid[hex_code] = {
                    "icao24": hex_code, "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084, "velocity": float(ac.get("speed") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(), "flight_number": str(ac.get("flight_iata", "UNKN")), 
                    "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip(), "military": False, "Classification": "CIVILIAN"
                }
                if hex_code in military_watchlist:
                    tactical_grid[hex_code].update({"military": True, "aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN"), "airline_code": "MIL", "Classification": "MILITARY"})
            except Exception: continue
    except Exception: pass

    df = pd.DataFrame(list(tactical_grid.values()))
    mil_df = pd.DataFrame(military_tracks)
    if not mil_df.empty: df = pd.concat([df, mil_df[~mil_df["icao24"].isin(df["icao24"])]], ignore_index=True)
    if df.empty: return df

    if "Classification" not in df.columns: df["Classification"] = "CIVILIAN"
    else: df["Classification"] = df["Classification"].fillna("CIVILIAN")

    df["Threat_Reason"] = ""
    
    biz_jets = [
        "GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "GL5T", "GL7T", "G280", "G150", 
        "CL30", "CL35", "CL60", "CRJ2", "F900", "F9EX", "FA7X", "FA8X", "F2TH", 
        "C750", "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C", 
        "E55P", "E50P", "E550", "E135", "E35L", "LJ60", "LJ75", "LJ70", "LJ45", "LJ40", "LJ35", "HDJT", "PC24"
    ]
   
    for idx, row in df.iterrows():
        try:
            vel, alt, ac_type, is_mil = float(row.get("velocity", 0.0)), float(row.get("baro_altitude", 0.0)), str(row.get("aircraft_type", "")), row.get("military", False)
            reasons = []
            
            # --- STATIC KINEMATIC EVALUATION ---
            if (alt < 15000 and vel > 850): reasons.append("LOW-ALT/HI-VEL")
            if (alt > (49000 if ac_type in biz_jets else 45000)): reasons.append("CEILING-BREACH")
            if (vel > 1250) or (vel > 1050 and alt < 28000): reasons.append("OVER-SPEED")
            if (alt > 30000 and vel < 20): reasons.append("TELEMETRY ANOMALY")
            
            if reasons: 
                df.at[idx, "Threat_Reason"] = " | ".join(reasons)
                df.at[idx, "Classification"] = "ANOMALY" 
            elif is_mil: 
                df.at[idx, "Classification"] = "MILITARY"
        except Exception: pass

    try:
        tracked = supabase.table("aircraft_tracking").select("icao24,sightings").execute()
        sightings_lookup = {r["icao24"]: r["sightings"] for r in tracked.data}
        df["sightings"] = df["icao24"].map(sightings_lookup).fillna(0).astype(int)
    except Exception: df["sightings"] = 0

    return df

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
        
        return {
            "density": f"{int(current.get('total_flights', 0)):,}",
            "busiest_region": str(current.get('busiest_region', 'NORTH AMERICAN SECTOR')).upper(),
            "busiest_airport": apt_txt,
            "global_carrier": g_carrier_txt,
            "global_airframe": str(current.get('top_global_airframe', 'B738')).upper(),
            "regional_payload": current.get('intelligence_payload', {})
        }
    except Exception: return None

# =====================================================================
# UI PRESENTATION GRID
# =====================================================================
dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)
dynamic_airline_map["MIL"] = "Military Asset"

df = fetch_global_fusion(client.api_key)
macro = get_historical_macro_intel(dynamic_airline_map)

if not df.empty:
    mil_count = len(df[df['military'] == True])
    anom_count = len(df[df['Classification'] == 'ANOMALY'])
    
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
        <div>
            <div style="font-size: 13px; color: #666; letter-spacing: 2px; font-weight: bold;">MIL_ASSETS</div>
            <div style="font-size: 30px; font-weight: bold; color: #ffaa00; text-align: right;">{mil_count:,}</div>
        </div>
        <div>
            <div style="font-size: 13px; color: #666; letter-spacing: 2px; font-weight: bold;">FLAGGED_ANOMALIES</div>
            <div style="font-size: 30px; font-weight: bold; color: #ff3333; text-align: right;">{anom_count:,}</div>
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

        # 3. REGIONAL MARKET PROFILE TABLE
        st.markdown("<div style='font-size: 15px; color: #fff; font-weight: bold; margin-bottom: 8px;'>REGIONAL SECTOR OPERATOR EXPOSURE PROFILE</div>", unsafe_allow_html=True)
        
        reg_data = []
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

    # Visual Mapping Colors Restoration
    def assign_color(cls):
        if cls == "ANOMALY": return [255, 51, 51, 220]
        elif cls == "MILITARY": return [255, 170, 0, 220]
        return [0, 255, 204, 80]

    df['color'] = df['Classification'].apply(assign_color)
    
    layer = pdk.Layer(
        'ScatterplotLayer',
        data=df,
        get_position='[longitude, latitude]',
        get_fill_color='color',
        get_radius=4000,
        radius_min_pixels=2.5,
        radius_max_pixels=8,
        pickable=True
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer], 
        initial_view_state=pdk.ViewState(latitude=22, longitude=10, zoom=1.3, pitch=0), 
        tooltip={"html": "<b>Asset ID:</b> {icao24}<br><b>Registration:</b> {callsign}<br><b>Airframe:</b> {aircraft_type}<br><b>Status:</b> {Classification}<br><b>Altitude:</b> FL{baro_altitude:.0f} | <b>Speed:</b> {velocity:.0f} km/h", "style": {"backgroundColor": "#000", "color": "#fff", "fontFamily": "monospace", "fontSize": "13px", "border": "1px solid #333"}},
        map_style="mapbox://styles/mapbox/dark-v11"
    ), use_container_width=True)

    # 5. CONTROL GRID
    st.write("")
    if st.button("RUN GLOBAL PORTFOLIO SWEEP", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # 6. ASSET TRACKING DATA LOG
    st.markdown("<br><div style='font-size: 16px; color: #fff; margin-bottom: 8px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>RAW CAPACITY UTILIZATION RESOURCE MATRIX</div>", unsafe_allow_html=True)
    
    drop_cols = ["color"]
    display_cols = [c for c in df.columns if c not in drop_cols]
    
    front_cols = ["Classification", "icao24", "callsign", "airline_code", "aircraft_type", "military", "sightings", "Threat_Reason"]
    for c in reversed(front_cols):
        if c in display_cols:
            display_cols.insert(0, display_cols.pop(display_cols.index(c)))
            
    df_full = df[display_cols].copy()
    
    if "Classification" in df_full.columns:
        df_full["_rank"] = df_full["Classification"].map({"ANOMALY": 0, "MILITARY": 1, "CIVILIAN": 2})
        df_full = df_full.sort_values(by=["_rank", "baro_altitude"], ascending=[True, False]).drop(columns=["_rank"])

    df_full.rename(columns={
        "Classification": "Status", "icao24": "Hex ID", "callsign": "Registration / Call", 
        "airline_code": "Carrier Code", "aircraft_type": "Airframe Model", "military": "Mil Asset", 
        "sightings": "Observed Sightings", "Threat_Reason": "Kinematic Alerts",
        "baro_altitude": "Altitude (ft)", "velocity": "Ground Speed (km/h)"
    }, inplace=True)
    
    if "Carrier Code" in df_full.columns:
        c_idx = df_full.columns.get_loc("Carrier Code")
        df_full.insert(c_idx + 1, "Airline Operating Title", df_full["Carrier Code"].map(dynamic_airline_map).fillna("Private Air Asset / Non-Scheduled"))

    st.dataframe(df_full, use_container_width=True, hide_index=True)
else:
    st.error("ERR_NO_STREAM: Fleet array monitoring validation required.")
