.PHONY: help install install-js install-hooks test test-js test-fast test-parallel test-clean lint lint-py lint-js format clean run debug docker-build docker-run venv vulture vulture-all

VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
BLACK = $(VENV)/bin/black
ISORT = $(VENV)/bin/isort
FLAKE8 = $(VENV)/bin/flake8
MYPY = $(VENV)/bin/mypy
VULTURE = $(VENV)/bin/vulture
PRE_COMMIT = $(VENV)/bin/pre-commit
MYPY_MODELS = models/
VULTURE_MODELS = models/

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create virtual environment
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: install-py install-js install-hooks ## Install all dependencies and git pre-commit hooks

install-py: venv ## Install Python dependencies in venv
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

install-js: ## Install JavaScript dependencies
	npm install

install-hooks: install-py ## Install git pre-commit hooks (same linters as CI)
	$(PRE_COMMIT) install

test-clean: ## Remove stale test database files
	rm -f test.db test.db-* instance/test.db instance/test.db-* instance/pytest.db instance/pytest.db-*
	rm -f instance/pytest_gw*.db instance/pytest_gw*.db-*

test: install test-clean ## Run tests with coverage in venv (parallel, matches CI)
	$(PYTEST) tests/ -v -n auto --cov=. --cov-report=html --cov-report=term-missing

test-js: install-js ## Run JavaScript unit tests
	npm test

test-fast: install test-clean ## Run tests without coverage in venv (parallel)
	$(PYTEST) tests/ -q --no-cov -n auto

test-parallel: test-fast ## Alias for parallel no-coverage run

lint-py: install ## Run Python linting checks in venv
	$(FLAKE8) . --count --select=E9,F63,F7,F82 --show-source --statistics
	$(FLAKE8) . --count --exit-zero --statistics
	$(BLACK) --check .
	$(ISORT) --check-only .
	$(MYPY) app.py $(MYPY_MODELS) services/ routes/

vulture: install ## Find dead code with vulture
	$(VULTURE) app.py $(VULTURE_MODELS) services/ routes/ schemas.py error_handling.py vulture_whitelist.py --min-confidence 80

vulture-all: install ## Find dead code including lower confidence results
	$(VULTURE) app.py $(VULTURE_MODELS) services/ routes/ schemas.py error_handling.py vulture_whitelist.py --min-confidence 60

lint-js: ## Run JavaScript/HTML linting
	npm run lint

lint: lint-py lint-js ## Run all linting checks (Python + JavaScript)

format: venv ## Format code with black and isort in venv
	$(BLACK) .
	$(ISORT) .

clean: ## Clean up Python generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf $(VENV)/

# Local development environment variables
export DATABASE_URL ?= sqlite:///$(PWD)/data/iptv_proxy.db

clean-js: ## Clean up JavaScript dependencies
	rm -rf node_modules package-lock.json

clean-all: clean clean-js ## Clean up all generated files

run: ## Run the application locally
	python app.py

debug: ## Run the application in debug mode with auto-reload
	FLASK_DEBUG=1 FLASK_ENV=development python app.py

migrate: ## Run database migrations
	python run_migrations.py

docker-build: ## Build Docker image
	docker-compose build

docker-run: ## Run with Docker Compose
	docker-compose up -d

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-stop: ## Stop Docker containers
	docker-compose down

docker-migrate: ## Run migrations in Docker container
	docker exec -it iptv-proxy-v2 python run_migrations.py

ci: lint test-js test ## Run all CI checks (Python + JavaScript linting + tests)
