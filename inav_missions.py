from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import pandas as pd
import math
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

app = Flask(__name__)
app.secret_key = "edgetx_inav_mission_secret_key"

# --- GEOGRAPHIC & GEOMETRIC CALCULATIONS ---

def haversine(lat1, lon1, lat2, lon2):
    """Calculates distance between two points in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculates the bearing between two points in degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def process_logs(df, base_spacing_m, max_wps, manual_alt_m=None, manual_speed_cms=None):
    """Processes logs with adaptive spacing based on turn rate."""
    df.columns = [str(c).strip() for c in df.columns]

    current_base_spacing = base_spacing_m

    while True:
        waypoints = []
        last_wp_pos = None
        last_bearing = None

        for _, row in df.iterrows():
            try:
                # 1. Parse GPS
                gps_raw = str(row.get('GPS', '')).strip()
                if not gps_raw or gps_raw.lower() in ['0', '0 0', 'nan']: continue
                coords = gps_raw.split()
                if len(coords) < 2: continue
                lat, lon = float(coords[0]), float(coords[1])

                if lat == 0 and lon == 0: continue

                # 2. Get Telemetry Data
                alt_m = manual_alt_m if manual_alt_m is not None else float(row.get('Alt(m)', 0))
                if manual_speed_cms is not None:
                    speed_cms = manual_speed_cms
                else:
                    speed_cms = int(float(row.get('GSpd(kmh)', 0)) * 100000 / 3600)

                # 3. Dynamic Spacing Logic
                if last_wp_pos is None:
                    waypoints.append((lat, lon, alt_m, speed_cms))
                    last_wp_pos = (lat, lon)
                    continue

                dist = haversine(last_wp_pos[0], last_wp_pos[1], lat, lon)
                current_bearing = calculate_bearing(last_wp_pos[0], last_wp_pos[1], lat, lon)

                # Determine Adaptive Spacing:
                # If we have a previous bearing, check the turn angle
                target_spacing = current_base_spacing
                if last_bearing is not None:
                    turn_angle = abs((current_bearing - last_bearing + 180) % 360 - 180)
                    
                    # If turning more than 10 degrees, tighten spacing
                    # Factor reduces spacing down to 30% of base for very sharp turns
                    if turn_angle > 10:
                        reduction_factor = max(0.3, 1.0 - (turn_angle / 90.0))
                        target_spacing = current_base_spacing * reduction_factor

                if dist >= target_spacing:
                    waypoints.append((lat, lon, alt_m, speed_cms))
                    last_wp_pos = (lat, lon)
                    last_bearing = current_bearing

            except: continue

        if not waypoints: return []

        # If mission fits limit, return; else increase base spacing and retry
        if len(waypoints) <= max_wps or current_base_spacing > 5000:
            return waypoints
        current_base_spacing += 10

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    timestamp = datetime.now().strftime("%y%m%d_%H%M")
    initial_default_name = f"mission_{timestamp}"

    if request.method == 'POST':
        file = request.files.get('file')
        if not file: return redirect(url_for('index'))

        mission_name = request.form.get('mission_name', '').strip() or initial_default_name
        unit_system = request.form.get('unit_system', 'metric')

        try:
            # Parse inputs
            raw_alt = request.form.get('custom_alt', '').strip()
            raw_speed = request.form.get('cruise_speed', '').strip()
            raw_spacing = int(request.form.get('spacing', '100'))
            user_max_wps = int(request.form.get('max_wps', '60'))

            manual_alt_m = float(raw_alt) if raw_alt else None
            if manual_alt_m and unit_system == 'imperial': manual_alt_m *= 0.3048

            manual_speed_cms = None
            if raw_speed:
                conv = 44.704 if unit_system == 'imperial' else (100000/3600)
                manual_speed_cms = int(float(raw_speed) * conv)

            spacing_m = raw_spacing * 0.3048 if unit_system == 'imperial' else raw_spacing

            df = pd.read_csv(file, low_memory=False)
            wps = process_logs(df, spacing_m, user_max_wps, manual_alt_m, manual_speed_cms)

            if not wps:
                flash("Error: No valid GPS data found.")
                return redirect(url_for('index'))

            # --- XML GENERATION ---
            root = ET.Element("mission")
            ET.SubElement(root, "mwp", {"save-date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "generator": "EdgeTX-Adaptive-v1"})

            for i, (lat, lon, alt, speed) in enumerate(wps, start=1):
                flag = "165" if i == len(wps) else "0"
                ET.SubElement(root, "missionitem", {
                    "no": str(i), "action": "WAYPOINT",
                    "lat": f"{lat:.7f}", "lon": f"{lon:.7f}",
                    "alt": str(int(round(alt))), # Altitude in Meters for XML
                    "parameter1": str(int(speed)), # Speed in CM/S
                    "parameter2": "0", "parameter3": "0", "flag": flag
                })

            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
            mem_file = io.BytesIO(xml_str.encode('utf-8'))
            return send_file(mem_file, as_attachment=True, download_name=f"{mission_name}.mission", mimetype="application/xml")

        except Exception as e:
            flash(f"Error: {str(e)}")
            return redirect(url_for('index'))

    return render_template('inav_missions.html', default_name=initial_default_name)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5800, debug=False)
