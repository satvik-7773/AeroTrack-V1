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
    if 35 <= lat <= 70 and -15 <= lon <= 45: return "EUROPEAN ZONE"
    if 25 <= lat <= 60 and -130 <= lon <= -60: return "NORTH AMERICAN ZONE"
    if 0 <= lat <= 50 and 100 <= lon <= 150: return "EAST ASIAN ZONE"
    if 10 <= lat <= 35 and 35 <= lon <= 85: return "MIDDLE EAST / S. ASIA ZONE"
    if -50 <= lat <= 15 and -80 <= lon <= -35: return "SOUTH AMERICAN ZONE"
    if 15 <= lat <= 60 and -60 <= lon <= -15: return "NORTH ATLANTIC ZONE"
    if -50 <= lat <= 10 and 10 <= lon <= 50: return "AFRICAN ZONE"
    if -45 <= lat <= -10 and 110 <= lon <= 160: return "OCEANIC / AUSTRALASIA ZONE"
    return "INTERNATIONAL WATERS"

# =====================================================================
# ENGINE 1: TAXONOMY & CLASSIFICATION MAPPINGS
# =====================================================================
def classify_airframe_taxonomy(icao_code):
    code = str(icao_code).upper().strip()
    
    # 1. Family Classification
    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N"]: family = "Airbus A320 Family"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM"]: family = "Boeing 737 Family"
    elif code in ["A332", "A333", "A338", "A339"]: family = "Airbus A330 Family"
    elif code in ["B772", "B773", "B77W", "B77L", "B778", "B779"]: family = "Boeing 777 Family"
    elif code in ["B788", "B789", "B78X"]: family = "Boeing 787 Family"
    elif code in ["A359", "A35K"]: family = "Airbus A350 Family"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "BCS1", "BCS3", "AT43", "AT72"]: family = "Regional Aircraft"
    elif code in ["B744", "B748", "B762", "B763", "B764", "MD11", "A300", "A310"]: family = "Legacy Widebody / Cargo"
    elif code in ["GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "FA7X", "FA8X", "C750", "C680", "E55P", "LJ60", "LJ75", "PC24"]: family = "Business Jets"
    else: family = "Other / Unclassified"

    # 2. Body Type Classification
    if family in ["Airbus A320 Family", "Boeing 737 Family"]: body_type = "Narrowbody"
    elif family in ["Airbus A330 Family", "Boeing 777 Family", "Boeing 787 Family", "Airbus A350 Family", "Legacy Widebody / Cargo"]: body_type = "Widebody"
    elif family == "Regional Aircraft": body_type = "Regional"
    elif family == "Business Jets": body_type = "Business Jet"
    else: body_type = "Other"

    # 3. Generation Classification
    if code in ["A20N", "A21N", "A19N", "B38M", "B39M", "B3XM", "A338", "A339", "B788", "B789", "B78X", "A359", "A35K", "E290", "E295", "BCS1", "BCS3"]:
        generation = "Next-Gen"
    else:
        generation = "Legacy"

    return pd.Series([family, body_type, generation])

# =====================================================================
# SYNCHRONIZED TACTICAL SWEEP ENGINE
# =====================================================================
def process_hourly_sweep():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Executing Global Tactical Sweep...")
    
    tactical_grid = {}
    military_watchlist = {}
    military_tracks = []
    
    fallback_mil_icaos = {"AFX", "RRR", "CNV", "CFC", "GAF", "RFF", "ASY", "FCE", "AME", "IAM", "BAF", "NAF", "SVF", "SUI", "PLF", "ROF", "HAF", "TUAF", "MMF"}

    # 1. ADSB.LOL MILITARY
    try:
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack-Worker/1.2"}, timeout=15)
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
        elif res.status_code == 429:
            print("⚠️ ADSB.lol API Rate Limit (429) hit. Relying on AirLabs fallback classifier.")
    except Exception as e: 
        print(f"⚠️ ADSB.lol API connection failed: {e}")

    # 2. AIRLABS COMMERCIAL
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=15)
        if res.status_code == 200:
            for ac in res.json().get("response", []):
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                
                airline_icao = str(ac.get("airline_icao", "UNKN")).upper().strip()
                is_mil = (hex_code in military_watchlist) or (airline_icao in fallback_mil_icaos)
                
                tactical_grid[hex_code] = {
                    "icao24": hex_code, "military": is_mil,
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084, "velocity": float(ac.get("speed") or 0),
                    "airline": str(ac.get("airline_iata", "UNKN")).upper().strip(),   
                    "airframe": str(ac.get("aircraft_icao", "UNKN")).upper().strip(), 
                    "dep": str(ac.get("dep_iata", "UNKN")).upper().strip()
                }
                
                if is_mil and hex_code in military_watchlist:
                    tactical_grid[hex_code]["airframe"] = military_watchlist[hex_code].get("aircraft_type", "UNKN")
    except Exception: pass

    # 3. CONSOLIDATE AND CLEAN
    df_comm = pd.DataFrame(list(tactical_grid.values()))
    if df_comm.empty: return
    
    df_comm = df_comm.drop_duplicates(subset=["icao24"])
    df_comm = df_comm.rename(columns={"airline": "airline_code", "airframe": "aircraft_type", "dep": "departure_iata"})
    
    if military_tracks:
        mil_df = pd.DataFrame(military_tracks).drop_duplicates(subset=["icao24"])
        new_mil_tracks = mil_df[~mil_df["icao24"].isin(df_comm["icao24"])]
        df = pd.concat([df_comm, new_mil_tracks], axis=0, ignore_index=True)
    else:
        df = df_comm

    # 4. DERIVE METRICS & TAXONOMY
    if "Classification" not in df.columns: df["Classification"] = "CIVILIAN"
    else: df["Classification"] = df["Classification"].fillna("CIVILIAN")

    df["Threat_Reason"] = ""
    df["sector"] = df.apply(lambda r: get_airspace_sector(r["latitude"], r["longitude"]), axis=1)
    
    # Apply Taxonomy Engine (#2, #3, #8, #9)
    df[["Family", "Body_Type", "Generation"]] = df["aircraft_type"].apply(classify_airframe_taxonomy)
    
    # 5. KINEMATIC THRESHOLDS
    biz_jets = ["GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "GL5T", "GL7T", "G280", "G150", "CL30", "CL35", "CL60", "CRJ2", "F900", "F9EX", "FA7X", "FA8X", "F2TH", "C750", "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C", "E55P", "E50P", "E550", "E135", "E35L", "LJ60", "LJ75", "LJ70", "LJ45", "LJ40", "LJ35", "HDJT", "PC24"]
   
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

    # 6. GLOBAL MACRO AGGREGATES
    valid_airports = df[(df["departure_iata"].str.upper() != "UNKN") & (df["departure_iata"] != "")]
    busiest_airport = str(valid_airports["departure_iata"].mode()[0]).upper() if not valid_airports.empty else "DFW"
    busiest_region = str(df["sector"].mode()[0]) if not df["sector"].empty else "NORTH ATLANTIC TRACKS"
    
    clean_airlines = df[~df["airline_code"].isin(["UNKN", "", "MIL"])]
    top_carrier = str(clean_airlines["airline_code"].mode()[0]) if not clean_airlines.empty else "UNKN"
    top_carrier_count = int(clean_airlines["airline_code"].value_counts().max()) if not clean_airlines.empty else 0
    
    clean_frames = df[~df["aircraft_type"].isin(["UNKN", ""])]
    top_frame = str(clean_frames["aircraft_type"].mode()[0]) if not clean_frames.empty else "UNKN"
    top_frame_count = int(clean_frames["aircraft_type"].value_counts().max()) if not clean_frames.empty else 0

    # 7. ENRICHED REGIONAL GEOFENCING MATRIX (#1, #5, #13, #14)
    total_global_tracks = len(df)
    regional_payload = {}
    
    for sector_name, sector_df in df.groupby("sector"):
        sec_tracks = len(sector_df)
        deployment_share = round((sec_tracks / total_global_tracks) * 100, 2) if total_global_tracks > 0 else 0.0
        
        # Herfindahl-Hirschman Index - Operator Concentration (#14)
        carrier_counts = sector_df[~sector_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts()
        if not carrier_counts.empty:
            c_props = carrier_counts / carrier_counts.sum()
            hhi = round(float(sum(c_props ** 2) * 10000), 1)
            if hhi > 2500: conc_status = "Highly Concentrated"
            elif hhi > 1500: conc_status = "Moderately Concentrated"
            else: conc_status = "Highly Competitive"
            top_c = str(carrier_counts.index[0])
            top_c_cnt = int(carrier_counts.iloc[0])
        else:
            hhi = 0.0
            conc_status = "N/A (Charter/Mil)"
            top_c = "UNKN"
            top_c_cnt = 0

        # Dominant Airframes & Families (#5, #13)
        sec_clean_frames = sector_df[~sector_df["aircraft_type"].isin(["UNKN", ""])]
        top_f = str(sec_clean_frames["aircraft_type"].mode()[0]) if not sec_clean_frames.empty else "UNKN"
        top_f_cnt = int(sec_clean_frames["aircraft_type"].value_counts().max()) if not sec_clean_frames.empty else 0

        sec_clean_fams = sector_df[~sector_df["Family"].isin(["Other / Unclassified"])]
        top_fam = str(sec_clean_fams["Family"].mode()[0]) if not sec_clean_fams.empty else "UNKN"
        top_fam_cnt = int(sec_clean_fams["Family"].value_counts().max()) if not sec_clean_fams.empty else 0
        
        regional_payload[sector_name] = {
            "total_aircraft": sec_tracks,
            "deployment_share_pct": deployment_share,    # #1
            "hhi_index": hhi,                            # #14
            "concentration_status": conc_status,         # #14
            "top_carrier": top_c,
            "top_carrier_count": top_c_cnt,
            "top_airframe": top_f,
            "top_airframe_count": top_f_cnt,
            "top_family": top_fam,                       # #5 / #13
            "top_family_count": top_fam_cnt
        }

    # 8. FINAL PAYLOAD ASSEMBLY
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
        "top_frame_count": top_frame_count,
        "regional_breakdown": regional_payload           # Stores enriched analytical dict as JSONB
    }

    try:
        supabase.table("aerotrack_stats").insert(stats_payload).execute()
        print("🎉 LOG COMPLETE: Tactical data & Enriched Regional Matrix synchronized.")
    except Exception as e:
        print(f"❌ Database Write Rejection: {e}")

if __name__ == "__main__":
    process_hourly_sweep()
