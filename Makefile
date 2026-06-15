.PHONY: install test lint reindex mcp dream doctor clean

PYTHON := python3
UV := uv
APP := brain

install:
	$(UV) sync --all-extras
	$(UV) pip install -e .

test:
	$(UV) run pytest tests/ -v

lint:
	$(UV) run ruff check src/ tests/
	$(UV) run ruff format --check src/ tests/

lint-fix:
	$(UV) run ruff check --fix src/ tests/
	$(UV) run ruff format src/ tests/

reindex:
	$(UV) run $(APP) reindex --all

mcp:
	$(UV) run $(APP) mcp

dream:
	$(UV) run $(APP) dream

doctor:
	$(UV) run $(APP) doctor

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ dist/ build/ *.egg-info/
