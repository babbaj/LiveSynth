import whisper
from whisper.audio import SAMPLE_RATE
import ffmpeg
import numpy as np
import signal
import threading
import subprocess
from pynput import keyboard


class AudioStream:
    def __init__(self):
        try:
            # this is cringe as heck
            #self.process = (
            #    ffmpeg.input("default", format="pulse", loglevel="panic")
            #    .output("pipe:", format="s16le", acodec="pcm_s16le", ac=1, ar=SAMPLE_RATE)
            #    .run_async(pipe_stdout=True)
            #)
            # i love arecord now
            command = ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1", "-"]
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except ffmpeg.Error as e:
            raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e
        self.buffer = np.empty(0, dtype=np.int16)

    def stop(self):
        self.process.send_signal(signal.SIGINT)
        #self.process.terminate()

def transcribe(stream):
    print("transcribing...")
    result = model.transcribe(stream.buffer, language="en")
    print("done transcribing:")
    print(result["text"])

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
    transcribe(stream)
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
    #print(f'Key {key} released')
    if key == keyboard.Key.menu and stream is not None:
        print("sending SIGINT")
        stream.stop()


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
