import sys
import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

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
# 1. CORE DATA INGESTION ENGINE (STABLE AIRLABS BASELINE)
# =====================================================================
@st.cache_data(ttl=15)
def fetch_airlabs_baseline(api_key):
    """Pulls the stable, metadata-rich civilian global matrix."""
    try:
        url = f"https://airlabs.co/api/v9/flights?api_key={api_key}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json().get("response", [])
        
        parsed_vectors = []
        for ac in data:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue
                
            parsed_vectors.append({
                "icao24": str(ac.get("hex", "UNKN")).upper(),
                "callsign": str(ac.get("flight_iata") or ac.get("flight_icao") or "UNKN").strip(),
                "latitude": float(lat),
                "longitude": float(lon),
                "baro_altitude": float(ac.get("alt", 0)) * 3.28084, # Converts meters to feet
                "velocity": float(ac.get("speed", 0.0)),
                "heading": float(ac.get("dir", 0.0)),
                "vertical_rate": float(ac.get("v_speed", 0.0)),
                "aircraft_type": str(ac.get("aircraft_icao", "UNKN")),
                "flight_number": str(ac.get("flight_iata", "UNKN")),
                "airline_code": str(ac.get("airline_iata", "UNKN")),
                "departure_iata": str(ac.get("dep_iata", "UNKN")),
                "military": False, # AirLabs scrubs tactical assets by default
                "source": "AirLabs"
            })
            
        df = pd.DataFrame(parsed_vectors)
        if df.empty:
            return df
            
        # --- KINEMATIC ANOMALY ENGINE (V4 STABLE BASELINE) ---
        df["Classification"] = "Standard Track"
        biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "F900", "FA7X", "C750", "E55P", "C56X"]
        
        for idx, row in df.iterrows():
            try:
                velocity = float(row.get("velocity", 0.0))
                altitude = float(row.get("baro_altitude", 0.0))
                aircraft_type = str(row.get("aircraft_type", "UNKN")).upper().strip()
                icao24 = str(row.get("icao24", "UNKN")).upper().strip()
                
                is_low_alt_dash = (altitude < 15000 and velocity > 850)
                max_ceiling = 51000 if aircraft_type in biz_jets else 44000
                is_ceiling_breach = (altitude > max_ceiling)
                is_true_dash = (velocity > 1250) or (velocity > 1050 and altitude < 28000)
                is_malformed_hex = (icao24 != "UNKN" and len(icao24) != 6)
                
                if is_low_alt_dash or is_ceiling_breach or is_true_dash or is_malformed_hex:
                    df.at[idx, "Classification"] = "Threat Alert"
            except Exception:
                pass
                
        return df

    except Exception as e:
        st.error(f"AirLabs Pipeline Error: {e}")
        return pd.DataFrame()

# =====================================================================
# APPLICATION HEADER & UI
# =====================================================================
st.title("🛰️ AeroTrack-V1 // Airspace Monitor")
st.caption("Real-Time Global Aircraft Anomaly Detection")
st.divider()

st.sidebar.header("Global Airspace Command")
st.sidebar.markdown("Execute the 'Refresh Global Coordinates' command to perform a radar sweep.")

if st.sidebar.button("📡 Refresh Global Coordinates", width="stretch"):
    st.cache_data.clear()
    st.toast("Global radar sweep dispatched!", icon="🚀")

with st.spinner("Synchronizing stable civilian air traffic..."):
    df = fetch_airlabs_baseline(AIRLABS_API_KEY)

# --- GRAPHICS RENDERING LAYER ---
if df.empty:
    st.warning("⚠️ Warning: No active tracking streams detected. Check API key and quota.")
else:
    total_targets = len(df)
    threat_count = len(df[df["Classification"] == "Threat Alert"])
    
    m1, m2, m3 = st.columns(3)
    m1.metric(label="Total Logged Airspace Tracks", value=f"{total_targets} Targets")
    m2.metric(label="Kinematic Anomalies", value=f"{threat_count} Active")
    m3.metric(label="Radar Status", value="LIVE🔴")
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
    
    st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("Active Airspace Intelligence Log")
    
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
    
    available_cols = [col for col in display_columns if col in df.columns]
    df_display = df[available_cols].copy()
    
    df_display = df_display.rename(columns={
        "Classification": "Threat Status",
        "flight_number": "Flight No.",
        "airline_code": "Operator ID",
        "aircraft_type": "Airframe",
        "departure_iata": "Origin",
        "baro_altitude": "Alt (ft)",
        "velocity": "Speed (km/h)",
        "heading": "Track (°)",
        "icao24": "Hex"
    })
    
    if "Threat Status" in df_display.columns:
        df_display["_sort_rank"] = df_display["Threat Status"].apply(lambda x: 0 if x == "Threat Alert" else 1)
        df_display = df_display.sort_values(by=["_sort_rank", "Alt (ft)"], ascending=[True, False])
        df_display = df_display.drop(columns=["_sort_rank"])

    st.dataframe(df_display, width="stretch", hide_index=True)

st.markdown("--- *Real-Time Civilian Airspace Telemetry by AirLabs • Designed & Built by - Satvik (satvik-7773)*")
