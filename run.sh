#!/usr/bin/env bash
# Menjalankan aplikasi. Mode dev: ./run.sh   |   Produksi: ./run.sh prod
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
if [ "${1:-dev}" = "prod" ]; then
  exec .venv/bin/gunicorn -w 3 -b "${HOST:-0.0.0.0}:${PORT:-8000}" wsgi:app
else
  exec .venv/bin/flask --app wsgi run --debug -p "${PORT:-5000}"
fi
