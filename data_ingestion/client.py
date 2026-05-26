"""
AeroTrack-V1: High-Availability AirLabs Ingestion Node
Author: Certified Python Developer
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
        
        # Pull API key from Hugging Face environment variables or Streamlit secrets
        if "AIRLABS_KEY" in os.environ:
            self.api_key = os.environ.get("AIRLABS_KEY", "")
        elif hasattr(sys, 'modules') and 'streamlit' in sys.modules:
            import streamlit as st
            self.api_key = st.secrets.get("AIRLABS_KEY", "")
        else:
            self.api_key = os.getenv("AIRLABS_KEY", "")
        
    def poll_airspace_matrix(self):
        """Polls tracking telemetry using the cloud-allowed AirLabs engine."""
        if not self.api_key:
            logging.error("CRITICAL: AIRLABS_KEY environment variable is missing!")
            return None
            
        params = {
            "api_key": self.api_key
        }
        
        try:
            logging.info("Initiating cloud-friendly telemetry pipe to AirLabs Engine...")
            response = requests.get(self.endpoint, params=params, timeout=12)
            if response.status_code == 200:
                logging.info("AirLabs link established. Live telemetry streaming verified.")
                return response.json()
            logging.warning("AirLabs responded with unexpected status code: %d", response.status_code)
        except Exception as error:
            logging.error("Failed to connect to AirLabs data pipeline: %s", str(error))
            
        return None

    @staticmethod
    def parse_state_vectors(payload):
        """Parses the AirLabs dynamic JSON structure into the core AeroTrack telemetry matrix."""
        if not payload or not isinstance(payload, dict) or "response" not in payload:
            logging.warning("Received blank or invalid payload matrix array.")
            return []

        parsed_records = []
        import time
        timestamp = int(time.time()) # Use current Unix epoch time
        
        for ac in payload["response"]:
            # Filter out entries missing crucial positional metrics
            if "lat" not in ac or "lng" not in ac or ac["lat"] is None or ac["lng"] is None:
                continue
                
            parsed_records.append({
                "icao24": ac.get("hex", "UNKN"),
                "callsign": ac.get("flight_number", ac.get("flight_icao", "UNKN")),
                "origin_country": ac.get("flag", "Unknown"),
                "timestamp": timestamp,
                "longitude": float(ac["lng"]),
                "latitude": float(ac["lat"]),
                "baro_altitude": float(ac.get("alt", 0.0)) * 3.28084, # Convert meters to feet if necessary
                "velocity": float(ac.get("speed", 0.0)), # Ground speed in km/h or knots
                "heading": float(ac.get("dir", 0.0)), # Direction track angle
                "vertical_rate": float(ac.get("v_speed", 0.0)) # Vertical speed
            })
            
        return parsed_records
