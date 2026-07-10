import os
import requests
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
# SYNCHRONIZED TACTICAL SWEEP ENGINE
# =====================================================================
def process_hourly_sweep():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Executing Global Tactical Sweep...")
    
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []

    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack-Worker/1.0"}, timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("ac", []):
                hex_code = str(ac.get("hex", "")).upper().strip()
                if not hex_code: continue
                military_watchlist[hex_code] = {"aircraft_type": str(ac.get("t", "")).strip()}
                military_tracks.append({
                    "icao24": hex_code, "military": True, "Classification": "MILITARY",
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")), "velocity": safe_float(ac.get("gs")) * 1.852,
                    "aircraft_type": str(ac.get("t", ""))
                })
    except Exception: pass

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
                    "airframe": str(ac.get("aircraft_icao", "UNKN")).upper().strip(), 
                    "airline": str(ac.get("airline_iata", "UNKN")).upper().strip(),   
                    "dep": str(ac.get("dep_iata", "UNKN")).upper().strip())
                }
                
                if hex_code in military_watchlist:
                    tactical_grid[hex_code].update({"military": True, "aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN")})
    except Exception: pass

    df = pd.DataFrame(list(tactical_grid.values()))
    df = df.rename(columns={
        "airline": "airline_code", 
        "airframe": "aircraft_type",
        "dep": "departure_iata"
    })
    mil_df = pd.DataFrame(military_tracks)
    if not mil_df.empty: df = pd.concat([df, mil_df[~mil_df["icao24"].isin(df["icao24"])]], ignore_index=True)
    if df.empty: return

    if "Classification" not in df.columns: df["Classification"] = "CIVILIAN"
    else: df["Classification"] = df["Classification"].fillna("CIVILIAN")

    df["Threat_Reason"] = ""
    df["sector"] = df.apply(lambda r: get_airspace_sector(r["latitude"], r["longitude"]), axis=1)
    
    biz_jets = [
        "GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "GL5T", "GL7T", "G280", "G150", 
        "CL30", "CL35", "CL60", "CRJ2", "F900", "F9EX", "FA7X", "FA8X", "F2TH", 
        "C750", "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C", 
        "E55P", "E50P", "E550", "E135", "E35L", "LJ60", "LJ75", "LJ70", "LJ45", "LJ40", "LJ35", "HDJT", "PC24"
    ]
   
    for idx, row in df.iterrows():
        try:
            vel, alt, ac_type, is_mil = float(row.get("velocity", 0.0)), float(row.get("baro_altitude", 0.0)), str(row.get("aircraft_type", "")).upper(), row.get("military", False)
            reasons = []
            
            if (alt < 15000 and vel > 850): reasons.append("LOW-ALT/HI-VEL")
            if (alt > (49000 if ac_type in biz_jets else 45000)): reasons.append("CEILING-BREACH")
            if (vel > 1250) or (vel > 1050 and alt < 28000): reasons.append("OVER-SPEED")
            if (alt > 30000 and vel < 20): reasons.append("TELEMETRY ANOMALY")

            if reasons: 
                df.at[idx, "Threat_Reason"] = " | ".join(reasons)
                df.at[idx, "Classification"] = "ANOMALY" 
            elif is_mil: 
                df.at[idx, "Classification"] = "MILITARY"
        except Exception: pass

    # Aggregates (Standard Old Schema)
    valid_airports = df[(df["departure_iata"].str.upper() != "UNKN") & (df["departure_iata"] != "")]
    busiest_airport = str(valid_airports["departure_iata"].mode()[0]).upper() if not valid_airports.empty else "DFW"
    busiest_region = str(df["sector"].mode()[0]) if not df["sector"].empty else "NORTH ATLANTIC TRACKS"
    clean_airlines = df[~df["airline_code"].isin(["UNKN", ""])]
    top_carrier = str(clean_airlines["airline_code"].mode()[0]) if not clean_airlines.empty else "UNKN"
    top_carrier_count = int(clean_airlines["airline_code"].value_counts().max()) if not clean_airlines.empty else 0
    
    clean_frames = df[~df["aircraft_type"].isin(["UNKN", ""])]
    top_frame = str(clean_frames["aircraft_type"].mode()[0]) if not clean_frames.empty else "UNKN"
    top_frame_count = int(clean_frames["aircraft_type"].value_counts().max()) if not clean_frames.empty else 0

    stats_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_flights": len(df),
        "threat_count": len(df[df["Classification"] == "ANOMALY"]),
        "military_count": len(df[df["military"] == True]),
        "busiest_airport": busiest_airport,
        "busiest_region": busiest_region,
        "top_carrier": top_carrier,
        "top_carrier_count": top_carrier_count,
        "top_frame": top_frame,
        "top_frame_count": top_frame_count
    }

    

    try:
        supabase.table("aerotrack_stats").insert(stats_payload).execute()
        print("🎉 LOG COMPLETE: Tactical data synchronized.")
    except Exception as e:
        print(f"❌ Database Write Rejection: {e}")

if __name__ == "__main__":
    process_hourly_sweep()
