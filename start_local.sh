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

echo ""
echo -e "${BLUE}Starting FastAPI Backend on http://127.0.0.1:8000${NC}"
.venv/bin/python -m uvicorn app.backend.api:app --host 127.0.0.1 --port 8000 --reload &
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
