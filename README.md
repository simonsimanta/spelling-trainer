# Spelling Trainer

Dedicated spelling trainer with a FastAPI backend, React/Vite frontend, SQLite or PostgreSQL persistence, Oxford 5000 ingestion, OpenAI TTS audio caching, cached AI word content, practice sessions, dictation, progress, and achievements.

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
3. Install frontend dependencies:
   - `cd web`
   - `npm install`
4. Start both apps from the repo root:
   - `./start_local.sh`

Backend runs on `http://127.0.0.1:8000`.
Frontend runs on `http://127.0.0.1:5173`.

## Frontend API Base URL
Set this before `npm run dev` if the API is not on the default local port:

```bash
export VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Database And Environment Readiness

`./start_local.sh` creates, migrates, and uses `data/spelling_trial.db` by default. This local database avoids internet round trips during practice and persists between restarts. A Supabase URL in `.env` remains untouched for deployment and backup work.

Set `APP_DATABASE_URL` to override the database for a single local run:

```bash
APP_DATABASE_URL=sqlite:///./data/another.db ./start_local.sh
```

Commands that do not set `APP_DATABASE_URL` continue to read `DATABASE_URL` from `.env`.

Local SQLite:

```dotenv
DATABASE_URL=sqlite:///./data/spelling.db
```

Supabase PostgreSQL:

1. Open the Supabase project and use **Connect** to copy its current connection string.
2. For this persistent local FastAPI process, use the Session pooler connection on port `5432` when direct IPv6 is unavailable.
3. Change the URI scheme to `postgresql+psycopg://` if the copied value starts with `postgresql://`.
4. Put the complete URI in `.env` as `DATABASE_URL`. Do not commit it.
5. Run `python -m alembic upgrade head`, then restart the backend.

To run the local app directly against Supabase, set `APP_DATABASE_URL` to the Supabase URI before starting it. The local trial database and Supabase are independent; this release does not automatically synchronise attempts between them.

Diagnostic endpoints:

- `GET /health` is a liveness check. It returns while the API process is running, even if the database is unavailable.
- `GET /readiness` checks the database connection, migration/schema version, OpenAI configuration, Oxford PDFs, and audio-cache write access.
- Settings displays the same readiness report with concrete recovery actions.

Supabase transaction pooler connections on port `6543` are intended for short-lived/serverless workloads and do not support prepared statements. Prefer the connection string recommended by the Supabase dashboard for the backend's runtime.

## Oxford Words And Audio
- Load Oxford words with `python -m scripts.load_oxford_core5k`.
- Generate cached AI word content from Settings in the app or `POST /spelling/content/bulk-generate`.
- Generate OpenAI TTS audio from Settings in the app or `POST /spelling/audio/bulk-generate`.
- The default development bulk limit is 100 words per run.
