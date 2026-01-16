from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import pandas as pd
import math
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

app = Flask(__name__)
# The secret key is required for Flask's session-based Flash messages
app.secret_key = "edgetx_inav_mission_secret_key"

# --- GEOGRAPHIC CALCULATIONS ---

def haversine(lat1, lon1, lat2, lon2):
    """Calculates distance between two points in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def process_logs(df, spacing_m, max_wps, manual_alt_m=None):
    """Processes the dataframe into a list of waypoints using meters."""
    current_spacing = spacing_m

    while True:
        waypoints = []
        start_pos = None
        last_wp_pos = None

        for _, row in df.iterrows():
            try:
                # Parse GPS column
                gps_str = str(row['GPS']).strip().replace(',', '')
                if not gps_str or gps_str in ['0', '0 0', '0.0 0.0']:
                    continue

                coords = gps_str.split()
                if len(coords) < 2: continue

                lat, lon = float(coords[0]), float(coords[1])

                # Sanity Check: Global Coordinates
                if lat == 0 and lon == 0: continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): continue

                # Altitude handling (Internal logic is always Metric)
                alt = manual_alt_m if manual_alt_m is not None else float(row['Alt(m)'])

                if start_pos is None:
                    start_pos = (lat, lon)
                    waypoints.append((lat, lon, alt))
                    last_wp_pos = (lat, lon)
                    continue

                # Distance filtering: Ignore massive GPS sensor jumps (> 500km)
                if haversine(start_pos[0], start_pos[1], lat, lon) > 500000: continue

                # Waypoint Spacing
                if haversine(last_wp_pos[0], last_wp_pos[1], lat, lon) >= current_spacing:
                    waypoints.append((lat, lon, alt))
                    last_wp_pos = (lat, lon)
            except:
                continue

        if not waypoints:
            return []

        # Automatic spacing adjustment to fit within Waypoint Limit
        if len(waypoints) <= max_wps or current_spacing > 5000:
            return waypoints

        current_spacing += 10

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    # Generate the dynamic timestamp for the mission name
    timestamp = datetime.now().strftime("%y%m%d_%H%M")
    initial_default_name = f"mission_{timestamp}"

    if request.method == 'POST':
        file = request.files.get('file')

        # 1. Basic File Validation
        if not file or file.filename == '':
            flash("No file selected. Please upload an EdgeTX CSV log.")
            return redirect(url_for('index'))

        if not file.filename.lower().endswith('.csv'):
            flash("Invalid file format. Please upload a .csv file.")
            return redirect(url_for('index'))

        mission_name = request.form.get('mission_name', '').strip() or initial_default_name
        unit_system = request.form.get('unit_system', 'metric')

        try:
            raw_alt = request.form.get('custom_alt')
            raw_speed = float(request.form.get('cruise_speed', '25.0'))
            raw_spacing = int(request.form.get('spacing', '100'))
            user_max_wps = int(request.form.get('max_wps', '100'))

            # 2. Unit Conversion to iNAV Native (Meters / cm/s)
            if unit_system == 'imperial':
                # Convert feet to meters
                manual_alt_m = float(raw_alt) * 0.3048 if raw_alt and raw_alt.strip() else None
                spacing_m = raw_spacing * 0.3048
                # MPH to cm/s
                speed_cms = int(raw_speed * 44.704)
            else:
                # Meters stay meters
                manual_alt_m = float(raw_alt) if raw_alt and raw_alt.strip() else None
                spacing_m = raw_spacing
                # km/h to cm/s
                speed_cms = int(raw_speed * 100000 / 3600)

            # 3. Data Processing
            df = pd.read_csv(file)
            df.columns = df.columns.str.strip()

            # Column Validation
            if 'GPS' not in df.columns or 'Alt(m)' not in df.columns:
                flash("Column Error: Could not find 'GPS' or 'Alt(m)' in the CSV file.")
                return redirect(url_for('index'))

            wps = process_logs(df, spacing_m, user_max_wps, manual_alt_m)

            if not wps:
                flash("Processing Error: No valid GPS telemetry found. Ensure your log has a satellite lock.")
                return redirect(url_for('index'))

            # 4. XML Generation (mwp/iNAV format)
            root = ET.Element("mission")
            ET.SubElement(root, "version", value="25.09.13")
            ET.SubElement(root, "mwp", {
                "save-date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-0400"),
                "generator": "EdgeTX-to-iNAV-Web-v2"
            })

            for i, (lat, lon, alt) in enumerate(wps, start=1):
                ET.SubElement(root, "missionitem", {
                    "no": str(i),
                    "action": "WAYPOINT",
                    "lat": f"{lat:.7f}",
                    "lon": f"{lon:.7f}",
                    "alt": str(int(alt)),
                    "parameter1": str(speed_cms),
                    "parameter2": "0",
                    "parameter3": "0",
                    "flag": "0"
                })

            xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")

            # 5. Serve the file in-memory
            mem_file = io.BytesIO(xml_str.encode('utf-8'))
            filename = mission_name if mission_name.lower().endswith('.mission') else f"{mission_name}.mission"

            return send_file(
                mem_file,
                as_attachment=True,
                download_name=filename,
                mimetype="application/octet-stream"
            )

        except Exception as e:
            flash(f"Error Processing File: {str(e)}")
            return redirect(url_for('index'))

    return render_template('inav_missions.html', default_name=initial_default_name)

if __name__ == '__main__':
    # Use 0.0.0.0 for deployment visibility
    app.run(host='0.0.0.0', port=5800, debug=False)
