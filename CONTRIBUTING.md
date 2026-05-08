# Contributing to ibot

Thank you for your interest in contributing to ibot! This document provides guidelines for contributing.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ibot.git
cd ibot
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install in development mode with dev dependencies:
```bash
pip install -e ".[dev]"
```

4. Create a test config:
```bash
cp default.cfg test.cfg
# Edit test.cfg with your test server details
```

## Running Tests

```bash
pytest
```

For coverage:
```bash
pytest --cov=ibot --cov-report=html
```

## Code Style

- Follow PEP 8 guidelines
- Use descriptive variable and function names
- Add docstrings to all public functions and classes
- Keep functions focused and under 50 lines when possible
- Add type hints where appropriate

## Adding Features

1. Create a new branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes with clear, atomic commits

3. Test your changes thoroughly:
   - Run existing tests
   - Add new tests for new functionality
   - Test with actual IRC server if possible

4. Update documentation:
   - Update README.md if adding user-facing features
   - Add docstrings to new functions
   - Update comments as needed

5. Submit a pull request with:
   - Clear description of changes
   - Motivation for the change
   - Any breaking changes noted

## Plugin Development

To test plugins:

1. Create a plugin in the `plugins/` directory
2. Use the standard Sopel plugin decorators
3. Test with `python -m ibot test.cfg`
4. Use `.reload <plugin>` for hot-reloading during development

## Reporting Issues

When reporting issues, include:

- Python version
- Operating system
- ibot version or commit hash
- Full error traceback
- Steps to reproduce
- Expected vs actual behavior

## Code Review Process

All submissions require review. We aim to respond within a few days.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
