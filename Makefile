.PHONY: up down api test lint

up:      ## Sobe Postgres + pgvector
	docker compose up -d --wait

down:
	docker compose down

api:     ## Roda a API em modo desenvolvimento (http://localhost:8000/docs)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
