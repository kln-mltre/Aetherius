# Aetherius developer tasks.
# Single source of truth for "how we check the project": the CI (.github/workflows/ci.yml) calls
# these same targets, so local and CI runs never drift.

.DEFAULT_GOAL := help
PY := python3
TS_DIR := sdks

.PHONY: help install-dev lint format format-check typecheck test test-fast test-browser test-ts contracts conformance check check-all screenshots screenshots-check dist release-check

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install-dev: ## Install the package with dev tooling (editable)
	$(PY) -m pip install -e ".[dev]"

lint: ## Lint with Ruff
	ruff check .

format: ## Format the code with Ruff
	ruff format .

format-check: ## Check formatting without writing (CI)
	ruff format --check .

typecheck: ## Strict static typing with mypy
	mypy

test: ## Run the full Python test suite with coverage
	pytest --cov=aetherius --cov-report=term-missing

test-fast: ## Run only the fast tests (skip heavy extras and slow tests)
	pytest -m "not browser and not vision and not cognition and not slow"

test-browser: ## Run the browser tests (Act II) against a real Chromium; needs the [browser] extra
	pytest -m browser

test-ts: ## Typecheck, build and test the npm workspace (client SDK + embedded engine)
	npm --prefix $(TS_DIR) install
	npm --prefix $(TS_DIR) test

contracts: ## Regenerate the generated contracts (contracts/actions.json) from the action registry
	$(PY) -m aetherius.core.actions.contract

conformance: ## Replay the shared Blueprint corpus on both engines (Python + TypeScript)
	pytest tests/conformance -q
	npm --prefix $(TS_DIR) install
	npm --prefix $(TS_DIR) run conformance --workspace @aetherius/engine
	# Act II needs a WebView, which the neutral engine has not got: the same corpus is replayed
	# by the package that owns the driver, on a jsdom-backed host.
	npm --prefix $(TS_DIR) run conformance --workspace @aetherius/react-native

screenshots: ## Regenerate the Console SVG screenshots under docs/screenshots/
	$(PY) -m aetherius.console.screenshots

screenshots-check: ## Fail if the committed screenshots are stale (deterministic; CI guard)
	@tmp=$$(mktemp -d); \
	$(PY) -c "import asyncio; from pathlib import Path; from aetherius.console.screenshots import capture_all; asyncio.run(capture_all(Path('$$tmp')))" >/dev/null; \
	if diff -rq docs/screenshots "$$tmp" >/dev/null; then \
		echo "screenshots up to date"; rm -rf "$$tmp"; \
	else \
		echo "Screenshots are stale — run 'make screenshots' and commit the result."; \
		diff -rq docs/screenshots "$$tmp" || true; rm -rf "$$tmp"; exit 1; \
	fi

check: ## Full Python gate: format check, lint, types, tests
	@$(MAKE) format-check lint typecheck test

check-all: ## Full repository gate: Python + npm workspace
	@$(MAKE) check test-ts

dist: ## Build the Python distribution (wheel + sdist) into dist/
	rm -rf dist
	$(PY) -m build

release-check: ## Build and validate the distribution metadata before uploading (see RELEASING.md)
	@$(MAKE) dist
	$(PY) -m twine check dist/*
