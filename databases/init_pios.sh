#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PG_INIT_SQL="${SCRIPT_DIR}/pg_init.sql"

DATABASE_URL="${DATABASE_URL:-postgresql://postgres:password@localhost:5432/pios}"

if [[ ! -f "${PG_INIT_SQL}" ]]; then
  echo "Schema file not found: ${PG_INIT_SQL}" >&2
  exit 1
fi

parse_database_url() {
  local url="${1#postgresql://}"
  local userpass="${url%%@*}"
  local hostportdb="${url#*@}"
  local hostport="${hostportdb%%/*}"
  local db="${hostportdb#*/}"

  PGUSER="${userpass%%:*}"
  PGPASSWORD="${userpass#*:}"
  PGHOST="${hostport%%:*}"
  PGPORT="${hostport#*:}"
  PGDATABASE="${db%%\?*}"

  export PGUSER PGPASSWORD PGHOST PGPORT
}

parse_database_url "${DATABASE_URL}"

ADMIN_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/postgres"

if ! psql "${ADMIN_URL}" -tAc "SELECT 1 FROM pg_database WHERE datname = 'pios'" | grep -q 1; then
  echo "Creating database pios..."
  psql "${ADMIN_URL}" -v ON_ERROR_STOP=1 -c "CREATE DATABASE pios;"
fi

echo "Applying schema from ${PG_INIT_SQL}..."
psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -f "${PG_INIT_SQL}"

echo "PIOS schema initialized."
