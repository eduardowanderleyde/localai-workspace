.PHONY: up down api ingest eval test lint

up:      ## Sobe Postgres + pgvector
	docker compose up -d --wait

down:
	docker compose down

api:     ## Roda a API em modo desenvolvimento (http://localhost:8000/docs)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

ingest:  ## Baixa e indexa as fontes públicas da EMPETUR
	cd backend && uv run python -m scripts.ingest_sources ../data/empetur/sources.json

eval:    ## Mede a recuperação (hit@k, MRR)
	cd backend && uv run python -m scripts.eval_retrieval ../data/empetur/eval.json

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
