.PHONY: setup run extract lint format clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Full local setup: venv, runtime + dev deps, a .env to fill in, pre-commit
# hooks (skipped if this isn't a git repo yet).
setup:
	python3 -m venv $(VENV)
	$(PIP) install -q -r requirements.txt
	$(PIP) install -q -r requirements-dev.txt
	[ -f .env ] || cp .env.example .env
	git rev-parse --git-dir >/dev/null 2>&1 \
		&& $(VENV)/bin/pre-commit install \
		|| echo "Skipping pre-commit hook install (not a git repo yet — run 'git init' first)"

run:
	$(PYTHON) app.py

# One-time real-data extraction from Overture (needs requirements-dev.txt
# and network access) — see scripts/01_download_raw.sh.
extract:
	bash scripts/01_download_raw.sh
	$(PYTHON) scripts/02_filter_and_build.py

lint:
	$(VENV)/bin/flake8 .
	$(VENV)/bin/black --check .
	$(VENV)/bin/isort --check-only .

format:
	$(VENV)/bin/black .
	$(VENV)/bin/isort .

clean:
	rm -rf $(VENV) __pycache__ data/raw
