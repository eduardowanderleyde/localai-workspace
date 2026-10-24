# Diário de progresso

## 2026-10-22: Etapa 1 concluída, Etapa 2 (RAG) funcional com recuperação ainda imperfeita

### Decisões
- **Foco: Assistente da EMPETUR**, só com **dados públicos** do site oficial. O repositório é público, então nada interno entra nele. Dados internos (chamados etc.) serão **fictícios** na Etapa 3.
- O repositório guarda apenas a **lista de fontes** ([data/empetur/sources.json](../data/empetur/sources.json)). Os arquivos são baixados para `data/raw/`, que está no `.gitignore`.
- O Ollama roda nativo no macOS. O Postgres + pgvector roda no Docker, na **porta 5434**: a 5432 tem um Postgres 14 do Homebrew e a 5433 está ocupada pelo container `rag-licitacoes-db-1`.
- Sem LangGraph até a Etapa 3, porque ainda não há ferramentas para orquestrar.

### O que funciona
- `POST /chat`: conversa com o qwen3:8b, com resposta completa ou streaming SSE.
- `POST /documents` (upload de PDF/DOCX/HTML/TXT), `GET /documents` e `DELETE /documents/{id}`.
- `POST /ask`: responde citando as fontes `[n]` com título e página. Com `stream: true`, as fontes saem primeiro e depois os tokens.
- Recusa corretamente quando não há informação ("Não encontrei essa informação…").
- 23 fontes indexadas, 416 trechos, cerca de 45 s de ingestão.
- Remoção de cabeçalhos e rodapés repetidos nos PDFs (o timbre poluía a busca).
- Busca híbrida (vetor + texto em português) com fusão RRF e suporte a várias consultas.
- Conjunto de avaliação em [data/empetur/eval.json](../data/empetur/eval.json), com 14 perguntas, e o script `scripts/eval_retrieval.py`.

### Resultados da avaliação (hit@6, 14 perguntas)
| Configuração | hit@6 | MRR | Latência da busca |
|---|---|---|---|
| Híbrida, trechos de 1200 caracteres | **71%** | **0.55** | ~0,1 s |
| Híbrida + HyDE | 71% | 0.49 | +3 a 5 s |

O HyDE ficou **desligado** (`RAG_HYDE=false`) porque não trouxe ganho. Trechos de 600 caracteres foram **piores** que os de 1200.

Falhas atuais (✗): presentes de fornecedores, documentos para convênio, programa de integridade e cachê de artistas.
**Causa:** diferença de vocabulário entre a pergunta coloquial e o texto jurídico, além de trechos longos que misturam vários assuntos (a lista de vedações do Código de Ética, por exemplo).

### Experimentos já feitos (não repetir)
- **Reranker `BAAI/bge-reranker-v2-m3`** (sentence-transformers, MPS): coloca o trecho certo em 1º quando ele está entre os candidatos (resolveu a pergunta de convênio). O custo é cerca de 2 a 4 s por pergunta, 40 s para carregar e a dependência do torch. Não resolve quando o trecho nem chega aos 40 candidatos (caso dos presentes).
- **HyDE sozinho** (só a consulta hipotética) levou "presentes" e "convênio" ao top 4, mas piorou o endereço. Combinado com a pergunta original via RRF, empatou com o original.
- O bge-m3 do Ollama está saudável: em lote e individual dão o mesmo resultado, e a similaridade entre frases faz sentido.

## 2026-10-24: Recuperação de 71% para 86%

- **Trechos por artigo:** um artigo novo começa um trecho novo, e os trechos que continuam um artigo longo recebem o caput entre parênteses, por exemplo `(ART. 13. É vedado ao integrante da EMPETUR…:) III. …`.
- **Título do documento no texto vetorizado** (contextual chunking). O título não é gravado no trecho, só entra no embedding.
- Resultado: **hit@6 = 86%** (12/14), MRR 0.55, com 514 trechos.
- Ainda falham: "presentes de fornecedores" (trecho na posição 73 do vetor e 49 do texto) e "documentos para convênio" (melhor posição 27). Os dois precisam de um **reranker** com mais candidatos.

### Reranker (bge-reranker-v2-m3, 80 candidatos), opcional com `RAG_RERANK=true`
| Configuração | hit@6 | MRR | Latência da busca |
|---|---|---|---|
| Sem reranker | 86% | 0.55 | ~0,1 s |
| Com reranker | 86% | **0.75** | +3 a 4 s (38 s na 1ª, para carregar o modelo) |

- Com o reranker, o trecho certo fica em **1º lugar** em 10 das 14 perguntas. "Convênio" passou a ser encontrado.
- Ele quebrou "senha" (o trecho não passou da nota mínima de 0,1 ou caiu do top 6), e "presentes" segue fora dos 80 candidatos.
- Fica **desligado por padrão** até ampliar o eval. Com 14 perguntas, uma pergunta vale 7 pontos, o que é pouco para decidir.

### OCR e avaliação ampliada (mesma sessão)
- **OCR com Tesseract** (`app/rag/ocr.py`): as páginas de PDF com menos de 100 caracteres são renderizadas a 300 dpi (pypdfium2) e lidas em português. O modelo `por.traineddata` (tessdata_best) fica em `data/tessdata/`, fora do Git. Para baixar: `curl -L -o data/tessdata/por.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/por.traineddata`.
- Resoluções 006/2021 e 007/2021 recuperadas (antes só tinham o carimbo). Entraram as **08/2023** (gratificações de pregoeiro e comissões de licitação) e **09/2023** (atualização dos valores de cachês). Agora são 25 fontes, e a ingestão leva cerca de 4,5 min por causa do OCR (~4 s por página).
- ⚠️ **O OCR erra números** (leu "Nº 68" em vez de "Nº 08" e trocou dígitos do CNPJ). Valores vindos desses documentos merecem desconfiança.
- O gabarito de "presentes" foi corrigido: a regra certa é o **Art. 15** do Código de Ética (proibido, salvo até R$ 100 etc.), não o Art. 13.
- **Eval ampliado para 31 perguntas**, todas com o trecho esperado conferido no banco, mais 3 perguntas sem resposta (`unanswerable`) para avaliar recusas no futuro.

| Configuração (31 perguntas) | hit@6 | MRR |
|---|---|---|
| Sem reranker | **77%** | 0.54 |
| Com reranker | 77% | **0.65** |

Falhas sem reranker: documentos para convênio, ONG em convênio, salário do aprendiz, penalidades do Código, campanha política, irregularidade e devolução de recursos.

### O que tem no corpus (resumo)
Regras e processos, não turismo em si: fomento e pedidos de apoio, contratação de artistas e cachês, convênios (resoluções, decreto e portaria SCGE), Código de Ética 2024, Jovem Aprendiz, gratificações de licitação e páginas institucionais (contato, ouvidoria, comissão de ética). **Não tem** eventos, destinos, estatísticas de turismo, salários nem conteúdo de contratos e licitações.

## Próximos passos (retomar aqui)
1. **Melhorar a recuperação**, sempre medindo com `make eval`:
   - ~~Dividir por artigo/inciso~~ e ~~título no embedding~~: feitos em 2026-10-24.
   - ~~Reranker~~: feito, opcional (ver a tabela acima).
   - ~~Ampliar o eval~~: feito (31 perguntas).
   - **Próximo:** analisar uma a uma as 7 falhas acima, ver em que posição está o trecho e por quê.
   - Avaliar a **resposta final** (fidelidade às fontes), não só a recuperação.
   - Ampliar o eval para cerca de 30 perguntas.
2. **Interface web (Next.js)**: chat com as fontes clicáveis (título, página, link para o PDF oficial).
3. ~~OCR~~: feito.
4. **Etapa 3**: agente com ferramentas (LangGraph), chamados fictícios, confirmação antes de ações e auditoria.

## Como retomar
```bash
docker compose up -d --wait                       # Postgres na 5434 (o volume mantém os dados)
make api                                          # http://localhost:8000/docs
make ingest                                       # só se o banco estiver vazio
make eval                                         # avaliação da recuperação
```
