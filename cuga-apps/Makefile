.PHONY: help up down build logs test test-quick test-mcp test-wiring test-llm test-all install-test-deps

help:
	@echo "Targets:"
	@echo "  make up                  bring the full stack up"
	@echo "  make down                stop the stack"
	@echo "  make build               rebuild all images"
	@echo "  make logs                tail combined apps logs"
	@echo ""
	@echo "  make install-test-deps   pip install -r requirements.test.txt (one-time)"
	@echo "  make test                smoke + mcp + wiring (default; no LLM cost)"
	@echo "  make test-quick          smoke only (~5s — fastest sanity check)"
	@echo "  make test-mcp            mcp tier only"
	@echo "  make test-wiring         app-wiring tier only"
	@echo "  make test-llm            opt-in LLM round-trips (slow, costs tokens)"
	@echo "  make test-all            everything (smoke + mcp + wiring + llm)"

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f apps

install-test-deps:
	pip install -r requirements.test.txt

# Default test run: everything except the slow + costly LLM tier.
test:
	pytest -m "smoke or mcp or wiring"

# Tiered runs.
test-quick:
	pytest -m smoke

test-mcp:
	pytest -m mcp

test-wiring:
	pytest -m wiring

test-llm:
	pytest -m llm

test-all:
	pytest
