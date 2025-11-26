#!/bin/bash
set -e

# Only run the wait logic if we're the main process (PID 1)
# This prevents the script from running multiple times when gunicorn forks workers
if [ $$ -eq 1 ]; then
  POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
  POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  POSTGRES_USER="${POSTGRES_USER:-postgres}"
  POSTGRES_DB="${POSTGRES_DB:-${POSTGRES_NAME:-postgres}}"

  echo "Waiting for database at ${POSTGRES_HOST}:${POSTGRES_PORT}..." >&2

  # Wait for PostgreSQL
  max_attempts=60
  attempt=0

  while [ $attempt -lt $max_attempts ]; do
    if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1; then
      echo "✓ Database ready" >&2
      break
    fi

    attempt=$((attempt + 1))

    if [ $attempt -ge $max_attempts ]; then
      echo "ERROR: Database not available after $max_attempts attempts" >&2
      exit 1
    fi

    if [ $((attempt % 10)) -eq 1 ]; then
      echo "Waiting for database... (attempt $attempt/$max_attempts)" >&2
    fi

    sleep 2
  done

  # Wait for Redis (if configured)
  if [ -n "$REDIS_HOST" ]; then
    echo "Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT:-6379}..." >&2
    REDIS_PORT="${REDIS_PORT:-6379}"
    attempt=0

    while [ $attempt -lt $max_attempts ]; do
      if [ -n "$REDIS_PASSWORD" ]; then
        redis_check=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning ping 2>&1)
        redis_exit_code=$?
      else
        redis_check=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>&1)
        redis_exit_code=$?
      fi

      if [ $redis_exit_code -eq 0 ] && echo "$redis_check" | grep -q "PONG"; then
        echo "✓ Redis ready" >&2
        break
      fi

      attempt=$((attempt + 1))

      if [ $attempt -ge $max_attempts ]; then
        echo "ERROR: Redis not available after $max_attempts attempts" >&2
        echo "Last Redis response: $redis_check" >&2
        echo "Exit code: $redis_exit_code" >&2
        exit 1
      fi

      if [ $((attempt % 10)) -eq 1 ]; then
        echo "Waiting for Redis... (attempt $attempt/$max_attempts)" >&2
        echo "Redis check output: '$redis_check'" >&2
      fi

      sleep 2
    done
  fi

  echo "✓ All services ready - starting application" >&2
fi

# Execute the command
exec "$@"

