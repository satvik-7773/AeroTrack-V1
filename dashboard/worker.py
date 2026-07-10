import os
import requests
import json
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone

# =====================================================================
# SYSTEM INITIALIZATION
# =====================================================================
AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not all([AIRLABS_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    print("❌ ERROR: Missing target environment variable infrastructure.")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def safe_float(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default

def get_airspace_sector(lat, lon):
    if 35 <= lat <= 70 and -15 <= lon <= 45: return "EUROPEAN AIRSPACE"
    if 25 <= lat <= 60 and -130 <= lon <= -60: return "NORTH AMERICAN SECTOR"
    if 0 <= lat <= 50 and 100 <= lon <= 150: return "EAST ASIAN SECTOR"
    if 10 <= lat <= 35 and 35 <= lon <= 85: return "MIDDLE EAST / S. ASIA"
    if -50 <= lat <= 15 and -80 <= lon <= -35: return "SOUTH AMERICAN SECTOR"
    if 15 <= lat <= 60 and -60 <= lon <= -15: return "NORTH ATLANTIC TRACKS"
    if -50 <= lat <= 10 and 10 <= lon <= 50: return "AFRICAN AIRSPACE"
    if -45 <= lat <= -10 and 110 <= lon <= 160: return "OCEANIC / AUSTRALASIA"
    return "INTERNATIONAL WATERS"

# =====================================================================
# STRATEGIC ASSET AGGREGATION ENGINE
# =====================================================================
def process_hourly_sweep():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Launching Synchronized Intel Aggregator...")
    
    tactical_grid = {}
    military_watchlist = set()

    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack-Worker/1.0"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if hex_code: military_watchlist.add(hex_code)
    except Exception: pass

    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("response", []):
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                if hex_code in military_watchlist or str(ac.get("airline_iata")).upper() == "MIL": continue

                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "latitude": float(ac.get("lat") or 0),
                    "longitude": float(ac.get("lng") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(),
                    "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip(),
                    "departure_iata": str(ac.get("dep_iata", "UNKN")).upper().strip()
                }
    except Exception as e:
        print(f"❌ API INGESTION ERROR: {e}")
        return

    df = pd.DataFrame(list(tactical_grid.values()))
    if df.empty: return

    df["sector"] = df.apply(lambda r: get_airspace_sector(r["latitude"], r["longitude"]), axis=1)

    # 🛑 Strict Filtering for clean mode calculations
    clean_airlines = df[~df["airline_code"].isin(["UNKN", "", "NONE", "NULL", "N/A"])]
    clean_frames = df[~df["aircraft_type"].isin(["UNKN", "", "NONE", "NULL", "N/A"])]
    clean_airports = df[~df["departure_iata"].isin(["UNKN", "", "NONE", "NULL", "N/A"])]

    top_global_carrier = str(clean_airlines["airline_code"].mode()[0]) if not clean_airlines.empty else "UNKN"
    top_global_airframe = str(clean_frames["aircraft_type"].mode()[0]) if not clean_frames.empty else "UNKN"
    busiest_airport = str(clean_airports["departure_iata"].mode()[0]) if not clean_airports.empty else "DFW"
    busiest_region = str(df["sector"].mode()[0]) if not df["sector"].empty else "NORTH AMERICAN SECTOR"

    regional_intel = {}
    for sector_name, group in df.groupby("sector"):
        sec_airlines = group[~group["airline_code"].isin(["UNKN", "", "NONE", "NULL", "N/A"])]
        sec_frames = group[~group["aircraft_type"].isin(["UNKN", "", "NONE", "NULL", "N/A"])]
        
        regional_intel[sector_name] = {
            "top_carrier": str(sec_airlines["airline_code"].mode()[0]) if not sec_airlines.empty else "UNKN",
            "top_airframe": str(sec_frames["aircraft_type"].mode()[0]) if not sec_frames.empty else "UNKN"
        }

    stats_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_flights": len(df),
        "threat_count": 0,  
        "military_count": len(military_watchlist),
        "busiest_airport": busiest_airport,
        "busiest_region": busiest_region,
        "top_global_carrier": top_global_carrier,
        "top_global_airframe": top_global_airframe,
        "intelligence_payload": regional_intel
    }

    try:
        response = supabase.table("aerotrack_stats").insert(stats_payload).execute()
        print("🎉 SUCCESS: Sync complete. Supabase accepted the payload.")
    except Exception as e:
        print(f"❌ SUPABASE WRITER ERROR (Check your columns!): {e}")

if __name__ == "__main__":
    process_hourly_sweep()
