import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
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
    initial_sidebar_state="collapsed"
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- TRUE MIL-SPEC CSS (Minimalist, No Neon, Slate & Muted Tones) ---
st.markdown("""
    <style>
    /* Hide Streamlit Clutter */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Maximize Screen Real Estate */
    .block-container {
        padding-top: 1.5rem; 
        padding-bottom: 0rem; 
        padding-left: 2rem; 
        padding-right: 2rem;
        max-width: 100%;
    }
    
    /* Clean Slate Background */
    .main { background-color: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    
    /* Professional Flat Buttons */
    div.stButton > button:first-child {
        background-color: #21262d; 
        color: #c9d1d9; 
        border-radius: 4px;
        font-weight: 600; 
        border: 1px solid #30363d; 
        height: 3em;
        transition: all 0.2s ease;
    }
    div.stButton > button:first-child:hover { 
        background-color: #30363d; 
        border-color: #8b949e;
    }
    
    /* Clean, Flat Metric Cards */
    div[data-testid="stMetric"] {
        background-color: #161b22;
        padding: 12px 16px; 
        border-radius: 6px; 
        border: 1px solid #30363d; 
    }
    [data-testid="stMetricValue"] {
        font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
        color: #c9d1d9;
        font-size: 1.6rem;
    }
    [data-testid="stMetricLabel"] {
        color: #8b949e;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    /* Flat Dataframe */
    .stDataFrame {
        border: 1px solid #30363d !important;
        border-radius: 6px;
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
    military_watchlist = {}
    military_tracks = []

    # --- FEED 1: ADSB.LOL MILITARY OVERLAY ---
    try:
        mil_url = "https://api.adsb.lol/v2/mil"
        response = requests.get(mil_url, headers={"User-Agent": "AeroTrack-Global/1.0"}, timeout=15)
        if response.status_code == 200:
            for ac in response.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code: continue
                military_watchlist[hex_code] = {"callsign": str(ac.get("flight", "")).strip(), "aircraft_type": str(ac.get("t", "")).strip()}
                military_tracks.append({
                    "icao24": hex_code, "callsign": str(ac.get("flight", "")).strip(),
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")), "velocity": safe_float(ac.get("gs")) * 1.852,
                    "aircraft_type": str(ac.get("t", "")), "military": True, "source": "ADSB-MIL", "Classification": "Military Asset"
                })
    except Exception: pass

    # --- FEED 2: AIRLABS GLOBAL METADATA OVERLAY ---
    try:
        response = requests.get(f"https://airlabs.co/api/v9/flights?api_key={api_key}", timeout=15)
        aircraft_list = response.json().get("response", []) if response.status_code == 200 else []
        for ac in aircraft_list:
            try:
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                tactical_grid[hex_code] = {
                    "icao24": hex_code, "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084, "velocity": float(ac.get("speed") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")), "flight_number": str(ac.get("flight_iata", "UNKN")),
                    "departure_iata": str(ac.get("dep_iata", "UNKN")), "military": False, "source": "AirLabs"
                }
                if hex_code in military_watchlist:
                    tactical_grid[hex_code]["military"] = True
                    tactical_grid[hex_code]["aircraft_type"] = military_watchlist[hex_code].get("aircraft_type", tactical_grid[hex_code]["aircraft_type"])
            except Exception: continue
    except Exception as e: st.error(f"AirLabs Error: {e}")

    # --- DATAFRAME GENERATION & KINEMATICS ---
    final_list = list(tactical_grid.values())
    if not final_list: return pd.DataFrame()
        
    df = pd.DataFrame(final_list)
    mil_df = pd.DataFrame(military_tracks)
    if not mil_df.empty:
        mil_df = mil_df[~mil_df["icao24"].isin(df["icao24"])]
        df = pd.concat([df, mil_df], ignore_index=True)
        
    df["Classification"] = df.get("Classification", "Standard Track").fillna("Standard Track")
    df["Threat_Reason"] = "None"
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750", "E55P", "C56X", "C25A", "LJ60"]
   
    for idx, row in df.iterrows():
        try:
            vel, alt, ac_type, icao, is_mil = float(row.get("velocity", 0.0)), float(row.get("baro_altitude", 0.0)), str(row.get("aircraft_type", "UNKN")).upper().strip(), str(row.get("icao24", "UNKN")).upper().strip(), row.get("military", False)
            reasons = []
            if (alt < 15000 and vel > 850): reasons.append("Low Alt / High Vel")
            if (alt > (51000 if ac_type in biz_jets else 44000)): reasons.append("Ceiling Breach")
            if (vel > 1250) or (vel > 1050 and alt < 28000): reasons.append("Kinematic Anomaly")
            if (icao != "UNKN" and len(icao) != 6): reasons.append("Malformed ICAO")
            if is_mil: reasons.append("Military Asset")

            if reasons: df.at[idx, "Threat_Reason"] = ", ".join(reasons)
            if is_mil: df.at[idx, "Classification"] = "Military Asset"
            elif len(reasons) > 0: df.at[idx, "Classification"] = "Threat Alert"    
        except Exception: pass

    # Background Sync (Errors suppressed for UI cleanliness)
    flagged_df = df[(df["military"] == True) & (df["Threat_Reason"] != "Military Asset")]
    df["sightings"] = 0
    for _, row in flagged_df.iterrows():
        try:
            supabase.table("anomaly_history").insert({"icao24": str(row.get("icao24", "")), "classification": str(row.get("Classification", "")), "threat_reason": str(row.get("Threat_Reason", "")), "latitude": float(row.get("latitude", 0)), "longitude": float(row.get("longitude", 0))}).execute()
        except Exception: pass
    try:
        tracked = supabase.table("aircraft_tracking").select("icao24,sightings").execute()
        df["sightings"] = df["icao24"].map({r["icao24"]: r["sightings"] for r in tracked.data}).fillna(0)
    except Exception: pass

    return df

# =====================================================================
# 2. SUPABASE INTELLIGENCE ANALYTICS LAYER
# =====================================================================
def render_analytics_dashboard():
    try:
        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(24).execute()
        stats_df = pd.DataFrame(res.data)
    except Exception: return

    if stats_df.empty: return
    current = stats_df.iloc[0]

    if len(stats_df) > 1:
        avg_flights = stats_df["total_flights"].mean()
        avg_threat_pct = (stats_df["threat_count"].sum() / stats_df["total_flights"].sum()) * 100
        avg_mil_pct = (stats_df["military_count"].sum() / stats_df["total_flights"].sum()) * 100
    else:
        avg_flights, avg_threat_pct, avg_mil_pct = current["total_flights"], (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0, (current["military_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

    curr_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0
    curr_mil_pct = (current["military_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

    col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 1.5, 2, 2])
    col1.metric("Global Density", f"{int(current['total_flights']):,}", f"{((current['total_flights'] - avg_flights) / avg_flights) * 100 if avg_flights > 0 else 0:.2f}% (24h)", delta_color="inverse")
    col2.metric("Anomalies", f"{curr_threat_pct:.2f}%", f"{curr_threat_pct - avg_threat_pct:.2f}% (24h)", delta_color="inverse")
    col3.metric("Military Matrix", f"{curr_mil_pct:.2f}%", f"{curr_mil_pct - avg_mil_pct:.2f}% (24h)", delta_color="off")
    col4.info(f"📍 **Dense Region:**\n{current['busiest_region']}")
    col5.info(f"🛫 **Active Hub:**\n{current['busiest_airport']} (IATA)")
    st.write("")

# =====================================================================
# 3. APPLICATION HEADER & UI EXECUTION
# =====================================================================
st.markdown("<h3 style='color: #c9d1d9; font-weight: 600; margin-bottom: 0px;'>AEROTRACK-V1 // COMMAND CONSOLE</h3>", unsafe_allow_html=True)
st.markdown("<p style='color: #8b949e; font-size: 14px; margin-top: 0px;'>Global Telemetry Fusion & Kinematic Anomaly Detection</p>", unsafe_allow_html=True)

render_analytics_dashboard()

# --- GRAPHICS RENDERING LAYER ---
df = fetch_global_fusion(client.api_key)

if not df.empty:
    col_a, col_b = st.columns([8.5, 1.5])
    
    with col_a:
        # Sharp, crisp Plotly vector map (No WebGL blurriness)
        fig = px.scatter_mapbox(
            df, lat="latitude", lon="longitude",
            hover_name="callsign",
            hover_data={"icao24": True, "aircraft_type": True, "baro_altitude": True, "velocity": True, "Classification": True, "Threat_Reason": True},
            color="Classification",
            color_discrete_map={"Standard Track": "#44b4e2", "Threat Alert": "#fa4646", "Military Asset": "#f0b72f"}, 
            size_max=8, zoom=1.2, height=600
        )
        fig.update_layout(
            mapbox_style="carto-darkmatter",
            margin={"r":0,"t":0,"l":0,"b":0},
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", font_color="#c9d1d9",
            legend=dict(yanchor="top", y=0.98, xanchor="left", x=0.01, bgcolor="rgba(13, 17, 23, 0.85)", font=dict(color="#c9d1d9", size=11))
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        if st.button("📡 Execute Sweep", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            
        st.write("")
        st.metric(label="Active Targets", value=f"{len(df):,}")
        st.metric(label="Threat Vectors", value=f"{len(df[df['Classification'] == 'Threat Alert']):,}")
        st.metric(label="Military Assets", value=f"{len(df[df['military'] == True]):,}")

    st.write("")
    
    # Clean Dataframe presentation
    display_columns = ["Classification", "Threat_Reason", "flight_number", "aircraft_type", "baro_altitude", "velocity", "icao24"]
    df_display = df[[col for col in display_columns if col in df.columns]].copy()
    df_display.rename(columns={"Classification": "Status", "Threat_Reason": "Reason", "flight_number": "Flight No.", "aircraft_type": "Airframe", "baro_altitude": "Alt (ft)", "velocity": "Speed (km/h)", "icao24": "Hex"}, inplace=True)
    
    if "Status" in df_display.columns:
        df_display["_sort_rank"] = df_display["Status"].apply(lambda x: 0 if x == "Threat Alert" else (1 if x == "Military Asset" else 2))
        df_display = df_display.sort_values(by=["_sort_rank", "Alt (ft)"], ascending=[True, False]).drop(columns=["_sort_rank"])

    st.dataframe(df_display, use_container_width=True, hide_index=True)

else:
    st.warning("No active tracking streams detected. Check API Quotas.")

# --- THE CREDITS FOOTER ---
st.markdown("""
    <div style='text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #30363d; color: #8b949e; font-size: 13px;'>
        Unrestricted Global Telemetry Fusion via ADSB.lol & AirLabs<br>
        <strong>Designed & Built by - Satvik (satvik-7773)</strong>
    </div>
""", unsafe_allow_html=True)
