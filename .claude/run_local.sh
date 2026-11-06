#!/usr/bin/env bash
# Local launcher for Ploppy (Streamlit). Override DATABASE_URL to point at another Postgres.
set -euo pipefail
cd "$(dirname "$0")/.."
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://$(whoami)@127.0.0.1:5432/ploppy}"
exec .venv/bin/streamlit run ploppy.py \
  --server.port "${PORT:-8501}" --server.address 127.0.0.1 --server.headless true
