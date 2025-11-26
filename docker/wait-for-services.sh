#!/bin/bash
set -e

# Use environment variables
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-${POSTGRES_NAME:-postgres}}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# Generate instance ID for tracking multiple containers
INSTANCE_ID="[Container-$$]"

echo "${INSTANCE_ID} Checking database connection..." >&2

# Function to check postgres using pg_isready
check_postgres() {
  pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1
}

# Wait for PostgreSQL
max_attempts=60
attempt=0

while [ $attempt -lt $max_attempts ]; do
  if check_postgres; then
    echo "${INSTANCE_ID} ✓ Database ready" >&2
    break
  fi

  attempt=$((attempt + 1))

  if [ $attempt -ge $max_attempts ]; then
    echo "${INSTANCE_ID} ERROR: Database not available after $max_attempts attempts" >&2
    exit 1
  fi

  # Only log every 5 attempts to reduce noise
  if [ $((attempt % 5)) -eq 1 ] || [ $attempt -eq 1 ]; then
    echo "${INSTANCE_ID} Waiting for database (attempt $attempt/$max_attempts)..." >&2
  fi

  sleep 2
done

# Wait for Redis (if configured)
if [ -n "$REDIS_HOST" ]; then
  REDIS_PORT="${REDIS_PORT:-6379}"
  attempt=0

  while [ $attempt -lt $max_attempts ]; do
    if [ -n "$REDIS_PASSWORD" ]; then
      if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
        echo "${INSTANCE_ID} ✓ Redis ready" >&2
        break
      fi
    else
      if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        echo "${INSTANCE_ID} ✓ Redis ready" >&2
        break
      fi
    fi

    attempt=$((attempt + 1))

    if [ $attempt -ge $max_attempts ]; then
      echo "${INSTANCE_ID} ERROR: Redis not available after $max_attempts attempts" >&2
      exit 1
    fi

    if [ $((attempt % 5)) -eq 1 ] || [ $attempt -eq 1 ]; then
      echo "${INSTANCE_ID} Waiting for Redis (attempt $attempt/$max_attempts)..." >&2
    fi

    sleep 2
  done
fi

echo "${INSTANCE_ID} ✓ All services ready - starting application" >&2
exec "$@"

