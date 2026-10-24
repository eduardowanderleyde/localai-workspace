# Assistente EMPETUR (LocalAI Workspace)

Assistente de IA da EMPETUR (Empresa de Turismo de Pernambuco) que roda **100% local**: responde perguntas, consulta documentos (RAG) citando a fonte e, no futuro, executa ações autorizadas, sem custo de API e sem enviar dados para fora da máquina.

> Usa apenas **informações públicas** do site oficial ([empetur.pe.gov.br](https://www.empetur.pe.gov.br)). Dados internos usados em demonstrações são fictícios. Desenvolvido num MacBook Pro M3 Pro (18 GB).

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
- [~] **Etapa 2 — RAG:** upload de PDF/DOCX/HTML/TXT, busca híbrida (pgvector + texto) e respostas com citação das fontes. *Funciona; a qualidade da recuperação ainda está em ajuste (hit@6 = 77% em 31 perguntas).*
- [ ] **Etapa 3 — Agente:** ferramentas (chamados, relatórios), confirmação antes de ações e trilha de auditoria
- [ ] **Etapa 4 — Publicação:** interface web, demo, testes e documentação

## Como rodar

Pré-requisitos: [Ollama](https://ollama.com), Docker, [uv](https://docs.astral.sh/uv/) e, para OCR de PDFs escaneados, `brew install tesseract` com o modelo de português em `data/tessdata/` (veja [docs/PROGRESSO.md](docs/PROGRESSO.md)).

```bash
ollama pull qwen3:8b
ollama pull bge-m3

make up       # Postgres + pgvector (porta 5434)
make ingest   # baixa e indexa as fontes públicas da EMPETUR
make api      # API em http://localhost:8000/docs
make eval     # mede a qualidade da recuperação
make test
```

Exemplo:

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"O que é RAG?"}]}'

# pergunta sobre os documentos, com fontes citadas
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"Qual o telefone da ouvidoria?"}'

# streaming (Server-Sent Events)
curl -N localhost:8000/chat -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"O que é RAG?"}],"stream":true}'
```

O andamento, as decisões e os próximos passos estão em [docs/PROGRESSO.md](docs/PROGRESSO.md).
