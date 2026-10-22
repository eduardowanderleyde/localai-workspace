"""Testes da API com o Ollama simulado (não exigem modelo rodando)."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def fake_ollama(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/tags":
        models = [{"name": "qwen3:8b"}, {"name": "bge-m3:latest"}]
        return httpx.Response(200, json={"models": models})
    if request.url.path == "/api/chat":
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        if body["stream"]:
            lines = [
                {"message": {"content": "Olá"}, "done": False},
                {"message": {"content": ", mundo"}, "done": False},
                {"message": {"content": ""}, "done": True},
            ]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Olá!"}})
    return httpx.Response(404)


@pytest.fixture
def client():
    settings = Settings(_env_file=None, database_url="")
    app = create_app(settings, transport=httpx.MockTransport(fake_ollama))
    with TestClient(app) as c:
        yield c


def test_health(client):
    data = client.get("/health").json()
    assert data["ollama"] == "ok"
    assert data["missing_models"] == []
    # Sem banco configurado a API continua de pé, mas sinaliza o problema.
    assert data["database"] == "unavailable"
    assert data["status"] == "degraded"


def test_chat(client):
    resp = client.post("/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    assert resp.status_code == 200
    assert resp.json() == {"content": "Olá!", "model": "qwen3:8b"}


def test_chat_stream(client):
    resp = client.post(
        "/chat", json={"messages": [{"role": "user", "content": "oi"}], "stream": True}
    )
    assert resp.status_code == 200
    tokens = [
        json.loads(line.removeprefix("data: "))["content"]
        for line in resp.text.splitlines()
        if line.startswith("data: ") and "content" in line
    ]
    assert "".join(tokens) == "Olá, mundo"
    assert "event: done" in resp.text


def test_chat_rejects_empty(client):
    assert client.post("/chat", json={"messages": []}).status_code == 422
