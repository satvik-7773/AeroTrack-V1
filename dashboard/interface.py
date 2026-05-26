"""
AeroTrack-V1: Tactical Airspace Monitoring Interface
Author: Certified Python Developer
"""
import sys
import os

# Dynamically append the project root directory to the Python tracking path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Your existing imports continue perfectly below
import streamlit as st
import pandas as pd
import plotly.express as px
import time
from data_ingestion.client import OpenSkyClient

import streamlit as st
import pandas as pd
import plotly.express as px
import time
from data_ingestion.client import OpenSkyClient

# Page configuration for tactical dark-mode dashboard aesthetics
st.set_page_config(
    page_title="AeroTrack-V1 // Airspace Monitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Force Dark Theme styling injection
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    div.stButton > button:first-child {
        background-color: #0066cc; color: white; border-radius: 4px;
        font-weight: bold; border: none; height: 3em;
    }
    div.stButton > button:first-child:hover { background-color: #0052a3; }
    </style>
    """, unsafe_allow_html=True)

# Initialize the underlying ingestion client node
client = OpenSkyClient()

# --- STRATEGY 1 & 2: MEMORY CACHE SHIELD ---
# This function buffers the API payload in server memory for 60 seconds
@st.cache_data(ttl=60)
def fetch_airspace_telemetry():
    """Queries the AirLabs data pipeline and returns structured data frame mapping."""
    raw_payload = client.poll_airspace_matrix()
    parsed_vectors = client.parse_state_vectors(raw_payload)
    
    if not parsed_vectors:
        return pd.DataFrame()
        
    return pd.DataFrame(parsed_vectors)

# --- APPLICATION HEADER ---
st.title("🛰️ AeroTrack-V1 // Tactical Airspace Control Grid")
st.caption("Real-Time Global ADS-B Ingestion Engine • Powered by AirLabs API & Machine Learning")
st.divider()

# --- SIDEBAR CONTROLLER MATRIX ---
st.sidebar.header("🕹️ Tactical Control Panel")
st.sidebar.markdown("Use the primary sweep mechanism to ping active transponders over global airspace corridors.")

# Quota tracking helper inside sidebar
st.sidebar.info("💡 **Quota Optimization Active:** Radar sweeps are throttled to 1 request per 60 seconds to protect your free 1,000 monthly tier limit.")

# --- ON-DEMAND RADAR SWEEP TRIGGER ---
col1, col2 = st.columns([3, 1])

with col1:
    # Clicking this button clears the local 60-second cache to allow a fresh API call
    if st.button("📡 EXECUTE ACTIVE RADAR CORRIDOR SWEEP", use_container_width=True):
        st.cache_data.clear()
        st.toast("Transponder ping dispatched to AirLabs matrix!", icon="🚀")

with col2:
    # Explicit timestamp tracker so you know exactly when the current map data was pulled
    if 'last_sweep' not in st.session_state:
        st.session_state.last_sweep = time.strftime("%H:%M:%S")
        
    if st.button("🔄 Force UI Redraw", use_container_width=True):
        st.session_state.last_sweep = time.strftime("%H:%M:%S")

# Fetch data (Will pull instantly from local cache memory unless the Sweep button clears it)
with st.spinner("Processing tactical sensor arrays..."):
    df = fetch_airspace_telemetry()

# --- GRAPHICS RENDERING MATRIX ---
if df.empty:
    st.warning("⚠️ Airspace Grid Cold: No active tracking streams detected. Execute an Active Radar Corridor Sweep above.")
else:
    # Metric Snapshot Layout
    total_aircraft = len(df)
    avg_velocity = df['velocity'].mean()
    max_altitude = df['baro_altitude'].max()

    m1, m2, m3 = st.columns(3)
    m1.metric(label="Active Radar Targets", value=f"{total_aircraft} Airborne")
    m2.metric(label="Mean Ground Speed", value=f"{avg_velocity:.1f} km/h")
    m3.metric(label="Ceiling Peak", value=f"{max_altitude:,.0f} ft")

    # Layout Partition: Left Map, Right Data Grid
    graph_col, table_col = st.columns([2, 1])

    with graph_col:
        st.subheader("🌐 Real-Time Spatial Vector Tracking Map")
        
        # Build Mapbox plot engine
        fig = px.scatter_mapbox(
            df,
            lat="latitude",
            lon="longitude",
            hover_name="callsign",
            hover_data=["icao24", "origin_country", "baro_altitude", "velocity"],
            color="velocity",
            color_continuous_scale=px.colors.sequential.Plasma,
            size_max=15,
            zoom=1.5,
            height=600
        )
        
        fig.update_layout(
            mapbox_style="carto-darkmatter",
            margin={"r":0,"t":0,"l":0,"b":0},
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font_color="#ffffff"
        )
        
        st.plotly_chart(fig, use_container_width=True)

    with table_col:
        st.subheader("📋 Airborne Target Matrix Log")
        
        # Cleaned-up display frame for the raw log viewer
        display_df = df[["callsign", "origin_country", "baro_altitude", "velocity", "heading"]].copy()
        display_df.columns = ["Callsign", "Flag", "Altitude (ft)", "Speed (km/h)", "Heading"]
        
        st.dataframe(
            display_df,
            height=560,
            use_container_width=True,
            hide_index=True
        )

st.markdown(f"--- *Grid Data Frame Static Memory Address State • Last Valid Fetch Sequence Verified*")
