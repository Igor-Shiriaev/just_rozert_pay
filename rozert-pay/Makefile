#
THIS_FILE := $(lastword $(MAKEFILE_LIST))

CLUSTER ?= develop
TARGET ?= rozert-pay
include ../Makefile-common.mk

########################################################

HELM_OPTIONS ?=

ifeq ($(CLUSTER),production)
HELMARGS_BACKEND ?= -f .helm/secrets.production.yaml
HELMARGS_FRONTEND ?=
else
HELMARGS_BACKEND ?= -f .helm/secrets.devs.yaml
HELMARGS_FRONTEND ?=
endif

########################################################

help:
	@awk 'BEGIN {FS = ":.*?## "} /^[0-9a-zA-Z_-]+:.*?## / {sub("\\\\n",sprintf("\n%22c"," "), $$2);printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

########################################################

all: build unittest ## Build and test project

build: build-backend ## Build project

build-backend:
	docker buildx build $(BUILDARG) --build-arg SHA=$(SHA) $(call CACHEARGS,backend) \
		--build-arg ENV=production \
		--rm -t ${REGISTRY}/rozert-pay-backend:$(TAG) \
		-f Dockerfile --target=release ../

build-frontend:
	docker buildx build $(BUILDARG) --build-arg SHA=$(SHA) $(call CACHEARGS,frontend) \
		--build-arg ENV=production \
		--rm -t ${REGISTRY}/rozert-pay-frontend:$(TAG) \
		-f front/Dockerfile --target=frontend-release front/

########################################################

unittest-stop:
	@docker compose -f docker compose.test.yml down ||:

migratetest: ## Run migratetest
	@docker compose -f docker compose.test.yml build
	@docker compose -f docker compose.test.yml up -d --wait
	@docker compose -f docker compose.test.yml cp ../Makefile-common.mk unittest:/www/Makefile-common.mk
	@docker compose -f docker compose.test.yml exec unittest python3 manage.py migrate --noinput || \
		($(MAKE) -f $(THIS_FILE) unittest-stop; exit 1)

	$(MAKE) -f $(THIS_FILE) unittest-stop

unittest: ## Run unittests
	touch .env
	@docker compose -f docker compose.test.yml build
	@docker compose -f docker compose.test.yml up -d --wait
	@docker compose -f docker compose.test.yml cp ../Makefile-common.mk unittest:/www/Makefile-common.mk
	@docker compose cp ../.git unittest:/www/.git
	@docker compose -f docker compose.test.yml exec unittest git config --global --add safe.directory /www
	docker compose -f docker compose.test.yml exec -e GITHUB_TOKEN=$(GITHUB_TOKEN) \
	  -e GITHUB_REF_NAME=$(GITHUB_REF_NAME) \
	  -e BASE_BRANCH=$(BASE_BRANCH) \
	  -e GITHUB_REPOSITORY=nvnv/betmaster  unittest python bin/run_checks.py || \
		($(MAKE) -f $(THIS_FILE) unittest-stop; exit 1)
	@docker compose -f docker compose.test.yml cp unittest:/app/rozert_pay/coverage.xml ../reports/ ||:

	$(MAKE) -f $(THIS_FILE) unittest-stop

########################################################

CHECK_COMMIT_MESSAGE_FORMAT_FROM_REF ?= origin/develop
COMPARE_BRANCH ?= origin/develop
FAIL_UNDER ?= 80

up:
	WEB_PORT=8006 docker compose up

pytest:
	poetry run pytest tests $(ARGS)

swagger:
	poetry run python manage.py spectacular --color --file swagger.yml

coverage:
	pytest tests --cov=rozert_pay --cov-report=xml

pytest-cov:
	make pytest ARGS="--cov=rozert_pay --cov-report=xml"

mypy:
	poetry run mypy . ../shared-apps/rozert_pay_shared/

lint:
	poetry run pre-commit run --all-files

pylint:
	poetry run pylint --ignore=migrations,tests,stubs --ignore-patterns=".*migrations.*" rozert_pay/ code_checks/

check_commit_message_format:
	@bad_commits=$$(git log --pretty=format:'%h %s' ${CHECK_COMMIT_MESSAGE_FORMAT_FROM_REF}..HEAD | grep -Ev '\[(sc|ch)\d+\]'); \
	if [ -n "$$bad_commits" ]; then \
		echo "Error: The following commit messages do not contain [sc\\d+] substring:"; \
		echo "$$bad_commits"; \
		exit 1; \
	fi


########################################################

DOCKER_IMAGE_NAME ?= rozert_pay

dev-build:
	WEB_PORT=8006 docker compose build --build-arg ENV=dev

dev-up:
	WEB_PORT=8006 docker compose up

dev-web-bash:
	docker compose run --rm -e DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest back bash

########################################################

deploy: deploy-backend ## Deploy all project
deploy-%:
	helm secrets $(HELM_CMD) -n $(TARGET) $(HELMARGS_BACKEND) \
		-f .helm/values.$*.yaml \
		-f .helm/values.$*.$(CLUSTER).yaml \
		--set-string image.repository=$(REGISTRY)/rozert-pay-$* \
		--set-string image.tag=$(TAG) \
		rozert-pay-$* ${HELM_REPO}/backend-common

deploy-frontend: ## Deploy frontend
	helm $(HELM_CMD) -n $(TARGET) $(HELMARGS_FRONTEND) \
		-f .helm/values.frontend.yaml \
		-f .helm/values.frontend.$(CLUSTER).yaml \
		--set-string image.repository=$(REGISTRY)/rozert-pay-frontend \
		--set-string image.tag=$(TAG) \
		rozert-pay-frontend ${HELM_REPO}/frontend-common

secrets-sync:
	kubectl -n $(TARGET) annotate es rozert-pay-backend force-sync=$$(date +%s) --overwrite
