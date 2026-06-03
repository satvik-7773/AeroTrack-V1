import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import time
from data_ingestion.client import OpenSkyClient
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)
try:
    result = (
        supabase.table("anomaly_history")
        .select("*")
        .limit(1)
        .execute()
    )

    st.sidebar.success("Supabase Connected")

except Exception as e:
    st.sidebar.error(f"Supabase Error: {e}")

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default



st.set_page_config(
    page_title="AeroTrack-V1 // Airspace Monitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #ffffff; }
    div.stButton > button:first-child {
        background-color: #0088cc; color: white; border-radius: 4px;
        font-weight: bold; border: none; height: 3em;
    }
    div.stButton > button:first-child:hover { background-color: #006699; }
    .stMetric { background-color: #121824; padding: 15px; border-radius: 5px; border-left: 3px solid #00ffff; }
    </style>
    """, unsafe_allow_html=True)

# =====================================================================
# 1. CORE DATA INGESTION ENGINE (ADSB.LOL FUSION)
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

        response = requests.get(
            mil_url,
            headers={"User-Agent": "AeroTrack-Global/1.0"},
            timeout=15
       )
        

        

        if response.status_code == 200:
            military_aircraft = response.json().get("ac", [])

            

            military_tracks = []

            for ac in military_aircraft:

                hex_code = str(ac.get("hex", "")).upper().strip()

                if not hex_code:
                    continue

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
    except Exception as e:
        st.warning(f"ADSB Military Feed Offline: {e}")


    # --- FEED 2: AIRLABS GLOBAL METADATA OVERLAY ---
    
    try:
        airlabs_url = f"https://airlabs.co/api/v9/flights?api_key={api_key}"
        response = requests.get(airlabs_url, timeout=15)

        
        aircraft_list = []
        if response.status_code == 200:
            aircraft_list = response.json().get("response", [])

        
        for ac in aircraft_list:
            
            try:
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()

                if (
                    hex_code == "UNKN"
                    or ac.get("lat") is None
                    or ac.get("lng") is None
                ):
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

                    if adsb_type:
                        tactical_grid[hex_code]["aircraft_type"] = adsb_type
                

                       
            
            except Exception as aircraft_error:
                st.write("Aircraft Parse Error:", aircraft_error)
                continue

    except Exception as e:
        st.error(f"AirLabs Error: {e}")

    adsb_hexes = set(military_watchlist.keys())
    airlabs_hexes = set(tactical_grid.keys())

    intersection = adsb_hexes.intersection(airlabs_hexes)

    
    

    # --- DATAFRAME GENERATION & KINEMATICS ---
    
    final_list = list(tactical_grid.values())
    if not final_list:
        return pd.DataFrame()
        
    df = pd.DataFrame(final_list)
    mil_df = pd.DataFrame(military_tracks)
    
    if not mil_df.empty:
        mil_df = mil_df[
            ~mil_df["icao24"].isin(df["icao24"])
       ]


    if not mil_df.empty:
        
        df = pd.concat([df, mil_df], ignore_index=True)
        
    
    # Stable Kinematics
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

            if is_low_alt_dash:
                reasons.append("Low Altitude High Velocity")

            if is_ceiling_breach:
                reasons.append("Altitude Ceiling Breach")

            if is_true_dash:
                reasons.append("Excessive Velocity")

            if is_malformed_hex:
                reasons.append("Malformed ICAO")

            if is_military:
                reasons.append("Military Asset")

            if altitude > 60000 and velocity < 10:
                reasons.append("Telemetry Anomaly")

            if altitude < 100 and velocity > 1500:
                reasons.append("Ground-Level Hypersonic Velocity")        

            if reasons:
                df.at[idx, "Threat_Reason"] = ", ".join(reasons)

            if is_military:
                df.at[idx, "Classification"] = "Military Asset"

            elif len(reasons) > 0:
                df.at[idx, "Classification"] = "Threat Alert"    
        
        
        except Exception:
            pass
    return df

# =====================================================================
# APPLICATION HEADER & UI
# =====================================================================
st.title("🛰️ AeroTrack-V1 // Global Tactical Monitor")
st.caption("Unrestricted Global Radar Fusion (ADSB.lol + AirLabs Intelligence)")
st.divider()

st.sidebar.header("Command Center Controls")


# --- GRAPHICS RENDERING LAYER ---
df = fetch_global_fusion(client.api_key)

if df.empty:
    st.warning("⚠️ Warning: No active tracking streams detected. Check network connections or API Quota.")
else:
    st.markdown("Execute the 'Global Fusion Sweep' to pull the entire planet.")

    if st.button("📡 Execute Global Fusion Sweep", width="stretch"):
        st.cache_data.clear()
        st.toast("Executing full planetary sweep...", icon="🌍")

        with st.spinner("Stitching 15,000+ global tactical tracks with commercial metadata..."):
            df = fetch_global_fusion(client.api_key)

    total_targets = len(df)
    threat_count = len(df[df["Classification"] == "Threat Alert"])
    mil_count = len(df[df["military"] == True])
    
    m1, m2, m3 = st.columns(3)
    m1.metric(label="Total Global Tracks", value=f"{total_targets} Targets")
    m2.metric(label="Threats / Military Assets", value=f"{threat_count} / {mil_count}")
    m3.metric(label="Radar Status", value="GLOBAL FUSION ACTIVE🔴")
    st.write("")
    
    fig = px.scatter_mapbox(
        df,
        lat="latitude",
        lon="longitude",
        hover_name="callsign",
        hover_data={
            "icao24": True,
            "aircraft_type": True,
            "flight_number": True,
            "military": True,
            "baro_altitude": True, 
            "velocity": True,
            "source": True,
            "Classification": True
        },
        color="Classification",
        color_discrete_map={"Standard Track": "#00ffff", "Threat Alert": "#ff0033", "Military Asset": "#ffaa00"}, 
        size_max=12,
        zoom=1.5,
        height=700
    )
    
    fig.update_layout(
        mapbox_style="carto-darkmatter",
        margin={"r":0,"t":0,"l":0,"b":0},
        paper_bgcolor="#0b0e14",
        plot_bgcolor="#0b0e14",
        font_color="#ffffff",
        legend=dict(
            yanchor="top", y=0.98,
            xanchor="left", x=0.01,
            bgcolor="rgba(11, 14, 20, 0.8)",
            font=dict(color="#ffffff")
        )
    )
    
    st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("Active Airspace Intelligence Log")
    
    display_columns = [
        "Classification",
        "Threat_Reason", 
        "flight_number",
        "aircraft_type",
        "departure_iata",
        "military",
        "baro_altitude", 
        "velocity", 
        "source", 
        "icao24"
    ]
    
    available_cols = [col for col in display_columns if col in df.columns]
    df_display = df[available_cols].copy()
    
    df_display = df_display.rename(columns={
        "Classification": "Threat Status",
        "Threat_Reason": "Reason",
        "flight_number": "Flight No.",
        "aircraft_type": "Airframe",
        "departure_iata": "Origin",
        "military": "Mil Asset",
        "baro_altitude": "Alt (ft)",
        "velocity": "Speed (km/h)",
        "source": "Data Source",
        "icao24": "Hex"
    })
    
    if "Threat Status" in df_display.columns:
        df_display["_sort_rank"] = df_display["Threat Status"].apply(lambda x: 0 if x == "Threat Alert" else 1)
        df_display = df_display.sort_values(by=["_sort_rank", "Alt (ft)"], ascending=[True, False])
        df_display = df_display.drop(columns=["_sort_rank"])

    st.dataframe(df_display, width="stretch", hide_index=True)

st.markdown("--- *Unrestricted Global Telemetry Fusion via ADSB.lol • Designed & Built by - Satvik (satvik-7773)*")
