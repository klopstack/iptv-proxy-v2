.PHONY: help install test lint format clean run docker-build docker-run venv

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

install: venv ## Install dependencies in venv
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

test: venv ## Run tests with coverage in venv
	$(PYTEST) tests/ -v --cov=. --cov-report=html --cov-report=term-missing

test-fast: venv ## Run tests without coverage in venv
	$(PYTEST) tests/ -v

lint: venv ## Run linting checks in venv
	$(FLAKE8) . --count --select=E9,F63,F7,F82 --show-source --statistics
	$(FLAKE8) . --count --exit-zero --statistics
	$(BLACK) --check .
	$(ISORT) --check-only .
	$(MYPY) app.py models.py services/ || true

format: venv ## Format code with black and isort in venv
	$(BLACK) .
	$(ISORT) .

clean: ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf $(VENV)/

run: ## Run the application locally
	python app.py

docker-build: ## Build Docker image
	docker-compose build

docker-run: ## Run with Docker Compose
	docker-compose up -d

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-stop: ## Stop Docker containers
	docker-compose down

ci: lint test ## Run CI checks (lint + test)
