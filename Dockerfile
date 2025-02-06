# Use a slim Python 3.8 base image
FROM python:3.8-slim

# Set working directory
WORKDIR /app

# Copy your Python script to the container
COPY main.py .

# Install required libraries
RUN pip install --upgrade pip
RUN apt-get update && apt-get install -y gcc python3-dev portaudio19-dev
RUN pip install websockets assemblyai anthropic 'assemblyai[extras]' numpy python-dotenv

# Expose the port used by the WebSocket server (default 8765)
EXPOSE 8765

# Run the Python script as the entry point
CMD ["python", "main.py"]