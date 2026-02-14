
# Development

## Codex Agent (cloud) quick start

### Setup script (chatgpt.com/codex → Settings → Environments)

Paste into **Setup script**:

```bash
bash scripts/codex_setup.sh
```

Optional **Maintenance script** (runs when cached container resumes):

```bash
bash scripts/codex_maintenance.sh
```

**Environment variables** in Codex settings:
- `PYTHONPATH` — set automatically by setup script via ~/.bashrc
- Pin Python 3.11+ (project uses `^3.11`)

### Docker flow (CI / local)

```bash
make setup
make up
make test
make down
```

Notes for CI/cloud:

- `make setup` checks `docker`, `docker compose`, `make`, and creates `.env` from `.env.example` if needed.
- `make up` runs `docker compose up -d --wait` and waits for healthy dependencies.
- To avoid name collisions between concurrent runners, set a unique compose project name:

```bash
COMPOSE_PROJECT_NAME=rozert-pay-${RUN_ID} make up
```

## Запуск без Docker (локально)

### 1. Установка зависимостей (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib redis-server rabbitmq-server
sudo service postgresql start
sudo service redis-server start
sudo service rabbitmq-server start
```

### 2. База данных

```bash
sudo -u postgres psql -c "CREATE USER rozert_pay WITH PASSWORD 'rozert_pay' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE rozert_pay OWNER rozert_pay;"
```

### 3. Конфигурация

```bash
cd rozert-pay
cp .env.example .env
```

Для локального Postgres (порт 5432) в `.env` укажи: `DB_PORT=5432`, `POSTGRES_HOST=localhost`, `REDIS_HOST=localhost`.

### 4. Python-зависимости и миграции

```bash
export PYTHONPATH="../shared-apps:$(pwd):../common"
poetry install --with dev
poetry run python manage.py migrate --noinput
```

### 5. Запуск (3 терминала)

**Терминал 1 — Django:**
```bash
cd rozert-pay
export PYTHONPATH="../shared-apps:$(pwd):../common"
poetry run python manage.py startserver 0.0.0.0:8000
```

**Терминал 2 — Celery worker:**
```bash
cd rozert-pay
export PYTHONPATH="../shared-apps:$(pwd):../common"
poetry run celery -A rozert_pay.celery_app worker -l info -Q high,normal,low --pool threads -c 20
```

**Терминал 3 — Celery beat:**
```bash
cd rozert-pay
export PYTHONPATH="../shared-apps:$(pwd):../common"
poetry run celery -A rozert_pay.celery_app beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Приложение: http://localhost:8000

---

## Start server (Docker)

```
make dev-build
make dev-up

# wait for the front_devserver to install dependepcies.
# You can check installation log via
# docker compose logs -f front_devserver
```


It runs docker-compose with all requirement services at http://localhost:8006

You can access:

```
http://localhost:8006/admin/ --- admin panel
http://localhost:8006/backoffice --- merchant backoffice
http://localhost:8006/redoc/public/ --- public API docs
```

## Локальный запуск команд

При выполнении Django-команд или скриптов вне Docker нужно прописать общий каталог приложений в `PYTHONPATH`, иначе импорт модулей из `../shared-apps` завершится ошибкой:

```
export PYTHONPATH="../shared-apps:${PYTHONPATH}"
poetry run python manage.py migrate
```

## Install pre-commit hook

```
pre-commit install
```


## Run tests in container

Assume container is build (`make dev-build`)

Run tests:

```
make dev-web-bash
pytest .
```

Run mypy:

```
make dev-web-bash
make mypy
```

## DB inialization

To initialize the database with data from staging:

* **If you have access to staging kube env:**
  * Create .env.preprod.local file with credentials for stage:
    * go to API pod
    * run env | grep POSTGRES -> save data to the project root in .env.preprod.local
* **If you don't have access**
  * Ask developers for dump.sql file, put it into project roon
* Run ./bin/load_dump.sh

## Typescript client generation

Client generation works like that:

* `./manage.py startserver` on each code reload calls spectacular to update schema in `swagger.yml`
* `client_generator` container runs script `generate-client.ts` which tracks changes in `swagger.yml`
* If `swagger.yml` changes, it generates client and puts it in `client` folder

So if you run all services via `make dev-up` all should work automatically.


## Test payment systems with callbacks using ngrok

* Install ngrok: https://ngrok.com/
* Run `./manage.py ngrok <system> [--port <local_port>]`
* It will create webhooks for ngrok host, so you can initiate payments locally
* When done, stop command, it will remove all ngrok webhooks.
