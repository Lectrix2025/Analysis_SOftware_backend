import multiprocessing
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import shutil
import zipfile
from multiprocessing import Process
import asyncio
import websockets

# Importing external scripts
import Influx_LX70
import Influx_LXS
import Influx_NDuro
import Influx_NDuro_NoGPS

# --------------------- Flask Setup ---------------------
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

UPLOAD_FOLDER = os.path.abspath("uploaded_folders")
PROCESSED_FOLDER = os.path.abspath("processed_folders")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def run_script(script_func, input_folder, output_folder):
    """Runs the given script function with the provided path."""
    try:
        os.makedirs(output_folder, exist_ok=True)
        script_func(input_folder, output_folder)
        print(f"✅ {script_func.__name__} completed successfully.")
    except Exception as e:
        print(f"❌ Error in {script_func.__name__}: {e}")

def compress_folder(folder_path, output_zip_path):
    """Compresses a folder into a ZIP file."""
    try:
        shutil.make_archive(output_zip_path.replace('.zip', ''), 'zip', folder_path)
        print(f"✅ Folder compressed successfully: {output_zip_path}")
        return output_zip_path
    except Exception as e:
        print(f"❌ Failed to compress folder: {e}")
        return None

@app.route('/run-analysis', methods=['POST'])
def run_analysis():
    """Handles API requests to execute specific analysis scripts."""
    try:
        if 'file' not in request.files or 'scriptName' not in request.form:
            return jsonify({'status': 'error', 'message': 'Missing zip file or scriptName'}), 400

        uploaded_file = request.files['file']
        script_name = request.form['scriptName']

        # Save ZIP file
        zip_path = os.path.join(UPLOAD_FOLDER, uploaded_file.filename)
        uploaded_file.save(zip_path)

        # Extract ZIP
        extract_folder = os.path.join(UPLOAD_FOLDER, uploaded_file.filename.replace(".zip", ""))
        os.makedirs(extract_folder, exist_ok=True)
        shutil.unpack_archive(zip_path, extract_folder)

        # Output folder for processed data
        output_folder = os.path.join(PROCESSED_FOLDER, uploaded_file.filename.replace(".zip", ""))
        os.makedirs(output_folder, exist_ok=True)

        # Run selected script
        script_functions = {
            "Influx_LX70": Influx_LX70.Influx_LX70_input,
            "Influx_LXS": Influx_LXS.Influx_LXS_input,
            "Influx_NDuro": Influx_NDuro.Influx_NDuro_input,
            "Influx_NDuro_NoGPS": Influx_NDuro_NoGPS.Influx_NDuro_NoGPS_input
        }

        if script_name not in script_functions:
            return jsonify({'status': 'error', 'message': 'Invalid script name.'}), 400

        process = Process(target=run_script, args=(script_functions[script_name], extract_folder, output_folder))
        process.start()
        process.join()

        # Compress processed folder
        output_zip_path = os.path.join(PROCESSED_FOLDER, f"{uploaded_file.filename.replace('.zip', '_processed.zip')}")
        compressed_zip = compress_folder(output_folder, output_zip_path)

        if compressed_zip:
            return send_file(compressed_zip, as_attachment=True)

        return jsonify({'status': 'error', 'message': 'Failed to compress processed data'}), 500

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

# --------------------- WebSocket Setup ---------------------
connected_clients = set()

async def websocket_handler(websocket, path):
    """Handles WebSocket connections and messages."""
    print(f"🔗 New WebSocket connection from {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            print(f"📩 Received message: {message}")
            response = f"Server received: {message}"
            await websocket.send(response)
    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 Client disconnected: {websocket.remote_address}")
    finally:
        connected_clients.remove(websocket)

async def start_websocket_server():
    """Starts WebSocket server."""
    server = await websockets.serve(websocket_handler, "0.0.0.0", 5001)
    print("✅ WebSocket server running at ws://0.0.0.0:5001")
    await server.wait_closed()

# --------------------- Running Flask & WebSocket in Parallel ---------------------
def start_flask():
    """Starts the Flask app."""
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)

def start_websocket():
    """Starts the WebSocket server."""
    asyncio.run(start_websocket_server())

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')

    flask_process = Process(target=start_flask)
    websocket_process = Process(target=start_websocket)

    flask_process.start()
    websocket_process.start()

    try:
        flask_process.join()
        websocket_process.join()
    except KeyboardInterrupt:
        print("🛑 Stopping servers...")
        flask_process.terminate()
        websocket_process.terminate()
        flask_process.join()
        websocket_process.join()