# ==============================================================================
# Sahayak AI Voice Assistant - Developer Automation & Task Runner
# ==============================================================================

SHELL := /bin/bash
PYTHON := python3
VENV := ../.venv/bin
PYTEST := $(if $(wildcard $(VENV)/pytest),$(VENV)/pytest,pytest)
UVICORN := $(if $(wildcard $(VENV)/uvicorn),$(VENV)/uvicorn,uvicorn)
RUFF := $(if $(wildcard $(VENV)/ruff),$(VENV)/ruff,ruff)

.PHONY: help dev test test-fast ingest benchmark lint clean docker-build docker-up docker-down

help:
	@echo "======================================================================"
	@echo " Sahayak AI Voice Assistant: Command Automation"
	@echo "======================================================================"
	@echo "  make dev          Start FastAPI uvicorn development server on :8000"
	@echo "  make test         Execute full automated pytest test suite in memory"
	@echo "  make test-fast    Run fast unit tests (excluding live external APIs)"
	@echo "  make ingest       Index citizen welfare schemes from data/ into Qdrant"
	@echo "  make benchmark    Run automated TTFT & TTFAB multi-provider benchmarks"
	@echo "  make lint         Verify code quality with ruff"
	@echo "  make clean        Remove cache files, pytest dumps, and temporary artifacts"
	@echo "  make docker-build Build the container image"
	@echo "  make docker-up    Start FastAPI + Qdrant standalone services via Docker Compose"
	@echo "  make docker-down  Stop Docker Compose services"
	@echo "======================================================================"

dev:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	QDRANT_PATH=":memory:" $(PYTEST) tests/

test-fast:
	QDRANT_PATH=":memory:" $(PYTEST) tests/ -m "not live"

ingest:
	$(PYTHON) scripts/ingest_knowledge.py

benchmark:
	$(PYTHON) scripts/benchmark_providers.py --include-mock --runs 2

lint:
	$(RUFF) check app/ scripts/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name "*.py[cod]" -delete
	find . -type f -name "*.wav" -delete
	find . -type f -name "*.mp3" -delete
	find . -type f -name "*.pcm" -delete

docker-build:
	docker build -t sahayak-voice-assistant:latest .

docker-up:
	docker compose up -d

docker-down:
	docker compose down
