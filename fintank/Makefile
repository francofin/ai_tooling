# Fintank dev Makefile
#
#   make dev        -> Django + Celery (worker & beat) + Next.js, all in one terminal
#   make backend    -> Django dev server only
#   make celery     -> Celery worker with embedded beat only
#   make frontend   -> Next.js dev server only
#
# Assumes your virtualenv is already activated in the shell. Override if not:
#   make dev PY="uv run python"                   (uv-managed backend/.venv)
#   make dev PY="../../.venv/bin/python"          (monorepo shared venv)
# Note: PY runs from inside backend/, so relative paths are relative to it.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_DIR  := backend
CELERY_APP   := fintank_backend
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 8020

# Python interpreter used for manage.py / celery (always run from backend/).
PY ?= python

.PHONY: help dev backend celery frontend redis migrate makemigrations superuser install shell lint format check

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

## ---------------------------------------------------------------- run

dev: ## Run Django, Celery (worker+beat) and Next.js together
	@$(MAKE) --no-print-directory redis
	@echo ""
	@echo "  Django   -> http://localhost:$(BACKEND_PORT)"
	@echo "  Next.js  -> http://localhost:$(FRONTEND_PORT)"
	@echo "  Celery   -> worker + beat"
	@echo "  (ctrl-c stops everything)"
	@echo ""
	@trap 'echo; echo "shutting down..."; kill 0' EXIT INT TERM; \
	( cd $(BACKEND_DIR) && $(PY) manage.py runserver ) & \
	( cd $(BACKEND_DIR) && celery -A $(CELERY_APP) worker -B -l info ) & \
	( npm run dev ) & \
	wait

backend: ## Run the Django dev server
	cd $(BACKEND_DIR) && $(PY) manage.py runserver $(BACKEND_PORT)

celery: ## Run the Celery worker with embedded beat scheduler
	cd $(BACKEND_DIR) && $(PY) -m celery -A $(CELERY_APP) worker -B -l info

frontend: ## Run the Next.js dev server
	npm run dev

redis: ## Make sure redis-server is up (celery broker)
	@redis-cli ping >/dev/null 2>&1 && echo "redis: already running" || { \
		echo "redis: starting..."; \
		sudo service redis-server start; \
	}

## ---------------------------------------------------------------- django

migrate: ## Apply database migrations
	cd $(BACKEND_DIR) && $(PY) manage.py migrate

makemigrations: ## Create new migrations
	cd $(BACKEND_DIR) && $(PY) manage.py makemigrations

superuser: ## Create a Django superuser
	cd $(BACKEND_DIR) && $(PY) manage.py createsuperuser

shell: ## Open the Django shell
	cd $(BACKEND_DIR) && $(PY) manage.py shell

## ---------------------------------------------------------------- misc

install: ## Install frontend and backend dependencies
	npm install
	cd $(BACKEND_DIR) && uv sync

lint: ## Lint the frontend
	npm run lint

format: ## Format the frontend
	npm run format

check: ## Build + lint + format check
	npm run ci
