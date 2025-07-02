# Makefile for ORBIT CLI
# Provides common development and packaging tasks

.PHONY: help install install-dev build clean test lint format check dist upload upload-test version clean-build clean-pyc

# Default target
help:
	@echo "ORBIT CLI Development Commands"
	@echo "=============================="
	@echo ""
	@echo "Setup Commands:"
	@echo "  install      Install package in current environment"
	@echo "  install-dev  Install package with development dependencies"
	@echo ""
	@echo "Development Commands:"
	@echo "  test         Run tests with pytest"
	@echo "  lint         Run linting with flake8"
	@echo "  format       Format code with black and isort"
	@echo "  check        Run all checks (lint, format-check, type-check)"
	@echo "  type-check   Run type checking with mypy"
	@echo ""
	@echo "Build Commands:"
	@echo "  build        Build package for distribution"
	@echo "  clean        Clean all build artifacts"
	@echo "  clean-build  Clean build artifacts only"
	@echo "  clean-pyc    Clean Python cache files"
	@echo ""
	@echo "Release Commands:"
	@echo "  dist         Create distribution packages"
	@echo "  upload-test  Upload to TestPyPI"
	@echo "  upload       Upload to PyPI (production)"
	@echo "  version      Show current version"
	@echo ""
	@echo "Usage:"
	@echo "  make install-dev  # Set up development environment"
	@echo "  make test         # Run tests"
	@echo "  make build        # Build package"

# Installation commands
install:
	pip install -e .

install-dev:
	pip install -e ".[dev,test]"

# Development commands
test:
	pytest -v --cov=orbit_cli --cov-report=term-missing --cov-report=html

lint:
	flake8 orbit_cli/ --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 orbit_cli/ --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics

format:
	black orbit_cli/
	isort orbit_cli/

format-check:
	black --check orbit_cli/
	isort --check-only orbit_cli/

type-check:
	mypy orbit_cli/

check: lint format-check type-check
	@echo "All checks passed!"

# Build commands
build: clean
	python -m build

clean: clean-build clean-pyc
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

clean-build:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .eggs/

clean-pyc:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete

# Distribution and release commands
dist: clean build
	@echo "Distribution packages created in dist/"
	@ls -la dist/

version:
	@python -c "from orbit_cli.__version__ import __version__; print(f'Version: {__version__}')"

# PyPI upload commands (requires twine)
upload-test: dist
	@echo "Uploading to TestPyPI..."
	twine check dist/*
	twine upload --repository testpypi dist/*
	@echo "Package uploaded to TestPyPI: https://test.pypi.org/project/orbit-cli/"

upload: dist
	@echo "Uploading to PyPI..."
	twine check dist/*
	@read -p "Are you sure you want to upload to PyPI? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		twine upload dist/*; \
		echo "Package uploaded to PyPI: https://pypi.org/project/orbit-cli/"; \
	else \
		echo "Upload cancelled."; \
	fi

# Development helpers
dev-setup: install-dev
	@echo "Development environment setup complete!"
	@echo "Run 'make test' to verify installation"

# Check if we can import the package
test-import:
	python -c "import orbit_cli; print('✅ Package imports successfully')"
	python -c "from orbit_cli.main import main; print('✅ Main entry point accessible')"
	python -c "from orbit_cli.__version__ import __version__; print(f'✅ Version: {__version__}')"

# Quick development test
dev-test: test-import
	@echo "Running quick development tests..."
	python -m orbit_cli.main --help > /dev/null && echo "✅ CLI help command works" || echo "❌ CLI help command failed"
	python -m orbit_cli.main --version > /dev/null && echo "✅ CLI version command works" || echo "❌ CLI version command failed"

# Pre-commit hook setup (if using pre-commit)
pre-commit-install:
	pre-commit install

# Full development workflow
dev-workflow: clean install-dev test lint format check
	@echo "🎉 Full development workflow completed successfully!"

# Release workflow
release-workflow: clean test lint format check build dist
	@echo "🚀 Release workflow completed. Package ready for upload."
	@echo "Run 'make upload-test' to upload to TestPyPI first." 