import os
import requests
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone


AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not all([AIRLABS_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    print("ERROR: Missing target environment variable infrastructure.")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CARGO_CARRIERS = {
    "FX", "FDX", "5X", "UPS", "5Y", "GTI", "PO", "PAC", "K4", "CKS",
    "CV", "CLX", "3S", "BOX", "RU", "ABW", "D0", "BCS", "ABR", "GEC",
    "SQC", "CK", "CKK", "KZ", "NCA", "MP", "MPH", "QT", "TAY", "LD", "AHK"
}


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_airspace_sector(lat, lon):
    if 35 <= lat <= 70 and -15 <= lon <= 45:
        return "EUROPE"
    if 25 <= lat <= 60 and -130 <= lon <= -60:
        return "NORTH AMERICA"
    if 0 <= lat <= 50 and 100 <= lon <= 150:
        return "EAST ASIA & APAC"
    if 10 <= lat <= 35 and 35 <= lon <= 85:
        return "MIDDLE EAST & S. ASIA"
    if -50 <= lat <= 15 and -80 <= lon <= -35:
        return "LATIN AMERICA"
    if 15 <= lat <= 60 and -60 <= lon <= -15:
        return "NORTH ATLANTIC"
    if -50 <= lat <= 10 and 10 <= lon <= 50:
        return "AFRICA"
    if -45 <= lat <= -10 and 110 <= lon <= 160:
        return "OCEANIA"
    return "TRANSOCEANIC"


def classify_airframe_taxonomy(icao_code):
    code = str(icao_code).upper().strip()

    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N", "A332", "A333", "A338", "A339", "A359", "A35K", "A300", "A306", "A310", "A343", "A346", "A388", "BCS1", "BCS3"]:
        manufacturer = "Airbus"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM", "B772", "B773", "B77W", "B77L", "B778", "B779", "B788", "B789", "B78X", "B744", "B748", "B762", "B763", "B764", "B712", "B752", "B753", "MD11", "MD82", "MD83", "MD88", "DC10"]:
        manufacturer = "Boeing"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "E135", "E145", "E35L", "E55P", "E50P", "E550"]:
        manufacturer = "Embraer"
    elif code in ["CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "CL30", "CL35", "CL60", "GLEX", "GL5T", "GL7T"]:
        manufacturer = "Bombardier / MHI"
    elif code in ["AT43", "AT72", "AT42", "AT75", "AT76"]:
        manufacturer = "ATR"
    elif code in ["C919", "ARJ2"]:
        manufacturer = "COMAC"
    else:
        manufacturer = "Other"

    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N"]:
        family = "Airbus A320 Family"
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM"]:
        family = "Boeing 737 Family"
    elif code in ["A332", "A333", "A338", "A339"]:
        family = "Airbus A330 Family"
    elif code in ["B772", "B773", "B77W", "B77L", "B778", "B779"]:
        family = "Boeing 777 Family"
    elif code in ["B788", "B789", "B78X"]:
        family = "Boeing 787 Family"
    elif code in ["A359", "A35K"]:
        family = "Airbus A350 Family"
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "BCS1", "BCS3", "AT43", "AT72", "AT75", "AT76"]:
        family = "Regional Jet / Turboprop"
    elif code in ["B744", "B748", "B762", "B763", "B764", "MD11", "A300", "A306", "A310"]:
        family = "Dedicated Widebody / Freighter"
    elif code in ["GLEX", "GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "FA7X", "FA8X", "C750", "C680", "E55P", "LJ60", "LJ75", "PC24"]:
        family = "Business Jets"
    else:
        family = "Other / Unclassified"

    if family in ["Airbus A320 Family", "Boeing 737 Family"]:
        body_type = "Narrowbody"
    elif family in ["Airbus A330 Family", "Boeing 777 Family", "Boeing 787 Family", "Airbus A350 Family", "Dedicated Widebody / Freighter"]:
        body_type = "Widebody"
    elif family == "Regional Jet / Turboprop":
        body_type = "Regional"
    elif family == "Business Jets":
        body_type = "Business Jet"
    else:
        body_type = "Other"

    if code in ["A20N", "A21N", "A19N", "B38M", "B39M", "B3XM", "A338", "A339", "B788", "B789", "B78X", "A359", "A35K", "E290", "E295", "BCS1", "BCS3", "C919"]:
        generation = "Next-Gen"
    else:
        generation = "Legacy"

    return pd.Series([manufacturer, family, body_type, generation])


def process_hourly_sweep():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Executing Commercial Fleet & Market Sweep...")

    tactical_grid = {}
    try:
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={AIRLABS_API_KEY}", timeout=20)
        if res.status_code == 200:
            for ac in res.json().get("response", []):
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None:
                    continue

                tactical_grid[hex_code] = {
                    "icao24": hex_code,
                    "latitude": safe_float(ac.get("lat")),
                    "longitude": safe_float(ac.get("lng")),
                    "baro_altitude": safe_float(ac.get("alt")) * 3.28084,
                    "velocity": safe_float(ac.get("speed")),
                    "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip(),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(),
                    "departure_iata": str(ac.get("dep_iata", "UNKN")).upper().strip(),
                }
        else:
            print(f"AirLabs HTTP {res.status_code}")
    except Exception as e:
        print(f"AirLabs connection failed: {e}")

    df = pd.DataFrame(list(tactical_grid.values()))
    if df.empty:
        print("No commercial telemetry returned; skipping insert.")
        return

    df = df.drop_duplicates(subset=["icao24"]).reset_index(drop=True)
    df["sector"] = df.apply(lambda r: get_airspace_sector(r["latitude"], r["longitude"]), axis=1)
    df[["Manufacturer", "Family", "Body_Type", "Generation"]] = df["aircraft_type"].apply(classify_airframe_taxonomy)
    df["is_cargo"] = df["airline_code"].isin(CARGO_CARRIERS) | (df["Family"] == "Dedicated Widebody / Freighter")

    valid_airports = df[~df["departure_iata"].isin(["UNKN", ""])]
    busiest_airport = str(valid_airports["departure_iata"].mode()[0]).upper() if not valid_airports.empty else "ATL"
    busiest_region = str(df["sector"].mode()[0]) if not df.empty else "NORTH AMERICA"

    clean_airlines = df[~df["airline_code"].isin(["UNKN", ""])]
    top_carrier = str(clean_airlines["airline_code"].mode()[0]) if not clean_airlines.empty else "UNKN"
    top_carrier_count = int(clean_airlines["airline_code"].value_counts().max()) if not clean_airlines.empty else 0

    clean_frames = df[~df["aircraft_type"].isin(["UNKN", ""])]
    top_frame = str(clean_frames["aircraft_type"].mode()[0]) if not clean_frames.empty else "UNKN"
    top_frame_count = int(clean_frames["aircraft_type"].value_counts().max()) if not clean_frames.empty else 0

    total_global_tracks = len(df)
    regional_payload = {}

    for sector_name, sector_df in df.groupby("sector"):
        sec_tracks = len(sector_df)
        deployment_share = round((sec_tracks / total_global_tracks) * 100, 2) if total_global_tracks > 0 else 0.0

        carrier_counts = sector_df[~sector_df["airline_code"].isin(["UNKN", ""])]["airline_code"].value_counts()
        if not carrier_counts.empty:
            c_props = carrier_counts / carrier_counts.sum()
            hhi = round(float(sum(c_props ** 2) * 10000), 1)
            if hhi > 2500:
                conc_status = "Highly Concentrated"
            elif hhi > 1500:
                conc_status = "Moderately Concentrated"
            else:
                conc_status = "Competitive"
            top_c = str(carrier_counts.index[0])
            top_c_cnt = int(carrier_counts.iloc[0])
        else:
            hhi, conc_status, top_c, top_c_cnt = 0.0, "Charter / Unscheduled", "UNKN", 0

        sec_clean_frames = sector_df[~sector_df["aircraft_type"].isin(["UNKN", ""])]
        top_f = str(sec_clean_frames["aircraft_type"].mode()[0]) if not sec_clean_frames.empty else "UNKN"
        top_f_cnt = int(sec_clean_frames["aircraft_type"].value_counts().max()) if not sec_clean_frames.empty else 0

        sec_clean_fams = sector_df[sector_df["Family"] != "Other / Unclassified"]
        top_fam = str(sec_clean_fams["Family"].mode()[0]) if not sec_clean_fams.empty else "UNKN"
        top_fam_cnt = int(sec_clean_fams["Family"].value_counts().max()) if not sec_clean_fams.empty else 0

        regional_payload[sector_name] = {
            "total_aircraft": sec_tracks,
            "deployment_share_pct": deployment_share,
            "hhi_index": hhi,
            "concentration_status": conc_status,
            "top_carrier": top_c,
            "top_carrier_count": top_c_cnt,
            "top_airframe": top_f,
            "top_airframe_count": top_f_cnt,
            "top_family": top_fam,
            "top_family_count": top_fam_cnt,
            "nextgen_pct": round(float((sector_df["Generation"] == "Next-Gen").mean() * 100), 1),
        }

    # Backwards-compatible metadata inside JSONB for historical fleet growth & index sparklines
    regional_payload["__meta_airlines"] = {
        str(k): int(v) for k, v in clean_airlines["airline_code"].value_counts().head(45).items()
    }
    regional_payload["__meta_body_types"] = {
        str(k): int(v) for k, v in df["Body_Type"].value_counts().items()
    }
    regional_payload["__meta_oems"] = {
        str(k): int(v) for k, v in df["Manufacturer"].value_counts().items()
    }
    regional_payload["__meta_cargo_count"] = int(df["is_cargo"].sum())
    regional_payload["__meta_nextgen_pct"] = round(float((df["Generation"] == "Next-Gen").mean() * 100), 1)

    # Preserves existing Supabase table columns while zeroing legacy threat/military fields
    stats_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_flights": total_global_tracks,
        "threat_count": 0,
        "military_count": 0,
        "busiest_airport": busiest_airport,
        "busiest_region": busiest_region,
        "top_carrier": top_carrier,
        "top_carrier_count": top_carrier_count,
        "top_frame": top_frame,
        "top_frame_count": top_frame_count,
        "regional_breakdown": regional_payload,
    }

    try:
        supabase.table("aerotrack_stats").insert(stats_payload).execute()
        print(f"LOG COMPLETE: {total_global_tracks} commercial tracks & market matrix synchronized.")
    except Exception as e:
        print(f"Database Write Rejection: {e}")


if __name__ == "__main__":
    process_hourly_sweep()
