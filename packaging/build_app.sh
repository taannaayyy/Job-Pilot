#!/bin/sh
# Builds dist/Job Pilot.app: the React UI, then the Python backend + window bundled with PyInstaller.
set -e
cd "$(dirname "$0")/.."

(cd frontend && npm run build)
(cd backend && uv run pyinstaller --noconfirm --clean \
  --distpath ../dist --workpath ../build ../packaging/jobpilot.spec)

echo
echo "Built: dist/Job Pilot.app"
echo "Install: rm -rf '/Applications/Job Pilot.app' && cp -R 'dist/Job Pilot.app' /Applications/"
