import os
import requests
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

print("🚀 --- AEROTRACK HOURLY WORKER BOOTING ---")

# --- CONFIGURATION ---
AIRLABS_API_KEY = os.environ.get("AIRLABS_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ CRITICAL ERROR: Supabase Keys are missing from GitHub Environment!")
    exit(1)

print("✅ Credentials loaded. Connecting to Supabase...")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_region(lat, lon):
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

    # 1. Pull Tactical Data from OpenSky Network
    print("📡 STEP 1: Requesting Tactical Global Feed (OpenSky)...")
    try:
        res = requests.get("https://opensky-network.org/api/states/all", timeout=20)
        print(f"OpenSky Status Code: {res.status_code}")
        
        if res.status_code == 200:
            data = res.json().get("states", [])
            print(f"✅ Successfully downloaded {len(data)} raw aircraft records.")
            for ac in data:
                # OpenSky format: [icao24, callsign, origin_country, time_pos, last_contact, lon, lat, baro_alt, on_ground, velocity, true_track, vertical_rate]
                hex_code = str(ac[0]).upper() if ac[0] else "UNKN"
                lon = ac[5]
                lat = ac[6]
                
                if hex_code == "UNKN" or lat is None or lon is None: 
                    continue
                
                velocity_ms = float(ac[9]) if ac[9] is not None else 0.0
                altitude_m = float(ac[7]) if ac[7] is not None else 0.0
                
                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "altitude": altitude_m * 3.28084, # Convert meters to feet
                    "velocity": velocity_ms * 3.6, # Convert m/s to km/h
                    "military": False, # OpenSky doesn't tag military, we rely on kinematics
                    "aircraft_type": "UNKN",
                    "region": get_region(float(lat), float(lon)),
                    "departure_iata": "UNKN"
                }
            print(f"✅ Parsed {len(tactical_grid)} valid positional tracks.")
        else:
            print("❌ FATAL: OpenSky feed blocked or unavailable.")
            return
            
    except Exception as e:
        print(f"❌ Network Error during Tactical Fetch: {e}")
        return

    # 2. Merge AirLabs Metadata
    print("📡 STEP 2: Requesting AirLabs Intelligence Overlay...")
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=15)
        print(f"AirLabs Status Code: {res.status_code}")
        if res.status_code == 200:
            al_data = res.json().get("response", [])
            print(f"✅ Successfully downloaded {len(al_data)} civilian records.")
            matches = 0
            for ac in al_data:
                hex_code = str(ac.get("hex", "UNKN")).upper()
                if hex_code in tactical_grid:
                    matches += 1
                    al_type = str(ac.get("aircraft_icao", "UNKN")).strip()
                    if al_type != "UNKN": tactical_grid[hex_code]["aircraft_type"] = al_type
                    dep = str(ac.get("dep_iata", "UNKN")).strip()
                    if dep != "UNKN": tactical_grid[hex_code]["departure_iata"] = dep
            print(f"✅ Successfully merged AirLabs data into {matches} active tracks.")
    except Exception as e:
        print(f"⚠️ AirLabs Fetch Error (Continuing without metadata): {e}")

    # 3. Process Dataframe
    df = pd.DataFrame(list(tactical_grid.values()))
    if df.empty:
        print("❌ FATAL: DataFrame is empty. Aborting Supabase upload.")
        return

    print("🧠 STEP 3: Executing Kinematic Threat Detection...")
    df["is_threat"] = False
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "CL30", "CL60", "FA7X"]
    
    for idx, row in df.iterrows():
        try:
            vel, alt = row["velocity"], row["altitude"]
            # Kinematic flags for anomalies (low alt/high speed or ceiling breaches)
            if (alt < 15000 and vel > 850) or \
               (alt > (51000 if row["aircraft_type"] in biz_jets else 44000)) or \
               (vel > 1250) or (vel > 1050 and alt < 28000):
                df.at[idx, "is_threat"] = True
        except:
            pass

    # 4. Math & Aggregation
    print("🧮 STEP 4: Aggregating Global Statistics...")
    total_flights = len(df)
    threat_count = int(df["is_threat"].sum())
    mil_count = int(df["military"].sum())
    
    known_airports = df[df["departure_iata"] != "UNKN"]["departure_iata"]
    busiest_airport = known_airports.mode()[0] if not known_airports.empty else "N/A"
    busiest_region = df["region"].mode()[0] if not df.empty else "N/A"

    print(f"📊 SUMMARY: {total_flights} Flights | {threat_count} Threats | {mil_count} Military")
    print(f"📍 Busiest Region: {busiest_region} | 🛫 Busiest Airport: {busiest_airport}")

    # 5. Supabase Upload
    print("☁️ STEP 5: Pushing payload to Supabase...")
    stats_payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_flights": total_flights,
        "threat_count": threat_count,
        "military_count": mil_count,
        "busiest_airport": busiest_airport,
        "busiest_region": busiest_region
    }
    
    try:
        response = supabase.table("aerotrack_stats").insert(stats_payload).execute()
        print("🎉 SUCCESS! Data safely written to Supabase.")
    except Exception as e:
        print(f"❌ FATAL: Supabase rejected the insert command. Error: {e}")

if __name__ == "__main__":
    process_hourly_sweep()
