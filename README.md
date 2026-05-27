# Dynamic Audio Creative

A Flask web application that generates dynamic radio advertisements by combining live data feeds, AI copywriting, and audio synthesis. Each ad run:

1. Fetches live context data (weather, events, etc.)
2. Generates an ad script via Anthropic Claude
3. Produces a voiceover via ElevenLabs TTS
4. Mixes the voiceover with a music bed using FFmpeg
5. Uploads the finished ad to S3-compatible storage

## Prerequisites

- Python 3.11+
- FFmpeg (`brew install ffmpeg` on macOS)
- Redis (optional — required only for background job queue in Phase 3)

## Local Development Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd dynamic-audio-creative
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values (see [Environment Variables](#environment-variables) below).

### 4. Initialise the database

```bash
flask db upgrade
```

This creates a local SQLite database (`dev.db`) and applies all migrations.

### 5. Start the development server

```bash
flask run
```

The app runs at `http://localhost:5000`. The admin dashboard is at `http://localhost:5000/admin`.

Log in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` values from your `.env`.

---

## Environment Variables

Copy `.env.example` to `.env` and set the following:

### Required

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session signing key — any long random string |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `ELEVENLABS_API_KEY` | ElevenLabs text-to-speech API key |
| `S3_ENDPOINT_URL` | S3-compatible storage endpoint (e.g. Cloudflare R2, AWS S3, Backblaze B2) |
| `S3_ACCESS_KEY` | Storage access key ID |
| `S3_SECRET_KEY` | Storage secret access key |
| `S3_BUCKET` | Bucket name (default: `dynamic-audio`) |

### Optional / Defaults

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Set to `production` on Render |
| `DATABASE_URL` | `sqlite:///dev.db` | PostgreSQL connection string in production |
| `S3_REGION` | `auto` | Storage region (use `auto` for Cloudflare R2) |
| `ADMIN_USERNAME` | `admin` | Bootstrap admin login username |
| `ADMIN_PASSWORD` | `changeme` | Bootstrap admin login password |
| `API_KEY` | — | Machine-to-machine key for `/api/v1` endpoints |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model ID |
| `ELEVENLABS_MODEL` | `eleven_monolingual_v1` | ElevenLabs model ID |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection (Phase 3 background jobs) |

### Frequency Ad Server (not yet implemented)

| Variable | Description |
|---|---|
| `FREQUENCY_ENABLED` | Set to `true` to enable delivery (default: `false`) |
| `FREQUENCY_API_URL` | Frequency REST API endpoint |
| `FREQUENCY_API_KEY` | Frequency API key |
| `FREQUENCY_SFTP_HOST` | Frequency SFTP hostname |
| `FREQUENCY_SFTP_USER` | Frequency SFTP username |
| `FREQUENCY_SFTP_KEY` | Path to SFTP private key |

---

## Deployment (Render)

The `render.yaml` file defines the full Render Blueprint. Render will:

- Install dependencies (`pip install -r requirements.txt`)
- Run migrations before each deploy (`flask db upgrade`)
- Start the app with Gunicorn (`gunicorn wsgi:app --workers 2 --timeout 60`)
- Provision and connect a PostgreSQL database automatically

### Steps

1. Push the repo to GitHub.
2. Create a new **Blueprint** on [Render](https://render.com) pointing at your repo.
3. Render will detect `render.yaml` and provision all services.
4. In the Render dashboard, set the following environment variables (marked `sync: false` in the Blueprint — they are **not** auto-generated):

   - `ANTHROPIC_API_KEY`
   - `ELEVENLABS_API_KEY`
   - `S3_ENDPOINT_URL`
   - `S3_ACCESS_KEY`
   - `S3_SECRET_KEY`
   - `S3_BUCKET`
   - `S3_REGION`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
   - `FLASK_ENV` → `production`

   `SECRET_KEY`, `API_KEY`, and `DATABASE_URL` are generated/injected automatically by Render.

---

## Database Migrations

```bash
# Apply all pending migrations
flask db upgrade

# Create a new migration after model changes
flask db migrate -m "describe the change"
flask db upgrade

# Roll back one migration
flask db downgrade
```

---

## Running Tests

```bash
pytest
```

---

## Project Structure

```
app/
├── admin/          # Admin dashboard blueprint (CRUD UI, auth)
├── api/            # REST API blueprint (/api/v1/...)
├── models/         # SQLAlchemy models (Advertiser, Campaign, AdRun, ...)
├── pipeline/       # Ad generation orchestration
│   ├── runner.py   # Main pipeline orchestrator
│   ├── script_gen.py  # Claude copywriting
│   ├── voiceover.py   # ElevenLabs TTS
│   ├── mixer.py       # FFmpeg audio mixing
│   └── feeds/      # Data source plugins (weather, events, ...)
├── storage/        # S3-compatible storage wrapper
└── config.py       # Environment-based configuration

pilot/              # Standalone CLI pipeline (Phase 0 proof-of-concept)
migrations/         # Flask-Migrate / Alembic migration files
tests/              # Pytest test suite
```

## External Services

| Service | Purpose |
|---|---|
| Anthropic Claude | Ad script generation |
| ElevenLabs | Text-to-speech voiceover synthesis |
| S3-compatible storage | Store music beds and generated audio files |
| Environment Canada | Weather data feed (no API key required) |
| FFmpeg | Audio mixing and ducking |
| PostgreSQL | Production database (provided by Render) |
| Redis | Background job queue (Phase 3, optional in development) |
