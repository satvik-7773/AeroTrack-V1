"""
AeroTrack-X1: Telemetry Ingestion Node
Author: Certified Python Developer
"""

import os
import sys
import logging
import requests
from datetime import datetime

# Configure enterprise-grade logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

class OpenSkyClient:
    """Production REST client for global ADS-B telemetry data stream extraction."""
    
    def __init__(self):
        self.endpoint = "https://opensky-network.org/api/states/all"
        self.username = os.getenv("AEROTRACK_USER", "")
        self.password = os.getenv("AEROTRACK_PASS", "")
        
    def poll_airspace_matrix(self):
        """Polls the global tracking matrix state vector array."""
        auth = (self.username, self.password) if self.username and self.password else None
        
        try:
            logging.info("Initiating connection to OpenSky telemetry grid...")
            response = requests.get(self.endpoint, auth=auth, timeout=15)
            
            if response.status_code == 200:
                return response.json()
                
            logging.error("Inbound link failure. HTTP Status Code: %d", response.status_code)
            return None
            
        except requests.exceptions.RequestException as error:
            logging.error("Network interface connection aborted: %s", str(error))
            return None

    @staticmethod
    def parse_state_vectors(payload):
        """Parses raw matrices into structured records, filtering out dropped packets."""
        if not payload or "states" not in payload or not payload["states"]:
            logging.warning("Received blank or invalid payload matrix.")
            return []

        parsed_records = []
        timestamp = payload["time"]
        
        for vector in payload["states"]:
            # Coordinate validation check
            if vector[5] is None or vector[6] is None or vector[7] is None:
                continue
                
            parsed_records.append({
                "icao24": vector[0],
                "callsign": vector[1].strip() if vector[1] else "UNKN",
                "origin_country": vector[2],
                "timestamp": timestamp,
                "longitude": vector[5],
                "latitude": vector[6],
                "baro_altitude": vector[7],
                "velocity": vector[9],
                "heading": vector[10],
                "vertical_rate": vector[11]
            })
            
        return parsed_records