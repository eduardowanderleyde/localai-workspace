"""Divide páginas em trechos com sobreposição, respeitando parágrafos e frases."""

import re
from dataclasses import dataclass

from app.rag.parsing import Page

_SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " "]


@dataclass
class Chunk:
    page: int | None
    content: str


def _split(text: str, size: int, separators: list[str]) -> list[str]:
    """Quebra o texto em pedaços de até `size` caracteres, usando o separador mais "forte"."""
    if len(text) <= size:
        return [text]
    for i, sep in enumerate(separators):
        if sep not in text:
            continue
        parts = [p + sep for p in text.split(sep)]
        parts[-1] = parts[-1].removesuffix(sep)
        out: list[str] = []
        for part in parts:
            out.extend(_split(part, size, separators[i + 1 :]) if len(part) > size else [part])
        return out
    return [text[i : i + size] for i in range(0, len(text), size)]


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        current = ""
        for piece in _split(page.text, size, _SEPARATORS):
            if current and len(current) + len(piece) > size:
                chunks.append(Chunk(page.number, current.strip()))
                tail = current[-overlap:] if overlap else ""
                # Começa a sobreposição numa fronteira de palavra.
                current = tail[tail.find(" ") + 1 :] if " " in tail else tail
            current += piece
        if current.strip():
            chunks.append(Chunk(page.number, current.strip()))
    return [c for c in chunks if re.search(r"\w", c.content)]
