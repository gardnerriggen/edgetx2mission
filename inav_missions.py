from flask import Flask, render_template, request, send_file
import pandas as pd
import math
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

app = Flask(__name__)
app.secret_key = "edgetx_dark_mode_secret"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def process_logs(df, spacing, max_wps, manual_alt=None):
    current_spacing = spacing
    
    while True:
        waypoints = []
        start_pos = None
        last_wp_pos = None
        
        for _, row in df.iterrows():
            try:
                # 1. Parse GPS Column
                gps_str = str(row['GPS']).strip().replace(',', '')
                if not gps_str or gps_str in ['0', '0 0', '0.0 0.0']: 
                    continue
                
                coords = gps_str.split()
                if len(coords) < 2: continue
                
                lat, lon = float(coords[0]), float(coords[1])
                
                # 2. Basic Global Sanity Check (Ignore 0,0 and invalid coords)
                if lat == 0 and lon == 0: continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): continue
                
                # 3. Handle Altitude
                alt = manual_alt if manual_alt is not None else float(row['Alt(m)'])
                
                # 4. Initialize Start Position (First valid GPS lock)
                if start_pos is None:
                    start_pos = (lat, lon)
                    waypoints.append((lat, lon, alt))
                    last_wp_pos = (lat, lon)
                    continue

                # 5. Distance Filtering (Ignore massive sensor jumps > 500km)
                dist_from_start = haversine(start_pos[0], start_pos[1], lat, lon)
                if dist_from_start > 500000: continue
                
                # 6. Waypoint Spacing logic
                if haversine(last_wp_pos[0], last_wp_pos[1], lat, lon) >= current_spacing:
                    waypoints.append((lat, lon, alt))
                    last_wp_pos = (lat, lon)
            except:
                continue
        
        # If no points found at all, break to avoid infinite loop
        if not waypoints:
            return []

        # If we are under the waypoint limit, we are done
        if len(waypoints) <= max_wps or current_spacing > 5000:
            return waypoints

        # Otherwise, increase spacing and try again
        current_spacing += 10

@app.route('/', methods=['GET', 'POST'])
def index():
    timestamp = datetime.now().strftime("%y%m%d_%H%M")
    initial_default_name = f"mission_{timestamp}"

    if request.method == 'POST':
        file = request.files.get('file')
        mission_name = request.form.get('mission_name', '').strip() or initial_default_name
        custom_alt = request.form.get('custom_alt')
        cruise_speed_kmh = float(request.form.get('cruise_speed', '25.0'))
        user_spacing = int(request.form.get('spacing', '100'))
        user_max_wps = int(request.form.get('max_wps', '100'))
        
        if not file: return "No file uploaded"
        
        speed_cms = int(cruise_speed_kmh * 100000 / 3600)
        manual_alt = float(custom_alt) if custom_alt and custom_alt.strip() != "" else None
        
        try:
            df = pd.read_csv(file)
            df.columns = df.columns.str.strip()
            wps = process_logs(df, user_spacing, user_max_wps, manual_alt)

            if not wps:
                return "Error: No valid GPS data found in file. Check that 'GPS' and 'Alt(m)' columns exist and contain data."

            root = ET.Element("mission")
            ET.SubElement(root, "version", value="25.09.13")
            ET.SubElement(root, "mwp", {
                "save-date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-0400"), 
                "generator": "EdgeTX-to-iNAV-Web-Dark"
            })
            
            for i, (lat, lon, alt) in enumerate(wps, start=1):
                ET.SubElement(root, "missionitem", {
                    "no": str(i), "action": "WAYPOINT", "lat": f"{lat:.7f}", "lon": f"{lon:.7f}",
                    "alt": str(int(alt)), "parameter1": str(speed_cms), "parameter2": "0", "parameter3": "1", "flag": "0"
                })

            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
            mem_file = io.BytesIO(xml_str.encode('utf-8'))
            filename = mission_name if mission_name.lower().endswith('.mission') else f"{mission_name}.mission"
            
            return send_file(mem_file, as_attachment=True, download_name=filename, mimetype="application/octet-stream")
        except Exception as e:
            return f"Error processing file: {str(e)}"

    return render_template('inav_missions.html', default_name=initial_default_name)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5800)
