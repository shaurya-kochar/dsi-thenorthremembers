#!/usr/bin/env bash
# Start the InfoBridge demo: the API (with Gemini text extraction) and the four-screen app.
#   scripts/run_demo.sh            -> app on http://localhost:8501, API on http://localhost:8000
#   SHARE=1 scripts/run_demo.sh    -> also listen on the local network (http://<this-ip>:8501)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin
API_PORT=${API_PORT:-8000}
APP_PORT=${APP_PORT:-8501}
ADDRESS=$([ "${SHARE:-0}" = 1 ] && echo 0.0.0.0 || echo localhost)

INFOBRIDGE_API_LLM_EXTRACTION=${INFOBRIDGE_API_LLM_EXTRACTION:-1} \
  $PY/uvicorn infobridge.api:app --port "$API_PORT" --log-level warning &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

echo "API: http://localhost:$API_PORT/docs"
echo "App: http://localhost:$APP_PORT"
INFOBRIDGE_API_URL="http://127.0.0.1:$API_PORT" $PY/streamlit run app.py \
  --server.port "$APP_PORT" --server.address "$ADDRESS" --server.headless true --browser.gatherUsageStats false
