# Lumine Makefile — canonical entry for all commands.
# CI invokes these targets only, guaranteeing local/CI parity.
# Keep targets idempotent and self-documenting.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON := uv
BACKEND_DIR := backend
FRONTEND_DIR := frontend

##@ Help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

##@ Install

.PHONY: install install-backend install-frontend
install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install backend deps (uv)
	cd $(BACKEND_DIR) && $(PYTHON) sync

install-frontend: ## Install frontend deps (if frontend scaffolded)
	@if [ -f $(FRONTEND_DIR)/package.json ]; then cd $(FRONTEND_DIR) && npm ci; else echo "frontend not scaffolded; skipping"; fi

##@ Database

.PHONY: migrate migrate-dev migrations-new
migrate: ## Apply migrations (dev)
	cd $(BACKEND_DIR) && uv run alembic upgrade head

migrate-dev: migrate

migrations-new: ## Create a new migration: make migrations-new m="msg"
	cd $(BACKEND_DIR) && uv run alembic revision --autogenerate -m "$(m)"

##@ Run

.PHONY: run-dev run-backend run-frontend
run-dev: ## Run backend + frontend dev servers
	@echo "Run 'make run-backend' and 'make run-frontend' in separate terminals for now"

run-backend: ## Run backend dev server
	cd $(BACKEND_DIR) && uv run uvicorn lumine.api:app --reload --port 8000

run-frontend: ## Run frontend dev server
	@if [ -f $(FRONTEND_DIR)/package.json ]; then cd $(FRONTEND_DIR) && npm run dev; else echo "frontend not scaffolded"; fi

##@ Quality

.PHONY: lint lint-backend lint-frontend typecheck typecheck-backend typecheck-frontend
lint: lint-backend lint-frontend ## Lint everything

lint-backend:
	cd $(BACKEND_DIR) && uv run ruff check . && uv run ruff format --check .

lint-frontend:
	@if [ -f $(FRONTEND_DIR)/package.json ]; then cd $(FRONTEND_DIR) && npm run lint; else echo "frontend not scaffolded; skipping"; fi

typecheck: typecheck-backend typecheck-frontend ## Typecheck everything

typecheck-backend:
	cd $(BACKEND_DIR) && uv run mypy src

typecheck-frontend:
	@if [ -f $(FRONTEND_DIR)/package.json ]; then cd $(FRONTEND_DIR) && npm run typecheck; else echo "frontend not scaffolded; skipping"; fi

##@ Test

.PHONY: test test-unit test-integration test-contract test-backtest test-system test-coverage
test: ## Run full backend test suite
	cd $(BACKEND_DIR) && uv run pytest

test-unit:
	cd $(BACKEND_DIR) && uv run pytest tests/unit

test-integration:
	cd $(BACKEND_DIR) && uv run pytest tests/integration

test-contract:
	cd $(BACKEND_DIR) && uv run pytest tests/contract

test-backtest:
	cd $(BACKEND_DIR) && uv run pytest tests/backtest

test-system:
	cd $(BACKEND_DIR) && uv run pytest tests/system

test-coverage:
	cd $(BACKEND_DIR) && uv run pytest --cov=src/lumine --cov-report=term --cov-report=html

##@ Eval & backtest

.PHONY: eval backtest
eval: ## Run AI eval suites
	cd $(BACKEND_DIR) && uv run python -m lumine.prompts.evals

backtest: ## Run backtest harness
	cd $(BACKEND_DIR) && uv run python -m lumine.backtest

##@ Security & supply chain

.PHONY: security-scan supply-chain sbom secret-scan
security-scan: supply-chain secret-scan ## Run all security scans

supply-chain: ## Scan dependencies for known CVEs
	cd $(BACKEND_DIR) && uv run pip-audit
	@command -v osv-scanner >/dev/null 2>&1 && osv-scanner --lockfile $(BACKEND_DIR)/uv.lock || echo "osv-scanner not installed; skipping"

sbom: ## Generate SBOM (CycloneDX)
	cd $(BACKEND_DIR) && uv run cyclonedx-py environment -o sbom.json

secret-scan: ## Scan for committed secrets
	@command -v gitleaks >/dev/null 2>&1 && gitleaks detect --no-banner || echo "gitleaks not installed; skipping"

##@ Docs

.PHONY: docs-lint docs-links adr-check docs-freshness
docs-lint: docs-links adr-check docs-freshness ## Lint documentation

docs-links: ## Check markdown links
	@command -v lychee >/dev/null 2>&1 && lychee --no-progress docs *.md || echo "lychee not installed; skipping"

adr-check: ## Verify ADR index is complete and phase decisions.md point to ADRs
	@command -v python3 >/dev/null 2>&1 && python3 docs/_ci/adr-index-check.py || echo "adr-index-check.py not found; skipping"

docs-freshness: ## Check docs are within review cadence (warns)
	@command -v python3 >/dev/null 2>&1 && python3 docs/_ci/doc-freshness-check.py || echo "doc-freshness-check.py not found; skipping"

##@ Docker

.PHONY: docker-build docker-up docker-down
docker-build: ## Build docker images
	cd $(BACKEND_DIR) && docker compose build

docker-up: ## Start dev compose
	cd $(BACKEND_DIR) && docker compose up -d

docker-down: ## Stop dev compose
	cd $(BACKEND_DIR) && docker compose down

##@ Clean

.PHONY: clean
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND_DIR)/dist $(BACKEND_DIR)/.coverage $(BACKEND_DIR)/htmlcov
