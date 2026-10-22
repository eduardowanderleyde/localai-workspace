# LocalAI Workspace

Plataforma open-source de assistentes empresariais que roda **100% local**: um chatbot que responde perguntas, consulta documentos (RAG) e executa ações autorizadas, sem custo de API e sem enviar dados para fora da máquina.

> Desenvolvido e testado num MacBook Pro M3 Pro (18 GB). Todos os dados de exemplo são fictícios.

## Arquitetura

```text
Next.js (chat)  ──►  FastAPI (+ LangGraph)  ──►  Ollama (macOS, Metal)
                          │                       ├─ qwen3:8b  (chat)
                          ▼                       └─ bge-m3    (embeddings)
                 PostgreSQL + pgvector (Docker)
```

O Ollama roda nativamente no macOS para usar a GPU do Apple Silicon; os demais serviços ficam no Docker, com limite de memória.

## Roadmap

- [x] **Etapa 1 — IA local:** API FastAPI conversando com o Qwen3 8B (resposta completa ou streaming SSE)
- [ ] **Etapa 2 — RAG:** upload de PDF/TXT/DOCX, embeddings no pgvector, respostas com citação das fontes
- [ ] **Etapa 3 — Agente:** ferramentas (chamados, relatórios), confirmação antes de ações e trilha de auditoria
- [ ] **Etapa 4 — Publicação:** interface web, demo, testes e documentação

## Como rodar

Pré-requisitos: [Ollama](https://ollama.com), Docker, [uv](https://docs.astral.sh/uv/).

```bash
ollama pull qwen3:8b
ollama pull bge-m3

make up     # Postgres + pgvector
make api    # API em http://localhost:8000/docs
make test
```

Exemplo:

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"O que é RAG?"}]}'

# streaming (Server-Sent Events)
curl -N localhost:8000/chat -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"O que é RAG?"}],"stream":true}'
```
