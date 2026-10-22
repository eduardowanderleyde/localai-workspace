"""Cliente mínimo para a API HTTP do Ollama."""

import json
from collections.abc import AsyncIterator
from typing import Literal

import httpx
from pydantic import BaseModel

from app.config import Settings


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=settings.request_timeout_s,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _chat_payload(self, messages: list[Message], stream: bool) -> dict:
        return {
            "model": self.settings.chat_model,
            "messages": [m.model_dump() for m in messages],
            "stream": stream,
            "think": self.settings.chat_think,
        }

    async def chat(self, messages: list[Message]) -> str:
        try:
            resp = await self._http.post("/api/chat", json=self._chat_payload(messages, False))
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Falha ao chamar o Ollama: {exc}") from exc
        return resp.json()["message"]["content"]

    async def chat_stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """Gera os pedaços de texto da resposta conforme o modelo produz."""
        try:
            async with self._http.stream(
                "POST", "/api/chat", json=self._chat_payload(messages, True)
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise OllamaError(chunk["error"])
                    if content := chunk.get("message", {}).get("content"):
                        yield content
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise OllamaError(f"Falha ao chamar o Ollama: {exc}") from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self._http.post(
                "/api/embed", json={"model": self.settings.embedding_model, "input": texts}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Falha ao gerar embeddings: {exc}") from exc
        return resp.json()["embeddings"]

    async def available_models(self) -> list[str]:
        resp = await self._http.get("/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
