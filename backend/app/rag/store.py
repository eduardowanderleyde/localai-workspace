"""Acesso a documentos e trechos no Postgres/pgvector."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from psycopg.rows import class_row
from psycopg_pool import AsyncConnectionPool

from app.rag.chunking import Chunk


@dataclass
class Document:
    id: int
    title: str
    filename: str
    source_url: str | None
    pages: int | None
    chunks: int
    created_at: datetime


@dataclass
class SearchHit:
    document_id: int
    title: str
    source_url: str | None
    page: int | None
    content: str
    score: float


_DOCUMENT_SELECT = """
    SELECT d.id, d.title, d.filename, d.source_url, d.pages, d.created_at,
           (SELECT count(*) FROM chunks c WHERE c.document_id = d.id)::int AS chunks
    FROM documents d
"""


class DocumentStore:
    def __init__(self, pool: AsyncConnectionPool):
        self.pool = pool

    async def find_by_hash(self, sha256: str) -> Document | None:
        async with self.pool.connection() as conn:
            cur = conn.cursor(row_factory=class_row(Document))
            await cur.execute(_DOCUMENT_SELECT + " WHERE d.content_sha256 = %s", (sha256,))
            return await cur.fetchone()

    async def add(
        self,
        *,
        title: str,
        filename: str,
        source_url: str | None,
        sha256: str,
        pages: int | None,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> Document:
        async with self.pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                """INSERT INTO documents (title, filename, source_url, content_sha256, pages)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (title, filename, source_url, sha256, pages),
            )
            (doc_id,) = await cur.fetchone()
            async with conn.cursor() as cur:
                await cur.executemany(
                    """INSERT INTO chunks (document_id, chunk_index, page, content, embedding)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [
                        (doc_id, i, c.page, c.content, np.array(e, dtype=np.float32))
                        for i, (c, e) in enumerate(zip(chunks, embeddings, strict=True))
                    ],
                )
        return await self.get(doc_id)

    async def get(self, doc_id: int) -> Document | None:
        async with self.pool.connection() as conn:
            cur = conn.cursor(row_factory=class_row(Document))
            await cur.execute(_DOCUMENT_SELECT + " WHERE d.id = %s", (doc_id,))
            return await cur.fetchone()

    async def list_all(self) -> list[Document]:
        async with self.pool.connection() as conn:
            cur = conn.cursor(row_factory=class_row(Document))
            await cur.execute(_DOCUMENT_SELECT + " ORDER BY d.created_at DESC")
            return await cur.fetchall()

    async def delete(self, doc_id: int) -> bool:
        async with self.pool.connection() as conn:
            cur = await conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            return cur.rowcount > 0

    async def search(
        self, queries: list[tuple[list[float], str]], top_k: int, candidates: int = 40
    ) -> list[SearchHit]:
        """Busca híbrida com várias consultas (embedding, texto).

        Para cada consulta gera um ranking vetorial e um textual; todos são fundidos por
        Reciprocal Rank Fusion (k=60). `score` é a maior similaridade de cosseno entre o
        trecho e as consultas, usada como limiar de relevância.
        """
        vectors = [np.array(e, dtype=np.float32) for e, _ in queries]
        async with self.pool.connection() as conn:
            rankings = [await self._vector_ranking(conn, v, candidates) for v in vectors]
            rankings += [await self._text_ranking(conn, t, candidates) for _, t in queries]

            rrf: dict[int, float] = {}
            for ranking in rankings:
                for rank, chunk_id in enumerate(ranking, 1):
                    rrf[chunk_id] = rrf.get(chunk_id, 0.0) + 1 / (60 + rank)
            best = sorted(rrf, key=rrf.__getitem__, reverse=True)[:top_k]

            cur = await conn.execute(
                """SELECT c.id, c.document_id, d.title, d.source_url, c.page, c.content,
                          c.embedding
                   FROM chunks c JOIN documents d ON d.id = c.document_id
                   WHERE c.id = ANY(%s)""",
                (best,),
            )
            rows = {row[0]: row for row in await cur.fetchall()}

        hits = []
        for chunk_id in best:
            _, document_id, title, source_url, page, content, embedding = rows[chunk_id]
            emb = embedding.to_numpy()
            score = max(float(emb @ v / (np.linalg.norm(emb) * np.linalg.norm(v))) for v in vectors)
            hits.append(SearchHit(document_id, title, source_url, page, content, score))
        return hits

    @staticmethod
    async def _vector_ranking(conn, vector: np.ndarray, limit: int) -> list[int]:
        cur = await conn.execute(
            "SELECT id FROM chunks ORDER BY embedding <=> %s LIMIT %s", (vector, limit)
        )
        return [r[0] for r in await cur.fetchall()]

    @staticmethod
    async def _text_ranking(conn, text: str, limit: int) -> list[int]:
        # Termos unidos por OU, para não exigir que todas as palavras apareçam no trecho.
        cur = await conn.execute(
            """WITH q AS (SELECT to_tsquery('portuguese',
                   replace(plainto_tsquery('portuguese', %s)::text, '&', '|')) AS tsq)
               SELECT c.id FROM chunks c, q WHERE c.tsv @@ q.tsq
               ORDER BY ts_rank_cd(c.tsv, q.tsq) DESC LIMIT %s""",
            (text, limit),
        )
        return [r[0] for r in await cur.fetchall()]
