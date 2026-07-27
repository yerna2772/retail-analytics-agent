PYTHON ?= .venv/bin/python

.PHONY: install run demo test check eval lint typecheck

install:
	$(PYTHON) -m pip install -e ".[dev]"

run:
	$(PYTHON) -m agent.cli

demo:
	$(PYTHON) -m agent demo

test:
	$(PYTHON) -m pytest -x -q

check: lint typecheck test eval

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/

typecheck:
	$(PYTHON) -m mypy src/agent/safety/

eval:
	$(PYTHON) -m pytest evals/ -x -q --tb=short
