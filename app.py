from flask import Flask, request, jsonify
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
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def run_script(script_func, path):
    """Runs the given script function with the provided path."""
    try:
        script_func(path)
        print(f"✅ {script_func.__name__} completed successfully.")
    except Exception as e:
        print(f"❌ Error in {script_func.__name__}: {e}")

@app.route('/upload-folder', methods=['POST'])
def upload_folder():
    """Handles ZIP file uploads, extracts them, and processes."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded.'}), 400

    zip_file = request.files['file']
    folder_name = os.path.splitext(zip_file.filename)[0]  # Remove .zip extension
    folder_path = os.path.join(UPLOAD_FOLDER, folder_name)

    # Save ZIP file temporarily
    zip_path = os.path.join(UPLOAD_FOLDER, zip_file.filename)
    zip_file.save(zip_path)

    # Extract ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(folder_path)
        os.remove(zip_path)  # Remove ZIP after extraction
    except zipfile.BadZipFile:
        return jsonify({'status': 'error', 'message': 'Invalid ZIP file.'}), 400

    print(f"✅ Folder '{folder_name}' extracted successfully.")
    return jsonify({'status': 'success', 'message': f'Folder "{folder_name}" extracted!', 'folderPath': folder_path}), 200

@app.route('/run-analysis', methods=['POST'])
def run_analysis():
    """Executes a selected script on the uploaded folder."""
    try:
        folder_path = request.form.get('folderPath')
        destination_folder = request.form.get('destinationFolder')
        script_name = request.form.get('scriptName')
        copy_folder_option = request.form.get('copyFolder', 'false').lower() == 'true'

        if not folder_path or not script_name:
            return jsonify({'status': 'error', 'message': 'Missing required fields: folderPath or scriptName.'}), 400

        print(f"📢 Running {script_name} on folder: {folder_path}")

        # Optional folder copying logic
        if copy_folder_option and destination_folder:
            destination_folder_path = os.path.join(destination_folder, os.path.basename(folder_path))
            if os.path.exists(destination_folder_path):
                shutil.rmtree(destination_folder_path)  # Remove existing folder before copying
            shutil.copytree(folder_path, destination_folder_path)
            folder_path = destination_folder_path
            print(f"✅ Folder copied to {destination_folder_path}.")

        # Mapping script names to functions
        script_functions = {
            "Influx_LX70": Influx_LX70.Influx_LX70_input,
            "Influx_LXS": Influx_LXS.Influx_LXS_input,
            "Influx_NDuro": Influx_NDuro.Influx_NDuro_input,
            "Influx_NDuro_NoGPS": Influx_NDuro_NoGPS.Influx_NDuro_NoGPS_input
        }

        if script_name not in script_functions:
            return jsonify({'status': 'error', 'message': 'Invalid script name.'}), 400

        # Run the selected script in a separate process
        process = Process(target=run_script, args=(script_functions[script_name], folder_path))
        process.start()

        return jsonify({'status': 'success', 'message': f'{script_name} analysis started successfully!', 'acknowledgement': 'Processing...'}), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Server error: {e}'}), 500

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

    # Creating separate processes for Flask and WebSocket
    flask_process = Process(target=start_flask)
    websocket_process = Process(target=start_websocket)

    # Start both servers
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
