#!/bin/bash
# Setup script for development environment

set -e

echo "🔧 IPTV Proxy v2 - Development Setup"
echo "===================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $PYTHON_VERSION"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo ""
echo "✓ Dependencies installed"

# Check linting tool versions
echo ""
echo "📋 Checking linting tool versions..."
BLACK_VERSION=$(black --version 2>&1 | grep -oP 'version \K[0-9.]+' | head -1)
ISORT_VERSION=$(isort --version 2>&1 | grep -oP 'VERSION \K[0-9.]+' | head -1)
FLAKE8_VERSION=$(flake8 --version 2>&1 | grep -oP '^[0-9.]+' | head -1)

echo "  black:  $BLACK_VERSION (expected: 23.12.1)"
echo "  isort:  $ISORT_VERSION (expected: 5.13.2)"
echo "  flake8: $FLAKE8_VERSION (expected: 7.0.0)"

# Run initial format
echo ""
echo "🎨 Formatting code..."
black . 2>&1 | head -n 5
isort . 2>&1 | head -n 5

echo ""
echo "✓ Code formatted"

# Run linting
echo ""
echo "🔍 Running linting checks..."
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true

echo ""
echo "✓ Linting complete"

# Run tests
echo ""
echo "🧪 Running tests..."
pytest tests/ -v --cov=. --cov-report=term-missing --cov-fail-under=70

echo ""
if command -v pre-commit >/dev/null 2>&1; then
    echo ""
    echo "🔗 Installing git pre-commit hooks..."
    pre-commit install
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Available commands:"
echo "  make test       - Run tests with coverage"
echo "  make test-fast  - Run tests without coverage"
echo "  make lint       - Check code quality (also runs on git commit via pre-commit)"
echo "  make install-hooks - Install git pre-commit hooks"
echo "  make format     - Auto-format code"
echo "  make run        - Run the application"
echo "  make help       - Show all commands"
