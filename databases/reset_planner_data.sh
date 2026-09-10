#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESET_SQL="${SCRIPT_DIR}/reset_planner_data.sql"

DATABASE_URL="${DATABASE_URL:-postgresql://postgres:password@localhost:5432/pios}"

if [[ ! -f "${RESET_SQL}" ]]; then
  echo "Reset file not found: ${RESET_SQL}" >&2
  exit 1
fi

echo "Clearing planner scheduling data..."
psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -f "${RESET_SQL}"
echo "Done. Cleared: events, planning_runs, goals."
