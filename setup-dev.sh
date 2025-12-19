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
echo "✅ Setup complete!"
echo ""
echo "Available commands:"
echo "  make test       - Run tests with coverage"
echo "  make test-fast  - Run tests without coverage"
echo "  make lint       - Check code quality"
echo "  make format     - Auto-format code"
echo "  make run        - Run the application"
echo "  make help       - Show all commands"
