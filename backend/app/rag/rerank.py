"""Reranker cross-encoder: lê pergunta e trecho juntos e dá uma nota de relevância.

Opcional: requer o extra `rerank` (uv sync --extra rerank), que instala sentence-transformers.
"""

import asyncio
from functools import cached_property


class Reranker:
    def __init__(self, model_name: str):
        self.model_name = model_name

    @cached_property
    def _model(self):
        # Import tardio: o torch só é carregado se o reranker estiver ligado.
        from sentence_transformers import CrossEncoder

        return CrossEncoder(self.model_name, max_length=512)

    def warm_up(self) -> None:
        _ = self._model

    async def score(self, question: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(question, p) for p in passages]
        # A inferência é síncrona (GPU/MPS); roda numa thread para não travar o servidor.
        scores = await asyncio.to_thread(self._model.predict, pairs, batch_size=16)
        return [float(s) for s in scores]
