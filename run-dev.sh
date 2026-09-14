#!/usr/bin/env bash
# 一键启动:后端(8000)+ 前端开发服务器(5173)
set -e
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt

if [ ! -f backend/museum.db ]; then
  (cd backend && ../backend/.venv/bin/python -m app.seed)
fi

(cd frontend && [ -d node_modules ] || npm install)

(cd backend && ../backend/.venv/bin/uvicorn app.main:app --reload --port 8000) &
BACK_PID=$!
(cd frontend && npm run dev) &
FRONT_PID=$!

trap "kill $BACK_PID $FRONT_PID 2>/dev/null" EXIT
wait
