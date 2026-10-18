#!/usr/bin/env bash
# Runs once when the Codespace is created.
set -euo pipefail

echo ">> Installing uv (Python package manager)"
pip install --upgrade uv

echo ">> Installing project dependencies"
uv sync

echo ">> Installing pre-commit hooks"
uv run pre-commit install || true

echo ">> Installing Claude Code (sign in with your PERSONAL account when you run 'claude')"
npm install -g @anthropic-ai/claude-code

echo ">> Versions"
python --version
uv --version
claude --version || true
docker --version || echo "Docker is still starting; retry in a few seconds"

echo ">> Done. Run 'claude' in the terminal to start."
