"""
AeroTrack-V1: Full-Width Tactical Airspace Control Center
Author: Certified Python Developer
"""

import sys
import os

# Dynamically append the project root directory to the Python tracking path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import time
from data_ingestion.client import OpenSkyClient

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

# Initialize the underlying ingestion client node
client = OpenSkyClient()

# --- DATA MEMORY BUFFER SHIELD ---
@st.cache_data(ttl=60)
def fetch_airspace_telemetry():
    """Queries the AirLabs data pipeline and structures the incoming vectors."""
    raw_payload = client.poll_airspace_matrix()
    parsed_vectors = client.parse_state_vectors(raw_payload)
    
    if not parsed_vectors:
        return pd.DataFrame()
        
    df_temp = pd.DataFrame(parsed_vectors)
    
    # Clean up callsign strings to ensure full format (e.g., "AI111")
    if "callsign" in df_temp.columns:
        df_temp["callsign"] = df_temp["callsign"].str.upper().str.strip()
        
    # --- TACTICAL THREAT DISCRIMINATION LOGIC ---
    # Assigning Cyan for baseline tracks, Red for targets matching alert criteria
    df_temp["Classification"] = "Standard Track"
    df_temp["Tactical_Color"] = "#00ffff"  # Default Cyan
    
    # Quick alert threshold: flag targets with extreme speeds or vertical rates as anomalies
    if not df_temp.empty:
        threat_mask = (df_temp["velocity"] > 950) | (df_temp["vertical_rate"].abs() > 3000)
        df_temp.loc[threat_mask, "Classification"] = "Threat Alert"
        df_temp.loc[threat_mask, "Tactical_Color"] = "#ff0000"  # High-Visibility Red
        
    return df_temp

# --- APPLICATION HEADER ---
st.title("🛰️ AeroTrack-V1 // Map Aircraft Anomalies in the Airspace")
st.caption("Real-Time Global Anomaly Detection • Threat Discrimination")
st.divider()

# --- SIDEBAR CONTROLLER ---
st.sidebar.header("Global Airspace Map")
st.sidebar.markdown("Execute the 'Refresh The Aircraft Coordinates' command to perform a radar sweep")
st.sidebar.info("💡Map Refresh Requests are Capped to 1Req per minute for Efficiency of the Tool !")

# --- SCAN TRIGGER CONTROLLER ---
if st.button("📡 Refresh The Aircraft Coordinates", use_container_width=True):
    st.cache_data.clear()
    st.toast("Radar sweep dispatched!", icon="🚀")

# Ingest and process telemetry matrix
with st.spinner("Synchronizing global aircraft positions...."):
    df = fetch_airspace_telemetry()

# --- GRAPHICS RENDERING LAYER ---
if df.empty:
    st.warning("⚠️ Warning: No active tracking streams detected. Retry...")
else:
    # Top-Level Fleet Metrics
    total_targets = len(df)
    threat_count = len(df[df["Classification"] == "Possible Threat Alert"])
    
    m1, m2, m3 = st.columns(3)
    m1.metric(label="Total Logged Airspace Tracks", value=f"{total_targets} Targets")
    m2.metric(label="Identified Anomalies / Alerts", value=f"{threat_count} Active")
    m3.metric(label="Sensor System Array Status", value="LIVE")
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
            "origin_country": True, 
            "baro_altitude": True, 
            "velocity": True,
            "Classification": True,
            "Tactical_Color": False # Hide color hex codes from tooltip
        },
        color="Classification",
        color_discrete_map={"Standard Track": "#00ffff", "Possible Threat Alert": "#ff0033"}, # Forces Cyan and Red dots
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
    st.divider()

    # SECTION 2: Full-Width Airborne Logs (Threats & Active Airspace Data)
    st.subheader("📋 Active Airspace Log & Anomaly Log Status")
    
    # Filter the view down to actionable flight vectors
    log_df = df[["Classification", "callsign", "origin_country", "baro_altitude", "velocity", "heading", "icao24"]].copy()
    log_df.columns = ["Status", "Full Callsign", "Country of Origin", "Altitude (ft)", "Ground Speed (km/h)", "Heading Angle", "ICAO24 Transponder"]
    
    # Sort so that any active Red "Threat Alerts" bubble straight to the top of the logging array
    log_df = log_df.sort_values(by="Status", ascending=False)
    
    st.dataframe(
        log_df,
        height=400,
        use_container_width=True,
        hide_index=True
    )

st.markdown("--- *Static Memory // State Verified Data • Designed & Built by - Satvik (satvik-7773)")
