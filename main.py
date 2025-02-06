import asyncio
import websockets
import assemblyai as aai
import json
from queue import Queue
from typing import Dict
from anthropic import Anthropic
import time
import os
import logging
import base64
import anthropic


logging.basicConfig(
    format="%(asctime)s %(message)s", level=logging.INFO
)

class PlaybookItem:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.completed = False
        self.completed_text = ""
        self.timestamp = None


def label_speakers(anthropic_client):
    """Label the speakers in the transcript after streaming is complete"""
    try:
        logging.info("Diarizing the transcript")
        with open("transcript.txt", "r") as file:
            transcript_text = file.read()
        
        transcript_string = " ".join(transcript_text)

        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": "Can you perform diarization on the following dialogue and output only \
                                the text labeled by who is speaking and label them Agent and Customer \
                                and do not provide any preceeding commentary only output the labled \
                                dialogue. If it appears to only be one speaker then only label one \
                                speaker and still provide no commentary. The agent should be the person\
                                asking questions and the customer should be the person answering questions\n" 
                                + transcript_string
                }
            ]
        )
        
        with open("processed_transcript.txt", "w") as file:
            file.write(f"{message.content[0].text}")
        
    except Exception as e:
        print(f"Error processing transcript: {e}")

class ConversationAnalyzer:
    def __init__(self, anthropic_api_key: str):
        self.client = Anthropic(api_key=anthropic_api_key)
        self.conversation_history = []
        self.playbook_items = [
            PlaybookItem("introduction", "Agent introduces themselves and their role"),
            PlaybookItem("situation_inquiry", "Agent asks about the customer's situation"),
            PlaybookItem("problem_identification", "Agent identifies the core problem"),
            PlaybookItem("solution_proposal", "Agent proposes potential solutions"),
            PlaybookItem("next_steps", "Agent outlines next steps or action items")
        ]
    
    def analyze_transcript(self, text: str) -> Dict:
        # Append new text to conversation history
        self.conversation_history.append(text)
        
        # Create prompt for Claude to analyze the conversation
        prompt = f"""Given the following conversation transcript and playbook items, identify which items have been completed.
        For each completed item, provide the relevant quote that demonstrates completion.
        
        Playbook items:
        {json.dumps([{'name': item.name, 'description': item.description} for item in self.playbook_items], indent=2)}
        
        Conversation transcript:
        {' '.join(self.conversation_history)}
        
        Respond in JSON format with completed items and their supporting quotes."""
        
        try:
            response = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1000,
                temperature=0,
                system="You are analyzing a customer service conversation to identify completed playbook items. Respond only with JSON.",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            analysis = json.loads(response.content[0].text)
            
            updates = []
            for item in self.playbook_items:
                if item.name in analysis and not item.completed:
                    item.completed = True
                    item.completed_text = analysis[item.name]
                    item.timestamp = time.time()
                    updates.append({
                        "item": item.name,
                        "completed": True,
                        "text": item.completed_text,
                        "timestamp": item.timestamp
                    })
            
            return {"updates": updates}
            
        except Exception as e:
            logging.error(f"Analysis error: {e}")
            return {"error": str(e)}

class TranscriptionWebSocket:
    def __init__(self, assembly_api_key: str, anthropic_api_key: str):
        self.assembly_api_key = assembly_api_key
        self.anthropic_client = anthropic.Anthropic()
        aai.settings.api_key = self.assembly_api_key
        self.websocket = None
        self.transcriber = None
        self.audio_queue = Queue()
        self.is_running = False
        self.loop = None
        self.analyzer = None
        self.first_audio_received = False
        self.transcriber_ready = asyncio.Event()

    async def handle_websocket(self, websocket: websockets.WebSocketServerProtocol):
        self.websocket = websocket
        self.loop = asyncio.get_running_loop()
        logging.info(f"Client connected from {websocket.remote_address}")

        def on_transcription_data(transcript: aai.RealtimeTranscript):
            logging.info(f"Transcript received: {json.dumps(transcript)}")
            
            try:
                current_dir = os.getcwd()
                logging.info(f"Current working directory: {current_dir}")
                
                with open("transcript.txt", "a") as file:
                    if isinstance(transcript, aai.RealtimeFinalTranscript):
                        file.write(transcript.text + "\n")
                        logging.info(f"Successfully wrote to transcript.txt: {transcript.text}")
                    else:
                        logging.info("Skipping non-final transcript")
            except Exception as e:
                logging.error(f"Error writing transcript: {e}")


        def on_transcription_error(error: aai.RealtimeError):
            logging.error(f"Transcription error: {error}")

        async def process_audio_queue():
            # Wait for transcriber to be ready
            await self.transcriber_ready.wait()
            
            while self.is_running:
                if not self.audio_queue.empty():
                    message = self.audio_queue.get()
                    
                    try:
                        if message.get("event") == "media" and "media" in message:
                            payload = message["media"].get("payload")
                            
                            if payload:
                                if not all(c == '/' for c in payload):
                                    try:
                                        audio_data = base64.b64decode(payload)
                                        chunk_size = len(audio_data)
                                        
                                        if chunk_size > 0 and self.transcriber:
                                            await self.loop.run_in_executor(
                                                None,
                                                lambda: self.transcriber.stream(audio_data)
                                            )
                                        else:
                                            logging.warning("Received empty audio chunk or transcriber not ready")
                                    except Exception as e:
                                        logging.error(f"Error processing audio chunk: {e}")
                                else:
                                    logging.debug("Skipping silent audio chunk")
                            else:
                                logging.warning("No payload in media message")
                        else:
                            logging.debug(f"Skipping non-media message: {message.get('event', 'unknown event')}")
                                
                    except Exception as e:
                        logging.error(f"Error processing message: {e}")
                        logging.error(f"Message that caused error: {message}")
                            
                await asyncio.sleep(0.01)

        async def init_transcriber():
            try:
                logging.info("Initializing transcriber...")
                
                self.transcriber = aai.RealtimeTranscriber(
                    on_data=on_transcription_data,
                    on_error=on_transcription_error,
                    sample_rate=16_000,
                    encoding=aai.AudioEncoding.pcm_mulaw
                )

                logging.info("Connecting transcriber...")
                await self.loop.run_in_executor(None, self.transcriber.connect)
                logging.info("Transcriber connected successfully")
                self.transcriber_ready.set()  # Signal that transcriber is ready
                
                while self.is_running:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logging.error(f"Error in transcription initialization: {e}")
                import traceback
                logging.error(f"Traceback: {traceback.format_exc()}")
            finally:
                logging.info("Closing transcriber connection")
                if self.transcriber:
                    self.transcriber.close()

        try:
            self.is_running = True
            
            # Start transcriber initialization
            transcriber_task = asyncio.create_task(init_transcriber())
            audio_process_task = asyncio.create_task(process_audio_queue())

            async for message in websocket:
                try:
                    json_parsed_message = json.loads(message)
                    if not self.first_audio_received and "media" in json_parsed_message:
                        payload = json_parsed_message["media"].get("payload", "")
                        if not all(c == '/' for c in payload):
                            logging.info("First non-silent audio message received")
                            logging.info(f"Message structure: {json.dumps(json_parsed_message, indent=2)}")
                            self.first_audio_received = True
                    
                    self.audio_queue.put(json_parsed_message)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON parse error: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error processing message: {e}")

        except websockets.exceptions.ConnectionClosed:
            logging.info("Client disconnected")
            label_speakers(anthropic_client=self.anthropic_client)

        finally:
            self.is_running = False
            if self.transcriber:
                self.transcriber.close()
            audio_process_task.cancel()
            transcriber_task.cancel()
            try:
                await audio_process_task
                await transcriber_task
            except asyncio.CancelledError:
                pass

    async def send_message(self, message):
        if self.websocket and self.websocket.open:
            try:
                await self.websocket.send(json.dumps(message))
            except Exception as e:
                logging.error(f"Error sending message: {e}")

async def start_server(
    host: str = "0.0.0.0",
    port: int = 8765,
    assembly_api_key: str = None,
    anthropic_api_key: str = None
):
    
    # Exit early if we don't get API keys
    if assembly_api_key is None:
        logging.error("Missing AssemblyAI API key")
        return None
    if anthropic_api_key is None:
        logging.error("Missing AnthropicAI API key")
        return None
    
    transcription_ws = TranscriptionWebSocket(assembly_api_key, anthropic_api_key)
    
    async with websockets.serve(
        transcription_ws.handle_websocket,
        host,
        port
    ):
        logging.info(f"WebSocket server started on ws://{host}:{port}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    ASSEMBLY_API_KEY = os.environ.get("ASSEMBLY_AI_KEY")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_AI_KEY")
    
    logging.info("Running websocket...")

    asyncio.run(start_server(
        assembly_api_key=ASSEMBLY_API_KEY,
        anthropic_api_key=ANTHROPIC_API_KEY
    ))
