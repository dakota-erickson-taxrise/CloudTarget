import json
from threading import Thread
import assemblyai as aai
import os
import sys
import anthropic
import websockets
import asyncio
import numpy as np
import base64
import struct

class PlaybookItem:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.completed = False
        self.supporting_quote = ""
        self.timestamp = None

class AudioTranscriptionServer:
    def __init__(self):
        self.transcriber = None
        self.anthropic_client = anthropic.Anthropic()
        self.client_config = None
        
    async def handle_audio_data(self, websocket):
        try:
            config_msg = await websocket.recv()
            self.client_config = json.loads(config_msg)
            
            self.transcriber = aai.RealtimeTranscriber(
                sample_rate=16000,
                on_data=self.on_data,
                on_error=self.on_error,
                on_open=self.on_open,
                on_close=self.on_close,
            )
            
            await self.transcriber.connect()
            
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                audio_bytes = base64.b64decode(data['audio_data'])
                
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                if self.client_config['channels'] == 2:
                    audio_array = audio_array[::2]
                
                if self.client_config['sample_rate'] != 16000:
                    audio_array = self.resample(audio_array, 
                                             self.client_config['sample_rate'], 
                                             16000)
                
                await self.transcriber.stream(audio_array)
                
        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected")
            await self.process_transcript()
        finally:
            if self.transcriber:
                await self.transcriber.close()

    def resample(self, audio_array, orig_rate, target_rate):
        resampled = np.interp(
            np.linspace(0, len(audio_array), int(len(audio_array) * target_rate / orig_rate)),
            np.arange(len(audio_array)),
            audio_array
        )
        return resampled.astype(np.int16)

    def on_data(self, transcript: aai.RealtimeTranscript):
        if not transcript.text:
            return

        with open("transcript.txt", "a") as file:
            if isinstance(transcript, aai.RealtimeFinalTranscript):
                file.write(transcript.text + "\n")
                print("Writing to file...\n", end="\r")

    def on_error(self, error: aai.RealtimeError):
        print("An error occurred:", error)

    def on_open(self, session_opened: aai.RealtimeSessionOpened):
        print("Session ID:", session_opened.session_id)

    def on_close(self):
        print("Connection closed")

    async def process_transcript(self):
        await self.label_speakers()
        await self.analyze_labeled_transcript()
        print("Transcript processing complete!")

    async def label_speakers(self):
        try:
            with open("transcript.txt", "r") as file:
                transcript_text = file.read()
            
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
                                + " ".join(transcript_text)
                }]
            )
            
            with open("processed_transcript.txt", "w") as file:
                file.write(f"{message.content[0].text}")
            
        except Exception as e:
            print(f"Error processing transcript: {e}")

    async def analyze_labeled_transcript(self):
        try:
            print("Analyzing transcript...")
            with open("processed_transcript.txt", "r") as file:
                transcript_text = file.read()
                
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
            {transcript_text}

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
            print(f"Error analyzing transcript: {e}")

async def main():
    server = AudioTranscriptionServer()
    ASSEMBLY_AI_KEY = os.environ.get("ASSEMBLY_AI_KEY")
    aai.settings.api_key = ASSEMBLY_AI_KEY
    
    async with websockets.serve(
        server.handle_audio_data, 
        "0.0.0.0",
        8765,
        ssl=None
    ):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())