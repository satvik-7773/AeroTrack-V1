import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
from data_ingestion.client import OpenSkyClient
from supabase import create_client



st.set_page_config(page_title="AeroTrack", layout="wide", initial_sidebar_state="expanded")


SUPABASE_URL = st.secrets["SUPABASE_URL"]

SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)



AIRPORT_MAP = {
    "ATL": "Atlanta", "DFW": "Dallas", "DEN": "Denver", "ORD": "Chicago", "LAX": "Los Angeles", 
    "JFK": "New York", "LHR": "London", "HND": "Tokyo", "CDG": "Paris", "DXB": "Dubai", 
    "DEL": "New Delhi", "BOM": "Mumbai", "FRA": "Frankfurt", "AMS": "Amsterdam", "MAD": "Madrid",
    "SIN": "Singapore", "HKG": "Hong Kong", "SYD": "Sydney", "YYZ": "Toronto", "IST": "Istanbul"
}



st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { padding: 1.5rem 2rem; max-width: 100%; }
    .main { background-color: #000000; color: #e0e0e0; font-family: 'SF Mono', Consolas, monospace; }
    div.stButton > button:first-child {
        background-color: transparent; color: #fff; border: 2px solid #333; 
        border-radius: 0px; font-family: inherit; font-size: 15px; font-weight: bold; height: 45px;
    }
    div.stButton > button:first-child:hover { border-color: #fff; color: #fff; background: rgba(255,255,255,0.1); }
    .stDataFrame { border: none !important; font-size: 15px !important; }
    [data-testid="stSidebar"] { background-color: #0a0a0a; border-right: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)



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



def classify_airframe_taxonomy(icao_code):
    
    code = str(icao_code).upper().strip()
    
    
    if code in ["A318", "A319", "A320", "A321", "A20N", "A21N", "A19N", "A332", "A333", "A338", "A339", "A359", "A35K", "A300", "A310", "A343", "A346", "A388", "BCS1", "BCS3"]:
        manufacturer = "Airbus"
   
    elif code in ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739", "B38M", "B39M", "B3XM", "B772", "B773", "B77W", "B77L", "B778", "B779", "B788", "B789", "B78X", "B744", "B748", "B762", "B763", "B764", "B712", "B752", "B753", "MD11", "MD82", "MD83", "MD88", "DC10"]:
        manufacturer = "Boeing / MD"
    
    elif code in ["E170", "E175", "E190", "E195", "E290", "E295", "E135", "E145", "E35L", "E55P", "E50P", "E550"]:
        manufacturer = "Embraer"
    
    elif code in ["CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "CL30", "CL35", "CL60", "GLEX", "GL5T", "GL7T"]:
        manufacturer = "Bombardier / MHI"
    
    elif code in ["GLF4", "GLF5", "GLF6", "GLF7", "GLF8", "G280", "G150"]:
        manufacturer = "Gulfstream"
    
    elif code in ["C750", "C700", "C680", "C56X", "C560", "C550", "C525", "C510", "C25A", "C25B", "C25C", "C208"]:
        manufacturer = "Cessna / Textron"
    
    elif code in ["F900", "F9EX", "FA7X", "FA8X", "F2TH"]:
        manufacturer = "Dassault"
    
    elif code in ["AT43", "AT72", "AT42"]:
        manufacturer = "ATR"
    
    elif code in ["PC24", "PC12"]:
        manufacturer = "Pilatus"
    
    else:
        manufacturer = "Other / Unclassified"

   
    
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

    
    
    if family in ["Airbus A320 Family", "Boeing 737 Family"]: body_type = "Narrowbody"
    
    elif family in ["Airbus A330 Family", "Boeing 777 Family", "Boeing 787 Family", "Airbus A350 Family", "Legacy Widebody / Cargo"]: body_type = "Widebody"
    
    elif family == "Regional Aircraft": body_type = "Regional"
    
    elif family == "Business Jets": body_type = "Business Jet"
    
    else: body_type = "Other"

    
    
    if code in ["A20N", "A21N", "A19N", "B38M", "B39M", "B3XM", "A338", "A339", "B788", "B789", "B78X", "A359", "A35K", "E290", "E295", "BCS1", "BCS3"]:
        generation = "Next-Gen"
    
    else:
        generation = "Legacy"

    return pd.Series([manufacturer, family, body_type, generation])



try: client = OpenSkyClient()

except Exception: st.stop()



@st.cache_data(ttl=86400) 


def fetch_dynamic_airline_map(api_key):
    try:
        res = requests.get(f"https://airlabs.co/api/v9/airlines?api_key={api_key}", timeout=15)
        if res.status_code == 200:
            return {al.get("iata_code"): al.get("name") for al in res.json().get("response", []) if al.get("iata_code")}
    except Exception: pass
    return {}


@st.cache_data(ttl=15)

def fetch_global_fusion(api_key):
    
    tactical_grid = {}
    
    military_watchlist = {}
    
    military_tracks = []
    
    fallback_mil_icaos = {"AFX", "RRR", "CNV", "CFC", "GAF", "RFF", "ASY", "FCE", "AME", "IAM", "BAF", "NAF", "SVF", "SUI", "PLF", "ROF", "HAF", "TUAF", "MMF"}

    
    try:
        
        res = requests.get("https://api.adsb.lol/v2/mil", headers={"User-Agent": "AeroTrack/1.1"}, timeout=15)
        
        if res.status_code == 200:
            
            for ac in res.json().get("ac", []):
            
                hex_code = str(ac.get("hex", "")).upper().strip()
            
                if not hex_code: continue
            
                military_watchlist[hex_code] = {"aircraft_type": str(ac.get("t", "")).strip()}
            
                military_tracks.append({
                    "icao24": hex_code, "callsign": str(ac.get("flight", "")).strip(), "flight_number": "MIL-OPS",
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lon") or 0),
                    "baro_altitude": safe_float(ac.get("alt_baro")), "velocity": safe_float(ac.get("gs")) * 1.852,
                    "aircraft_type": str(ac.get("t", "")), "airline_code": "MIL", "military": True, "Classification": "MILITARY"
                })
    
    except Exception: pass



    try:
     
        res = requests.get(f"https://airlabs.co/api/v9/flights?api_key={api_key}", timeout=15)
     
        for ac in (res.json().get("response", []) if res.status_code == 200 else []):
     
            try:
     
                hex_code = str(ac.get("hex", "UNKN")).upper().strip()
     
                if hex_code == "UNKN" or ac.get("lat") is None or ac.get("lng") is None: continue
                
     
                airline_icao = str(ac.get("airline_icao", "UNKN")).upper().strip()
     
                is_mil = (hex_code in military_watchlist) or (airline_icao in fallback_mil_icaos)
                
     
                tactical_grid[hex_code] = {
                    "icao24": hex_code, "callsign": str(ac.get("flight_iata", "UNKN")).strip(),
                    "latitude": float(ac.get("lat") or 0), "longitude": float(ac.get("lng") or 0),
                    "baro_altitude": float(ac.get("alt") or 0) * 3.28084, "velocity": float(ac.get("speed") or 0),
                    "aircraft_type": str(ac.get("aircraft_icao", "UNKN")).upper().strip(), "flight_number": str(ac.get("flight_number", "UNKN")), 
                    "airline_code": str(ac.get("airline_iata", "UNKN")).upper().strip(), "military": is_mil, "Classification": "MILITARY" if is_mil else "CIVILIAN"
                }
     
                if is_mil and hex_code in military_watchlist:
     
                    tactical_grid[hex_code].update({"aircraft_type": military_watchlist[hex_code].get("aircraft_type", "UNKN"), "airline_code": "MIL", "flight_number": "MIL-OPS"})
     
     
            except Exception: continue
    
    except Exception: pass

    
    df = pd.DataFrame(list(tactical_grid.values()))
    
    mil_df = pd.DataFrame(military_tracks)
    
    if not mil_df.empty: df = pd.concat([df, mil_df[~mil_df["icao24"].isin(df["icao24"])]], ignore_index=True)
    
    if df.empty: return df

    
    
    if "Classification" not in df.columns: df["Classification"] = "CIVILIAN"
    
    else: df["Classification"] = df["Classification"].fillna("CIVILIAN")

    
    df["Threat_Reason"] = ""
    
    df["sector"] = df.apply(lambda r: get_airspace_sector(r["latitude"], r["longitude"]), axis=1)
    
    
    df[["Manufacturer", "Family", "Body Type", "Generation"]] = df["aircraft_type"].apply(classify_airframe_taxonomy)
    
    
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
    
            elif is_mil: df.at[idx, "Classification"] = "MILITARY"
    
        except Exception: pass

    
    return df


@st.cache_data(ttl=30)

def get_macro_intelligence(_airline_map):

    try:

        res = supabase.table("aerotrack_stats").select("*").order("timestamp", desc=True).limit(24).execute()

        stats_df = pd.DataFrame(res.data)

        if stats_df.empty: return None

        current = stats_df.iloc[0]
        

        avg_flights = stats_df["total_flights"].mean() if len(stats_df) > 1 else current["total_flights"]

        curr_threat_pct = (current["threat_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

        curr_mil_pct = (current["military_count"] / current["total_flights"]) * 100 if current["total_flights"] > 0 else 0

        flight_delta = ((current["total_flights"] - avg_flights) / avg_flights) * 100 if avg_flights > 0 else 0
        

        raw_apt = str(current.get('busiest_airport', 'DFW')).upper()

        apt_txt = f"{raw_apt} ({AIRPORT_MAP.get(raw_apt, 'Intl Hub')})"

        carrier_code = str(current.get('top_carrier', 'UNKN')).upper()

        full_carrier_name = _airline_map.get(carrier_code, carrier_code)
        
        
        
        history_df = stats_df[['timestamp', 'total_flights', 'military_count', 'threat_count']].copy()
        
        history_df['timestamp'] = pd.to_datetime(history_df['timestamp']).dt.strftime('%H:%M')
        
        history_df = history_df.set_index('timestamp').iloc[::-1]
        
        history_df.rename(columns={'total_flights': 'Global Commercial Volume', 'military_count': 'Active Military Assets', 'threat_count': 'Flagged Anomalies'}, inplace=True)



        return {
            "density": f"{int(current.get('total_flights', 0)):,}", "density_delta": f"{flight_delta:+.1f}%",
            "threat_pct": f"{curr_threat_pct:.1f}%", "mil_pct": f"{curr_mil_pct:.1f}%",
            "region": str(current.get('busiest_region', 'NORTH AMERICAN SECTOR')).upper(), "airport": apt_txt,
            "top_carrier": f"{full_carrier_name} ({carrier_code})", "top_carrier_count": int(current.get('top_carrier_count', 0)),
            "top_frame": str(current.get('top_frame', 'UNKN')).upper(), "top_frame_count": int(current.get('top_frame_count', 0)),
            "history_df": history_df
        }
    
    except Exception: return None



dynamic_airline_map = fetch_dynamic_airline_map(client.api_key)

dynamic_airline_map["MIL"] = "Military Asset"


raw_df = fetch_global_fusion(client.api_key)

macro = get_macro_intelligence(dynamic_airline_map)


if not raw_df.empty:
    
    st.sidebar.markdown("<h3 style='color: #00ffcc; letter-spacing: 2px;'>TACTICAL FILTERS</h3>", unsafe_allow_html=True)
    
    class_filter = st.sidebar.radio("ASSET CLASSIFICATION", ["ALL ASSETS", "CIVILIAN ONLY", "MILITARY ONLY", "FLAGGED ANOMALIES"])
    
    
    sector_list = ["GLOBAL (ALL)"] + sorted(list(raw_df["sector"].unique()))
    
    region_filter = st.sidebar.selectbox("GEOGRAPHIC SECTOR", sector_list)
    
    
    min_alt, max_alt = int(raw_df["baro_altitude"].min()), int(raw_df["baro_altitude"].max())
    
    if min_alt == max_alt: max_alt += 1000 
    
    alt_filter = st.sidebar.slider("ALTITUDE ENVELOPE (FT)", min_value=min_alt, max_value=max_alt, value=(min_alt, max_alt), step=1000)
    
    
    st.sidebar.markdown("<hr style='border-color: #333;'>", unsafe_allow_html=True)
    
    if st.sidebar.button("EXECUTE SYSTEM RE-SWEEP", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    
    
    df = raw_df.copy()
    
    if class_filter == "CIVILIAN ONLY": df = df[df["Classification"] == "CIVILIAN"]
    
    elif class_filter == "MILITARY ONLY": df = df[df["Classification"] == "MILITARY/GOV"]
    
    elif class_filter == "FLAGGED ANOMALIES": df = df[df["Classification"] == "ANOMALY"]
    
    if region_filter != "GLOBAL (ALL)": df = df[df["sector"] == region_filter]
    
    df = df[(df["baro_altitude"] >= alt_filter[0]) & (df["baro_altitude"] <= alt_filter[1])]


    
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 10px;">
        <div><div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">SYSTEM</div><div style="font-size: 32px; font-weight: bold; color: #fff;">AEROTRACK</div></div>
        <div><div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">ACTIVE ASSETS</div><div style="font-size: 32px; font-weight: bold; color: #00ffcc;">{len(df):,}</div></div>
        <div><div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">MIL/GOV ASSETS</div><div style="font-size: 32px; font-weight: bold; color: #ffaa00;">{len(df[df['military']==True]):,}</div></div>
        <div><div style="font-size: 14px; color: #666; letter-spacing: 2px; font-weight: bold;">ANOMALOUS ASSETS</div><div style="font-size: 32px; font-weight: bold; color: #ff3333;">{len(df[df['Classification']=='ANOMALY']):,}</div></div>
        <div style="font-size: 14px; color: #555; text-align: right; line-height: 1.5;">SATVIK GOYAL<br>@satvik-7773(Github)</div>
    </div>
    """, unsafe_allow_html=True)

    
    if macro:
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; background-color: rgba(255,255,255,0.03); padding: 10px 20px; border: 1px solid #222; margin-bottom: 15px;">
            <div><span style="color:#666; font-size: 12px;">GLOBAL ASSET DENSITY:</span> <span style="color:#fff; font-size: 16px;">{macro['density']}</span> <span style="color:{'#00ffcc' if float(macro['density_delta'].strip('%')) < 0 else '#ff3333'}; font-size: 12px;">[{macro['density_delta']}]</span></div>
            <div><span style="color:#666; font-size: 12px;">ANOMALY INDEX:</span> <span style="color:#fff; font-size: 16px;">{macro['threat_pct']}</span></div>
            <div><span style="color:#666; font-size: 12px;">MILITARY/GOV INDEX:</span> <span style="color:#fff; font-size: 16px;">{macro['mil_pct']}</span></div>
            <div><span style="color:#666; font-size: 12px;">BUSIEST ZONE</span> <span style="color:#ffaa00; font-size: 16px;">{macro['region']}</span></div>
            <div><span style="color:#666; font-size: 12px;">BUSIEST HUB:</span> <span style="color:#ffaa00; font-size: 16px;">{macro['airport']}</span></div>
        </div>
        """, unsafe_allow_html=True)
        
        
        
        if macro.get("history_df") is not None and not macro["history_df"].empty:
            
            st.markdown("<div style='font-size: 18px; color: #fff; margin-top: 15px; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>24-HOUR GLOBAL FLIGHT & THREAT VOLUME TRENDLINE</div>", unsafe_allow_html=True)
            
            st.line_chart(macro["history_df"], height=250, use_container_width=True)

   
    
    st.markdown("<div style='font-size: 18px; color: #fff; margin-top: 25px; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>GLOBAL MARKET DOMINANCE, OPERATOR & CARGO ANALYTICS</div>", unsafe_allow_html=True)
    
    row1_col1, row1_col2 = st.columns(2)
    
    with row1_col1:
        
        st.markdown("<span style='color:#666; font-size:13px; font-weight:bold;'>TOP 10 AIRLINES GLOBALLY (ACTIVE FLEET COUNT)</span>", unsafe_allow_html=True)
        
        top10_airlines = df[~df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts().head(10)
        
        if not top10_airlines.empty:
        
            top10_airlines.index = top10_airlines.index.map(lambda x: f"{dynamic_airline_map.get(x, x)} ({x})")
        
            st.bar_chart(top10_airlines, color="#00ffcc", height=280)
        
        else: st.info("Insufficient commercial airline data in current filter.")
            
    
    
    with row1_col2:
        
        st.markdown("<span style='color:#666; font-size:13px; font-weight:bold;'>MANUFACTURER MARKET SHARE COMPARISON</span>", unsafe_allow_html=True)
        
        manuf_share = df[df["Manufacturer"] != "Other / Unclassified"]["Manufacturer"].value_counts()
        
        if not manuf_share.empty: st.bar_chart(manuf_share, color="#ffaa00", height=280)
        
        else: st.info("No manufacturer classification data available.")

    
    
    row2_col1, row2_col2 = st.columns(2)
    
    with row2_col1:
    
        st.markdown("<span style='color:#666; font-size:13px; font-weight:bold;'>ACTIVE CARGO OPERATORS</span>", unsafe_allow_html=True)
    
        cargo_codes = ["FX", "FDX", "5X", "UPS", "5Y", "GTI", "PO", "PAC", "K4", "CKS", "CV", "CLX", "3S", "BOX", "RU", "ABW", "D0", "BCS", "ABR", "LH", "GEC", "SQC", "CK", "CKK", "KZ", "NCA", "CI", "CAL", "BR", "EVA", "MP", "MPH", "QT", "TAY", "OOK", "LD", "AHK"]
    
        cargo_df = df[(df["airline_code"].isin(cargo_codes)) | (df["Family"] == "Legacy Widebody / Cargo")]
    
        top_cargo = cargo_df[~cargo_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts().head(10)
    
        if not top_cargo.empty:
    
            top_cargo.index = top_cargo.index.map(lambda x: f"{dynamic_airline_map.get(x, x)} ({x})")
    
            st.bar_chart(top_cargo, color="#ff5500", height=280)
    
        else: st.info("No dedicated cargo operators detected in current filter.")



    with row2_col2:
       
        st.markdown("<span style='color:#666; font-size:13px; font-weight:bold;'>TOP 10 DEPLOYED AIRCRAFT FAMILIES</span>", unsafe_allow_html=True)
       
        top10_fams = df[df["Family"] != "Other / Unclassified"]["Family"].value_counts().head(10)
       
        if not top10_fams.empty: st.bar_chart(top10_fams, color="#0088ff", height=280)
       
        else: st.info("Insufficient airframe family data.")

   
    
    st.markdown("<div style='font-size: 18px; color: #fff; margin-top: 20px; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>ACTIVE AIRCRAFT ASSET FAMILY TREND</div>", unsafe_allow_html=True)
    
    
    available_families = sorted([f for f in raw_df["Family"].unique() if f != "Other / Unclassified"])
    
    selected_family = st.selectbox("SELECT AIRCRAFT ASSET FAMILY", available_families)
    
    
    
    if selected_family:
        
        fam_df = raw_df[raw_df["Family"] == selected_family]
        
        fam_active = len(fam_df)
        
        fam_share = (fam_active / len(raw_df)) * 100 if len(raw_df) > 0 else 0
        
        fam_ops = fam_df[~fam_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].nunique()
        
        top_fam_region = fam_df["sector"].mode()[0] if not fam_df.empty else "N/A"
        
        
        top_op_code = fam_df[~fam_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].mode()[0] if fam_ops > 0 else "UNKN"
        
        top_op_name = dynamic_airline_map.get(top_op_code, top_op_code)
        
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; background-color: rgba(0,255,204,0.05); padding: 15px 20px; border: 1px solid #005544; margin-bottom: 20px;">
            <div><span style="color:#666; font-size: 12px;">ACTIVE ASSETS:</span><br><span style="color:#00ffcc; font-size: 20px; font-weight:bold;">{fam_active:,}</span> <span style="color:#fff; font-size: 14px;">({fam_share:.1f}% Global Share)</span></div>
            <div><span style="color:#666; font-size: 12px;">GLOBAL OPERATORS:</span><br><span style="color:#fff; font-size: 20px; font-weight:bold;">{fam_ops} Airlines</span></div>
            <div><span style="color:#666; font-size: 12px;">DOMINANT REGION:</span><br><span style="color:#ffaa00; font-size: 20px; font-weight:bold;">{top_fam_region}</span></div>
            <div><span style="color:#666; font-size: 12px;">PRIMARY OPERATOR:</span><br><span style="color:#fff; font-size: 20px; font-weight:bold;">{top_op_name} ({top_op_code})</span></div>
        </div>
        """, unsafe_allow_html=True)

  
    
    st.markdown("<div style='font-size: 18px; color: #fff; margin-top: 20px; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>REGIONAL ASSET CONCENTRATION</div>", unsafe_allow_html=True)
    
    
    total_global_tracks = len(raw_df)
    
    regional_data = []
    
    
    
    for sector_name, sector_df in raw_df.groupby("sector"):
    
        sec_tracks = len(sector_df)
    
        fleet_share_idx = (sec_tracks / total_global_tracks) * 100 if total_global_tracks > 0 else 0
        
    
        carrier_counts = sector_df[~sector_df["airline_code"].isin(["UNKN", "", "MIL"])]["airline_code"].value_counts()
    
        if not carrier_counts.empty:
    
            c_props = carrier_counts / carrier_counts.sum()
    
            hhi = sum(c_props ** 2) * 10000
    
            if hhi > 2500: conc_status = "Highly Concentrated"
    
            elif hhi > 1500: conc_status = "Moderately Concentrated"
    
            else: conc_status = "Highly Competitive"
            
            top_c = carrier_counts.index[0]
            
            top_c_str = f"{dynamic_airline_map.get(top_c, top_c)} ({top_c})"
        
        else:
            conc_status = "N/A (Charter/Mil)"
            
            top_c_str = "NONE / CHARTER"

        
        top_fam = sector_df["Family"].mode()[0] if not sector_df.empty else "UNKN"

        regional_data.append({
            "Airspace Sector": sector_name,
            "Active Tracks": sec_tracks,
            "Deployment Share (#1)": f"{fleet_share_idx:.1f}%",
            "Market Concentration (#14)": conc_status,
            "Dominant Carrier": top_c_str,
            "Dominant Family": top_fam
        })

    
    df_regional = pd.DataFrame(regional_data).sort_values(by="Active Tracks", ascending=False)
    
    st.dataframe(df_regional, use_container_width=True, hide_index=True)

   
    st.markdown("<div style='font-size: 18px; color: #fff; margin-top: 25px; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>ACTIVE-ASSET MAP</div>", unsafe_allow_html=True)

    
    def assign_color(cls):
     
        if cls == "ANOMALY": return [255, 51, 51, 220]
     
        elif cls == "MILITARY": return [255, 170, 0, 220]
     
        return [0, 255, 204, 80]

    
    
    df['color'] = df['Classification'].apply(assign_color)
    
    layer = pdk.Layer(
        'ScatterplotLayer', data=df, get_position='[longitude, latitude]',
        get_fill_color='color', get_radius=3500, radius_min_pixels=3, radius_max_pixels=10, pickable=True
    )
   
    st.pydeck_chart(pdk.Deck(
       
        layers=[layer], initial_view_state=pdk.ViewState(latitude=20, longitude=0, zoom=1.4, pitch=0), 
       
        tooltip={"html": "{icao24} | {callsign} | {aircraft_type} -> {Family} ({Generation}) <br> FL{baro_altitude} | {velocity} km/h <br> <span style='color:orange; font-weight:bold;'>{Classification}</span>", "style": {"backgroundColor": "#000", "color": "#fff", "fontFamily": "monospace", "border": "1px solid #333", "fontSize": "13px"}},
       
        map_style="mapbox://styles/mapbox/dark-v11"
    ), use_container_width=True)

   
    st.markdown("<br><div style='font-size: 18px; color: #fff; margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;'>AIRCRAFT INTELLIGENCE LOG</div>", unsafe_allow_html=True)
    
    
    
    display_cols = ["Classification", "icao24", "callsign", "flight_number", "airline_code", "aircraft_type", "Family", "Body_Type", "Generation", "sector", "baro_altitude", "velocity", "Threat_Reason"]
    
    df_full = df[[c for c in display_cols if c in df.columns]].copy()
    
    if "Classification" in df_full.columns:
        df_full["_rank"] = df_full["Classification"].map({"ANOMALY": 0, "MILITARY": 1, "CIVILIAN": 2})
        df_full = df_full.sort_values(by=["_rank", "baro_altitude"], ascending=[True, False]).drop(columns=["_rank"])
    
    
    df_full.rename(columns={
        "Classification": "Status", "icao24": "Hex ID", "callsign": "Callsign", "flight_number": "Flight No.",
        "airline_code": "Carrier", "aircraft_type": "Model Code", "Family": "Airframe Family", "Body_Type": "Body Type", 
        "Generation": "Gen", "sector": "Region", "baro_altitude": "Alt (ft)", "velocity": "Speed (km/h)", "Threat_Reason": "Flags"
    }, inplace=True)
    
    
    if "Carrier" in df_full.columns:
    
        df_full.insert(df_full.columns.get_loc("Carrier") + 1, "Airline Name", df_full["Carrier"].map(dynamic_airline_map).fillna("Unknown / Charter"))
    
    
    st.dataframe(df_full, use_container_width=True, hide_index=True)

else:
    st.error("ERR_NO_DATA: Check tracking configuration parameters or API limits.")
