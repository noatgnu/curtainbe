#!/bin/bash
set -e

# Use environment variables with fallback to command line arguments
POSTGRES_HOST="${POSTGRES_HOST:-${1:-localhost}}"
POSTGRES_PORT="${POSTGRES_PORT:-${2:-5432}}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-${POSTGRES_NAME:-postgres}}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# Shift arguments if they were provided
if [ $# -ge 2 ]; then
  shift 2
fi
cmd="$@"

>&2 echo "=== Database Connection Check ==="
>&2 echo "POSTGRES_HOST: ${POSTGRES_HOST}"
>&2 echo "POSTGRES_PORT: ${POSTGRES_PORT}"
>&2 echo "POSTGRES_USER: ${POSTGRES_USER}"
>&2 echo "POSTGRES_DB: ${POSTGRES_DB}"
>&2 echo "================================="

# Function to check TCP connectivity
check_tcp_connection() {
  timeout 2 bash -c "cat < /dev/null > /dev/tcp/${POSTGRES_HOST}/${POSTGRES_PORT}" 2>/dev/null
}

# Function to check postgres using pg_isready
check_postgres_isready() {
  pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1
}

# Function to check postgres using psql
check_postgres_psql() {
  if [ -n "$POSTGRES_PASSWORD" ]; then
    PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1" > /dev/null 2>&1
  else
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1" > /dev/null 2>&1
  fi
}

# Wait for PostgreSQL with timeout
max_attempts=60
attempt=0

>&2 echo "Starting connection attempts (max: $max_attempts, timeout: 2 seconds each)..."

while [ $attempt -lt $max_attempts ]; do
  attempt=$((attempt + 1))

  # First check if we can even reach the host/port
  if ! check_tcp_connection; then
    if [ $attempt -ge $max_attempts ]; then
      >&2 echo "ERROR: Cannot establish TCP connection to ${POSTGRES_HOST}:${POSTGRES_PORT}"
      >&2 echo "Please verify that:"
      >&2 echo "  1. The database service is running"
      >&2 echo "  2. POSTGRES_HOST environment variable is set correctly"
      >&2 echo "  3. The database is accessible from this container"
      exit 1
    fi
    >&2 echo "⏳ Waiting for TCP connection to ${POSTGRES_HOST}:${POSTGRES_PORT} - attempt $attempt/$max_attempts..."
    sleep 2
    continue
  fi

  # TCP connection works, now try pg_isready
  if check_postgres_isready; then
    >&2 echo "✓ Postgres is ready (verified with pg_isready)"
    break
  fi

  # If pg_isready fails, try psql as fallback
  if check_postgres_psql; then
    >&2 echo "✓ Postgres is ready (verified with psql)"
    break
  fi

  if [ $attempt -ge $max_attempts ]; then
    >&2 echo "ERROR: Postgres failed to become available after $max_attempts attempts ($(($max_attempts * 2)) seconds)"
    >&2 echo "TCP connection succeeded but database is not accepting connections"
    exit 1
  fi

  >&2 echo "⏳ Postgres accepting TCP but not ready - attempt $attempt/$max_attempts..."
  sleep 2
done

>&2 echo "Postgres is up - checking Redis"

# Wait for Redis with timeout (if Redis variables are set)
if [ -n "$REDIS_HOST" ]; then
  attempt=0
  REDIS_PORT="${REDIS_PORT:-6379}"

  if [ -n "$REDIS_PASSWORD" ]; then
    until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; do
      attempt=$((attempt + 1))
      if [ $attempt -ge $max_attempts ]; then
        >&2 echo "Redis failed to become available after $max_attempts attempts"
        exit 1
      fi
      >&2 echo "Redis is unavailable - attempt $attempt/$max_attempts - sleeping"
      sleep 2
    done
  else
    until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; do
      attempt=$((attempt + 1))
      if [ $attempt -ge $max_attempts ]; then
        >&2 echo "Redis failed to become available after $max_attempts attempts"
        exit 1
      fi
      >&2 echo "Redis is unavailable - attempt $attempt/$max_attempts - sleeping"
      sleep 2
    done
  fi
  >&2 echo "Redis is up"
else
  >&2 echo "Redis check skipped (REDIS_HOST not set)"
fi

>&2 echo "All services are up - executing command"
exec $cmd
