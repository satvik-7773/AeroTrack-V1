import sys
import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

# Dynamically append the project root directory to the Python tracking path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =====================================================================
# CONFIGURATION
# =====================================================================
# Insert your actual AirLabs API key here
AIRLABS_API_KEY = "4968fc59-348d-4a8a-af4f-73861d867e4e"

st.set_page_config(
    page_title="AeroTrack-V1 // Airspace Monitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Dark Combat Information Center CSS styling
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

import concurrent.futures

# =====================================================================
# 1. CORE DATA INGESTION ENGINE (HIGH-DENSITY GRID STITCHING)
# =====================================================================
@st.cache_data(ttl=15)
def fetch_global_unfiltered_airspace(airlabs_api_key):
    tactical_grid = {}

    # --- THE 20 MEGA-HUB STRIKE MATRIX ---
    # Firing simultaneous 250NM radius requests at the 20 densest airspaces on Earth
    strike_zones = [
        (39.0, -75.0),  # US East Coast (DC/NYC)
        (33.6, -84.4),  # US South (Atlanta - Hartsfield)
        (41.9, -87.9),  # US Midwest (Chicago - O'Hare)
        (32.9, -97.0),  # US Texas (Dallas/Fort Worth)
        (34.0, -118.0), # US West Coast (SoCal/LAX)
        (47.4, -122.3), # US Northwest (Seattle)
        (51.5, -0.1),   # UK (London - Heathrow)
        (48.8, 2.3),    # France (Paris - CDG)
        (50.1, 8.5),    # Germany (Frankfurt)
        (41.8, 12.5),   # Italy (Rome)
        (25.2, 55.3),   # UAE (Dubai)
        (28.6, 77.1),   # India (New Delhi)
        (1.3, 103.8),   # Singapore (Changi)
        (35.5, 139.7),  # Japan (Tokyo)
        (37.5, 126.9),  # South Korea (Seoul)
        (22.3, 113.9),  # Hong Kong / South China
        (31.2, 121.4),  # China (Shanghai)
        (-33.9, 151.1), # Australia (Sydney)
        (-23.5, -46.6), # Brazil (Sao Paulo)
        (50.1, 22.0)    # Poland/Ukraine Border (ISR Loiter Zone)
    ]

    def fetch_zone(coords):
        lat, lon = coords
        url = f"https://api.airplanes.live/v2/point/{lat}/{lon}/250"
        try:
            # We use standard requests since the /point endpoint is legal and unblocked
            res = requests.get(url, headers={"User-Agent": "AxisDef-Stitcher-V2/1.0"}, timeout=10)
            if res.status_code == 200:
                return res.json().get("ac", [])
        except Exception:
            return []
        return []

    # --- MULTI-THREADED EXECUTION (20 WORKERS) ---
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        zone_results = executor.map(fetch_zone, strike_zones)

    # --- PARSE AND MERGE PAYLOADS (WITH NATIVE METADATA EXTRACTION) ---
    for payload in zone_results:
        for ac in payload:
            hex_code = str(ac.get("hex", "UNKN")).upper()
            if hex_code == "UNKN": 
                continue
            
            raw_speed_knots = float(ac.get("gs", 0.0)) if ac.get("gs") is not None else 0.0
            
            # THE FIX: Extracting Aircraft Type ('t') directly from tactical radar
            airframe_type = str(ac.get("t", "UNKN")).upper().strip()
            if airframe_type == "": 
                airframe_type = "UNKN"

            tactical_grid[hex_code] = {
                "icao24": hex_code,
                "callsign": str(ac.get("flight", "UNKN")).strip(),
                "latitude": ac.get("lat"),
                "longitude": ac.get("lon"),
                "baro_altitude": float(ac.get("alt_baro", 0.0)) if isinstance(ac.get("alt_baro"), (int, float)) else 0.0,
                "velocity": raw_speed_knots * 1.852, 
                "heading": float(ac.get("track", 0.0)) if ac.get("track") is not None else 0.0,
                "vertical_rate": float(ac.get("baro_rate", 0.0)) if ac.get("baro_rate") is not None else 0.0,
                "military": True if ac.get("mil", False) else False, 
                "source": "Airplanes.live", 
                "aircraft_type": airframe_type, # Massive reduction in UNKN fields
                "flight_number": "UNKN",
                "airline_code": "UNKN",
                "departure_iata": "UNKN"
            }

    # Cold Start Safeguard
    if not tactical_grid:
        st.error("Grid Stitching Failed. Check core internet connectivity.")
        return pd.DataFrame(columns=[
            "icao24", "callsign", "latitude", "longitude", "baro_altitude", 
            "velocity", "heading", "vertical_rate", "military", "source",
            "aircraft_type", "flight_number", "airline_code", "departure_iata", "Classification"
        ])

    # --- INGEST AIRLABS (METADATA MERGE OVERLAY) ---
    try:
        airlabs_url = f"https://airlabs.co/api/v9/flights?api_key={airlabs_api_key}"
        response = requests.get(airlabs_url, timeout=15)
        if response.status_code == 200:
            for ac in response.json().get("response", []):
                hex_code = str(ac.get("hex", "UNKN")).upper()
                if hex_code in tactical_grid:
                    
                    # Only overwrite the aircraft type if Airplanes.live missed it
                    al_type = str(ac.get("aircraft_icao", "UNKN")).strip()
                    if al_type != "UNKN" and tactical_grid[hex_code]["aircraft_type"] == "UNKN":
                        tactical_grid[hex_code]["aircraft_type"] = al_type
                        
                    tactical_grid[hex_code]["flight_number"] = ac.get("flight_iata", "UNKN")
                    tactical_grid[hex_code]["airline_code"] = ac.get("airline_iata", "UNKN")
                    tactical_grid[hex_code]["departure_iata"] = ac.get("dep_iata", "UNKN")
    except Exception as e:
        st.warning(f"AirLabs Metadata Merge Warning: {e}")

    # --- SANITIZATION & DATAFRAME CREATION ---
    final_list = [t for t in tactical_grid.values() if t.get("latitude") is not None and t.get("longitude") is not None]
    df_temp = pd.DataFrame(final_list)
    
    # --- KINEMATIC ANOMALY ENGINE ---
    df_temp["Classification"] = "Standard Track"
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750", "E55P", "C56X"]
    
    for idx, row in df_temp.iterrows():
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
            
            if is_low_alt_dash or is_ceiling_breach or is_true_dash or is_malformed_hex or is_military:
                df_temp.at[idx, "Classification"] = "Threat Alert"
                
        except Exception:
            df_temp.at[idx, "Classification"] = "Standard Track"
            
    return df_temp
# =====================================================================
# APPLICATION HEADER & UI
# =====================================================================
st.title("🛰️ AeroTrack-V1 // Global Tactical Airspace Monitor")
st.caption("Unfiltered Global Detection • Anomaly & Military Tracking")
st.divider()

st.sidebar.header("Global Airspace Command")
st.sidebar.markdown("Execute the 'Refresh Global Coordinates' command to perform a planetary radar sweep.")
st.sidebar.info("💡 Pulling 15,000+ unfiltered global targets. Rendering may take a few seconds.")

# Trigger Sweep Button (Updated width syntax to clear Streamlit warnings)
if st.sidebar.button("📡 Refresh Global Coordinates", width="stretch"):
    st.cache_data.clear()
    st.toast("Global tracking grid active.", icon="🌍")

with st.spinner("Locking onto global transponders..."):
    df = fetch_global_unfiltered_airspace(AIRLABS_API_KEY)

# --- GRAPHICS RENDERING LAYER ---
if df.empty:
    st.warning("⚠️ Radar clear. No active tracking streams detected.")
else:
    total_targets = len(df)
    threat_count = len(df[df["Classification"] == "Threat Alert"])
    
    m1, m2, m3 = st.columns(3)
    m1.metric(label="Global Contacts", value=f"{total_targets} Targets")
    m2.metric(label="Anomalies / Military", value=f"{threat_count} Active")
    m3.metric(label="Radar Status", value="GLOBAL LOCKED🔴")
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
            "departure_iata": True,
            "baro_altitude": True, 
            "velocity": True,
            "military": True,
            "source": True,
            "Classification": True
        },
        color="Classification",
        color_discrete_map={"Standard Track": "#00ffff", "Threat Alert": "#ff0033"}, 
        size_max=12,
        zoom=1.5, 
        height=650
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
    
    # Updated width syntax
    st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("Active Global Intelligence Log")
    
    display_columns = [
        "Classification", 
        "flight_number",
        "airline_code",
        "aircraft_type",
        "departure_iata",
        "military",       
        "baro_altitude", 
        "velocity", 
        "heading", 
        "icao24"
    ]
    
    available_cols = [col for col in display_columns if col in df.columns]
    df_display = df[available_cols].copy()
    
    df_display = df_display.rename(columns={
        "Classification": "Threat Status",
        "flight_number": "Flight No.",
        "airline_code": "Operator ID",
        "aircraft_type": "Airframe",
        "departure_iata": "Origin",
        "military": "Mil Asset",
        "baro_altitude": "Alt (ft)",
        "velocity": "Speed (km/h)",
        "heading": "Track (°)",
        "icao24": "Hex"
    })
    
    if "Threat Status" in df_display.columns:
        df_display["_sort_rank"] = df_display["Threat Status"].apply(lambda x: 0 if x == "Threat Alert" else 1)
        df_display = df_display.sort_values(by=["_sort_rank", "Alt (ft)"], ascending=[True, False])
        df_display = df_display.drop(columns=["_sort_rank"])

    # Updated width syntax
    st.dataframe(df_display, width="stretch", hide_index=True)

st.markdown("--- *Tactical Airspace Telemetry by AirLabs & Airplanes.live • Designed & Built by - Satvik (satvik-7773)*")
