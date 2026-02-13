
# Development

## Start server

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
