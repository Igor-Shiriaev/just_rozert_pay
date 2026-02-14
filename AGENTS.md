# Codex Agent

## Lint & type check
```bash
cd rozert-pay && poetry run mypy . ../shared-apps/rozert_pay_shared/
cd rozert-pay && poetry run pre-commit run --all-files
cd rozert-pay && poetry run pylint --ignore=migrations,tests,stubs rozert_pay/ code_checks/
```

## Tests
Setup script installs PostgreSQL and Redis. Run:
```bash
cd rozert-pay && poetry run pytest tests -v
```
