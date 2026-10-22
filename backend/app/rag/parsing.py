"""Extrai texto de PDF, DOCX, HTML e TXT, preservando o número da página quando existe."""

import io
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePath

import docx
import trafilatura
from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".txt", ".md"}


class UnsupportedFileError(ValueError):
    pass


@dataclass
class Page:
    number: int | None  # None para formatos sem paginação
    text: str


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # palavras hifenizadas na quebra de linha
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    # Quebras simples dentro de um parágrafo viram espaço; parágrafos ficam separados.
    text = re.sub(r"(?<![.:;!?\n])\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_repeated_lines(pages: list[str], min_len: int = 15) -> list[str]:
    """Remove cabeçalhos e rodapés: linhas que se repetem em pelo menos metade das páginas."""
    if len(pages) < 3:
        return pages
    counts = Counter(
        line
        for text in pages
        for line in {ln.strip() for ln in text.splitlines()}
        if len(line) >= min_len
    )
    repeated = {line for line, n in counts.items() if n >= len(pages) / 2}
    return [
        "\n".join(ln for ln in text.splitlines() if ln.strip() not in repeated) for text in pages
    ]


def parse_document(filename: str, data: bytes) -> list[Page]:
    ext = PurePath(filename).suffix.lower()
    if ext == ".pdf":
        raw = [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
        pages = [Page(i, clean_text(t)) for i, t in enumerate(strip_repeated_lines(raw), 1)]
    elif ext == ".docx":
        paragraphs = [p.text for p in docx.Document(io.BytesIO(data)).paragraphs]
        pages = [Page(None, clean_text("\n\n".join(paragraphs)))]
    elif ext in {".html", ".htm"}:
        pages = [Page(None, clean_text(trafilatura.extract(data.decode("utf-8", "replace")) or ""))]
    elif ext in {".txt", ".md"}:
        pages = [Page(None, clean_text(data.decode("utf-8", "replace")))]
    else:
        raise UnsupportedFileError(f"Formato não suportado: {ext or filename}")
    return [p for p in pages if p.text]
