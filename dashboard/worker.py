import os
import requests
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# --- CONFIGURATION ---
AIRLABS_API_KEY = os.environ.get("AIRLABS_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_region(lat, lon):
    """Categorizes coordinates into global operational theaters."""
    if 15 <= lat <= 75 and -170 <= lon <= -50: return "North America"
    elif -60 <= lat < 15 and -90 <= lon <= -30: return "South America / LATAM"
    elif 35 <= lat <= 75 and -10 <= lon <= 45: return "Europe"
    elif 45 <= lat <= 75 and 45 < lon <= 180: return "Russia"
    elif 10 <= lat < 40 and 35 <= lon <= 60: return "Middle East"
    elif 5 <= lat < 35 and 65 <= lon <= 90: return "India"
    elif -10 <= lat < 25 and 90 < lon <= 140: return "Southeast Asia"
    elif -50 <= lat < -10 and 110 <= lon <= 180: return "Oceania"
    else: return "Oceanic / Uncategorized"

def process_hourly_sweep():
    tactical_grid = {}

    # 1. Pull Unrestricted ADSB.lol
    try:
        res = requests.get("https://api.adsb.lol/v2/all", headers={"User-Agent": "AeroTrack-Worker"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "UNKN")).upper()
                if hex_code == "UNKN" or ac.get("lat") is None: continue
                
                lat, lon = float(ac.get("lat")), float(ac.get("lon"))
                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": float(ac.get("alt_baro", 0.0)) if isinstance(ac.get("alt_baro"), (int, float)) else 0.0,
                    "velocity": float(ac.get("gs", 0.0)) * 1.852,
                    "military": True if ac.get("mil", False) else False,
                    "aircraft_type": str(ac.get("t", "UNKN")).strip(),
                    "region": get_region(lat, lon),
                    "departure_iata": "UNKN"
                }
    except Exception as e:
        print(f"ADSB Error: {e}")

    # 2. Merge AirLabs Metadata
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("response", []):
                hex_code = str(ac.get("hex", "UNKN")).upper()
                if hex_code in tactical_grid:
                    al_type = str(ac.get("aircraft_icao", "UNKN")).strip()
                    if al_type != "UNKN": tactical_grid[hex_code]["aircraft_type"] = al_type
                    
                    dep = str(ac.get("dep_iata", "UNKN")).strip()
                    if dep != "UNKN": tactical_grid[hex_code]["departure_iata"] = dep
    except Exception as e:
        print(f"AirLabs Error: {e}")

    df = pd.DataFrame(list(tactical_grid.values()))
    if df.empty:
        return

    # 3. KINEMATICS & THREAT DETECTION
    df["is_threat"] = False
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "FA7X"]
    
    for idx, row in df.iterrows():
        try:
            vel, alt = row["velocity"], row["altitude"]
            if (alt < 15000 and vel > 850) or \
               (alt > (51000 if row["aircraft_type"] in biz_jets else 44000)) or \
               (vel > 1250) or (vel > 1050 and alt < 28000) or row["military"]:
                df.at[idx, "is_threat"] = True
        except:
            pass

    # 4. AGGREGATE THE INTELLIGENCE
    total_flights = len(df)
    threat_count = int(df["is_threat"].sum())
    mil_count = int(df["military"].sum())
    
    # Calculate Busiest Airport (Excluding UNKN)
    known_airports = df[df["departure_iata"] != "UNKN"]["departure_iata"]
    busiest_airport = known_airports.mode()[0] if not known_airports.empty else "N/A"
    
    # Calculate Busiest Region
    busiest_region = df["region"].mode()[0] if not df.empty else "N/A"

    # 5. PUSH SUMMARY TO SUPABASE
    stats_payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_flights": total_flights,
        "threat_count": threat_count,
        "military_count": mil_count,
        "busiest_airport": busiest_airport,
        "busiest_region": busiest_region
    }
    
    supabase.table("aerotrack_stats").insert(stats_payload).execute()
    
    # (Optional) You can still push the individual threat rows to your aerotrack_logs table here 
    # to maintain the "sightings" feature without filling up your database with all 15k commercial flights.

if __name__ == "__main__":
    process_hourly_sweep()
