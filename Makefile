.PHONY: help install install-js test test-fast lint lint-js format clean run docker-build docker-run venv

VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
BLACK = $(VENV)/bin/black
ISORT = $(VENV)/bin/isort
FLAKE8 = $(VENV)/bin/flake8
MYPY = $(VENV)/bin/mypy

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create virtual environment
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv ## Install Python dependencies in venv
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

install-js: ## Install JavaScript dependencies
	npm install

test: venv ## Run tests with coverage in venv
	$(PYTEST) tests/ -v --cov=. --cov-report=html --cov-report=term-missing

test-fast: venv ## Run tests without coverage in venv
	$(PYTEST) tests/ -v

lint: venv ## Run Python linting checks in venv
	$(FLAKE8) . --count --select=E9,F63,F7,F82 --show-source --statistics
	$(FLAKE8) . --count --exit-zero --statistics
	$(BLACK) --check .
	$(ISORT) --check-only .
	$(MYPY) app.py models.py services/ || true

lint-js: ## Run JavaScript/HTML linting
	npm run lint

lint-all: lint lint-js ## Run all linting checks (Python + JavaScript)

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

clean-js: ## Clean up JavaScript dependencies
	rm -rf node_modules package-lock.json

clean-all: clean clean-js ## Clean up all generated files

run: ## Run the application locally
	python app.py

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

ci: lint-all test ## Run all CI checks (Python + JavaScript linting + tests)
