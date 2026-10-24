"""OCR de páginas de PDF escaneadas com o Tesseract (precisa do binário `tesseract` instalado)."""

import io
import logging
import shutil
import subprocess
from pathlib import Path

import pypdfium2 as pdfium

from app.config import Settings

log = logging.getLogger(__name__)


class TesseractOCR:
    def __init__(self, tessdata_dir: Path, lang: str = "por", dpi: int = 300):
        self.tessdata_dir = tessdata_dir
        self.lang = lang
        self.dpi = dpi

    def available(self) -> bool:
        if not shutil.which("tesseract"):
            log.warning("OCR desligado: binário `tesseract` não encontrado.")
            return False
        if not (self.tessdata_dir / f"{self.lang}.traineddata").exists():
            log.warning("OCR desligado: %s.traineddata ausente em %s", self.lang, self.tessdata_dir)
            return False
        return True

    def __call__(self, pdf: bytes, page_numbers: list[int]) -> dict[int, str]:
        """Renderiza as páginas pedidas (numeradas a partir de 1) e devolve o texto de cada uma."""
        doc = pdfium.PdfDocument(pdf)
        texts: dict[int, str] = {}
        try:
            for number in page_numbers:
                image = doc[number - 1].render(scale=self.dpi / 72).to_pil()
                png = io.BytesIO()
                image.save(png, format="PNG")
                result = subprocess.run(
                    [
                        "tesseract",
                        "stdin",
                        "stdout",
                        "-l",
                        self.lang,
                        "--tessdata-dir",
                        str(self.tessdata_dir),
                    ],
                    input=png.getvalue(),
                    capture_output=True,
                    check=True,
                )
                texts[number] = result.stdout.decode("utf-8", "replace")
        finally:
            doc.close()
        return texts


def build_ocr(settings: Settings) -> TesseractOCR | None:
    if not settings.ocr_enabled:
        return None
    ocr = TesseractOCR(settings.tessdata_dir)
    return ocr if ocr.available() else None
