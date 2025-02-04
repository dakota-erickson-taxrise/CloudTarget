import json
from threading import Thread
import assemblyai as aai
import os
from dotenv import load_dotenv
import sys
import anthropic

class PlaybookItem:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.completed = False
        self.supporting_quote = ""
        self.timestamp = None


def label_speakers(anthropic_client):
    """Label the speakers in the transcript after streaming is complete"""
    try:
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

def analyze_labeled_transcript(anthropic_client):
    """Analyze the labeld transcript to see how far we got during the conversation"""
    try:
        print("Analyzing transcript...")

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

        message = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
        with open("analyzed_transcript.txt", "w") as file:
            file.write(f"{message.content[0].text}")
    except:
        pass

def on_open(session_opened: aai.RealtimeSessionOpened):
    print("Session ID:", session_opened.session_id)

def on_data(transcript: aai.RealtimeTranscript):
    if not transcript.text:
        return

    with open("transcript.txt", "a") as file:
        if isinstance(transcript, aai.RealtimeFinalTranscript):
            file.write(transcript.text + "\n")
            print("Writing to file...\n", end="\r")
        else:
            pass

def on_error(error: aai.RealtimeError):
    print("An error occurred:", error)

def on_close():
    print("Connection closed...")


def main():
    SAMPLE_RATE = 16_000
    do_transcription = True
    while do_transcription:
        try:
            # uses default name for API key coming from env variable
            anthropic_client = anthropic.Anthropic()

            with open("transcript.txt", "w") as file:
                file.write("")

            load_dotenv()
            aai.settings.api_key = os.getenv('ASSEMBLY_AI_KEY')

            transcriber = aai.RealtimeTranscriber(
                sample_rate=SAMPLE_RATE,
                on_data=on_data,
                on_error=on_error,
                on_open=on_open,
                on_close=on_close,
            )

            transcriber.connect()

            microphone_stream = aai.extras.MicrophoneStream(sample_rate=SAMPLE_RATE)

            def stream_mic_audio():
                print("Starting transcription... \nType 'stop' to stop transcribing and move to processing.")
                transcriber.stream(microphone_stream)
            
            streaming_thread = Thread(target=stream_mic_audio, daemon=True)
            streaming_thread.start()

            key = input()
            if key == "stop":
                do_transcription = False
                print("\nProcessing transcription...")
                label_speakers(anthropic_client)
                analyze_labeled_transcript(anthropic_client)
                # add in a function here to do the playbook style analysis
                print("Transcript processing complete!")
            

        except Exception as e:
            print(f"An error occurred: {e}")
        print("\nClosing connections...")
        microphone_stream.close()
        transcriber.close()
        sys.exit(0)

if __name__ == "__main__":
    main()