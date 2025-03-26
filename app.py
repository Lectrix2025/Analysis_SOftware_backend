from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
from multiprocessing import Process
import multiprocessing
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

UPLOAD_FOLDER = os.path.abspath("uploaded_folders")  # Ensures folder is stored locally
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Creates the folder if not exists

def run_script(script_func, path):
    """Runs the given script function with the provided path."""
    try:
        script_func(path)
        print(f"✅ {script_func.__name__} completed successfully.")
    except Exception as e:
        print(f"❌ Error in {script_func.__name__}: {e}")

@app.route('/upload-folder', methods=['POST'])
def upload_folder():
    """Handles folder uploads from the frontend."""
    if 'folder' not in request.files:
        return jsonify({'status': 'error', 'message': 'No folder part in the request.'}), 400

    folder = request.files.getlist('folder')
    folder_name = request.form.get('folderName')

    if not folder_name:
        return jsonify({'status': 'error', 'message': 'Missing folder name.'}), 400

    folder_path = os.path.join(UPLOAD_FOLDER, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    for file in folder:
        file_path = os.path.join(folder_path, file.filename)
        file.save(file_path)

    print(f"✅ Folder '{folder_name}' uploaded successfully.")
    return jsonify({'status': 'success', 'message': f'Folder "{folder_name}" uploaded!', 'folderPath': folder_path}), 200

@app.route('/run-analysis', methods=['POST'])
def run_analysis():
    """Handles API requests to execute specific analysis scripts."""
    try:
        data = request.json
        folder_path = data.get('folderPath')
        destination_folder = data.get('destinationFolder')
        script_name = data.get('scriptName')
        copy_folder_option = data.get('copyFolder', False)

        if not folder_path or not script_name:
            return jsonify({'status': 'error', 'message': 'Missing required fields: folderPath or scriptName.'}), 400

        print(f"📢 Running {script_name} on folder: {folder_path}")

        # Optional folder copying logic
        if copy_folder_option and destination_folder:
            try:
                destination_folder_path = os.path.join(destination_folder, os.path.basename(folder_path))
                shutil.copytree(folder_path, destination_folder_path)
                new_path = destination_folder_path
                print(f"✅ Folder copied to {destination_folder_path}.")
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Error copying folder: {e}'}), 500
        else:
            new_path = folder_path

        # Mapping script names to corresponding functions
        script_functions = {
            "Influx_LX70": Influx_LX70.Influx_LX70_input,
            "Influx_LXS": Influx_LXS.Influx_LXS_input,
            "Influx_NDuro": Influx_NDuro.Influx_NDuro_input,
            "Influx_NDuro_NoGPS": Influx_NDuro_NoGPS.Influx_NDuro_NoGPS_input
        }

        if script_name not in script_functions:
            return jsonify({'status': 'error', 'message': 'Invalid script name.'}), 400

        # Running script in a separate process
        process = Process(target=run_script, args=(script_functions[script_name], new_path))
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
    multiprocessing.set_start_method('spawn', force=True)

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
