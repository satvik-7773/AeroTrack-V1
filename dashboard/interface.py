"""
AeroTrack-V1: Live Tactical Streaming Interface
Author: Certified Python Developer
"""

import os
import sys
import time
import joblib
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from data_ingestion.client import OpenSkyClient

st.set_page_config(page_title="AeroTrack-V1 Live Matrix", layout="wide")

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

st.title("🛰️ TACTICAL LIVE RADAR // AEROTRACK-V1")
st.caption("REAL-TIME STREAMING AIRSPACE TELEMETRY // AI INFERENCE CORE")
st.write("---")

CORE_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_TARGET = os.path.join(CORE_DIR, "ml_models", "skyguard_model.pkl")

if "radar_buffer" not in st.session_state:
    st.session_state.radar_buffer = pd.DataFrame()
if "client_node" not in st.session_state:
    st.session_state.client_node = OpenSkyClient()
if "classifier" not in st.session_state:
    st.session_state.classifier = joblib.load(MODEL_TARGET) if os.path.exists(MODEL_TARGET) else None

def process_live_stream(raw_vectors, prior_df):
    current_df = pd.DataFrame(raw_vectors)
    if current_df.empty:
        return prior_df
    if prior_df.empty:
        current_df["acceleration"] = 0.0
        current_df["turn_rate"] = 0.0
        return current_df

    prior_lookup = prior_df.set_index("icao24")[["timestamp", "velocity", "heading"]].drop_duplicates()
    current_df = current_df.join(prior_lookup, on="icao24", rsuffix="_prev")

    current_df["dt"] = current_df["timestamp"] - current_df["timestamp_prev"]
    current_df["dv"] = current_df["velocity"] - current_df["velocity_prev"]
    current_df["acceleration"] = np.where(current_df["dt"] > 0, current_df["dv"] / current_df["dt"], 0.0)

    current_df["d_heading"] = current_df["heading"] - current_df["heading_prev"]
    current_df["d_heading"] = np.where(current_df["d_heading"] > 180, current_df["d_heading"] - 360, current_df["d_heading"])
    current_df["d_heading"] = np.where(current_df["d_heading"] < -180, current_df["d_heading"] + 360, current_df["d_heading"])
    current_df["turn_rate"] = np.where(current_df["dt"] > 0, np.abs(current_df["d_heading"]) / current_df["dt"], 0.0)

    current_df["acceleration"] = current_df["acceleration"].fillna(0.0)
    current_df["turn_rate"] = current_df["turn_rate"].fillna(0.0)
    
    drop_cols = ["dt", "dv", "d_heading", "timestamp_prev", "velocity_prev", "heading_prev"]
    return current_df.drop(columns=[col for col in drop_cols if col in current_df.columns])

if st.session_state.classifier is None:
    st.error("SYSTEM ERROR: Machine Learning Model Binary Not Found.")
else:
    # Pull strict, un-cached live vectors from space
    raw_payload = st.session_state.client_node.poll_airspace_matrix()
    parsed_vectors = st.session_state.client_node.parse_state_vectors(raw_payload)

    if not parsed_vectors:
        st.warning("🔄 Connecting to live airspace coordinates... Radar sweeping...")
        working_df = st.session_state.radar_buffer
    else:
        st.session_state.radar_buffer = process_live_stream(parsed_vectors, st.session_state.radar_buffer)
        working_df = st.session_state.radar_buffer.copy()

    if not working_df.empty:
        working_df["vertical_rate"] = working_df["vertical_rate"].fillna(0.0)
        features = ["velocity", "vertical_rate", "acceleration", "turn_rate"]
        
        predictions = st.session_state.classifier.predict(working_df[features].values)
        working_df["threat_status"] = np.where(predictions == -1, "THREAT METRIC VIOLATION", "NOMINAL")

        total_targets = len(working_df)
        live_threats = len(working_df[working_df["threat_status"] == "THREAT METRIC VIOLATION"])

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Live Tracked Targets", total_targets)
        with col2:
            st.metric("Active Threat Alerts", live_threats, delta=f"Risk Corridors: {live_threats/total_targets*100:.2f}%" if total_targets > 0 else "0%")
        with col3:
            st.metric("Data Engine Status", "STREAMING // LIVE")

        # Map display
        palette = {"NOMINAL": "#00ffd0", "THREAT METRIC VIOLATION": "#ff2a5f"}
        live_map = px.scatter_map(
            working_df, lat="latitude", lon="longitude",
            color="threat_status", color_discrete_map=palette,
            hover_name="callsign", hover_data=["icao24", "velocity", "acceleration", "turn_rate"],
            zoom=1, height=600
        )
        live_map.update_layout(map_style="open-street-map", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(live_map, width="stretch")

        # Table Display
        st.write("### Live Incident Capture Log")
        threat_log = working_df[working_df["threat_status"] == "THREAT METRIC VIOLATION"][
            ["timestamp", "icao24", "callsign", "velocity", "acceleration", "turn_rate"]
        ].sort_values(by="acceleration", ascending=False)
        st.dataframe(threat_log, width="stretch")

    # Force continuous 30 second radar sweep rerun loop
    time.sleep(30)
    st.rerun()