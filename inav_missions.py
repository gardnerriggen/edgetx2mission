from flask import Flask, render_template, request, send_file
import pandas as pd
import math
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

app = Flask(__name__)
app.secret_key = "edgetx_xml_secret"

# --- CONFIG ---
INITIAL_SPACING = 300
MAX_WAYPOINTS = 100
MAX_DISTANCE_FROM_START_KM = 50
LAT_MIN, LAT_MAX = 24.396308, 49.384358
LON_MIN, LON_MAX = -125.0, -66.93457

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def process_logs(df, spacing, manual_alt=None):
    waypoints = []
    start_pos = None
    last_wp_pos = None
    
    for _, row in df.iterrows():
        try:
            gps_str = str(row['GPS']).strip().replace(',', '')
            if not gps_str or gps_str == '0': continue
            
            coords = gps_str.split()
            lat, lon = float(coords[0]), float(coords[1])
            alt = manual_alt if manual_alt is not None else float(row['Alt(m)'])
            
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX): continue
            
            if start_pos is None:
                start_pos = (lat, lon)
                waypoints.append((lat, lon, alt))
                last_wp_pos = (lat, lon)
                continue

            if haversine(start_pos[0], start_pos[1], lat, lon) > (MAX_DISTANCE_FROM_START_KM * 1000): continue
            if haversine(last_wp_pos[0], last_wp_pos[1], lat, lon) >= spacing:
                waypoints.append((lat, lon, alt))
                last_wp_pos = (lat, lon)
        except: continue
    return waypoints

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('file')
        mission_name = request.form.get('mission_name', 'converted_mission').strip()
        custom_alt = request.form.get('custom_alt')
        cruise_speed_kmh = request.form.get('cruise_speed', '25') # Default 25 km/h
        
        if not file or file.filename == '': return "No file selected"
        
        # Convert km/h to cm/s
        # (km/h * 100000) / 3600
        speed_cms = int(float(cruise_speed_kmh) * 100000 / 3600)
        manual_alt = float(custom_alt) if custom_alt and custom_alt.strip() != "" else None
        
        try:
            df = pd.read_csv(file)
            df.columns = df.columns.str.strip()
            
            spacing = INITIAL_SPACING
            while True:
                wps = process_logs(df, spacing, manual_alt)
                if len(wps) <= MAX_WAYPOINTS: break
                spacing += 50

            root = ET.Element("mission")
            ET.SubElement(root, "version", value="25.09.13")
            
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-0400")
            ET.SubElement(root, "mwp", {"save-date": now, "generator": "EdgeTX-to-iNAV-Converter"})
            
            for i, (lat, lon, alt) in enumerate(wps, start=1):
                ET.SubElement(root, "missionitem", {
                    "no": str(i),
                    "action": "WAYPOINT",
                    "lat": f"{lat:.7f}",
                    "lon": f"{lon:.7f}",
                    "alt": str(int(alt)),
                    "parameter1": str(speed_cms), 
                    "parameter2": "0",
                    "parameter3": "1",
                    "flag": "0"
                })

            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
            mem_file = io.BytesIO()
            mem_file.write(xml_str.encode('utf-8'))
            mem_file.seek(0)
            
            filename = f"{mission_name}.mission" if mission_name else "mission.mission"
            return send_file(mem_file, as_attachment=True, download_name=filename, mimetype="application/xml")
        except Exception as e:
            return f"Error: {str(e)}"

    return render_template('inav-missions.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5800)
