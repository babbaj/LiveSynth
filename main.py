import io
import sys
import os
import argparse
from enum import Enum

import whisper
from whisper.audio import SAMPLE_RATE
import numpy as np
import signal
import threading
import subprocess
import requests
from pydub import AudioSegment
from pynput import keyboard
import psutil


class State(Enum):
    IDLE = 1
    RECORDING = 2
    TRANSCRIBING = 3
    GENERATING = 4
    PLAYING = 5


def audio_commands(source, sink):
    format = lambda r: ["--rate=" + str(r), "--channels=1"]  # both default to s16
    for process in psutil.process_iter(['name']):
        if process.info['name'] == 'pipewire':
            return (
                ["pw-record", *(["--target", source] if source else []), *format(SAMPLE_RATE), "--latency=50", "-"],
                ["pw-cat", *(["--target", sink] if sink else []), *format(44100), "-p", "-"]
            )
        elif process.info['name'] == 'pulseaudio':
            return (
                ["parec", *(["--device", source] if source else []), *format(SAMPLE_RATE), "--latency-msec=50"],
                ["pacat", *(["--device", sink] if sink else []), *format(44100)]
            )
    else:
        print(f"No process named \"pipewire\" or \"pulseaudio\" running")


class MicInput:
    def __init__(self, command):
        try:
            self.command = command
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"Command '{e.cmd}' failed with return code {e.returncode}")
            exit(1)
        self.buffer = np.empty(0, dtype=np.int16)

    def stop(self):
        self.process.send_signal(signal.SIGINT)


def call_api(text, voice_id, api_key):
    url = 'https://api.elevenlabs.io/v1/text-to-speech/' + voice_id
    headers = {
        'accept': 'audio/mpeg',
        'Content-Type': 'application/json',
        'xi-api-key': api_key
    }
    data = {
        'text': text,
        #'voice_settings': {
        #    'stability': 0.75,
        #    'similarity_boost': 0.80
        #}
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        # Access the audio data from the response content
        mp3 = response.content
        audio = AudioSegment.from_file(io.BytesIO(mp3), format='mp3')
        # Get the raw audio data as a byte string
        # this is 44.1khz signed 16 bit
        return audio.raw_data
    else:
        print(f'Request failed with status code {response.status_code}')
        return None


def transcribe(data):
    result = model.transcribe(data, language="en")
    return result["text"]

def output_data(raw_data):
    output = subprocess.Popen(cat_cmd, stdin=subprocess.PIPE)
    output.stdin.write(raw_data)
    output.stdin.close()
    output.wait()

def read_until_stopped():
    global state
    global recording_stream
    while True:
        raw_audio = recording_stream.process.stdout.read(512)
        if not raw_audio:
            break
        audio_chunk = np.frombuffer(raw_audio, dtype=np.int16).flatten().astype(np.float32) / 32768.0
        recording_stream.buffer = np.append(recording_stream.buffer, audio_chunk)
    print("transcribing")
    state = State.TRANSCRIBING
    text = transcribe(recording_stream.buffer).strip()
    recording_stream = None
    if len(text):
        state = State.GENERATING
        print("calling api with:", text)
        raw_data = call_api(text, voice_id, api_key)
        if raw_data is not None:
            state = State.PLAYING
            output_data(raw_data)
    else:
        print("transcribed to empty string")
    state = State.IDLE


def on_press(key):
    global state
    global recording_stream
    if key == keyboard.Key.menu and state == State.IDLE:
        print("recording")
        recording_stream = MicInput(record_cmd)
        state = State.RECORDING
        reader_thread = threading.Thread(target=read_until_stopped)
        reader_thread.start()


def on_release(key):
    if key == keyboard.Key.menu and recording_stream is not None:
        recording_stream.stop()


parser = argparse.ArgumentParser(
    prog='LiveSynth'
)
parser.add_argument('-v', '--voice')
parser.add_argument('-k', '--api-key')
parser.add_argument('-in', '--input-source')
parser.add_argument('-out', '--output-sink')
args = parser.parse_args()

voice_id = args.voice
input_source = args.input_source
output_sink = args.output_sink
api_key = args.api_key

record_cmd, cat_cmd = audio_commands(input_source, output_sink)
print("record =", ' '.join(record_cmd))
print("playback =", ' '.join(cat_cmd))

print("Loading model...")
model = whisper.load_model("medium")
print("done loading")

state = State.IDLE
recording_stream = None
# Set up the keyboard listener using the X11 backend
listener = keyboard.Listener(
    on_press=on_press,
    on_release=on_release,
    backend='x11'
)
listener.start()
try:
    listener.join()
except KeyboardInterrupt:
    pass
