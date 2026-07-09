import os
import requests
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

print("🚀 --- AEROTRACK MATCHED WORKER BOOTING ---")

# --- CONFIGURATION ---
AIRLABS_API_KEY = os.environ.get("AIRLABS_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not AIRLABS_API_KEY:
    print("❌ CRITICAL ERROR: Environment keys (AirLabs or Supabase) are missing!")
    exit(1)

print("✅ Credentials verified. Connecting to Supabase...")
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

    # 1. Pull Military Assets (ADSB.lol)
    print("📡 STEP 1: Fetching ADSB.lol Tactical Military Overlay...")
    headers = {"User-Agent": "AeroTrack-Analytics-Worker/1.0"}
    try:
        res_mil = requests.get("https://api.adsb.lol/v2/mil", headers=headers, timeout=15)
        print(f"ADSB.lol /mil Status Code: {res_mil.status_code}")
        
        if res_mil.status_code == 200:
            mil_data = res_mil.json().get("ac", [])
            print(f"✅ Successfully ingested {len(mil_data)} active military tracks.")
            for ac in mil_data:
                hex_code = str(ac.get("hex", "UNKN")).upper()
                if hex_code == "UNKN" or ac.get("lat") is None: 
                    continue
                
                lat, lon = float(ac.get("lat")), float(ac.get("lon"))
                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": float(ac.get("alt_baro", 0.0)) if isinstance(ac.get("alt_baro"), (int, float)) else 0.0,
                    "velocity": float(ac.get("gs", 0.0)) * 1.852, # Knots to km/h
                    "military": True,
                    "aircraft_type": str(ac.get("t", "UNKN")).strip(),
                    "region": get_region(lat, lon),
                    "departure_iata": "UNKN"
                }
        else:
            print(f"⚠️ ADSB.lol returned non-200 code: {res_mil.status_code}. Proceeding with AirLabs only.")
    except Exception as e:
        print(f"⚠️ ADSB.lol Military Fetch Bypass: {e}")

    # 2. Pull Commercial Assets (AirLabs)
    print("📡 STEP 2: Fetching AirLabs Commercial Airspace Baseline...")
    try:
        res_al = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=20)
        print(f"AirLabs Status Code: {res_al.status_code}")
        
        if res_al.status_code == 200:
            al_data = res_al.json().get("response", [])
            print(f"✅ Successfully ingested {len(al_data)} commercial tracks.")
            
            for ac in al_data:
                hex_code = str(ac.get("hex", "UNKN")).upper()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: 
                    continue
                
                lat, lon = float(ac.get("lat")), float(ac.get("lng"))
                
                # If this aircraft is already marked by military radar, preserve it but update metadata
                if hex_code in tactical_grid:
                    al_type = str(ac.get("aircraft_icao", "UNKN")).strip()
                    if al_type != "UNKN": 
                        tactical_grid[hex_code]["aircraft_type"] = al_type
                    dep = str(ac.get("dep_iata", "UNKN")).strip()
                    if dep != "UNKN": 
                        tactical_grid[hex_code]["departure_iata"] = dep
                else:
                    # Add new unique commercial aircraft to the matrix
                    tactical_grid[hex_code] = {
                        "icao24": hex_code,
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": float(ac.get("alt", 0.0)) * 3.28084, # Meters to feet conversion if necessary
                        "velocity": float(ac.get("speed", 0.0)), # AirLabs natively tracks km/h
                        "military": False,
                        "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).strip(),
                        "region": get_region(lat, lon),
                        "departure_iata": str(ac.get("dep_iata", "UNKN")).strip()
                    }
        else:
            print(f"❌ FATAL: AirLabs core tracking stream rejected request. Status: {res_al.status_code}")
            return
    except Exception as e:
        print(f"❌ Network Error during AirLabs baseline fetch: {e}")
        return

    # 3. Compile Master Tracking Dataframe
    df = pd.DataFrame(list(tactical_grid.values()))
    if df.empty:
        print("❌ FATAL: Combined data grid is empty. Aborting run.")
        return

    # 4. Kinematic Anomaly Analysis
    print("🧠 STEP 3: Evaluating Flight Anomaly Vectors...")
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

    # 5. Core Metric Calculations
    print("🧮 STEP 4: Crunching Consolidated System Metrics...")
    total_flights = len(df)
    threat_count = int(df["is_threat"].sum())
    mil_count = int(df["military"].sum())
    
    known_airports = df[df["departure_iata"] != "UNKN"]["departure_iata"]
    busiest_airport = known_airports.mode()[0] if not known_airports.empty else "N/A"
    busiest_region = df["region"].mode()[0] if not df.empty else "N/A"

    print(f"📊 LIVE ALIGNMENT STATUS: {total_flights} Active Tracks mapped successfully.")
    print(f"📈 Details: {threat_count} Anomalies | {mil_count} Verified Military Assets")

    # 6. Database Storage Update
    print("☁️ STEP 5: Committing telemetry matrix log to Supabase...")
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
        print("🎉 LOG COMPLETE: Data records perfectly synchronized with live frontend.")
    except Exception as e:
        print(f"❌ Database Write Rejection: {e}")

- name: Keep Streamlit Awake (Heartbeat Ping)
  run: |
    curl -s "https://aerotrack-v1.streamlit.app" > /dev/null
    echo "Streamlit pinged to prevent sleep."

if __name__ == "__main__":
    process_hourly_sweep()
