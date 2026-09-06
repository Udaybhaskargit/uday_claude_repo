#!/bin/bash
set -euo pipefail

echo "=== Bootstrapping ClaimFlow dev environment ==="

# Backend dependencies
if [ -d "backend" ]; then
  cd backend && pip install -r requirements.txt && cd ..
fi

# Frontend dependencies
if [ -d "frontend" ]; then
  cd frontend && npm ci && cd ..
fi

# Environment
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — add your API keys"
fi

# Start local dev servers
echo "Starting backend (http://localhost:8000) ..."
(cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ../backend.log 2>&1 &)

echo "Starting frontend (http://localhost:5173) ..."
(cd frontend && npm run dev -- --host --port 5173 > ../frontend.log 2>&1 &)

# Health checks
echo "Waiting for services..."
for i in $(seq 1 5); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend healthy."
    break
  fi
  sleep 2
done

for i in $(seq 1 5); do
  if curl -sf http://localhost:5173 > /dev/null 2>&1; then
    echo "Frontend healthy."
    break
  fi
  sleep 2
done

echo "=== Environment ready ==="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
