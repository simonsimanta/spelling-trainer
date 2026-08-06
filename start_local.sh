#!/bin/bash

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Spelling Trainer ===${NC}"
echo "Starting local development environment..."

if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo -e "${GREEN}OK${NC} Python virtual environment activated"
else
    echo "Error: .venv directory not found."
    exit 1
fi

mkdir -p data
LOCAL_DB_URL="${APP_DATABASE_URL:-sqlite:///./data/spelling_trial.db}"

echo ""
echo -e "${BLUE}Preparing durable local trial database${NC}"
APP_DATABASE_URL="$LOCAL_DB_URL" .venv/bin/python -m alembic upgrade head

echo ""
echo -e "${BLUE}Starting FastAPI Backend on http://127.0.0.1:8000${NC}"
APP_DATABASE_URL="$LOCAL_DB_URL" .venv/bin/python -m uvicorn app.backend.api:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

echo "Waiting for backend..."
sleep 3

echo ""
echo -e "${BLUE}Starting React Frontend on http://127.0.0.1:5173${NC}"
cd web
npm run dev

echo ""
echo "Shutting down..."
kill $BACKEND_PID 2>/dev/null || true
echo -e "${GREEN}OK${NC} All services stopped"
