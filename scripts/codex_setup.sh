#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  sudo \
  python3 python3-venv python3-pip python3-poetry \
  postgresql postgresql-contrib \
  redis-server

# Remove pyenv shims from PATH (they can exist but be non-functional in cloud runners)
export PATH="$(echo "$PATH" | tr ':' '\n' | grep -v '^/root/.pyenv/shims$' | paste -sd ':' -)"
# Prefer system binaries
export PATH="/usr/bin:/usr/sbin:$PATH"
hash -r

service postgresql start
redis-server --daemonize yes 2>/dev/null || service redis-server start

# Create role/db (works even if sudo is quirky; we're root)
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='rozert_pay'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER rozert_pay WITH PASSWORD 'rozert_pay' CREATEDB;"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='rozert_pay'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE rozert_pay OWNER rozert_pay;"

cd rozert-pay
REPO_ROOT="$(pwd)/.."

# Use system poetry explicitly to avoid any poetry executable tied to pyenv shims
POETRY=/usr/bin/poetry

# Force poetry to use system python for the venv it creates
$POETRY env use /usr/bin/python3 || true

$POETRY install --with dev --no-interaction

{
  echo "export PYTHONPATH=\"$REPO_ROOT/shared-apps:$REPO_ROOT/rozert-pay:\$PYTHONPATH\""
  echo "export DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest"
  echo "export POSTGRES_HOST=localhost"
  echo "export POSTGRES_PORT=5432"
  echo "export REDIS_HOST=localhost"
} >> ~/.bashrc

export PYTHONPATH="$REPO_ROOT/shared-apps:$REPO_ROOT/rozert-pay"
export DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export REDIS_HOST=localhost

$POETRY run python manage.py migrate --noinput
