

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
        
   # --- KINEMATIC ANOMALY & PHYSICS ENFORCEMENT ENGINE ---
    # --- DYNAMIC RELATIONAL ENVELOPE & TRUE ANOMALY ENGINE ---
    if not df_temp.empty:
        df_temp["Classification"] = "Standard Track"
        
        # High-altitude business jets that routinely fly above commercial ceilings
        biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750"]
        
        for idx, row in df_temp.iterrows():
            try:
                velocity = float(row.get("velocity", 0.0))
                altitude = float(row.get("baro_altitude", 0.0))
                vert_rate = abs(float(row.get("vertical_rate", 0.0)))
                aircraft_type = str(row.get("aircraft_type", "UNKN")).upper().strip()
                icao24 = str(row.get("icao24", "UNKN")).upper().strip()
                
                # --- RULE 1: THE DRAG-LIMIT VIOLATION (Spoofed Aerodynamics) ---
                # It is physically impossible for a civil airliner to do 850+ km/h below 15,000 ft. 
                # This indicates a tactical asset or a spoofed transponder hiding down low.
                is_low_alt_dash = (altitude < 15000 and velocity > 850)
                
                # --- RULE 2: AIRFRAME-SPECIFIC CEILING BREACH ---
                # Dynamically set the ceiling based on the aircraft type to stop false alarms on private jets
                max_ceiling = 51000 if aircraft_type in biz_jets else 43500
                is_ceiling_breach = (altitude > max_ceiling)
                
                # --- RULE 3: TAILWIND PROTECTED DASH LIMIT ---
                # A plane at 40k ft can easily hit 1150 km/h with a jetstream (Standard).
                # We only flag if it exceeds 1200 km/h, OR if it hits Mach 1 at medium altitudes.
                is_true_dash = (velocity > 1250) or (velocity > 1050 and altitude < 28000)
                
                # --- RULE 4: HARDWARE METADATA TAMPERING ---
                # A valid ICAO24 code is exactly 6 hex characters. Spoofed SDRs often transmit 
                # corrupted hexes or default strings while still projecting a civil callsign.
                is_malformed_hex = (icao24 != "UNKN" and len(icao24) != 6)
                
                # --- EVALUATION ---
                if is_low_alt_dash or is_ceiling_breach or is_true_dash or is_malformed_hex:
                    df_temp.at[idx, "Classification"] = "Threat Alert"
                    
            except Exception:
                df_temp.at[idx, "Classification"] = "Standard Track"
    else:
        # Guarantee empty dataframe has ALL structural column names, including new intelligence metrics
        df_temp = pd.DataFrame(columns=[
            "Classification", "callsign", "origin_country", "baro_altitude", 
            "velocity", "heading", "icao24", "latitude", "longitude",
            "aircraft_type", "airline_code", "flight_number", "departure_iata", "arrival_iata"
        ])
        
    return df_temp

# --- APPLICATION HEADER ---
st.title("🛰️ AeroTrack-V1 // Map Aircraft Anomalies in the Airspace")
st.caption("Real-Time Global Aircraft Anomaly Detection • Possible Threat Detection")
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
            "origin_country": True, 
            "baro_altitude": True, 
            "velocity": True,
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
    # (We drop raw lat/lon to save screen space, keeping pure intelligence)
    display_columns = [
        "Classification", 
        "flight_number",
        "airline_code",
        "aircraft_type",
        "departure_iata",
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
        df_display = df_display.drop(columns=["_sort_rank"]) # Hide the sorting logic from the UI

    # 4. Render the final matrix in full width
    st.dataframe(df_display, use_container_width=True, hide_index=True)
st.markdown("--- *Real-Time Airspace Telemetry by AirLabs • Designed & Built by - Satvik (satvik-7773)")
