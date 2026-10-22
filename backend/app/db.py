"""Conexão com o Postgres e criação do esquema (idempotente)."""

import psycopg
from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id             bigserial PRIMARY KEY,
    title          text NOT NULL,
    filename       text NOT NULL,
    source_url     text,
    content_sha256 text NOT NULL UNIQUE,
    pages          int,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index int NOT NULL,
    page        int,
    content     text NOT NULL,
    embedding   vector({dim}) NOT NULL
);

-- Busca textual em português, combinada com a vetorial na busca híbrida.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED;

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id);
"""


async def _configure(conn: psycopg.AsyncConnection) -> None:
    await register_vector_async(conn)


async def open_pool(database_url: str, embedding_dim: int) -> AsyncConnectionPool:
    # A extensão precisa existir antes de registrar o tipo vector nas conexões do pool.
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await conn.execute(SCHEMA.format(dim=embedding_dim))

    pool = AsyncConnectionPool(database_url, configure=_configure, open=False, min_size=1)
    await pool.open(wait=True, timeout=10)
    return pool
