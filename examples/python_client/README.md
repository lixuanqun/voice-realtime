# Python realtime client

This minimal client connects to a local `voice-realtime` gateway using the OpenAI Realtime WebSocket event format. It sends `session.update`, optionally appends a raw PCM16 audio file with `input_audio_buffer.append`, and saves received `response.audio.delta` audio to a PCM16 file.

## Prerequisites

- Python 3.10 or later
- A running local gateway. From the repository root, configure a provider key in `.env` and run `go run ./cmd/voice-realtime`.

## Run

```bash
cd examples/python_client
python -m venv .venv
```

Activate the virtual environment on macOS or Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On Windows Command Prompt, use `.venv\Scripts\activate.bat` instead.

Then install the dependency and run the client:

```bash
python -m pip install -r requirements.txt
python realtime_client.py
```

The default URL uses the Zhipu provider. Change it with `--url` to select another supported provider:

```bash
python realtime_client.py --url "ws://localhost:8080/v1/realtime?provider=stepfun&model=stepaudio-2.5-realtime"
```

To send audio, provide a raw 24 kHz mono PCM16 file. The returned PCM16 data is saved to `response.pcm` by default:

```bash
python realtime_client.py --audio input.pcm --output response.pcm
```

The example deliberately keeps playback out of scope. Use any PCM16-capable player or convert the output to WAV for local playback.

Audio is uploaded in chunks of at most 18,000 raw bytes so each base64-encoded JSON event stays below the gateway's default 32 KiB WebSocket read limit. Connection and socket operations use a 30-second timeout so a stalled gateway does not leave the client waiting indefinitely. This is a per-operation timeout, not a limit on the total response duration. The connection is closed on both success and failure.

## Tests

With the virtual environment active and the dependency installed, run this from the repository root:

```bash
python -m unittest examples.python_client.test_realtime_client
```

The tests use a mock transport and temporary audio files. No running gateway or provider API key is needed. They cover client startup and cleanup, audio chunk sizes and event ordering, response audio reassembly, missing audio deltas, gateway errors, unsuccessful responses, and receive timeouts.
