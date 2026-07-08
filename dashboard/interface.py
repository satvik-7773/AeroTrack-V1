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

# --- TERMINAL AESTHETIC GRAPHICS CONFIG ---
st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { padding: 1.5rem 2rem; max-width: 100%; }
    .main { background-color: #000000; color: #e0e0e0; font-family: 'SF Mono', Consolas, monospace; }
    
    /* Action Controls */
    div.stButton > button:first-child {
        background-color: transparent; color: #fff; border: 2px solid #333; 
        border-radius: 0px; font-family: inherit; font-size: 15px; font-weight: bold; height: 45px;
    }
    div.stButton > button:first-child:hover { border-color: #fff; color: #fff; background: rgba(255,255,255,0.1); }
    
    /* Clean Logs Layout */
    .stDataFrame { border: none !important; font-size: 16px !important; }
    </style>
    """, unsafe_allow_html=True)

def safe_float(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default

# =====================================================================
# CORE ENGINE (LIVE TACTICAL FEED)
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

    if "Classification" not in df.columns: df["Classification"] = "CIVILIAN"
    else: df["Classification"] = df["Classification"].fillna("CIVILIAN")

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

    # --- SUPABASE PERSISTENCE TRACKING ---
    flagged_df = df[(df["military"] == True) & (df["Threat_Reason"] != "")]
    for _, row in flagged_df.iterrows():
        try:
            supabase.table("anomaly_history").insert({
                "icao24": str(row.get("icao24", "")), "classification": str(row.get("Classification", "")),
                "threat_reason": str(row.get("Threat_Reason", "")), "latitude": float(row.get("latitude", 0)),
                "longitude": float(row.get("longitude", 0))
            }).execute()
        except Exception: pass
        
        try:
            icao = str(row.get("icao24", "")).upper().strip()
            existing = supabase.table("aircraft_tracking").select("*").eq("icao24", icao).execute()

            if existing.data:
                record = existing.data[0]
                now = pd.Timestamp.utcnow()
                increment = ((now - pd.to_datetime(record["last_seen"])).total_seconds() > 300)
                update_data = {"last_seen": now.isoformat(), "latest_classification": str(row.get("Classification", ""))}
                if increment: update_data["sightings"] = record["sightings"] + 1
                supabase.table("aircraft_tracking").update(update_data).eq("icao24", icao).execute()
            else:
                now = pd.Timestamp.utcnow().isoformat()
                supabase.table("aircraft_tracking").insert({"icao24": icao, "first_seen": now, "last_seen": now, "sightings": 1, "latest_classification": str(row.get("Classification", ""))}).execute()
        except Exception: pass

    try:
        tracked = supabase.table("aircraft_tracking").select("icao24,sightings").execute()
        sightings_lookup = {r["icao24"]: r["sightings"] for r in tracked.data}
        df["sightings"] = df["icao24"].map(sightings_lookup).fillna(0).astype(int)
    except Exception:
        df["sightings"] = 0

    return df

# =====================================================================
# 24-HOUR MACRO INTELLIGENCE (SUPABASE HOURLY WORKER DATA)
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
            avg_mil_pct = (stats_df["military_count"].sum() / stats_df["total_flights"].sum()) * 100
        else:
            avg_flights = current["total_flights"]
            avg_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0
            avg_mil_pct = (current["military_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

        curr_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0
        curr_mil_pct = (current["military_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

        flight_delta = ((current["total_flights"] - avg_flights) / avg_flights) * 100 if avg_flights > 0 else 0
        threat_delta = curr_threat_pct - avg_threat_pct
        
        return {
            "density": f"{int(current['total_flights']):,}",
            "density_delta": f"{flight_delta:+.1f}%",
            "threat_pct": f"{curr_threat_pct:.1f}%",
            "threat_delta": f"{threat_delta:+.1f}%",
            "region": str(current['busiest_region']).upper(),
            "airport": str(current['busiest_airport']).upper()
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

    # 2. MACRO INTELLIGENCE HEADER (24H STATS)
    if macro:
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; background-color: rgba(255,255,255,0.03); padding: 10px 20px; border: 1px solid #222; margin-bottom: 25px;">
            <div><span style="color:#666; font-size: 12px;">GLOBAL DENSITY (24H):</span> <span style="color:#fff; font-size: 16px;">{macro['density']}</span> <span style="color:{'#00ffcc' if float(macro['density_delta'].strip('%')) < 0 else '#ff3333'}; font-size: 12px;">[{macro['density_delta']}]</span></div>
            <div><span style="color:#666; font-size: 12px;">THREAT INDEX (24H):</span> <span style="color:#fff; font-size: 16px;">{macro['threat_pct']}</span> <span style="color:{'#00ffcc' if float(macro['threat_delta'].strip('%')) < 0 else '#ff3333'}; font-size: 12px;">[{macro['threat_delta']}]</span></div>
            <div><span style="color:#666; font-size: 12px;">PRIMARY SECTOR:</span> <span style="color:#ffaa00; font-size: 16px;">{macro['region']}</span></div>
            <div><span style="color:#666; font-size: 12px;">ACTIVE HUB:</span> <span style="color:#ffaa00; font-size: 16px;">{macro['airport']}</span></div>
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
    
    tooltip = {"html": "{icao24} | {callsign} | {aircraft_type} <br> FL{baro_altitude} | {velocity} km/h <br> Sightings: {sightings} <br> <span style='color:orange; font-weight:bold;'>{Classification}</span>", 
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
    
    drop_cols = ["color"]
    display_cols = [c for c in df.columns if c not in drop_cols]
    
    front_cols = ["Classification", "icao24", "callsign", "aircraft_type", "military", "sightings", "Threat_Reason"]
    for c in reversed(front_cols):
        if c in display_cols:
            display_cols.insert(0, display_cols.pop(display_cols.index(c)))
            
    df_full = df[display_cols].copy()
    
    if "Classification" in df_full.columns:
        df_full["_rank"] = df_full["Classification"].map({"ANOMALY": 0, "MILITARY": 1, "CIVILIAN": 2})
        df_full = df_full.sort_values(by=["_rank", "baro_altitude"], ascending=[True, False]).drop(columns=["_rank"])

    df_full.rename(columns={
        "Classification": "Status", "icao24": "Hex", "callsign": "Callsign", 
        "aircraft_type": "Airframe", "military": "Mil Asset", "sightings": "Sightings", 
        "Threat_Reason": "Flags", "baro_altitude": "Alt (ft)", "velocity": "Speed (km/h)"
    }, inplace=True)

    st.dataframe(df_full, use_container_width=True, hide_index=True)

else:
    st.error("ERR_NO_DATA: Check tracking configuration parameters.")
