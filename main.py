import json
import threading
import assemblyai as aai
import os
from dotenv import load_dotenv
import sys
import anthropic
import websockets
import asyncio
from typing import Optional
import logging
import base64
from queue import Queue
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)

class AudioBuffer:
    def __init__(self, expected_sample_rate=16000):
        self.queue = Queue()
        self.is_closed = False
        self.expected_sample_rate = expected_sample_rate
        self._received_samples = 0
        self._start_time = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.is_closed and self.queue.empty():
            raise StopIteration
        
        try:
            chunk = self.queue.get(timeout=1.0)
            self._received_samples += len(chunk) // 2  # 2 bytes per sample for PCM16
            
            if self._start_time is None:
                self._start_time = time.time()
            else:
                elapsed_time = time.time() - self._start_time
                expected_samples = int(elapsed_time * self.expected_sample_rate)
                logging.debug(f"Received samples: {self._received_samples}, Expected: {expected_samples}")
            
            return chunk
        except Queue.Empty:
            return None

    def add_chunk(self, chunk):
        self.queue.put(chunk)

    def close(self):
        self.is_closed = True

class TranscriptionManager:
    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port
        self.audio_buffer = AudioBuffer()
        self.transcriber = None
        self.anthropic_client = anthropic.Anthropic()
        self.transcript_buffer = []
        self.current_session_id = None

    def on_data(self, transcript: aai.RealtimeTranscript):
        if not transcript.text:
            return

        if isinstance(transcript, aai.RealtimeFinalTranscript):
            logging.info(f"Final transcript: {transcript.text}")
            self.transcript_buffer.append(transcript.text)
            
            try:
                # Write to transcript file
                with open(f"transcript_{self.current_session_id}.txt", "a") as file:
                    file.write(f"{transcript.text}\n")
                
                # Process with Claude when we have enough content
                if len(self.transcript_buffer) >= 3:
                    self.process_transcript_chunk()
                    
            except Exception as e:
                logging.error(f"Error processing transcript: {e}")
        else:
            print(f"Interim transcript: {transcript.text}", end="\r")

    def process_transcript_chunk(self):
        try:
            transcript_text = " ".join(self.transcript_buffer)
            
            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": f"Please analyze this conversation segment and identify key points and topics discussed: {transcript_text}"
                }]
            )
            
            with open(f"analysis_{self.current_session_id}.txt", "a") as file:
                file.write(f"\nAnalysis of segment:\n{message.content[0].text}\n")
                
            self.transcript_buffer = []  # Clear buffer after processing
            
        except Exception as e:
            logging.error(f"Error in transcript analysis: {e}")

    def on_error(self, error: aai.RealtimeError):
        logging.error(f"AssemblyAI error: {error}")

    def on_open(self, session_opened: aai.RealtimeSessionOpened):
        self.current_session_id = session_opened.session_id
        logging.info(f"New transcription session started: {self.current_session_id}")

    def on_close(self):
        logging.info(f"Transcription session {self.current_session_id} closed")
        self.process_transcript_chunk()  # Process any remaining transcript
        self.current_session_id = None

    async def handle_websocket(self, websocket, path):
        connection_id = id(websocket)
        logging.info(f"New WebSocket connection: {connection_id}")
        
        try:
            # Wait for initial configuration
            config = await websocket.recv()
            config_data = json.loads(config)
            sample_rate = config_data.get('sample_rate', 16000)
            
            self.audio_buffer = AudioBuffer(expected_sample_rate=sample_rate)
            await websocket.send(json.dumps({"status": "config_accepted"}))
            
            # Start transcription in a separate thread
            self.start_transcription(sample_rate)
            
            while True:
                message = await websocket.recv()
                try:
                    data = json.loads(message)
                    if 'audio_data' in data:
                        audio_chunk = base64.b64decode(data['audio_data'])
                        self.audio_buffer.add_chunk(audio_chunk)
                        await websocket.send(json.dumps({"status": "chunk_received"}))
                except json.JSONDecodeError:
                    logging.error("Received invalid JSON message")
                    continue
                
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"WebSocket connection {connection_id} closed")
        except Exception as e:
            logging.error(f"Error in WebSocket handler: {e}")
        finally:
            self.audio_buffer.close()

    def start_transcription(self, sample_rate):
        self.transcriber = aai.RealtimeTranscriber(
            sample_rate=sample_rate,
            on_data=self.on_data,
            on_error=self.on_error,
            on_open=self.on_open,
            on_close=self.on_close,
            encoding=aai.AudioEncoding.pcm_s16le
        )
        
        threading.Thread(
            target=self._run_transcription,
            daemon=True
        ).start()

    def _run_transcription(self):
        try:
            self.transcriber.connect()
            self.transcriber.stream(self.audio_buffer)
        except Exception as e:
            logging.error(f"Error in transcription thread: {e}")

    async def run(self):
        async with websockets.serve(self.handle_websocket, self.host, self.port):
            logging.info(f"WebSocket server running on ws://{self.host}:{self.port}")
            await asyncio.Future()  # run forever

def main():
    try:
        load_dotenv()
        aai.settings.api_key = os.getenv('ASSEMBLY_AI_KEY')
        
        if not aai.settings.api_key:
            raise ValueError("ASSEMBLY_AI_KEY environment variable not set")
        
        manager = TranscriptionManager()
        asyncio.run(manager.run())
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
