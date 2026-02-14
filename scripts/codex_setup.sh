#!/usr/bin/env bash
set -euo pipefail

# Load Codex runtime env so poetry finds Python (mise/pyenv)
export PATH="/root/.local/bin:/root/.pyenv/shims:/root/.pyenv/bin:/root/.local/share/mise/shims:$PATH"
eval "$(mise activate bash 2>/dev/null)" || true
eval "$(pyenv init - bash 2>/dev/null)" || true
# Point poetry to pyenv python directly (shim returns 127 in Codex setup context)
PYENV_PYTHON=$(find /root/.pyenv/versions -path '*/bin/python' 2>/dev/null | head -1)
[[ -n "$PYENV_PYTHON" ]] && export POETRY_PYTHON="$PYENV_PYTHON"

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

# Login shell loads /etc/profile with pyenv init; needed for poetry to find python
bash -l -c "poetry install --with dev --no-interaction"

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
bash -l -c "poetry run python manage.py migrate --noinput"
