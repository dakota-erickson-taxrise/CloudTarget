import json
from threading import Thread
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Outputs to console/stdout
        logging.FileHandler('app.log')  # Also saves to a file
    ]
)

class PlaybookItem:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.completed = False
        self.supporting_quote = ""
        self.timestamp = None

class TranscriptionProcessor:
    def __init__(self):
        self.anthropic_client = anthropic.Anthropic()
        self.current_transcript = ""
        self.last_processed_length = 0
        
    def process_new_content(self):
        if len(self.current_transcript) > self.last_processed_length:
            self.label_speakers()
            self.analyze_labeled_transcript()
            self.last_processed_length = len(self.current_transcript)
    
    def label_speakers(self):
        try:
            transcript_string = " ".join(self.current_transcript)
            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": "Can you perform diarization on the following dialogue and output only \
                              the text labeled by who is speaking and label them Agent and Customer \
                              and do not provide any preceeding commentary only output the labled \
                              dialogue. If it appears to only be one speaker then only label one \
                              speaker and still provide no commentary. The agent should be the person\
                              asking questions and the customer should be the person answering questions\n" 
                              + transcript_string
                }]
            )
            
            with open("processed_transcript.txt", "w") as file:
                file.write(f"{message.content[0].text}")
            
        except Exception as e:
            logging.info(f"Error processing transcript: {e}")

    def analyze_labeled_transcript(self):
        try:
            with open("processed_transcript.txt", "r") as file:
                transcript_text = file.read()
                
            transcript_string = " ".join(transcript_text)
            playbook_items = [
                PlaybookItem("introduction", "Agent introduces themselves and their role"),
                PlaybookItem("situation_inquiry", "Agent asks about the customer's situation"),
                PlaybookItem("problem_identification", "Agent identifies the core problem"),
                PlaybookItem("solution_proposal", "Agent proposes potential solutions"),
                PlaybookItem("next_steps", "Agent outlines next steps or action items")
            ]
            
            prompt = f"""
            Given the following conversation transcript and playbook items, identify which items have been completed.
            For each completed item, provide the relevant quote that demonstrates completion. The key for the name should
            be name and the key for the supporting quote should be supporting_quote. Do not include uncompleted items
            in your response.
            
            Conversation Transcript:
            {transcript_string}

            Playbook items:
            {json.dumps([{'name': item.name, 'description': item.description} for item in playbook_items], indent=2)}
            
            Respond in JSON format with completed items and their supporting quotes."""

            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
                
            with open("analyzed_transcript.txt", "w") as file:
                file.write(f"{message.content[0].text}")
        except Exception as e:
            logging.info(f"Error analyzing transcript: {e}")

# In main.py, modify the WebSocketAudioStream class:

class WebSocketAudioStream:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.queue = asyncio.Queue()
        self.is_closed = False
        self.active_connection: Optional[websockets.WebSocketServerProtocol] = None
        self.config_received = False
        self._iterator = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.is_closed:
            raise StopIteration
        
        try:
            # Use get_nowait() to avoid blocking indefinitely
            return asyncio.get_event_loop().run_until_complete(self.queue.get())
        except asyncio.QueueEmpty:
            # If queue is empty, yield None to let the transcriber know we're still active
            return None
        except Exception as e:
            logging.error(f"Error getting next audio chunk: {e}")
            raise StopIteration

    async def receive_audio(self, websocket):
        self.active_connection = websocket
        try:
            connection_id = id(websocket)
            logging.info(f"New audio stream connection established (ID: {connection_id})")
            received_chunks = 0
            
            while not self.is_closed:
                message = await websocket.recv()
                
                try:
                    # Try to parse as JSON
                    data = json.loads(message)
                    
                    if not self.config_received:
                        # Handle initial config message
                        if 'sample_rate' in data:
                            logging.info(f"Received config: {data}")
                            self.config_received = True
                            await websocket.send(json.dumps({"status": "config_accepted"}))
                            continue
                    
                    # Handle audio data in JSON format
                    if 'audio_data' in data:
                        audio_data = base64.b64decode(data['audio_data'])
                        await self.queue.put(audio_data)
                        received_chunks += 1
                        if received_chunks % 100 == 0:
                            logging.info(f"Connection {connection_id}: Received {received_chunks} audio chunks")
                        await websocket.send(json.dumps({"status": "chunk_received"}))
                
                except json.JSONDecodeError:
                    # If not JSON, assume raw audio data
                    await self.queue.put(message)
                    received_chunks += 1
                    if received_chunks % 100 == 0:
                        logging.info(f"Connection {connection_id}: Received {received_chunks} audio chunks")
                    await websocket.send(json.dumps({"status": "chunk_received"}))
                    
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"WebSocket connection {connection_id} closed after receiving {received_chunks} chunks")
        except Exception as e:
            logging.error(f"Error in audio stream: {e}")
        finally:
            self.active_connection = None
            self.config_received = False

    def close(self):
        self.is_closed = True

class TranscriptionManager:
    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port
        self.processor = TranscriptionProcessor()
        self.audio_stream = WebSocketAudioStream()
        self.transcriber = None
        
    def on_data(self, transcript: aai.RealtimeTranscript):
        if not transcript.text:
            logging.info("Received empty transcript text")
            return

        if isinstance(transcript, aai.RealtimeFinalTranscript):
            logging.info(f"New transcription: {transcript.text}")
            try:
                # Use absolute path in /tmp directory
                transcript_path = "/tmp/transcript.txt"
                with open(transcript_path, "a") as file:
                    file.write(transcript.text + "\n")
                logging.info(f"Successfully wrote to {transcript_path}")
            except Exception as e:
                logging.error(f"Error writing to transcript file: {e}")

    def on_error(self, error: aai.RealtimeError):
        logging.info(f"An error occurred: {error}")

    def on_open(self, session_opened: aai.RealtimeSessionOpened):
        logging.info(f"Session ID: {session_opened.session_id}")

    def on_close(self):
        logging.info("Connection closed")
        if self.audio_stream.active_connection:
            asyncio.run(self.audio_stream.active_connection.close())

    async def handle_websocket(self, websocket, path):
        await self.audio_stream.receive_audio(websocket)

    def _run_transcription(self):
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.transcriber.connect()
            self.transcriber.stream(self.audio_stream)
        except Exception as e:
            logging.error(f"Error in transcription thread: {e}")
        finally:
            loop.close()

    def start_transcription(self):
        self.transcriber = aai.RealtimeTranscriber(
            sample_rate=16_000,
            on_data=self.on_data,
            on_error=self.on_error,
            on_open=self.on_open,
            on_close=self.on_close,
        )
        
        return self._run_transcription()

    async def run(self):
        transcription_thread = Thread(target=self.start_transcription, daemon=True)
        transcription_thread.start()
        
        async with websockets.serve(self.handle_websocket, self.host, self.port):
            logging.info(f"WebSocket server running on ws://{self.host}:{self.port}")
            await asyncio.Future()

def main():
    try:
        load_dotenv()
        aai.settings.api_key = os.getenv('ASSEMBLY_AI_KEY')
        
        manager = TranscriptionManager()
        asyncio.run(manager.run())
    except KeyboardInterrupt:
        logging.info("\nShutting down...")
    except Exception as e:
        logging.info(f"An error occurred: {e}")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
