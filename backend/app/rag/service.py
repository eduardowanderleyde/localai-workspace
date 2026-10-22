"""Ingestão de documentos e respostas fundamentadas (RAG)."""

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import PurePath

from app.config import Settings
from app.llm import Message, OllamaClient
from app.rag.chunking import chunk_pages
from app.rag.parsing import parse_document
from app.rag.store import Document, DocumentStore, SearchHit

EMBED_BATCH = 16

RAG_INSTRUCTIONS = """Responda à pergunta usando SOMENTE as fontes abaixo.
- Cite as fontes usadas com o número entre colchetes, por exemplo [1] ou [2][3].
- Seja fiel ao texto: preserve condições, exceções e prazos, e mencione o artigo ou \
resolução quando a fonte indicar. Não generalize uma regra além do que está escrito.
- Se as fontes não contiverem a resposta, responda: "Não encontrei essa informação nos \
documentos disponíveis." Não invente.

Fontes:
{context}"""


HYDE_PROMPT = """Escreva um trecho curto (3 a 5 frases) de um documento oficial de uma empresa \
pública estadual (resolução, código de ética ou regulamento) que responderia à pergunta abaixo. \
Use a linguagem formal e jurídica típica desses documentos. Não explique, escreva só o trecho.

Pergunta: {question}"""


class EmptyDocumentError(ValueError):
    pass


@dataclass
class IngestResult:
    document: Document
    created: bool


@dataclass
class Source:
    """Fonte numerada como aparece no prompt, para a interface exibir as citações."""

    ref: int
    document_id: int
    title: str
    source_url: str | None
    page: int | None
    excerpt: str
    score: float


class RagService:
    def __init__(self, settings: Settings, llm: OllamaClient, store: DocumentStore):
        self.settings = settings
        self.llm = llm
        self.store = store

    async def ingest(
        self, filename: str, data: bytes, title: str | None = None, source_url: str | None = None
    ) -> IngestResult:
        sha256 = hashlib.sha256(data).hexdigest()
        if existing := await self.store.find_by_hash(sha256):
            return IngestResult(existing, created=False)

        pages = parse_document(filename, data)
        chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            raise EmptyDocumentError(
                f"Nenhum texto extraído de {filename} (PDF escaneado precisa de OCR)."
            )

        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[i : i + EMBED_BATCH]
            embeddings += await self.llm.embed([c.content for c in batch])

        has_pages = pages[0].number is not None
        document = await self.store.add(
            title=title or PurePath(filename).stem.replace("_", " "),
            filename=filename,
            source_url=source_url,
            sha256=sha256,
            pages=pages[-1].number if has_pages else None,
            chunks=chunks,
            embeddings=embeddings,
        )
        return IngestResult(document, created=True)

    async def retrieve(self, question: str) -> list[Source]:
        texts = [question]
        if self.settings.rag_hyde:
            # HyDE: um trecho hipotético no estilo dos documentos aproxima a pergunta coloquial
            # do vocabulário jurídico. Ele só orienta a busca; nunca é usado como fonte.
            hypothetical = await self.llm.chat(
                [Message(role="user", content=HYDE_PROMPT.format(question=question))]
            )
            texts.append(f"{question}\n{hypothetical}")
        embeddings = await self.llm.embed(texts)
        hits = await self.store.search(
            list(zip(embeddings, texts, strict=True)), self.settings.rag_top_k
        )
        relevant = [h for h in hits if h.score >= self.settings.rag_min_score]
        return [_to_source(i, h) for i, h in enumerate(relevant, 1)]

    def build_messages(self, question: str, sources: list[Source]) -> list[Message]:
        context = "\n\n".join(
            f"[{s.ref}] {s.title}{f' (p. {s.page})' if s.page else ''}\n{s.excerpt}"
            for s in sources
        )
        return [
            Message(role="system", content=self.settings.system_prompt),
            Message(
                role="system",
                content=RAG_INSTRUCTIONS.format(context=context or "(nenhuma fonte encontrada)"),
            ),
            Message(role="user", content=question),
        ]

    async def answer(self, question: str) -> tuple[str, list[Source]]:
        sources = await self.retrieve(question)
        return await self.llm.chat(self.build_messages(question, sources)), sources

    async def answer_stream(self, question: str, sources: list[Source]) -> AsyncIterator[str]:
        async for token in self.llm.chat_stream(self.build_messages(question, sources)):
            yield token


def _to_source(ref: int, hit: SearchHit) -> Source:
    return Source(
        ref=ref,
        document_id=hit.document_id,
        title=hit.title,
        source_url=hit.source_url,
        page=hit.page,
        excerpt=hit.content,
        score=round(hit.score, 4),
    )
