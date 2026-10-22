from app.rag.chunking import chunk_pages
from app.rag.parsing import Page, clean_text, strip_repeated_lines


def test_clean_text_joins_lines_and_hyphenation():
    assert clean_text("Art. 1º O presente\ncódigo apli-\nca-se a todos.") == (
        "Art. 1º O presente código aplica-se a todos."
    )


def test_strip_repeated_lines_removes_letterhead():
    header = "EMPRESA DE TURISMO DE PERNAMBUCO S/A"
    pages = [f"{header}\nconteúdo da página {i}" for i in range(4)]
    assert strip_repeated_lines(pages) == [f"conteúdo da página {i}" for i in range(4)]


def test_chunks_respect_size_and_keep_page():
    text = " ".join(f"Frase número {i}." for i in range(200))
    chunks = chunk_pages([Page(3, text)], size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c.content) <= 300 for c in chunks)
    assert all(c.page == 3 for c in chunks)
