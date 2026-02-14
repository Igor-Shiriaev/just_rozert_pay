#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  sudo \
  python3 python3-venv python3-pip python3-poetry \
  postgresql postgresql-contrib \
  redis-server

# Disable pyenv influence in cloud runners where shims can be present but broken.
unset PYENV_VERSION PYENV_ROOT PYENV_SHELL PYENV_VIRTUALENV_INIT
export PATH="$(echo "$PATH" | tr ':' '\n' | grep -Ev '/\.pyenv/(shims|bin)(/|$)' | paste -sd ':' -)"
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

# Select poetry binary available in the container.
if [[ -x /usr/bin/poetry ]]; then
  POETRY=/usr/bin/poetry
else
  POETRY="$(command -v poetry)"
fi

# Force poetry to use system python and ignore any active/pyenv interpreter.
export POETRY_PYTHON=/usr/bin/python3
export POETRY_VIRTUALENVS_USE_POETRY_PYTHON=true
export POETRY_VIRTUALENVS_PREFER_ACTIVE_PYTHON=false

$POETRY install --with dev --no-interaction

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

$POETRY run python manage.py migrate --noinput
