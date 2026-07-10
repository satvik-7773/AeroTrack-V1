import os
import requests
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone

# =====================================================================
# INITIALIZATION
# =====================================================================
AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not all([AIRLABS_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    print("❌ ERROR: Missing Environment Variables.")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def safe_float(value, default=0.0):
    try: return float(value)
    except (TypeError, ValueError): return default

# =====================================================================
# SYNCHRONIZED HOURLY SWEEP ENGINE
# =====================================================================
def process_hourly_sweep():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Executing Global Background Sweep...")
    
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []

    # 1. FETCH ADSB.LOL MILITARY
    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack-Worker/1.0"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code: continue
                military_watchlist[hex_code] = {"callsign": str(ac.get("flight", "")).strip(), "aircraft_type": str(ac.get("t", "")).strip()}
                military_tracks.append({
                    "icao24": hex_code, "military": True, "Classification": "MILITARY",
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")), "velocity": safe_float(ac.get("gs")) * 1.852,
                    "aircraft_type": str(ac.get("t", ""))
                })
    except Exception as e:
        print(f"Warning: ADSB pull failed: {e}")

    # 2. FETCH AIRLABS
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("response", []):
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                
                tactical_grid[hex_code] = {
                    "icao24": hex_code, "military": False,
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084, "velocity": float(ac.get("speed") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN"))
                }
                
                if hex_code in military_watchlist:
                    tactical_grid[hex_code].update({"military": True, "aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN")})
    except Exception as e:
        print(f"Warning: AirLabs pull failed: {e}")

    # 3. DATAFRAME BUILD
    df = pd.DataFrame(list(tactical_grid.values()))
    mil_df = pd.DataFrame(military_tracks)
    if not mil_df.empty: df = pd.concat([df, mil_df[~mil_df["icao24"].isin(df["icao24"])]], ignore_index=True)
    
    if df.empty:
        print("❌ ERROR: Empty DataFrame. Aborting stats calculation.")
        return

    if "Classification" not in df.columns: df["Classification"] = "CIVILIAN"
    else: df["Classification"] = df["Classification"].fillna("CIVILIAN")

    df["Threat_Reason"] = ""
    
    # EXACT SAME WHITELIST AS FRONTEND
    biz_jets = [
        "GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "GL5T", "GL7T", "G280", "G150", 
        "CL30", "CL35", "CL60", "CRJ2", "F900", "F9EX", "FA7X", "FA8X", "F2TH", 
        "C750", "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C", 
        "E55P", "E50P", "E550", "E135", "E35L", "LJ60", "LJ75", "LJ70", "LJ45", "LJ40", "LJ35", "HDJT", "PC24"
    ]
   
    # 4. SYNCHRONIZED KINEMATICS LOOP
    for idx, row in df.iterrows():
        try:
            vel = float(row.get("velocity", 0.0))
            alt = float(row.get("baro_altitude", 0.0))
            ac_type = str(row.get("aircraft_type", "")).upper()
            is_mil = row.get("military", False)
            reasons = []
            
            # ABSOLUTE THRESHOLDS (45k / 49k)
            if (alt < 15000 and vel > 850): reasons.append("LOW-ALT/HI-VEL")
            if (alt > (49000 if ac_type in biz_jets else 45000)): reasons.append("CEILING-BREACH")
            if (vel > 1250) or (vel > 1050 and alt < 28000): reasons.append("OVER-SPEED")
            if (alt > 30000 and vel < 20): reasons.append("TELEMETRY ANOMALY")

            # THE HIERARCHY FIX
            if reasons: 
                df.at[idx, "Threat_Reason"] = " | ".join(reasons)
                df.at[idx, "Classification"] = "ANOMALY" 
            elif is_mil: 
                df.at[idx, "Classification"] = "MILITARY"
                  
        except Exception: pass

   # 5. CALCULATE AGGREGATES & GEOSPATIAL CLUSTERS
    total_flights = len(df)
    threat_count = len(df[df["Classification"] == "ANOMALY"])
    mil_count = len(df[df["military"] == True])
    
    # Extract the highest recurring destination airport from the current flight grid
    if "departure_iata" in df.columns and not df["departure_iata"].empty:
        # Filter out missing/malformed entries and grab the top occurrence
        valid_airports = df[df["departure_iata"].str.upper() != "UNKN"]["departure_iata"]
        busiest_airport = str(valid_airports.mode()[0]).upper() if not valid_airports.empty else "DFW"
    else:
        busiest_airport = "DFW" # System fallback seed

    # Compute a rough geographical sector based on coordinate rounding
    if "latitude" in df.columns and "longitude" in df.columns:
        # Round coordinates to map flights to rough 600-mile regional grid grids
        df["lat_zone"] = df["latitude"].round(-1).astype(str)
        df["lon_zone"] = df["longitude"].round(-1).astype(str)
        df["grid_sector"] = "LAT: " + df["lat_zone"] + " / LON: " + df["lon_zone"]
        
        # Pull the highest density sector zone
        busiest_region = str(df["grid_sector"].mode()[0]) if not df["grid_sector"].empty else "NORTH ATLANTIC"
    else:
        busiest_region = "NORTH ATLANTIC"
    
    # 6. PUSH TO SUPABASE
    stats_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
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

if __name__ == "__main__":
    process_hourly_sweep()
