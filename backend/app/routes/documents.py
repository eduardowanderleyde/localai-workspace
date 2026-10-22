from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm import OllamaError
from app.rag.parsing import UnsupportedFileError
from app.rag.service import EmptyDocumentError, RagService
from app.rag.store import Document
from app.sse import sse

router = APIRouter(tags=["documentos"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def get_rag(request: Request) -> RagService:
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")
    return rag


Rag = Annotated[RagService, Depends(get_rag)]


class DocumentOut(BaseModel):
    id: int
    title: str
    filename: str
    source_url: str | None
    pages: int | None
    chunks: int


class IngestOut(BaseModel):
    document: DocumentOut
    created: bool


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    stream: bool = False


class SourceOut(BaseModel):
    ref: int
    document_id: int
    title: str
    source_url: str | None
    page: int | None
    excerpt: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]


def _doc_out(doc: Document) -> DocumentOut:
    return DocumentOut(**{k: v for k, v in asdict(doc).items() if k in DocumentOut.model_fields})


@router.post("/documents", response_model=IngestOut, status_code=201)
async def upload_document(
    rag: Rag,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    source_url: Annotated[str | None, Form()] = None,
):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo maior que 50 MB.")
    try:
        result = await rag.ingest(file.filename or "arquivo", data, title, source_url)
    except (UnsupportedFileError, EmptyDocumentError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IngestOut(document=_doc_out(result.document), created=result.created)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(rag: Rag):
    return [_doc_out(d) for d in await rag.store.list_all()]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: int, rag: Rag):
    if not await rag.store.delete(doc_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, rag: Rag):
    """Responde com base nos documentos indexados, citando as fontes."""
    try:
        if not body.stream:
            answer, sources = await rag.answer(body.question)
            return AskResponse(answer=answer, sources=[asdict(s) for s in sources])
        sources = await rag.retrieve(body.question)
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    async def events():
        # As fontes vão primeiro, para a interface já mostrar de onde vem a resposta.
        yield sse("sources", {"sources": [asdict(s) for s in sources]})
        try:
            async for token in rag.answer_stream(body.question, sources):
                yield sse("token", {"content": token})
            yield sse("done", {})
        except OllamaError as exc:
            yield sse("error", {"detail": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")
