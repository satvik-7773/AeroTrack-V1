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
# INITIALIZATION & STATIC MAPS
# =====================================================================
st.set_page_config(page_title="AeroTrack // Root", layout="wide", initial_sidebar_state="collapsed")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Static Airport Map for the Macro Intelligence Header
AIRPORT_MAP = {
    "ATL": "Atlanta", "DFW": "Dallas", "DEN": "Denver", "ORD": "Chicago", "LAX": "Los Angeles", 
    "JFK": "New York", "LHR": "London", "HND": "Tokyo", "CDG": "Paris", "DXB": "Dubai", 
    "DEL": "New Delhi", "BOM": "Mumbai", "FRA": "Frankfurt", "AMS": "Amsterdam", "MAD": "Madrid",
    "SIN": "Singapore", "HKG": "Hong Kong", "SYD": "Sydney", "YYZ": "Toronto", "IST": "Istanbul"
}

@st.cache_resource
def init_radar_memory():
    return {}

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
# CORE ENGINE (PURE READ-ONLY TACTICAL CALCULATOR)
# =====================================================================
try: client = OpenSkyClient()
except Exception as e: st.stop()

@st.cache_data(ttl=86400) # Caches the dictionary for 24 hours to save API calls
def fetch_dynamic_airline_map(api_key):
    try:
        res = requests.get(f"https://airlabs.co/api/v9/airlines?api_key={api_key}", timeout=15)
        if res.status_code == 200:
            airlines = res.json().get("response", [])
            return {al.get("iata_code"): al.get("name") for al in airlines if al.get("iata_code")}
    except Exception:
        pass
    return {}

@st.cache_data(ttl=15)
def fetch_global_fusion(api_key):
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []
    
    radar_memory = init_radar_memory()
    now_ts = pd.Timestamp.utcnow().timestamp()

    # ADSB.LOL MILITARY
    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack/1.0"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code: continue
                military_watchlist[hex_code] = {"callsign": str(ac.get("flight", "")).strip(), "aircraft_type": str(ac.get("t", "")).strip()}
                military_tracks.append({
                    "icao24": hex_code, "callsign": str(ac.get("flight", "")).strip(),
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")), "velocity": safe_float(ac.get("gs")) * 1.852,
                    "heading": safe_float(ac.get("track")), "aircraft_type": str(ac.get("t", "")), 
                    "airline_code": "MIL", "military": True, "Classification": "MILITARY"
                })
    except Exception: pass

    # AIRLABS
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
                    "heading": float(ac.get("dir") or 0), "aircraft_type": str(ac.get("aircraft_icao", "UNKN")), 
                    "flight_number": str(ac.get("flight_iata", "UNKN")), "airline_code": str(ac.get("airline_iata", "UNKN")),
                    "military": False
                }
                if hex_code in military_watchlist:
                    tactical_grid[hex_code].update({
                        "military": True, 
                        "aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN"),
                        "airline_code": "MIL"
                    })
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
            vel, alt, heading, ac_type, icao, is_mil = float(row.get("velocity", 0.0)), float(row.get("baro_altitude", 0.0)), float(row.get("heading", 0.0)), str(row.get("aircraft_type", "")).upper(), str(row.get("icao24", "")), row.get("military", False)
            reasons = []
            
            # --- 1. ABSOLUTE KINEMATICS ---
            if (alt < 15000 and vel > 850): reasons.append("LOW-ALT/HI-VEL")
            if (alt > (49000 if ac_type in biz_jets else 45000)): reasons.append("CEILING-BREACH")
            if (vel > 1250) or (vel > 1050 and alt < 28000): reasons.append("OVER-SPEED")
            if (alt > 30000 and vel < 20): reasons.append("TELEMETRY ANOMALY")
            
            # --- 2. DELTA KINEMATICS ---
            if icao in radar_memory:
                last_data = radar_memory[icao]
                time_delta = now_ts - last_data['ts']
                
                if 10 < time_delta < 120:
                    h_diff = abs((heading - last_data['heading'] + 180) % 360 - 180)
                    v_diff = vel - last_data['velocity']
                    
                    if h_diff > 35 and vel > 300: reasons.append(f"HIGH-G-TURN ({int(h_diff)}°)")
                    if v_diff > 300: reasons.append("HARD-ACCEL")
                    elif v_diff < -400 and alt > 5000: reasons.append("HARD-DECEL")

            radar_memory[icao] = {'heading': heading, 'velocity': vel, 'ts': now_ts}

            # --- 3. THE HIERARCHY FIX ---
            if reasons: 
                df.at[idx, "Threat_Reason"] = " | ".join(reasons)
                df.at[idx, "Classification"] = "ANOMALY" 
            elif is_mil: 
                df.at[idx, "Classification"] = "MILITARY"
                  
        except Exception: pass

    # Read-Only Database Sightings Fetch
    try:
        tracked = supabase.table("aircraft_tracking").select("icao24,sightings").execute()
        sightings_lookup = {r["icao24"]: r["sightings"] for r in tracked.data}
        df["sightings"] = df["icao24"].map(sightings_lookup).fillna(0).astype(int)
    except Exception:
        df["sightings"] = 0

    return df

# =====================================================================
# 24-HOUR MACRO INTELLIGENCE
# =====================================================================
def get_macro_intelligence():
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(24).execute()
        stats_df = pd.DataFrame(res.data)
        if stats_df.empty: return None
        
        current = stats_df.iloc[0]
        if len(stats_df) > 1:
            avg_flights = stats_df["total_flights"].mean()
            avg_threat_pct = (stats_df["threat_count"].sum() / stats_df["total_flights"].sum()) * 100
        else:
            avg_flights = current["total_flights"]
            avg_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

        curr_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0
        flight_delta = ((current["total_flights"] - avg_flights) / avg_flights) * 100 if avg_flights > 0 else 0
        threat_delta = curr_threat_pct - avg_threat_pct
        
        raw_airport = str(current['busiest_airport']).upper()
        airport_display = f"{raw_airport} ({AIRPORT_MAP.get(raw_airport, 'Intl Hub')})"
        
        return {
            "density": f"{int(current['total_flights']):,}",
            "density_delta": f"{flight_delta:+.1f}%",
            "threat_pct": f"{curr_threat_pct:.1f}%",
            "threat_delta": f"{threat_delta:+.1f}%",
            "region": str(current['busiest_region']).upper(),
            "airport": airport_display
        }
    except Exception:
        return None

# =====================================================================
# UI RENDERING
# =====================================================================
df = fetch_global_fusion(client.api_key)
macro = get_macro_intelligence()

if not df.empty:
    mil_count = len(df[df['military'] == True])
    anom_count = len(df[df['Classification'] == 'ANOMALY'])
    
    # 1. LIVE TACTICAL HEADER
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 10px;">
        <div>
            <div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">SYSTEM</div>
            <div style="font-size: 32px; font-weight: bold; color: #fff;">AEROTRACK_V1</div>
        </div>
        <div>
            <div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">LIVE_TRACKS</div>
            <div style="font-size: 32px; font-weight: bold; color: #00ffcc;">{len(df):,}</div>
        </div>
        <div>
            <div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">MIL_ASSETS</div>
            <div style="font-size: 32px; font-weight: bold; color: #ffaa00;">{mil_count:,}</div>
        </div>
        <div>
            <div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">ANOMALIES</div>
            <div style="font-size: 32px; font-weight: bold; color: #ff3333;">{anom_count:,}</div>
        </div>
        <div style="font-size: 14px; color: #555; text-align: right; line-height: 1.5;">
            DATA: ADSB.LOL + AIRLABS<br>AUTH: SATVIK-7773
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. MACRO INTELLIGENCE HEADER
    if macro:
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; background-color: rgba(255,255,255,0.03); padding: 10px 20px; border: 1px solid #222; margin-bottom: 25px;">
            <div><span style="color:#666; font-size: 12px;">GLOBAL DENSITY (24H):</span> <span style="color:#fff; font-size: 16px;">{macro['density']}</span> <span style="color:{'#00ffcc' if float(macro['density_delta'].strip('%')) < 0 else '#ff3333'}; font-size: 12px;">[{macro['density_delta']}]</span></div>
            <div><span style="color:#666; font-size: 12px;">THREAT INDEX (24H):</span> <span style="color:#fff; font-size: 16px;">{macro['threat_pct']}</span> <span style="color:{'#00ffcc' if float(macro['threat_delta'].strip('%')) < 0 else '#ff3333'}; font-size: 12px;">[{macro['threat_delta']}]</span></div>
            <div><span style="color:#666; font-size: 12px;">HIGHEST AIR TRAFFIC:</span> <span style="color:#ffaa00; font-size: 16px;">{macro['region']}</span></div>
            <div><span style="color:#666; font-size: 12px;">BUSIEST AIRPORT:</span> <span style="color:#ffaa00; font-size: 16px;">{macro['airport']}</span></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='color: #666; font-size: 12px; margin-bottom: 25px;'>AWAITING BACKGROUND WORKER TELEMETRY...</div>", unsafe_allow_html=True)

    # 3. FULL WIDTH MAP
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
        get_radius=3500,
        radius_min_pixels=3,
        radius_max_pixels=10,
        pickable=True
    )

    view_state = pdk.ViewState(latitude=20, longitude=0, zoom=1.4, pitch=0) 
    
    tooltip = {"html": "{icao24} | {callsign} | {aircraft_type} ({airline_code}) <br> FL{baro_altitude} | {velocity} km/h <br> Sightings: {sightings} <br> <span style='color:orange; font-weight:bold;'>{Classification}</span>", 
               "style": {"backgroundColor": "#000", "color": "#fff", "fontFamily": "monospace", "border": "1px solid #333", "fontSize": "14px"}}

    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="mapbox://styles/mapbox/dark-v11"), use_container_width=True)

    # 4. CONTROL ROW
    st.write("")
    if st.button("EXECUTE SYSTEM RE-SWEEP", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # 5. UNFILTERED LOG
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 18px; color: #fff; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>UNFILTERED RAW TELEMETRY MATRIX LOG</div>", unsafe_allow_html=True)
    
    drop_cols = ["color", "heading"] 
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
        "Classification": "Status", "icao24": "Hex", "callsign": "Callsign", 
        "airline_code": "Carrier", "aircraft_type": "Airframe", "military": "Mil Asset", "sightings": "Sightings", 
        "Threat_Reason": "Flags", "baro_altitude": "Alt (ft)", "velocity": "Speed (km/h)"
    }, inplace=True)

    # --- DYNAMIC AIRLINE INJECTION ---
    dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)
    dynamic_airline_map["MIL"] = "Military Asset" 
    
    if "Carrier" in df_full.columns:
        carrier_idx = df_full.columns.get_loc("Carrier")
        df_full.insert(carrier_idx + 1, "Airline Name", df_full["Carrier"].map(dynamic_airline_map).fillna("Unknown Carrier"))

    st.dataframe(df_full, use_container_width=True, hide_index=True)

else:
    st.error("ERR_NO_DATA: Check tracking configuration parameters.")
