#!/usr/bin/env bash
set -euo pipefail

# Disable pyenv influence in cloud runners where shims can be present but broken.
unset PYENV_VERSION PYENV_ROOT PYENV_SHELL PYENV_VIRTUALENV_INIT
export PATH="$(echo "$PATH" | tr ':' '\n' | grep -Ev '/\.pyenv/(shims|bin)(/|$)' | paste -sd ':' -)"
export PATH="/usr/bin:/usr/sbin:$PATH"
hash -r

service postgresql start 2>/dev/null || true
redis-server --daemonize yes 2>/dev/null || service redis-server start 2>/dev/null || true

cd rozert-pay
export POETRY_PYTHON=/usr/bin/python3
export POETRY_VIRTUALENVS_USE_POETRY_PYTHON=true
export POETRY_VIRTUALENVS_PREFER_ACTIVE_PYTHON=false
poetry install --with dev --no-interaction
