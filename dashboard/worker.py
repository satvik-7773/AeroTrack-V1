import os
import requests
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone

AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_airspace_sector(lat, lon):
    if 35 <= lat <= 70 and -15 <= lon <= 45: return "EUROPEAN AIRSPACE"
    if 25 <= lat <= 60 and -130 <= lon <= -60: return "NORTH AMERICAN SECTOR"
    if 0 <= lat <= 50 and 100 <= lon <= 150: return "EAST ASIAN SECTOR"
    if 10 <= lat <= 35 and 35 <= lon <= 85: return "MIDDLE EAST / S. ASIA"
    return "INTERNATIONAL WATERS"

def process_hourly_sweep():
    tactical_grid = {}
    military_watchlist = set()

    # Ingest Data
    try:
        res = requests.get("https://api.adsb.lol/v2/mil", timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                if ac.get("hex"): military_watchlist.add(str(ac.get("hex")).upper())
    except: pass

    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=15)
        for ac in res.json().get("response", []):
            hex_c = str(ac.get("hex", "UNKN")).upper()
            if hex_c in military_watchlist or str(ac.get("airline_iata")).upper() == "MIL": continue
            tactical_grid[hex_c] = {
                "icao24": hex_c,
                "lat": float(ac.get("lat") or 0),
                "lon": float(ac.get("lng") or 0),
                "alt": float(ac.get("alt") or 0) * 3.28084,
                "vel": float(ac.get("speed") or 0),
                "airframe": str(ac.get("aircraft_icao", "UNKN")).upper(),
                "airline": str(ac.get("airline_iata", "UNKN")).upper(),
                "dep": str(ac.get("dep_iata", "UNKN")).upper()
            }
    except: return

    df = pd.DataFrame(list(tactical_grid.values()))
    if df.empty: return

    # Calculations
    clean_df = df[~df["airline"].isin(["UNKN", ""])]
    top_carrier = str(clean_df["airline"].mode()[0]) if not clean_df.empty else "UNKN"
    top_carrier_count = int(clean_df["airline"].value_counts().max()) if not clean_df.empty else 0
    
    frame_df = df[~df["airframe"].isin(["UNKN", ""])]
    top_frame = str(frame_df["airframe"].mode()[0]) if not frame_df.empty else "UNKN"
    top_frame_count = int(frame_df["airframe"].value_counts().max()) if not frame_df.empty else 0

    stats_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_flights": len(df),
        "threat_count": len(df[df["alt"] > 45000]),
        "military_count": len(military_watchlist),
        "busiest_airport": str(df["dep"].mode()[0]) if not df.empty else "DFW",
        "busiest_region": str(df.apply(lambda r: get_airspace_sector(r["lat"], r["lon"]), axis=1).mode()[0]),
        "top_carrier": top_carrier,
        "top_carrier_count": top_carrier_count,
        "top_global_airframe": top_frame,
        "top_frame_count": top_frame_count
    }
    supabase.table("aerotrack_stats").insert(stats_payload).execute()

if __name__ == "__main__": process_hourly_sweep()
