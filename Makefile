# One entry point for every routine task. `make help` lists them.
# Windows users without make can run the underlying commands directly, or use
# `docker compose` targets which work everywhere.

BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/Scripts/python
ifeq ($(OS),)
PY := $(BACKEND)/.venv/bin/python
endif

.DEFAULT_GOAL := help
.PHONY: help setup dev backend frontend test test-backend test-frontend lint format \
        check seed demo build docker-up docker-down docker-logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend + frontend dependencies
	cd $(BACKEND) && python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r $(BACKEND)/requirements-dev.txt
	cd $(FRONTEND) && npm ci

backend: ## Run the API with autoreload (http://localhost:8000)
	cd $(BACKEND) && ../$(PY) -m uvicorn app.main:app --reload --port 8000

frontend: ## Run the web app in dev mode (http://localhost:3000)
	cd $(FRONTEND) && npm run dev

test: test-backend test-frontend ## Run every test suite

test-backend: ## Backend tests with coverage gate
	cd $(BACKEND) && ../$(PY) -m pytest --cov=app --cov-report=term-missing

test-frontend: ## Frontend unit tests
	cd $(FRONTEND) && npm run test:run

lint: ## Lint backend and frontend
	cd $(BACKEND) && ../$(PY) -m ruff check app tests
	cd $(FRONTEND) && npm run lint

format: ## Auto-format backend and frontend
	cd $(BACKEND) && ../$(PY) -m ruff format app tests && ../$(PY) -m ruff check app tests --fix
	cd $(FRONTEND) && npx prettier --write "app/**/*.{ts,tsx}" "components/**/*.tsx" "lib/**/*.ts"

check: lint test ## Everything CI runs, locally

build: ## Production build of the frontend
	cd $(FRONTEND) && npm run build

seed: ## Load the scripted sample dataset
	cd $(BACKEND) && ../$(PY) -m app.seed

demo: ## Run the API with a freshly provisioned demo workspace
	cd $(BACKEND) && DEMO_MODE=true ../$(PY) -m uvicorn app.main:app --reload --port 8000

docker-up: ## Start the full stack (Postgres + Redis + API + web)
	docker compose up -d --build

docker-down: ## Stop the stack
	docker compose down

docker-logs: ## Tail backend logs
	docker compose logs -f backend

clean: ## Remove caches, build output and the local database
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(BACKEND)/htmlcov \
	       $(BACKEND)/.coverage $(BACKEND)/data $(FRONTEND)/.next $(FRONTEND)/coverage
	find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
