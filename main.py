import json
from threading import Thread
import assemblyai as aai
import os
import anthropic
import websockets
import asyncio
import numpy as np
import base64

class PlaybookItem:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.completed = False
        self.supporting_quote = ""
        self.timestamp = None

class AudioTranscriptionServer:
    def __init__(self):
        self.transcriber = aai.RealtimeTranscriber(
            sample_rate=16000,
            on_data=self.on_data,
            on_error=self.on_error,
            on_open=self.on_open,
            on_close=self.on_close,
        )
        self.anthropic_client = anthropic.Anthropic()
        self.client_config = None
        
    async def handle_audio_data(self, websocket):
        try:
            await self.transcriber.connect()
            
            config_msg = await websocket.recv()
            self.client_config = json.loads(config_msg)
            
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