#!/usr/bin/env bash
set -euo pipefail

# Bypass pyenv shim (exit 127): put real python bin first in PATH
PYTHON_BIN=$(find /root/.pyenv/versions /root/.local/share/mise -path '*/bin/python' 2>/dev/null | head -1)
[[ -n "$PYTHON_BIN" ]] && export PATH="$(dirname "$PYTHON_BIN"):/root/.local/bin:$PATH"

export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get install -y --no-install-recommends postgresql postgresql-contrib redis-server
service postgresql start
redis-server --daemonize yes 2>/dev/null || service redis-server start

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='rozert_pay'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER rozert_pay WITH PASSWORD 'rozert_pay' CREATEDB;"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='rozert_pay'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE rozert_pay OWNER rozert_pay;"

cd rozert-pay
REPO_ROOT="$(pwd)/.."

poetry install --with dev --no-interaction

{
  echo "export PYTHONPATH=\"$REPO_ROOT/shared-apps:$REPO_ROOT/rozert-pay:\$PYTHONPATH\""
  echo "export DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest"
  echo "export POSTGRES_HOST=localhost"
  echo "export REDIS_HOST=localhost"
} >> ~/.bashrc

export PYTHONPATH="$REPO_ROOT/shared-apps:$REPO_ROOT/rozert-pay"
export DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest
export POSTGRES_HOST=localhost
export REDIS_HOST=localhost
poetry run python manage.py migrate --noinput
