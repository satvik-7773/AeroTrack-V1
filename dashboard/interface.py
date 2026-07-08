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
# INITIALIZATION
# =====================================================================
st.set_page_config(page_title="AeroTrack // Root", layout="wide", initial_sidebar_state="collapsed")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- RAW TERMINAL / CUSTOM REACT AESTHETIC ---
st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { padding: 1rem 2rem; max-width: 100%; }
    .main { background-color: #000000; color: #e0e0e0; font-family: 'SF Mono', Consolas, monospace; }
    
    /* Custom Button */
    div.stButton > button:first-child {
        background-color: transparent; color: #fff; border: 1px solid #333; 
        border-radius: 0px; font-family: inherit; font-size: 12px; height: 35px;
    }
    div.stButton > button:first-child:hover { border-color: #fff; color: #fff; background: rgba(255,255,255,0.1); }
    
    /* Hide default dataframe styling */
    .stDataFrame { border: none !important; }
    </style>
    """, unsafe_allow_html=True)

def safe_float(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default

# =====================================================================
# CORE ENGINE
# =====================================================================
try: client = OpenSkyClient()
except Exception as e: st.stop()

@st.cache_data(ttl=15)
def fetch_global_fusion(api_key):
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []

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
                    "aircraft_type": str(ac.get("t", "")), "military": True, "Classification": "MILITARY"
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
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")), "flight_number": str(ac.get("flight_iata", "UNKN")),
                    "military": False
                }
                if hex_code in military_watchlist:
                    tactical_grid[hex_code].update({"military": True, "aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN")})
            except Exception: continue
    except Exception: pass

    df = pd.DataFrame(list(tactical_grid.values()))
    mil_df = pd.DataFrame(military_tracks)
    if not mil_df.empty: df = pd.concat([df, mil_df[~mil_df["icao24"].isin(df["icao24"])]], ignore_index=True)
    if df.empty: return df

    df["Classification"] = df.get("Classification", "CIVILIAN").fillna("CIVILIAN")
    df["Threat_Reason"] = ""
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750", "E55P", "C56X"]
   
    for idx, row in df.iterrows():
        try:
            vel, alt, ac_type, icao, is_mil = float(row.get("velocity", 0.0)), float(row.get("baro_altitude", 0.0)), str(row.get("aircraft_type", "")).upper(), str(row.get("icao24", "")), row.get("military", False)
            reasons = []
            if (alt < 15000 and vel > 850): reasons.append("LOW-ALT/HI-VEL")
            if (alt > (51000 if ac_type in biz_jets else 44000)): reasons.append("CEILING-BREACH")
            if (vel > 1250) or (vel > 1050 and alt < 28000): reasons.append("KINEMATIC-ANOMALY")
            
            if reasons: df.at[idx, "Threat_Reason"] = " | ".join(reasons)
            if is_mil: df.at[idx, "Classification"] = "MILITARY"
            elif reasons: df.at[idx, "Classification"] = "ANOMALY"    
        except Exception: pass

    return df

# =====================================================================
# UI RENDERING
# =====================================================================
df = fetch_global_fusion(client.api_key)

# Raw HTML Header instead of st.metric
if not df.empty:
    mil_count = len(df[df['military'] == True])
    anom_count = len(df[df['Classification'] == 'ANOMALY'])
    
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 20px;">
        <div>
            <div style="font-size: 10px; color: #666; letter-spacing: 1px;">SYSTEM</div>
            <div style="font-size: 18px; font-weight: bold; color: #fff;">AEROTRACK_V1</div>
        </div>
        <div>
            <div style="font-size: 10px; color: #666; letter-spacing: 1px;">ACTIVE_TRACKS</div>
            <div style="font-size: 18px; color: #00ffcc;">{len(df):,}</div>
        </div>
        <div>
            <div style="font-size: 10px; color: #666; letter-spacing: 1px;">MILITARY_ASSETS</div>
            <div style="font-size: 18px; color: #ffaa00;">{mil_count:,}</div>
        </div>
        <div>
            <div style="font-size: 10px; color: #666; letter-spacing: 1px;">KINEMATIC_ANOMALIES</div>
            <div style="font-size: 18px; color: #ff3333;">{anom_count:,}</div>
        </div>
        <div style="font-size: 10px; color: #444; text-align: right;">
            DATA: ADSB.LOL + AIRLABS<br>AUTH: SATVIK-7773
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_map, col_list = st.columns([7, 3])
    
    with col_map:
        # FLAT, FAST 2D PYDECK
        def assign_color(cls):
            if cls == "ANOMALY": return [255, 51, 51, 200]
            elif cls == "MILITARY": return [255, 170, 0, 200]
            return [0, 255, 204, 60]

        df['color'] = df['Classification'].apply(assign_color)
        
        layer = pdk.Layer(
            'ScatterplotLayer',
            data=df,
            get_position='[longitude, latitude]',
            get_fill_color='color',
            get_radius=3000,
            radius_min_pixels=2,
            radius_max_pixels=8,
            pickable=True
        )

        view_state = pdk.ViewState(latitude=20, longitude=0, zoom=1.2, pitch=0) # Flat pitch
        
        tooltip = {"html": "{icao24} | {callsign} | {aircraft_type} <br> FL{baro_altitude} | {velocity} km/h <br> <span style='color:orange'>{Classification}</span>", 
                   "style": {"backgroundColor": "#000", "color": "#fff", "fontFamily": "monospace", "border": "1px solid #333", "fontSize": "11px"}}

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="mapbox://styles/mapbox/dark-v11"), use_container_width=True)

    with col_list:
        if st.button("RUN MANUAL SWEEP", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            
        st.write("")
        display_cols = ["Classification", "icao24", "baro_altitude", "velocity", "Threat_Reason"]
        df_disp = df[[c for c in display_cols if c in df.columns]].copy()
        df_disp.rename(columns={"Classification": "CLASS", "icao24": "HEX", "baro_altitude": "ALT", "velocity": "SPD", "Threat_Reason": "FLAGS"}, inplace=True)
        
        if "CLASS" in df_disp.columns:
            df_disp["_rank"] = df_disp["CLASS"].map({"ANOMALY": 0, "MILITARY": 1, "CIVILIAN": 2})
            df_disp = df_disp.sort_values(by=["_rank", "ALT"], ascending=[True, False]).drop(columns=["_rank"])

        st.dataframe(df_disp, use_container_width=True, hide_index=True)

else:
    st.error("ERR_NO_DATA: Check network or API quota.")
