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


# Início de artigo em textos normativos ("Art. 13.", "ART. 09º.", "Art. 4o").
_ARTICLE = re.compile(r"(?=\b(?:Art|ART)\.?\s*\d+\s*[º°o]?\.?\s)")
_CAPUT_END = re.compile(r":|\s[IVXL]{1,6}\s*[.\-–)]\s")
_CAPUT_MAX = 200


def _caput(article: str) -> str:
    """Enunciado do artigo, até os dois-pontos ou o primeiro inciso."""
    end = _CAPUT_END.search(article)
    caput = article[: end.start() + 1 if end else _CAPUT_MAX].strip()
    return caput[:_CAPUT_MAX]


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[Chunk]:
    """Agrupa o texto em trechos de até `size` caracteres.

    Em textos normativos, um artigo novo começa um trecho novo (se o atual já tiver conteúdo
    razoável), e os trechos que continuam um artigo longo recebem o caput como contexto,
    para que um inciso isolado ainda diga a que regra pertence.
    """
    chunks: list[Chunk] = []
    caput = ""
    for page in pages:
        # Uma página que continua um artigo da anterior já começa com o caput.
        current = f"({caput}) " if caput else ""
        for segment in _ARTICLE.split(page.text):
            if _ARTICLE.match(segment):
                if len(current) > size * 0.4:
                    chunks.append(Chunk(page.number, current.strip()))
                    current = ""
                elif current.startswith("(") and caput:
                    current = ""  # descarta o caput do artigo anterior, que não tem conteúdo
                caput = _caput(segment)
            for piece in _split(segment, size, _SEPARATORS):
                if current.strip() and len(current) + len(piece) > size:
                    chunks.append(Chunk(page.number, current.strip()))
                    tail = current[-overlap:] if overlap else ""
                    # Começa a sobreposição numa fronteira de palavra.
                    tail = tail[tail.find(" ") + 1 :] if " " in tail else tail
                    current = (f"({caput}) " if caput else "") + tail
                current += piece
        if current.strip() and current.strip() != f"({caput})":
            chunks.append(Chunk(page.number, current.strip()))
    return [c for c in chunks if re.search(r"\w", c.content)]
