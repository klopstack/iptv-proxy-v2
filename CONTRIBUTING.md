# Contributing to IPTV Proxy v2

Thank you for your interest in contributing! This document provides guidelines and information for contributors.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/klopstack/iptv-proxy-v2.git
cd iptv-proxy-v2
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

4. Run tests:
```bash
pytest tests/ -v
```

5. Start the development server:
```bash
python app.py
```

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and single-purpose

## Testing

- Write tests for new features
- Ensure existing tests pass before submitting PR
- Run tests with: `pytest tests/ -v`

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Write/update tests as needed
5. Ensure all tests pass
6. Commit with clear, descriptive messages
7. Push to your fork
8. Open a Pull Request with a clear description

## Reporting Issues

When reporting issues, please include:
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages
- Environment details (Docker, OS, etc.)

## Feature Requests

We welcome feature requests! Please:
- Check existing issues first
- Describe the use case clearly
- Explain why it would be useful
- Consider contributing the implementation

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Keep discussions professional

## Questions?

Open an issue with your question, and we'll do our best to help!
