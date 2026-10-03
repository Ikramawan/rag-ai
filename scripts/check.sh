#!/usr/bin/env bash

set -euo pipefail

echo "Fixing lint issues..."
ruff check --fix .

echo "Formatting Python files..."
ruff format .

echo "Checking formatting..."
ruff format --check .

echo "Checking lint rules..."
ruff check .

echo "Running tests..."
python -m pytest -v

echo "All checks passed."%  