"""
AeroTrack-V1
Author: Satvik
"""

import os
import sys
import time
import logging
import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import joblib


sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from data_ingestion.client import OpenSkyClient


st.set_page_config(page_title="AeroTrack-V1 Live", layout="wide")


st.markdown("""
    <style>
    .main { background-color: #070a12; color: #ffffff; }
    .metric-card {
        background-color: #0f1424;
        border: 1px solid #1e294b;
        padding: 1.2rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    div[data-testid="stMetricValue"] { color: #00ffaa; font-family: 'Courier New', monospace; font-weight: 700; }
    div[data-testid="stMetricLabel"] { color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛰️ AEROTRACK-V1 // Live Flight Map")
st.caption("Real Time Flight Anomaly Detector // Active NDSB Interference Node")
st.write("---")

CORE_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_TARGET = os.path.join(CORE_DIR, "ml_models", "skyguard_model.pkl")

# Initialize persistent session states , acts as radar buffer
if "radar_buffer" not in st.session_state:
    st.session_state.radar_buffer = pd.DataFrame()
if "client_node" not in st.session_state:
    st.session_state.client_node = OpenSkyClient()
if "classifier" not in st.session_state:
    st.session_state.classifier = joblib.load(MODEL_TARGET) if os.path.exists(MODEL_TARGET) else None

def process_live_stream(raw_vectors, prior_df):
    """Performs stream feature engineering matching against previous state vectors."""
    current_df = pd.DataFrame(raw_vectors)
    if current_df.empty:
        return prior_df
        
    if prior_df.empty:
        #cycle fallback defaults
        current_df["acceleration"] = 0.0
        current_df["turn_rate"] = 0.0
        return current_df

    
    prior_lookup = prior_df.set_index("icao24")[["timestamp", "velocity", "heading"]]
    current_df = current_df.join(prior_lookup, on="icao24", rsuffix="_prev")

    #differential kinematics
    current_df["dt"] = current_df["timestamp"] - current_df["timestamp_prev"]
    
    #acceleration vector
    current_df["dv"] = current_df["velocity"] - current_df["velocity_prev"]
    current_df["acceleration"] = np.where(current_df["dt"] > 0, current_df["dv"] / current_df["dt"], 0.0)

    #heading angular delta handling circular wrapping bounds
    current_df["d_heading"] = current_df["heading"] - current_df["heading_prev"]
    current_df["d_heading"] = np.where(current_df["d_heading"] > 180, current_df["d_heading"] - 360, current_df["d_heading"])
    current_df["d_heading"] = np.where(current_df["d_heading"] < -180, current_df["d_heading"] + 360, current_df["d_heading"])
    current_df["turn_rate"] = np.where(current_df["dt"] > 0, np.abs(current_df["d_heading"]) / current_df["dt"], 0.0)

    
    current_df["acceleration"] = current_df["acceleration"].fillna(0.0)
    current_df["turn_rate"] = current_df["turn_rate"].fillna(0.0)
    
    drop_cols = ["dt", "dv", "d_heading", "timestamp_prev", "velocity_prev", "heading_prev"]
    return current_df.drop(columns=[col for col in drop_cols if col in current_df.columns])

#control block
if st.session_state.classifier is None:
    st.error("CRITICAL ERROR: AI model brain missing at ml_models/skyguard_model.pkl. Run train_detector.py first.")
else:
    
    raw_payload = st.session_state.client_node.poll_airspace_matrix()
    parsed_vectors = st.session_state.client_node.parse_state_vectors(raw_payload)

   
    st.session_state.radar_buffer = process_live_stream(parsed_vectors, st.session_state.radar_buffer)
    working_df = st.session_state.radar_buffer.copy()

    if not working_df.empty:
        
        working_df["vertical_rate"] = working_df["vertical_rate"].fillna(0.0)
        features = ["velocity", "vertical_rate", "acceleration", "turn_rate"]
        
        predictions = st.session_state.classifier.predict(working_df[features].values)
        working_df["threat_status"] = np.where(predictions == -1, "THREAT METRIC VIOLATION", "NOMINAL")

       
        total_targets = len(working_df)
        live_threats = len(working_df[working_df["threat_status"] == "THREAT METRIC VIOLATION"])

        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Live Tracked Targets", total_targets)
            st.markdown('</div>', unsafe_allow_html=True)
        with m_col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Active Threat Alerts", live_threats, delta=f"Risk: {live_threats/total_targets*100:.2f}%", delta_color="inverse")
            st.markdown('</div>', unsafe_allow_html=True)
        with m_col3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Stream Refresh Window", "POLLING INTERV. // 30s")
            st.markdown('</div>', unsafe_allow_html=True)

        #map updates
        palette = {"NOMINAL": "#00ffd0", "THREAT METRIC VIOLATION": "#ff2a5f"}
        
        live_map = px.scatter_map(
            working_df,
            lat="latitude",
            lon="longitude",
            color="threat_status",
            color_discrete_map=palette,
            hover_name="callsign",
            hover_data=["icao24", "velocity", "acceleration", "turn_rate"],
            zoom=1,
            height=600
        )
        live_map.update_layout(map_style="carto-darkmatter", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(live_map, width="stretch")

        #dyanmic table
        st.write("### Live Incident Capture Log")
        threat_log = working_df[working_df["threat_status"] == "THREAT METRIC VIOLATION"][
            ["timestamp", "icao24", "callsign", "velocity", "acceleration", "turn_rate"]
        ].sort_values(by="acceleration", ascending=False)
        st.dataframe(threat_log, width="stretch")

    else:
        st.warning("Awaiting initial telemetry package lock from API network...")

    #autorefresh
    time.sleep(30)
    st.rerun()
