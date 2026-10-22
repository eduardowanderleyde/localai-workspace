"""Baixa as fontes públicas listadas em um manifesto e as indexa no RAG.

Uso (a partir de backend/):
    uv run python -m scripts.ingest_sources ../data/empetur/sources.json
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.config import get_settings
from app.db import open_pool
from app.llm import OllamaClient
from app.rag.service import EmptyDocumentError, RagService
from app.rag.store import DocumentStore

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def _encode_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(parts.path)))


async def download(http: httpx.AsyncClient, url: str, kind: str) -> tuple[str, bytes]:
    """Baixa com cache em disco; retorna (nome do arquivo, conteúdo)."""
    ext = ".pdf" if kind == "pdf" else ".html"
    cached = CACHE_DIR / f"{hashlib.sha1(url.encode()).hexdigest()[:12]}{ext}"
    filename = Path(urlsplit(url).path).name or "index"
    filename = filename if filename.endswith(ext) else filename + ext
    if cached.exists():
        return filename, cached.read_bytes()
    resp = await http.get(_encode_url(url))
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(resp.content)
    return filename, resp.content


async def main(manifest: Path) -> int:
    sources = json.loads(manifest.read_text())["sources"]
    settings = get_settings()
    llm = OllamaClient(settings)
    pool = await open_pool(settings.database_url, settings.embedding_dim)
    rag = RagService(settings, llm, DocumentStore(pool))
    failures = 0

    headers = {"User-Agent": "Mozilla/5.0 (LocalAI Workspace; public data ingestion)"}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as http:
        for src in sources:
            try:
                filename, data = await download(http, src["url"], src["type"])
                result = await rag.ingest(filename, data, src["title"], src["url"])
            except (httpx.HTTPError, EmptyDocumentError) as exc:
                failures += 1
                print(f"  ✗ {src['title']}: {exc}")
                continue
            doc = result.document
            status = "novo" if result.created else "já indexado"
            print(f"  ✓ {doc.title} — {doc.chunks} trechos ({status})")

    await pool.close()
    await llm.aclose()
    print(f"\n{len(sources) - failures}/{len(sources)} fontes indexadas.")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    sys.exit(asyncio.run(main(parser.parse_args().manifest)))
