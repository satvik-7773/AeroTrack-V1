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

# =====================================================================
# 1. CORE DATA INGESTION ENGINE (GLOBAL BYPASS)
# =====================================================================
@st.cache_data(ttl=15)
def fetch_global_unfiltered_airspace(airlabs_api_key):
    tactical_grid = {}

    # --- INGEST AIRPLANES.LIVE (THE RAW MAP STATE DUMP) ---
    try:
        # Bypassing the locked API by pulling the raw tar1090 map state file
        adsb_url = "https://globe.airplanes.live/data/aircraft.json"
        
        # Spoofing Chrome to prevent 403 Forbidden/404 errors
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        response = requests.get(adsb_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # tar1090 map JSON uses 'aircraft' array
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
                # Strictly checking for 'mil', ignoring MLAT strings to prevent false military flags
                "military": True if ac.get("mil", False) else False, 
                "source": "Airplanes.live",
                # Default intelligence fields in case AirLabs misses a hex (prevents Plotly crashes)
                "aircraft_type": "UNKN",
                "flight_number": "UNKN",
                "airline_code": "UNKN",
                "departure_iata": "UNKN"
            }
    except Exception as e:
        st.error(f"Tactical Global Feed Error: {e}")

    # --- INGEST AIRLABS (GLOBAL METADATA MERGE) ---
    try:
        # Hitting the global AirLabs feed to guarantee metadata population
        airlabs_url = f"https://airlabs.co/api/v9/flights?api_key={airlabs_api_key}"
        response = requests.get(airlabs_url, timeout=15)
        response.raise_for_status()
        
        for ac in response.json().get("response", []):
            hex_code = str(ac.get("hex", "UNKN")).upper()
            if hex_code == "UNKN": 
                continue
            
            # THE MERGE: Overwrite the "UNKN" defaults with actual civil intelligence
            if hex_code in tactical_grid:
                tactical_grid[hex_code]["aircraft_type"] = ac.get("aircraft_icao", "UNKN")
                tactical_grid[hex_code]["flight_number"] = ac.get("flight_iata", "UNKN")
                tactical_grid[hex_code]["airline_code"] = ac.get("airline_iata", "UNKN")
                tactical_grid[hex_code]["departure_iata"] = ac.get("dep_iata", "UNKN")
            else:
                # If AirLabs caught a plane that the tactical feed missed entirely
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
    
    # --- KINEMATIC ANOMALY ENGINE ---
    df_temp["Classification"] = "Standard Track"
    # Extended business jet list to cover standard high-altitude flyers
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
