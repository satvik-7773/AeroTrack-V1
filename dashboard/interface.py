import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import pydeck as pdk
from pathlib import Path
from data_ingestion.client import OpenSkyClient
from supabase import create_client

# =====================================================================
# INITIALIZATION & CONFIGURATION
# =====================================================================
st.set_page_config(
    page_title="AeroTrack-V1 // Airspace Monitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed" # Start collapsed for a cleaner screen
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ADVANCED TACTICAL CSS ---
st.markdown("""
    <style>
    /* Hide Streamlit Branding completely */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Maximize Screen Real Estate */
    .block-container {
        padding-top: 1rem; 
        padding-bottom: 0rem; 
        padding-left: 2rem; 
        padding-right: 2rem;
        max-width: 100%;
    }
    
    /* Core Background */
    .main { background-color: #06090e; color: #e2e8f0; }
    
    /* Sleek Action Buttons */
    div.stButton > button:first-child {
        background-color: rgba(0, 136, 204, 0.1); 
        color: #00ffff; 
        border-radius: 4px;
        font-family: 'Courier New', monospace;
        font-weight: bold; 
        border: 1px solid #0088cc; 
        height: 3em;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover { 
        background-color: rgba(0, 136, 204, 0.4); 
        box-shadow: 0 0 15px rgba(0, 136, 204, 0.5);
    }
    
    /* Tactical Metric Cards */
    div[data-testid="stMetric"] {
        background-color: rgba(18, 24, 36, 0.8);
        padding: 15px; 
        border-radius: 4px; 
        border: 1px solid rgba(0, 255, 255, 0.15); 
        border-left: 3px solid #00ffff;
        box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.5);
    }
    [data-testid="stMetricValue"] {
        font-family: 'Courier New', Courier, monospace;
        color: #00ffff;
        font-size: 1.8rem;
    }
    [data-testid="stMetricLabel"] {
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-size: 0.8rem;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'Courier New', Courier, monospace;
    }
    
    /* Dataframe Styling */
    .stDataFrame {
        border: 1px solid rgba(0, 255, 255, 0.2) !important;
    }
    </style>
    """, unsafe_allow_html=True)

try:
    result = supabase.table("anomaly_history").select("*").limit(1).execute()
except Exception as e:
    st.error(f"Supabase Connection Error: {e}")

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

# =====================================================================
# 1. CORE DATA INGESTION ENGINE
# =====================================================================
try:
    client = OpenSkyClient()
except Exception as e:
    st.error(f"OpenSky initialization failed: {e}")
    st.stop()

@st.cache_data(ttl=15)
def fetch_global_fusion(api_key):
    tactical_grid = {}
    
    # --- FEED 1: ADSB.LOL MILITARY OVERLAY ---
    military_watchlist = {}
    military_tracks = []
    try:
        mil_url = "https://api.adsb.lol/v2/mil"
        response = requests.get(mil_url, headers={"User-Agent": "AeroTrack-Global/1.0"}, timeout=15)
        
        if response.status_code == 200:
            military_aircraft = response.json().get("ac", [])
            for ac in military_aircraft:
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code: continue

                military_watchlist[hex_code] = {
                    "callsign": str(ac.get("flight", "")).strip(),
                    "aircraft_type": str(ac.get("t", "")).strip()
                }

                military_tracks.append({
                    "icao24": hex_code,
                    "callsign": str(ac.get("flight", "")).strip(),
                    "latitude": float(ac.get("lat") or 0),
                    "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")),
                    "velocity": safe_float(ac.get("gs")) * 1.852,
                    "heading": safe_float(ac.get("track")),
                    "vertical_rate": safe_float(ac.get("baro_rate")),
                    "aircraft_type": str(ac.get("t", "")),
                    "military": True,
                    "source": "ADSB-MIL",
                    "Classification": "Military Asset"
                })
    except Exception:
        pass

    # --- FEED 2: AIRLABS GLOBAL METADATA OVERLAY ---
    try:
        airlabs_url = f"https://airlabs.co/api/v9/flights?api_key={api_key}"
        response = requests.get(airlabs_url, timeout=15)
        aircraft_list = response.json().get("response", []) if response.status_code == 200 else []
        
        for ac in aircraft_list:
            try:
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None:
                    continue

                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": float(ac.get("lat") or 0),
                    "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084,
                    "velocity": float(ac.get("speed") or 0),
                    "heading": float(ac.get("dir") or 0),
                    "vertical_rate": float(ac.get("v_speed") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")),
                    "flight_number": str(ac.get("flight_iata", "UNKN")),
                    "airline_code": str(ac.get("airline_iata", "UNKN")),
                    "departure_iata": str(ac.get("dep_iata", "UNKN")),
                    "military": False,
                    "source": "AirLabs"
                }
                
                if hex_code in military_watchlist:
                    tactical_grid[hex_code]["military"] = True
                    adsb_type = military_watchlist[hex_code].get("aircraft_type")
                    if adsb_type: tactical_grid[hex_code]["aircraft_type"] = adsb_type
            except Exception:
                continue
    except Exception as e:
        st.error(f"AirLabs Error: {e}")

    # --- DATAFRAME GENERATION & KINEMATICS ---
    final_list = list(tactical_grid.values())
    if not final_list: return pd.DataFrame()
        
    df = pd.DataFrame(final_list)
    mil_df = pd.DataFrame(military_tracks)
    
    if not mil_df.empty:
        mil_df = mil_df[~mil_df["icao24"].isin(df["icao24"])]
        df = pd.concat([df, mil_df], ignore_index=True)
        
    if "Classification" not in df.columns:
        df["Classification"] = "Standard Track"
    else:
        df["Classification"] = df["Classification"].fillna("Standard Track")
        
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750", "E55P", "C56X", "C25A", "LJ60"]
    df["Threat_Reason"] = "None"
   
    for idx, row in df.iterrows():
        try:
            velocity = float(row.get("velocity", 0.0))
            altitude = float(row.get("baro_altitude", 0.0))
            aircraft_type = str(row.get("aircraft_type", "UNKN")).upper().strip()
            icao24 = str(row.get("icao24", "UNKN")).upper().strip()
            is_military = row.get("military", False)
        
            is_low_alt_dash = (altitude < 15000 and velocity > 850)
            max_ceiling = 51000 if aircraft_type in biz_jets else 44000
            is_ceiling_breach = (altitude > max_ceiling)
            is_true_dash = (velocity > 1250) or (velocity > 1050 and altitude < 28000)
            is_malformed_hex = (icao24 != "UNKN" and len(icao24) != 6)
        
            reasons = []
            if is_low_alt_dash: reasons.append("Low Altitude High Velocity")
            if is_ceiling_breach: reasons.append("Altitude Ceiling Breach")
            if is_true_dash: reasons.append("Excessive Velocity")
            if is_malformed_hex: reasons.append("Malformed ICAO")
            if is_military: reasons.append("Military Asset")
            if altitude > 60000 and velocity < 10: reasons.append("Telemetry Anomaly")
            if altitude < 100 and velocity > 1500: reasons.append("Ground-Level Hypersonic Velocity")
            if altitude > 100000: reasons.append("Extreme Altitude")
            if (altitude > 30000 and velocity < 20) or (altitude > 50000 and velocity < 100): reasons.append("Airborne Velocity Anomaly")                

            if reasons:
                df.at[idx, "Threat_Reason"] = ", ".join(reasons)

            if is_military:
                df.at[idx, "Classification"] = "Military Asset"
            elif len(reasons) > 0:
                df.at[idx, "Classification"] = "Threat Alert"    
        except Exception:
            pass

    flagged_df = df[(df["military"] == True) & (df["Threat_Reason"] != "Military Asset")]
    df["sightings"] = 0
    
    for _, row in flagged_df.iterrows():
        try:
            supabase.table("anomaly_history").insert({
                "icao24": str(row.get("icao24", "")), "callsign": str(row.get("callsign", "")),
                "classification": str(row.get("Classification", "")), "threat_reason": str(row.get("Threat_Reason", "")),
                "aircraft_type": str(row.get("aircraft_type", "")), "altitude": float(row.get("baro_altitude", 0)),
                "velocity": float(row.get("velocity", 0)), "latitude": float(row.get("latitude", 0)),
                "longitude": float(row.get("longitude", 0)), "source": str(row.get("source", ""))
            }).execute()
        except Exception: pass
        
        try:
            icao = str(row.get("icao24", "")).upper().strip()
            existing = supabase.table("aircraft_tracking").select("*").eq("icao24", icao).execute()

            if existing.data:
                record = existing.data[0]
                now = pd.Timestamp.utcnow()
                increment = ((now - pd.to_datetime(record["last_seen"])).total_seconds() > 300)
                update_data = {
                    "last_seen": now.isoformat(), "latest_classification": str(row.get("Classification", "")),
                    "latest_reason": str(row.get("Threat_Reason", "")), "last_latitude": float(row.get("latitude", 0)),
                    "last_longitude": float(row.get("longitude", 0)),
                }
                if increment: update_data["sightings"] = record["sightings"] + 1
                supabase.table("aircraft_tracking").update(update_data).eq("icao24", icao).execute()
            else:
                now = pd.Timestamp.utcnow().isoformat()
                supabase.table("aircraft_tracking").insert({
                    "icao24": icao, "first_seen": now, "last_seen": now, "sightings": 1,
                    "latest_classification": str(row.get("Classification", "")), "latest_reason": str(row.get("Threat_Reason", "")),
                    "aircraft_type": str(row.get("aircraft_type", "")), "last_latitude": float(row.get("latitude", 0)),
                    "last_longitude": float(row.get("longitude", 0)),
                }).execute()
        except Exception: pass

    try:
        tracked = supabase.table("aircraft_tracking").select("icao24,sightings").execute()
        sightings_lookup = {r["icao24"]: r["sightings"] for r in tracked.data}
        df["sightings"] = df["icao24"].map(sightings_lookup).fillna(0)
    except Exception: pass

    return df


# =====================================================================
# 2. SUPABASE INTELLIGENCE ANALYTICS LAYER
# =====================================================================
def render_analytics_dashboard():
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(24).execute()
        stats_df = pd.DataFrame(res.data)
    except Exception as e:
        return

    if stats_df.empty: return
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
    mil_delta = curr_mil_pct - avg_mil_pct

    col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 1.5, 2, 2])
    
    col1.metric("Global Density", f"{int(current['total_flights']):,}", f"{flight_delta:.2f}% (24h)", delta_color="inverse")
    col2.metric("Threat Trajectories", f"{curr_threat_pct:.2f}%", f"{threat_delta:.2f}% (24h)", delta_color="inverse")
    col3.metric("Military Asset %", f"{curr_mil_pct:.2f}%", f"{mil_delta:.2f}% (24h)", delta_color="off")
    col4.info(f"📍 **Dense Region:**\n{current['busiest_region']}")
    col5.info(f"🛫 **Active Hub:**\n{current['busiest_airport']} (IATA)")
    st.markdown("<br>", unsafe_allow_html=True)


# =====================================================================
# 3. APPLICATION HEADER & UI EXECUTION
# =====================================================================
st.markdown("<h2 style='color: #ffffff; font-family: Courier New;'>🛰️ AEROTRACK-V1 // COMMAND CONSOLE</h2>", unsafe_allow_html=True)

render_analytics_dashboard()

# --- GRAPHICS RENDERING LAYER ---
df = fetch_global_fusion(client.api_key)

if not df.empty:
    col_a, col_b = st.columns([8, 2])
    
    with col_a:
        st.markdown("<p style='color:#00ffff; font-family:Courier; font-size:14px;'>LIVE SPATIAL RENDER LAYER</p>", unsafe_allow_html=True)
        
        # Color mapping for PyDeck [R, G, B, Alpha]
        def get_color(classification):
            if classification == "Threat Alert": return [255, 0, 51, 255] # Neon Red
            elif classification == "Military Asset": return [255, 170, 0, 255] # Gold/Amber
            else: return [0, 200, 255, 120] # Cyan Translucent

        df['color'] = df['Classification'].apply(get_color)
        
        # 3D Column Layer for Altitude Visualization
        layer = pdk.Layer(
            'ColumnLayer',
            data=df,
            get_position='[longitude, latitude]',
            get_elevation='baro_altitude',
            elevation_scale=5, # Exaggerate altitude to make stratospheres visible
            radius=4000,
            get_fill_color='color',
            pickable=True,
            auto_highlight=True,
        )

        view_state = pdk.ViewState(
            latitude=df['latitude'].mean() if not df.empty else 20,
            longitude=df['longitude'].mean() if not df.empty else 0,
            zoom=1.5,
            pitch=45, # Tilted perspective for 3D
            bearing=0
        )

        tooltip = {
            "html": "<b>Hex:</b> {icao24} <br/> <b>Callsign:</b> {callsign} <br/> <b>Airframe:</b> {aircraft_type} <br/> <b>Alt:</b> {baro_altitude} ft <br/> <b>Status:</b> <span style='color:orange;'>{Classification}</span>",
            "style": {"backgroundColor": "#121824", "color": "#ffffff", "border": "1px solid #00ffff", "font-family": "Courier"}
        }

        r = pdk.Deck(
            layers=[layer], 
            initial_view_state=view_state, 
            tooltip=tooltip, 
            map_style="mapbox://styles/mapbox/dark-v11"
        )
        
        st.pydeck_chart(r, use_container_width=True)

    with col_b:
        st.markdown("<p style='color:#00ffff; font-family:Courier; font-size:14px;'>SYSTEM CONTROLS</p>", unsafe_allow_html=True)
        if st.button("📡 INITIATE FUSION SWEEP", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            
        st.write("")
        st.metric(label="Live Rendered Tracks", value=f"{len(df)} Targets")
        st.metric(label="Active Threats", value=f"{len(df[df['Classification'] == 'Threat Alert'])}")
        st.metric(label="Military Assets", value=f"{len(df[df['military'] == True])}")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Custom Dataframe styling
    display_columns = ["Classification", "Threat_Reason", "flight_number", "aircraft_type", "military", "baro_altitude", "velocity", "icao24"]
    available_cols = [col for col in display_columns if col in df.columns]
    df_display = df[available_cols].copy()
    
    df_display = df_display.rename(columns={
        "Classification": "Status", "Threat_Reason": "Reason", "flight_number": "Flight No.",
        "aircraft_type": "Airframe", "military": "Mil Asset",
        "baro_altitude": "Alt (ft)", "velocity": "Speed (km/h)", "icao24": "Hex"
    })
    
    if "Status" in df_display.columns:
        df_display["_sort_rank"] = df_display["Status"].apply(lambda x: 0 if x == "Threat Alert" else (1 if x == "Military Asset" else 2))
        df_display = df_display.sort_values(by=["_sort_rank", "Alt (ft)"], ascending=[True, False]).drop(columns=["_sort_rank"])

    st.dataframe(df_display, use_container_width=True, hide_index=True)

else:
    st.warning("⚠️ Warning: No active tracking streams detected.")
