from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.llm import OllamaClient
from app.routes import chat


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.llm = OllamaClient(settings, transport=transport)
        yield
        await app.state.llm.aclose()

    app = FastAPI(title="LocalAI Workspace", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat.router)

    @app.get("/health", tags=["infra"])
    async def health(request: Request):
        llm: OllamaClient = request.app.state.llm
        try:
            models = await llm.available_models()
        except httpx.HTTPError:
            return {"status": "degraded", "ollama": "unreachable"}
        missing = [
            m
            for m in (settings.chat_model, settings.embedding_model)
            if not any(name == m or name == f"{m}:latest" for name in models)
        ]
        return {
            "status": "ok" if not missing else "degraded",
            "ollama": "ok",
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
            "missing_models": missing,
        }

    return app


app = create_app()
