import os
import logging
import requests
import streamlit as st


class OpenSkyClient:
    """Commercial AirLabs telemetry ingestion client (name preserved for import compatibility)."""

    def __init__(self):
        self.endpoint = "https://airlabs.co/api/v9/flights"
        try:
            secret_key = st.secrets.get("AIRLABS_API_KEY", "")
        except Exception:
            secret_key = ""
        self.api_key = os.getenv("AIRLABS_API_KEY", secret_key)

    def poll_airspace_matrix(self):
        if not self.api_key:
            logging.error("CRITICAL: AIRLABS_API_KEY is missing from environment/secrets.")
            return None
        try:
            response = requests.get(self.endpoint, params={"api_key": self.api_key}, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"AirLabs Pipe Failure: {e}")
            return None

    def parse_state_vectors(self, payload):
        if not payload or "response" not in payload:
            return []
        parsed = []
        for ac in payload["response"]:
            if ac.get("lat") is None or ac.get("lng") is None:
                continue
            parsed.append({
                "icao24": str(ac.get("hex", "UNKN")).upper().strip(),
                "callsign": str(ac.get("flight_iata") or ac.get("flight_icao") or "UNKN").strip(),
                "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(),
                "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip(),
                "airline_icao": str(ac.get("airline_icao", "UNKN")).upper().strip(),
                "flight_number": str(ac.get("flight_number", "UNKN")).strip(),
                "departure_iata": str(ac.get("dep_iata", "UNKN")).upper().strip(),
                "arrival_iata": str(ac.get("arr_iata", "UNKN")).upper().strip(),
                "longitude": float(ac.get("lng") or 0.0),
                "latitude": float(ac.get("lat") or 0.0),
                "baro_altitude": float(ac.get("alt") or 0.0) * 3.28084,
                "velocity": float(ac.get("speed") or 0.0),
                "heading": float(ac.get("dir") or 0.0),
                "vertical_rate": float(ac.get("v_speed") or 0.0),
                "status": str(ac.get("status", "en-route")).lower(),
                "source": "AirLabs",
            })
        return parsed
