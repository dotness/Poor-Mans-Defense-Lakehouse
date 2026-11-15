.PHONY: help setup up down clean status test simulate-telemetry trigger-pipeline query-analytics seed-graph

PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
PIP ?= $(shell if [ -f .venv/bin/pip ]; then echo .venv/bin/pip; else echo pip3; fi)
DOCKER_COMPOSE ?= docker compose

help:
	@echo "Poor Man's Defense Lakehouse Platform Lifecycle Commands:"
	@echo "  make setup                Initialize .env and local data buffers"
	@echo "  make up                   Start all platform containers in detached mode"
	@echo "  make down                 Stop platform containers (preserves volume data)"
	@echo "  make clean                Stop containers and wipe all persistent volumes/buffers"
	@echo "  make status               Display health and resource consumption of all services"
	@echo "  make test                 Run full test suite (contract, unit, integration)"
	@echo "  make simulate-telemetry   Publish 10,000 synthetic MQTT events to Mosquitto"
	@echo "  make trigger-pipeline     Run batch flush pipeline from buffer to MinIO Parquet"
	@echo "  make query-analytics      Execute DuckDB SQL query benchmark over MinIO Parquet"
	@echo "  make seed-graph           Seed Memgraph with synthetic intelligence entities"

setup:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	@mkdir -p /tmp/artemis/buffer
	@echo "Setup complete. Please update GOOGLE_AI_STUDIO_API_KEY in .env."

up:
	@$(DOCKER_COMPOSE) up -d
	@echo "Waiting for services to become healthy..."
	@sleep 3
	@$(DOCKER_COMPOSE) ps

down:
	@$(DOCKER_COMPOSE) down

clean:
	@$(DOCKER_COMPOSE) down -v --remove-orphans
	@rm -rf /tmp/artemis/buffer/*
	@echo "Platform stopped and all data volumes/buffers wiped."

status:
	@$(PYTHON) -m src.cli.main status || $(DOCKER_COMPOSE) ps

test:
	@$(PYTHON) -m pytest -v --timeout=60 tests/

api:
	@$(PYTHON) -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

simulate-telemetry:
	@$(PYTHON) tools/simulate_telemetry.py

trigger-pipeline:
	@$(PYTHON) -m src.pipelines.mqtt_to_minio

query-analytics:
	@$(PYTHON) -m src.cli.main query --sql "SELECT metric_name, COUNT(*) as sample_count, ROUND(AVG(value), 2) as avg_val FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY metric_name"

seed-graph:
	@$(PYTHON) src/scripts/seed_graph.py
