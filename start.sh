#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$ROOT/backend/.venv/bin/python" || ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo 'Install dependencies and build the frontend first; see README.md.' >&2
  exit 1
fi
echo 'HeadCount: http://127.0.0.1:8000 (Ctrl+C to stop)'
exec "$ROOT/backend/.venv/bin/python" -m uvicorn app.main:create_app --factory --app-dir "$ROOT/backend" --host 127.0.0.1 --port 8000
