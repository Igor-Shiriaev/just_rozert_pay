#!/usr/bin/env bash
set -euo pipefail

service postgresql start 2>/dev/null || true
redis-server --daemonize yes 2>/dev/null || service redis-server start 2>/dev/null || true

cd rozert-pay
poetry install --with dev --no-interaction
