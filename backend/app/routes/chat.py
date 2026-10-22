from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm import Message, OllamaClient, OllamaError
from app.sse import sse

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    model: str


def get_llm(request: Request) -> OllamaClient:
    return request.app.state.llm


def _with_system_prompt(llm: OllamaClient, messages: list[Message]) -> list[Message]:
    if messages[0].role == "system":
        return messages
    return [Message(role="system", content=llm.settings.system_prompt), *messages]


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, llm: Annotated[OllamaClient, Depends(get_llm)]):
    messages = _with_system_prompt(llm, body.messages)

    if body.stream:

        async def events():
            try:
                async for token in llm.chat_stream(messages):
                    yield sse("token", {"content": token})
                yield sse("done", {"model": llm.settings.chat_model})
            except OllamaError as exc:
                yield sse("error", {"detail": str(exc)})

        return StreamingResponse(events(), media_type="text/event-stream")

    try:
        content = await llm.chat(messages)
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(content=content, model=llm.settings.chat_model)
