"""Mede a qualidade da recuperação (hit@k e MRR) num conjunto de perguntas.

Uso (a partir de backend/):
    uv run python -m scripts.eval_retrieval ../data/empetur/eval.json [--compare-hyde]
"""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.db import open_pool
from app.llm import OllamaClient
from app.rag.rerank import Reranker
from app.rag.service import RagService
from app.rag.store import DocumentStore


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


async def evaluate(rag: RagService, cases: list[dict]) -> tuple[float, float]:
    hits = rr = 0.0
    for case in cases:
        start = time.time()
        sources = await rag.retrieve(case["question"])
        expected = [_norm(e) for e in case["expected"]]
        rank = next((s.ref for s in sources if any(e in _norm(s.excerpt) for e in expected)), None)
        hits += rank is not None
        rr += 1 / rank if rank else 0
        mark = f"#{rank}" if rank else "✗"
        print(f"  {mark:>3}  {time.time() - start:4.1f}s  {case['question']}")
    return hits / len(cases), rr / len(cases)


async def main(eval_file: Path, compare_hyde: bool) -> int:
    cases = json.loads(eval_file.read_text())["cases"]
    settings = get_settings()
    llm = OllamaClient(settings)
    pool = await open_pool(settings.database_url, settings.embedding_dim)

    reranker = Reranker(settings.rerank_model) if settings.rag_rerank else None
    configs = [False, True] if compare_hyde else [settings.rag_hyde]
    for hyde in configs:
        cfg = settings.model_copy(update={"rag_hyde": hyde})
        rag = RagService(cfg, llm, DocumentStore(pool), reranker)
        print(
            f"\nHyDE {'ligado' if hyde else 'desligado'}, "
            f"reranker {'ligado' if reranker else 'desligado'} (top_k={settings.rag_top_k}):"
        )
        hit_rate, mrr = await evaluate(rag, cases)
        print(f"  hit@{settings.rag_top_k}: {hit_rate:.0%}   MRR: {mrr:.2f}")

    await pool.close()
    await llm.aclose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("eval_file", type=Path)
    parser.add_argument("--compare-hyde", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.eval_file, args.compare_hyde)))
