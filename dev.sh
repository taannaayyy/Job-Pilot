#!/bin/sh
# Runs the backend and the UI together.
# Ports can be changed with JOBPILOT_PORT (backend, default 8766; the installed app uses 8765) and JOBPILOT_UI_PORT (UI, default 5173).
cd "$(dirname "$0")"

export JOBPILOT_PORT="${JOBPILOT_PORT:-8766}"
export JOBPILOT_UI_PORT="${JOBPILOT_UI_PORT:-5173}"

busy=0
for port in "$JOBPILOT_PORT" "$JOBPILOT_UI_PORT"; do
  pid=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1)
  if [ -n "$pid" ]; then
    echo "Port $port is already used by: $(ps -o command= -p "$pid" | cut -c1-120)"
    busy=1
  fi
done
if [ "$busy" = 1 ]; then
  echo "Stop that process, or pick other ports, e.g.: JOBPILOT_UI_PORT=5180 JOBPILOT_PORT=8770 ./dev.sh"
  exit 1
fi

trap 'kill 0' EXIT INT TERM
(cd backend && uv run jobpilot) &
(cd frontend && npm run dev) &
echo "Job Pilot: http://127.0.0.1:$JOBPILOT_UI_PORT"
wait
