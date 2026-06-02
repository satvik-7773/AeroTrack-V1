import sys
import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import time

# Dynamically append the project root directory to the Python tracking path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =====================================================================
# CONFIGURATION
# =====================================================================
# Insert your AirLabs API Key here (or use st.secrets["AIRLABS_API_KEY"])
AIRLABS_API_KEY = "4968fc59-348d-4a8a-af4f-73861d867e4e"

# Page configuration for tactical full-width dark-mode radar grid
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

# =====================================================================
# 1. CORE DATA INGESTION ENGINE (UNFILTERED GLOBAL SWEEP)
# =====================================================================
@st.cache_data(ttl=15)
def fetch_global_unfiltered_airspace(airlabs_api_key):
    """Pulls unfiltered global telemetry by bypassing the API and scraping the raw map state."""
    tactical_grid = {}

    # --- INGEST ADSB.FI (THE RAW MAP BYPASS) ---
    try:
        # Bypassing the restricted API and hitting the raw dump1090 state file
        adsb_url = "https://adsb.fi/data/aircraft.json"
        
        # Spoofing a standard Chrome browser so their server doesn't block the Python request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        response = requests.get(adsb_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # The map JSON uses the 'aircraft' array instead of 'ac'
        for ac in response.json().get("aircraft", []):
            hex_code = str(ac.get("hex", "UNKN")).upper()
            if hex_code == "UNKN": 
                continue
            
            raw_speed_knots = float(ac.get("gs", 0.0)) if ac.get("gs") is not None else 0.0
            speed_kmh = raw_speed_knots * 1.852 
            
            tactical_grid[hex_code] = {
                "icao24": hex_code,
                "callsign": str(ac.get("flight", "UNKN")).strip(),
                "latitude": ac.get("lat"),
                "longitude": ac.get("lon"),
                "baro_altitude": float(ac.get("alt_baro", 0.0)) if isinstance(ac.get("alt_baro"), (int, float)) else 0.0,
                "velocity": speed_kmh, 
                "heading": float(ac.get("track", 0.0)) if ac.get("track") is not None else 0.0,
                "vertical_rate": float(ac.get("baro_rate", 0.0)) if ac.get("baro_rate") is not None else 0.0,
                "military": ac.get("mil", False), 
                "source": "ADSB.fi"
            }
    except Exception as e:
        st.error(f"Tactical Global Feed Error: {e}")

    # --- INGEST AIRLABS (CIVILIAN METADATA OVERLAY) ---
    try:
        airlabs_url = f"https://airlabs.co/api/v9/flights?api_key={airlabs_api_key}"
        response = requests.get(airlabs_url, timeout=15)
        response.raise_for_status()
        
        for ac in response.json().get("response", []):
            hex_code = str(ac.get("hex", "UNKN")).upper()
            if hex_code == "UNKN": 
                continue
            
            if hex_code in tactical_grid:
                tactical_grid[hex_code]["aircraft_type"] = ac.get("aircraft_icao", "UNKN")
                tactical_grid[hex_code]["flight_number"] = ac.get("flight_iata", "UNKN")
                tactical_grid[hex_code]["airline_code"] = ac.get("airline_iata", "UNKN")
                tactical_grid[hex_code]["departure_iata"] = ac.get("dep_iata", "UNKN")
            else:
                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": ac.get("lat"),
                    "longitude": ac.get("lon"),
                    "baro_altitude": float(ac.get("alt", 0)) * 3.28084,
                    "velocity": float(ac.get("speed", 0.0)) if ac.get("speed") is not None else 0.0,
                    "heading": float(ac.get("dir", 0.0)) if ac.get("dir") is not None else 0.0,
                    "vertical_rate": float(ac.get("v_speed", 0.0)) if ac.get("v_speed") is not None else 0.0,
                    "aircraft_type": ac.get("aircraft_icao", "UNKN"),
                    "flight_number": ac.get("flight_iata", "UNKN"),
                    "airline_code": ac.get("airline_iata", "UNKN"),
                    "departure_iata": ac.get("dep_iata", "UNKN"),
                    "military": False,
                    "source": "AirLabs"
                }
    except Exception as e:
        st.error(f"AirLabs Global Feed Error: {e}")

    # --- SANITIZATION & DATAFRAME CREATION ---
    final_list = [t for t in tactical_grid.values() if t.get("latitude") is not None and t.get("longitude") is not None]
    
    if not final_list:
        return pd.DataFrame(columns=[
            "icao24", "callsign", "latitude", "longitude", "baro_altitude", 
            "velocity", "heading", "vertical_rate", "military", "source",
            "aircraft_type", "flight_number", "airline_code", "departure_iata", "Classification"
        ])
        
    df_temp = pd.DataFrame(final_list)
    
    # --- KINEMATIC ANOMALY & PHYSICS ENFORCEMENT ENGINE ---
    df_temp["Classification"] = "Standard Track"
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750"]
    
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
st.title("🛰️ AeroTrack-V1 // Map Aircraft Anomalies in the Airspace")
st.caption("Real-Time Global Aircraft Anomaly Detection • Possible Threat Detection")
st.divider()

# --- SIDEBAR CONTROLLER ---
st.sidebar.header("Global Airspace Map")
st.sidebar.markdown("Execute the 'Refresh The Aircraft Coordinates' command to perform a radar sweep")
st.sidebar.info("💡 Map Refresh Requests are processed locally. Global payloads pull 15k+ targets.")

# --- SCAN TRIGGER CONTROLLER ---
if st.button("📡 Refresh The Aircraft Coordinates", use_container_width=True):
    st.cache_data.clear()
    st.toast("Global radar sweep dispatched!", icon="🚀")

# Ingest and process telemetry matrix
with st.spinner("Synchronizing global unfiltered aircraft positions...."):
    df = fetch_global_unfiltered_airspace(AIRLABS_API_KEY)

# --- GRAPHICS RENDERING LAYER ---
if df.empty:
    st.warning("⚠️ Warning: No active tracking streams detected. Retry...")
else:
    # Top-Level Fleet Metrics
    total_targets = len(df)
    threat_count = len(df[df["Classification"] == "Threat Alert"])
    
    m1, m2, m3 = st.columns(3)
    m1.metric(label="Total Logged Airspace Tracks", value=f"{total_targets} Targets")
    m2.metric(label="Identified Anomalies / Alerts", value=f"{threat_count} Active")
    m3.metric(label="System Status", value="LIVE🔴")
    st.write("")

    # SECTION 1: Full-Width Tactical Tracking Map
    st.subheader("🌐 Real-Time Global Airspace Mapping")
    
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
            "military": True,  # New data point added to map
            "source": True,    # New data point added to map
            "Classification": True
        },
        color="Classification",
        color_discrete_map={"Standard Track": "#00ffff", "Threat Alert": "#ff0033"}, 
        size_max=12,
        zoom=1.8,
        height=650
    )
    
    fig.update_layout(
        mapbox_style="carto-darkmatter",
        margin={"r":0,"t":0,"l":0,"b":0},
        paper_bgcolor="#0b0e14",
        plot_bgcolor="#0b0e14",
        font_color="#ffffff",
        legend=dict(
            yanchor="top",
            y=0.98,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(11, 14, 20, 0.8)",
            font=dict(color="#ffffff")
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # --- AIRBORNE LOG MATRIX (TABLE UI) ---
    st.divider()
    st.subheader("Active Airspace Intelligence Log")
    
    # 1. Select only the most relevant columns for the tactical display
    display_columns = [
        "Classification", 
        "flight_number",
        "airline_code",
        "aircraft_type",
        "departure_iata",
        "military",       # Added to table for quick tactical reference
        "baro_altitude", 
        "velocity", 
        "heading", 
        "icao24"
    ]
    
    # Check if the columns exist (safeguard for cold starts)
    available_cols = [col for col in display_columns if col in df.columns]
    df_display = df[available_cols].copy()
    
    # 2. Rename the backend keys into professional UI headers
    df_display = df_display.rename(columns={
        "Classification": "Threat Status",
        "flight_number": "Flight No.",
        "airline_code": "Operator ID",
        "aircraft_type": "Airframe",
        "departure_iata": "Origin (IATA)",
        "military": "Mil Asset",
        "baro_altitude": "Altitude (ft)",
        "velocity": "Ground Speed (km/h)",
        "heading": "Track (°)",
        "icao24": "Transponder Hex"
    })
    
    # 3. Sort the matrix to bubble Threat Alerts to the absolute top
    if "Threat Status" in df_display.columns:
        # Create a custom sorting index (Threats get a 0, Standards get a 1)
        df_display["_sort_rank"] = df_display["Threat Status"].apply(lambda x: 0 if x == "Threat Alert" else 1)
        df_display = df_display.sort_values(by=["_sort_rank", "Altitude (ft)"], ascending=[True, False])
        df_display = df_display.drop(columns=["_sort_rank"])

    # 4. Render the final matrix in full width
    st.dataframe(df_display, use_container_width=True, hide_index=True)

st.markdown("--- *Real-Time Airspace Telemetry by AirLabs & ADSB.fi • Designed & Built by - Satvik (satvik-7773)*")
