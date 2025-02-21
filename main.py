# server
import asyncio
import websockets
import json
import base64
import assemblyai as aai
import os
import logging
import sys

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    stream=sys.stdout)

# Configure AssemblyAI API
aai.settings.api_key = os.environ.get("ASSEMBLY_AI_KEY")

# AssemblyAI event handlers
def on_open(session_opened: aai.RealtimeSessionOpened):
    logging.info("AssemblyAI Session ID:", session_opened.session_id)

def on_data(transcript: aai.RealtimeTranscript):
    if not transcript.text:
        return
        
    if isinstance(transcript, aai.RealtimeFinalTranscript):
        logging.info(f"Received final transcript and writing to file...")
        with open('raw_transcript.txt', 'a') as f:
            f.write(transcript.text + '\n')
    else:
        logging.info(f"Received Partial transcript: {transcript.text}")

def on_error(error: aai.RealtimeError):
    logging.info("AssemblyAI error occurred:", error)

def on_close():
    logging.info("AssemblyAI Session Closed")

# Create transcriber with 44.1kHz sample rate
transcriber = aai.RealtimeTranscriber(
    on_data=on_data,
    on_error=on_error,
    on_open=on_open,
    on_close=on_close,
    sample_rate=16_000,
)

# Dictionary to track active connections
connections = {}

async def handle_client(websocket):
    client_id = id(websocket)
    connections[client_id] = websocket
    logging.info(f"Client {client_id} connected")
    
    try:
        # Connect to AssemblyAI when a client connects
        transcriber.connect()
        
        # Process incoming audio data
        async for message in websocket:
            try:
                # Assuming client sends JSON with base64-encoded audio
                data = json.loads(message)
                if 'audio_data' in data:
                    # Decode base64 audio data
                    audio_bytes = base64.b64decode(data['audio_data'])
                    
                    # Stream to AssemblyAI
                    transcriber.stream(audio_bytes)
                    
            except json.JSONDecodeError:
                logging.info(f"Received invalid JSON from client {client_id}")
            except Exception as e:
                logging.info(f"Error processing message from client {client_id}: {e}")
    
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"Connection with client {client_id} closed")
    
    finally:
        # Clean up AssemblyAI connection and remove client
        transcriber.close()
        if client_id in connections:
            del connections[client_id]
        logging.info(f"Client {client_id} disconnected")

# Start WebSocket server
async def main():
    server = await websockets.serve(
        handle_client,
        "0.0.0.0",
        8765
    )
    logging.info(f"WebSocket server started at ws://0.0.0.0:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())