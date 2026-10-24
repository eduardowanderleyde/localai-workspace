import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.db import open_pool
from app.llm import OllamaClient
from app.rag.rerank import Reranker
from app.rag.service import RagService
from app.rag.store import DocumentStore
from app.routes import chat, documents

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.llm = OllamaClient(settings, transport=transport)
        app.state.rag = None
        pool = None
        if settings.database_url:
            try:
                pool = await open_pool(settings.database_url, settings.embedding_dim)
                reranker = None
                if settings.rag_rerank:
                    reranker = Reranker(settings.rerank_model)
                    reranker.warm_up()  # carrega o modelo na subida, não na 1ª pergunta
                app.state.rag = RagService(settings, app.state.llm, DocumentStore(pool), reranker)
            except Exception:
                # A API sobe mesmo sem banco; as rotas de documentos respondem 503.
                log.exception("Não foi possível conectar ao Postgres")
        yield
        if pool:
            await pool.close()
        await app.state.llm.aclose()

    app = FastAPI(title="Assistente EMPETUR", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat.router)
    app.include_router(documents.router)

    @app.get("/health", tags=["infra"])
    async def health(request: Request):
        llm: OllamaClient = request.app.state.llm
        try:
            models = await llm.available_models()
        except httpx.HTTPError:
            return {"status": "degraded", "ollama": "unreachable"}
        database = "ok" if request.app.state.rag else "unavailable"
        missing = [
            m
            for m in (settings.chat_model, settings.embedding_model)
            if not any(name == m or name == f"{m}:latest" for name in models)
        ]
        return {
            "status": "ok" if not missing and database == "ok" else "degraded",
            "ollama": "ok",
            "database": database,
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
            "missing_models": missing,
        }

    return app


app = create_app()
