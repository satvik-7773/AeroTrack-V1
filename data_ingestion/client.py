"""
AeroTrack-V1: High-Availability AirLabs Ingestion Node
"""

import os
import sys
import logging
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

class OpenSkyClient:
    """Production data client routing through cloud-friendly AirLabs data stream."""
    
    def __init__(self):
        self.endpoint = "https://airlabs.co/api/v9/flights"
        
        # Pull API key from Streamlit secrets, strictly matching your secret name
        try:
            import streamlit as st
            self.api_key = st.secrets["AIRLABS_API_KEY"]
        except Exception:
            self.api_key = os.getenv("AIRLABS_API_KEY", "")
        
    def poll_airspace_matrix(self):
        """Polls tracking telemetry using the cloud-allowed AirLabs engine."""
        if not self.api_key:
            logging.error("CRITICAL: AIRLABS_API_KEY is missing from Secrets!")
            return None
            
        params = {"api_key": self.api_key}
        
        try:
            logging.info("Initiating cloud-friendly telemetry pipe to AirLabs...")
            response = requests.get(self.endpoint, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"AirLabs Pipe Failure: {e}")
            return None

    def parse_state_vectors(self, payload):
        """Standardizes AirLabs JSON to internal AeroTrack format."""
        if not payload or "response" not in payload:
            return []

        parsed_records = []
        for ac in payload["response"]:
            # Standardize records
            parsed_records.append({
                "icao24": str(ac.get("hex", "UNKN")).upper(),
                "callsign": str(ac.get("flight_iata", "UNKN")),
                "aircraft_type": str(ac.get("aircraft_icao", "UNKN")),
                "airline_code": str(ac.get("airline_iata", "UNKN")),
                "flight_number": str(ac.get("flight_iata", "UNKN")),
                "departure_iata": str(ac.get("dep_iata", "UNKN")),
                "longitude": float(ac.get("lng", 0)),
                "latitude": float(ac.get("lat", 0)),
                "baro_altitude": float(ac.get("alt", 0)) * 3.28084,
                "velocity": float(ac.get("speed", 0.0)),
                "heading": float(ac.get("dir", 0.0)),
                "vertical_rate": float(ac.get("v_speed", 0.0)),
                "military": False,
                "source": "AirLabs"
            })
        return parsed_records
