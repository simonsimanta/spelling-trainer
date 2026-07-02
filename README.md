# Spelling Trainer

Dedicated spelling trainer with a FastAPI backend, React/Vite frontend, SQLite persistence, Oxford 5000 ingestion, OpenAI TTS audio caching, cached AI word content, practice sessions, dictation, progress, and achievements.

## Project Structure
- `app/backend`: FastAPI API, SQLAlchemy models, spelling repository, and DB config
- `app/backend/spelling`: small API service wrappers for spelling modules
- `web`: React + TypeScript + Vite frontend
- `scripts`: Oxford 3000/5000 ingestion and enrichment helpers
- `data`: local SQLite and cached spelling audio

## Quick Start
1. Create environment and install Python dependencies:
   - `python -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Copy env file:
   - `cp .env.example .env`
3. Apply database migrations:
   - `python -m alembic upgrade head`
4. Install frontend dependencies:
   - `cd web`
   - `npm install`
5. Start both apps from the repo root:
   - `./start_local.sh`

Backend runs on `http://127.0.0.1:8000`.
Frontend runs on `http://127.0.0.1:5173`.

## Frontend API Base URL
Set this before `npm run dev` if the API is not on the default local port:

```bash
export VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Oxford Words And Audio
- Load Oxford words with `python scripts/load_oxford_core5k.py`.
- Generate cached AI word content from Settings in the app or `POST /spelling/content/bulk-generate`.
- Generate OpenAI TTS audio from Settings in the app or `POST /spelling/audio/bulk-generate`.
- The default development bulk limit is 100 words per run.
