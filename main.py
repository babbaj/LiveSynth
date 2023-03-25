import io
import argparse
from enum import Enum
import traceback

import whisper
from whisper.audio import SAMPLE_RATE as WHISPER_SAMPLE_RATE
import numpy as np
import signal
import threading
import subprocess
import requests
from pynput import keyboard
import psutil
import Xlib.XK as XK


class State(Enum):
    IDLE = 1
    RECORDING = 2
    TRANSCRIBING = 3
    GENERATING = 4
    BUFFERED = 4 # audio received from api but we aren't playing it yet
    PLAYING = 5


def audio_commands(source, sink):
    format = lambda r: ["--rate=" + str(r), "--channels=1"]  # both default to s16
    for process in psutil.process_iter(['name']):
        if process.info['name'] == 'pipewire':
            return (
                ["pw-record", *(["--target", source] if source else []), *format(WHISPER_SAMPLE_RATE), "--latency=50", "-"],
                ["pw-cat", *(["--target", sink] if sink else []), *format(44100), "-p", "-"]
            )
        elif process.info['name'] == 'pulseaudio':  # not the ideal way to check for pulse but good enough
            return (
                ["parec", *(["--device", source] if source else []), *format(WHISPER_SAMPLE_RATE), "--latency-msec=50"],
                ["pacat", *(["--device", sink] if sink else []), *format(44100)]
            )
    else:
        print(f"No process named \"pipewire\" or \"pulseaudio\" running")

def ffmpeg_decode_mp3():
    cmd = "ffmpeg -hide_banner -loglevel error -f mp3 -i - -f s16le -ar 44100 -ac 1 -".split(' ')
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)


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
    url = 'https://api.elevenlabs.io/v1/text-to-speech/' + voice_id + "/stream"
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
    response = requests.post(url, headers=headers, json=data, stream=True)
    if response.status_code == 200:
        return response
    else:
        print(f'Request failed with status code {response.status_code}')
        return None


def transcribe(data):
    result = model.transcribe(data, language="en")
    return result["text"]

def output_data(response):
    decoder = ffmpeg_decode_mp3()
    output = subprocess.Popen(cat_cmd, stdin=decoder.stdout)
    for chunk in response.iter_content(chunk_size=1024):
        decoder.stdin.write(chunk)
    decoder.stdin.close()
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
    try:
        text = transcribe(recording_stream.buffer).strip()
    except Exception as e:
        print("Whisper did an oopsie")
        traceback.print_exc()
        state = State.IDLE
        return

    recording_stream = None
    if len(text):
        state = State.GENERATING
        print("calling api with:", text)
        response = call_api(text, voice_id, api_key)
        if response is not None:
            state = State.PLAYING
            print("outputting")
            output_data(response)
    else:
        print("transcribed to empty string")
    state = State.IDLE

def get_keysym(cringe):
    # very elegant and consistent library
    if hasattr(cringe, 'value'):
        return cringe.value.vk
    else:
        return cringe.vk

def on_press(key):
    global state
    global recording_stream
    keysym = get_keysym(key)

    if keysym == keysym_config and state == State.IDLE:
        print("recording")
        recording_stream = MicInput(record_cmd)
        state = State.RECORDING
        reader_thread = threading.Thread(target=read_until_stopped)
        reader_thread.start()


def on_release(key):
    keysym = get_keysym(key)
    if keysym == keysym_config and recording_stream is not None:
        recording_stream.stop()


parser = argparse.ArgumentParser(
    prog='LiveSynth'
)
parser.add_argument('-v', '--voice', help='The voice_id (not the name of the voice)')
parser.add_argument('-k', '--key', default='shift_r', help="The key (x11 keysym name, case insensitive) to use to start recording voice input")
parser.add_argument('--api-key', help="The ElevenLabs api key")
parser.add_argument('--cpu', action='store_true', help="Run whisper on the cpu")
parser.add_argument('-m', '--model', default='medium.en', help='The whisper model to use')
parser.add_argument('-in', '--input-source')
parser.add_argument('-out', '--output-sink')
args = parser.parse_args()

voice_id = args.voice
api_key = args.api_key
use_cpu = args.cpu
whisper_model = args.model
input_source = args.input_source
output_sink = args.output_sink

all_keysyms = {k[3:].lower(): v for k, v in vars(XK).items() if k.startswith('XK_')}
keysym_config = all_keysyms[args.key]

try:
    record_cmd, cat_cmd = audio_commands(input_source, output_sink)
    print("record =", ' '.join(record_cmd))
    print("playback =", ' '.join(cat_cmd))

    print("Loading model...")
    model = whisper.load_model(whisper_model, device='cpu' if use_cpu else 'cuda')
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
    listener.join()
except KeyboardInterrupt:
    pass
