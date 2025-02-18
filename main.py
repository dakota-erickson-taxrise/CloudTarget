# Server
import asyncio
import websockets
import json
import os
import io
import wave
import logging
import sys


import assemblyai as aai

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    stream=sys.stdout)

# AssemblyAI Configuration
aai.settings.api_key = os.environ.get("ASSEMBLY_AI_KEY")

# WebSocket Configuration
WEBSOCKET_URI = "wss://0.0.0.0:8765"

# Transcript File
TRANSCRIPT_FILE = "transcript.txt"


def create_wav_bytes(audio_data, sample_rate, channels):
    """Creates WAV PCM16 bytes from audio data."""
    with io.BytesIO() as bio:
        with wave.open(bio, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        return bio.getvalue()


# AssemblyAI Event Handlers
def on_open(session_opened: aai.RealtimeSessionOpened):
    """Called when the AssemblyAI session is open."""
    logging.info("Session ID:", session_opened.session_id)


def on_data(transcript: aai.RealtimeTranscript):
    """Called when a transcript is received from AssemblyAI."""
    if not transcript.text:
        return

    with open(TRANSCRIPT_FILE, "a") as f:  # Open file in append mode
        if isinstance(transcript, aai.RealtimeFinalTranscript):
            f.write(transcript.text + "\n")  # Write final transcript with newline
        else:
            f.write(transcript.text + "\r")  # Write partial transcript with carriage return


def on_error(error: aai.RealtimeError):
    """Called when an error occurs during transcription."""
    logging.info("An error occurred:", error)


def on_close():
    """Called when the AssemblyAI session is closed."""
    logging.info("Closing Session")


async def process_audio(websocket, path):
    """Handles a single WebSocket connection and transcribes audio."""
    transcriber = aai.RealtimeTranscriber(
        on_data=on_data,
        on_error=on_error,
        sample_rate=16_000,  # Match the sample rate from the client
        on_open=on_open,
        on_close=on_close,
    )

    logging.info(f"Client connected from {websocket.remote_address}")
    await transcriber.connect()  # Connect to AssemblyAI

    try:
        async for message in websocket:
            try:
                # Assuming the client sends raw WAV bytes first, then JSON metadata
                wav_bytes = message  # Receive raw WAV bytes

                # Receive and parse metadata (make sure the client sends this!)
                metadata_json = await websocket.recv()
                metadata = json.loads(metadata_json)
                sample_rate = metadata.get("sample_rate")
                channels = metadata.get("channels")

                # Create an in-memory audio stream from the WAV bytes
                audio_stream = io.BytesIO(wav_bytes)

                # Stream the audio data to AssemblyAI
                await transcriber.stream(audio_stream)

            except Exception as e:
                logging.info(f"Error processing audio: {e}")
                break

    finally:
        await transcriber.close()  # Close the AssemblyAI session
        logging.info(f"Client disconnected from {websocket.remote_address}")


async def main():
    """Starts the WebSocket server."""
    async with websockets.serve(process_audio, "0.0.0.0", 8765):
        logging.info("WebSocket server started on ws://0.0.0.0:8765")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
