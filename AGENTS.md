# Codex Agent

## Setup (run once)
```bash
cd rozert-pay && make agent-setup
```
Or: `bash scripts/codex_setup.sh` from repo root.

## Maintenance (PG/Redis + deps)
```bash
cd rozert-pay && make agent-maintenance
```

## Lint & type check
```bash
cd rozert-pay && make agent-mypy
cd rozert-pay && make agent-lint
cd rozert-pay && make agent-pylint
```
Or: `make agent-check` for all.

## Tests
```bash
cd rozert-pay && make agent-pytest
```
