from flask import Flask, request, jsonify, send_file
import os
import shutil
import time
from multiprocessing import Process
from threading import Thread
from flask_cors import CORS

# Import your analysis scripts
import Influx_LX70
import Influx_LXS
import Influx_NDuro
import Influx_NDuro_NoGPS

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access

UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

analysis_status = {}  # Store the status of running processes

def compress_folder(folder_path, output_zip):
    """Compresses a folder into a zip file."""
    shutil.make_archive(output_zip, 'zip', folder_path)

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files or 'scriptName' not in request.form:
            return jsonify({'status': 'error', 'message': 'Missing zip file or scriptName'}), 400

        uploaded_file = request.files['file']
        script_name = request.form['scriptName']

        zip_path = os.path.join(UPLOAD_FOLDER, uploaded_file.filename)
        uploaded_file.save(zip_path)

        extract_folder = os.path.join(UPLOAD_FOLDER, uploaded_file.filename.replace(".zip", ""))
        shutil.unpack_archive(zip_path, extract_folder)
        os.remove(zip_path)  # Remove original zip after extraction

        script_functions = {
            "Influx_LX70": Influx_LX70.Influx_LX70_input,
            "Influx_LXS": Influx_LXS.Influx_LXS_input,
            "Influx_NDuro": Influx_NDuro.Influx_NDuro_input,
            "Influx_NDuro_NoGPS": Influx_NDuro_NoGPS.Influx_NDuro_NoGPS_input
        }

        if script_name not in script_functions:
            return jsonify({'status': 'error', 'message': 'Invalid script name'}), 400

        analysis_status[extract_folder] = "Processing"

        def run_script(script_func, folder_path, folder_name):
            """Runs the script and updates status."""
            try:
                script_func(folder_path)
                analysis_status[folder_name] = "Completed"

                output_zip_path = os.path.join(PROCESSED_FOLDER, f"{folder_name}.zip")
                compress_folder(folder_path, output_zip_path.replace(".zip", ""))
                analysis_status[folder_name] = f"Ready for Download: {output_zip_path}"
            except Exception as e:
                analysis_status[folder_name] = f"Error: {str(e)}"
            finally:
                time.sleep(10)
                shutil.rmtree(folder_path, ignore_errors=True)

        thread = Thread(target=run_script, args=(script_functions[script_name], extract_folder, uploaded_file.filename.replace(".zip", "")))
        thread.start()

        return jsonify({'status': 'success', 'message': 'Processing started', 'folderName': uploaded_file.filename.replace(".zip", "")}), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/analysis-status/<folder_name>', methods=['GET'])
def get_analysis_status(folder_name):
    return jsonify({'status': analysis_status.get(folder_name, 'Processing')})

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    file_path = os.path.join(PROCESSED_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({'status': 'error', 'message': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
