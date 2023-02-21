# LiveSynth
LiveSynth is a program that allows you to generate a voice with AI using OpenAI's Whisper and the ElevenLabs API. By holding a key, you can record your voice, have it transcribed, and used to generate an AI voice from what you said. I use this to give myself an interesting voice in games. Windows is not and will not be supported lol.

## Requirements
- Linux
- PipeWire or PulseAudio
- CUDA

## Usage

`python whisper.py --voice 21m00Tcm4TlvDq8ikWAM --api-key <your xi-api-key>`

The default whisper model requires 5GB of vram. This can be changed with `--model`. The available whisper models are documented [here](https://github.com/openai/whisper#available-models-and-languages)

To output to a custom sink (useful for using as an input device) you can use the `--output-sink` option which expects the name or serial of the sink.

`--input-sink` is also available to choose a specific input.

Creating a virtual sink (named LiveSynth) and source (named LiveSynthSource) can be done with a couple commands:
```
pactl load-module module-null-sink sink_name="LiveSynth" sink_properties=device.description="LiveSynth Sink"
pactl load-module module-remap-source master="LiveSynth.monitor" source_name="LiveSynthSource" source_properties=device.description="LiveSynth Source"
```

## Caveats
- Whisper uses a lot of VRAM (5GB for medium)
- The ElevenLabs API often takes a while to return a result. Hopefully open source AI voice will catch up soon because this sucks.
