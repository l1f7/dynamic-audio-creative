# Weather Radio Ad Pipeline — Pilot

End-to-end pipeline that generates a weather-sponsored radio ad:
**Fetch weather** -> **Generate script (Claude)** -> **Voiceover (ElevenLabs)** -> **Mix with music (FFmpeg)** -> **Broadcast-ready MP3**

## Prerequisites

- Python 3.11+
- FFmpeg installed (`brew install ffmpeg` on Mac)
- Anthropic API key
- ElevenLabs API key

## Setup

```bash
cd weather-radio-pilot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Add your API keys to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
```

Place a background music MP3 at `./assets/music_bed.mp3`.

## Run

```bash
python main.py
```

Output lands in `./output/final_ad.mp3`.

## Project Structure

| File | Purpose |
|------|---------|
| `main.py` | Entry point — runs full pipeline |
| `weather.py` | Fetch + parse Environment Canada XML feed |
| `script_gen.py` | Build Claude prompt + generate ad script |
| `voiceover.py` | Generate voiceover via ElevenLabs |
| `mixer.py` | Mix voiceover with music bed via FFmpeg |
| `config.py` | Advertiser data + constants |
