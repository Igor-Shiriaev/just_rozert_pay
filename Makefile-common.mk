#

SHA ?= $(shell git rev-parse HEAD)
TAG ?= $(shell git rev-parse --short=7 HEAD)
BRANCH ?= $(shell git branch 2>/dev/null | sed -n '/^\*/s/^\* //p' | sed 's/^(HEAD detached at \(.*\))$$/\1/g')
BRANCH := $(shell echo $(BRANCH) | sed 's/\//-/g' | sed 's/\#//g')
REGISTRY ?= ghcr.io/nvnv/betmaster
REGCACHE ?= ghcr.io/nvnv/betmaster

PLATFORM ?=
PUSH ?= false

DEBUG ?= false

ifneq ($(PLATFORM),)
BUILDARG := --platform=$(PLATFORM)
endif
ifeq ($(PUSH),true)
BUILDARG += --push=$(PUSH)
else ifdef REGISTRY_CACHE_UPLOAD
BUILDARG += --output type=cacheonly
else
BUILDARG += --output type=docker
endif

ifneq ($(HTTP_PROXY),)
BUILDARG += --build-arg=HTTP_PROXY=$(HTTP_PROXY)
BUILDARG += --build-arg=NO_PROXY=cluster.local,github-actions-runner-mirrors,localhost,127.0.0.1
endif

ifdef ACTIONS_RUNTIME_TOKEN
CACHEARGS = $(shell echo "--cache-to type=gha,mode=max,ignore-error=true --cache-from type=gha")
else ifdef REGISTRY_CACHE_UPLOAD
CACHEARGS = $(shell echo "--cache-to type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-$(BRANCH),mode=max,ignore-error=true \
	--cache-from type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-master --cache-from type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-develop --cache-from type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-$(BRANCH)")
else ifneq ($(REGCACHE),)
CACHEARGS = $(shell echo "--cache-from type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-master --cache-from type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-develop --cache-from type=registry,ref=$(REGCACHE)/$(TARGET)-cache:$1-$(BRANCH)")
endif

HELM_REPO ?= oci://ghcr.io/nvnv/helm-charts
HELM_OPTIONS ?=

HELM_DRYRUN ?= false

ifeq ($(HELM_DRYRUN),true)
HELM_CMD ?= diff upgrade
else
HELM_CMD ?= upgrade -i --history-max 3 --timeout 10m $(HELM_OPTIONS)
endif
