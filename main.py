import io
import sys

import whisper
from whisper.audio import SAMPLE_RATE
import ffmpeg
import numpy as np
import signal
import threading
import subprocess
import requests
from pydub import AudioSegment
from pynput import keyboard


class AudioStream:
    def __init__(self):
        try:
            # this is cringe as heck
            # self.process = (
            #    ffmpeg.input("default", format="pulse", loglevel="panic")
            #    .output("pipe:", format="s16le", acodec="pcm_s16le", ac=1, ar=SAMPLE_RATE)
            #    .run_async(pipe_stdout=True)
            # )

            # might be a good idea to replace this with https://larsimmisch.github.io/pyalsaaudio/libalsaaudio.html
            # or https://soundcard.readthedocs.io/en/latest/
            command = ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1", "-"]
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except ffmpeg.Error as e:
            raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e
        self.buffer = np.empty(0, dtype=np.int16)

    def stop(self):
        self.process.send_signal(signal.SIGINT)
        # self.process.terminate()


def call_api(text, voice_id, api_key):
    url = 'https://api.elevenlabs.io/v1/text-to-speech/' + voice_id
    #print(url)
    headers = {
        'accept': 'audio/mpeg',
        'Content-Type': 'application/json',
        'xi-api-key': api_key
    }
    data = {
        'text': text,
        'voice_settings': {
            'stability': 0.75,
            'similarity_boost': 0.80
        }
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


def transcribe(stream):
    result = model.transcribe(stream.buffer, language="en")
    return result["text"]

def output_data(raw_data):
    with open('output', 'wb') as f:
        f.write(raw_data)
        print("wrote to output")

    # send it to ffmpeg (pacat also works)
    output = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-re", "-f", "s16le", "-ar", "44100", "-i", "-", "-f", "pulse", "-device",
         "LiveSynth", "sneed"],
        stdin=subprocess.PIPE)
    output.stdin.write(raw_data)
    output.stdin.close()
    output.wait()

def read_until_stopped():
    global stream
    print("reading stream...")
    while True:
        raw_audio = stream.process.stdout.read(512)
        if not raw_audio:
            break
        audio_chunk = np.frombuffer(raw_audio, dtype=np.int16).flatten().astype(np.float32) / 32768.0
        stream.buffer = np.append(stream.buffer, audio_chunk)
    print("finished reading", stream.buffer.size, "bytes")
    text = transcribe(stream)
    if len(text.strip()):
        print("calling api with:", text)
        raw_data = call_api(text, voice_id, api_key)
        if raw_data is not None:
            output_data(raw_data)
    else:
        print("empty string")
    stream = None


# Define the callback functions for key events
def on_press(key):
    global stream
    if key == keyboard.Key.menu and stream is None:
        print(f'Key {key} pressed')
        print("creating stream")
        stream = AudioStream()
        reader_thread = threading.Thread(target=read_until_stopped)
        reader_thread.start()


def on_release(key):
    # print(f'Key {key} released')
    if key == keyboard.Key.menu and stream is not None:
        print("sending SIGINT")
        stream.stop()


#output = subprocess.Popen(
#    ["ffmpeg", "-loglevel", "error", "-re", "-f", "s16le", "-ar", "44100", "-i", "-", "-f", "pulse", "-device", "sneed", "feed_and_seed"],
#    stdin=subprocess.PIPE
#)
#output.stdin.write(b'\x00\x00')
#output.stdin.flush()
#stream = sd.OutputStream(device="LiveSynthSink")
#stream.start()

voice_id = sys.argv[1]
sink_name = sys.argv[2]
api_key = sys.argv[3]

print("Loading model...")
model = whisper.load_model("medium")
print("done loading")

stream = None
# Set up the keyboard listener using the X11 backend
listener = keyboard.Listener(
    on_press=on_press,
    on_release=on_release,
    backend='x11'
)
listener.start()
listener.join()
