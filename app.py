from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
from multiprocessing import Process
import multiprocessing
import asyncio
import websockets

# Import your existing scripts here
import Influx_LX70
import Influx_LXS
import Influx_NDuro
import Influx_NDuro_NoGPS

# --------------------- Flask Setup ---------------------
app = Flask(__name__)
CORS(app)

def run_script(script_func, path):
    try:
        script_func(path)
        print(f"Process for {script_func.__name__} completed.")
    except Exception as e:
        print(f"Error in process: {e}")

@app.route('/run-analysis', methods=['POST'])
def run_analysis():
    try:
        data = request.json

        folder_path = data.get('folderPath')
        destination_folder = data.get('destinationFolder')
        script_name = data.get('scriptName')
        copy_folder_option = data.get('copyFolder')

        print(f"Received request to run {script_name} on folder {folder_path}")

        if not folder_path or not script_name:
            error_message = 'Missing required fields: folderPath or scriptName.'
            print(f"Validation error: {error_message}")
            return jsonify({
                'status': 'error',
                'message': error_message
            }), 400

        # Optional folder copying logic
        if copy_folder_option and destination_folder:
            try:
                destination_folder_path = os.path.join(destination_folder, os.path.basename(folder_path))
                print(f"Copying folder to {destination_folder_path}...")
                shutil.copytree(folder_path, destination_folder_path)
                new_path = destination_folder_path
                print("Folder copied successfully.")
            except Exception as e:
                error_message = f'Error copying folder: {str(e)}'
                print(error_message)
                return jsonify({
                    'status': 'error',
                    'message': error_message
                }), 500
        else:
            new_path = folder_path

        # Map script names to functions
        script_functions = {
            "Influx_LX70": Influx_LX70.Influx_LX70_input,
            "Influx_LXS": Influx_LXS.Influx_LXS_input,
            "Influx_NDuro": Influx_NDuro.Influx_NDuro_input,
            "Influx_NDuro_NoGPS": Influx_NDuro_NoGPS.Influx_NDuro_NoGPS_input
        }

        if script_name not in script_functions:
            error_message = 'Invalid script name.'
            print(error_message)
            return jsonify({
                'status': 'error',
                'message': error_message
            }), 400

        print(f"Running analysis: {script_name} on {new_path}...")

        # Launch the selected function in a separate process
        process = Process(target=run_script, args=(script_functions[script_name], new_path))
        process.start()


        print(f"{script_name} analysis completed successfully.")

        return jsonify({
            'status': 'success',
            'message': f'{script_name} analysis completed successfully!',
            'acknowledgement': 'Analysis Ready'
        }), 200

    except Exception as e:
        error_message = f'Server error: {str(e)}'
        print(error_message)
        return jsonify({
            'status': 'error',
            'message': error_message
        }), 500

# --------------------- WebSocket Setup ---------------------

connected_clients = set()

async def websocket_handler(websocket, path):
    print(f"New WebSocket connection from {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            print(f"Received message: {message}")
            # Echo back or handle your WebSocket logic here
            response = f"Server received: {message}"
            await websocket.send(response)
    except websockets.exceptions.ConnectionClosed:
        print(f"Client disconnected: {websocket.remote_address}")
    finally:
        connected_clients.remove(websocket)

async def start_websocket_server():
    async with websockets.serve(websocket_handler, "0.0.0.0", 5001):
        print("WebSocket server started on ws://0.0.0.0:5001")
        await asyncio.Future()  # Run forever

# --------------------- Running Flask & WebSocket in Parallel ---------------------

def start_flask():
    app.run(debug=True, port=5000, use_reloader=False)

def start_websocket():
    asyncio.run(start_websocket_server())

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')

    # Create separate processes for Flask and WebSocket
    flask_process = Process(target=start_flask)
    websocket_process = Process(target=start_websocket)

    # Start both servers
    flask_process.start()
    websocket_process.start()

    # Wait for both to finish (they run forever unless stopped)
    flask_process.join()
    websocket_process.join()
