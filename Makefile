COMPOSE := docker compose -f deploy/docker-compose.yml
BACKEND := cd backend &&

.PHONY: up down infra dev api worker migrate seed test test-backend test-frontend lint fmt chaos gen-api demo

up: ## Build and start the whole stack (offline, no keys needed)
	$(COMPOSE) --profile app up -d --build
	@./scripts/wait-for-stack.sh

down:
	$(COMPOSE) --profile app --profile mcp down

infra: ## Start only Postgres, Redis and Temporal (for local dev)
	$(COMPOSE) up -d postgres redis temporal temporal-ui

migrate:
	$(BACKEND) uv run alembic upgrade head

api:
	$(BACKEND) uv run uvicorn oryn.api.app:create_app --factory --reload --port 8800

worker:
	$(BACKEND) uv run python -m oryn.orchestration.worker

seed:
	$(BACKEND) uv run python -m oryn.seed

test: test-backend test-frontend

test-backend:
	$(BACKEND) uv run pytest -q

test-frontend:
	cd frontend && pnpm vitest run

lint:
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy oryn
	cd frontend && pnpm tsc --noEmit && pnpm lint

fmt:
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .

gen-api:
	$(BACKEND) uv run python scripts/export_openapi.py ../frontend/openapi.json
	cd frontend && pnpm gen:api

chaos:
	./scripts/chaos.sh
