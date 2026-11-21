"""Local PDF rendering and interchangeable OCR."""
import csv
import io
import math
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol

import pymupdf as fitz

MAX_BYTES = 16 * 1024 * 1024
MAX_PAGES = 12
MAX_PIXELS = 4_000_000


class InvalidPDF(ValueError):
    pass


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class Word:
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True)
class Page:
    width: int
    height: int
    png: bytes
    words: list[Word]


class OCREngine(Protocol):
    name: str
    language: str

    def recognize(self, png: bytes) -> list[Word]: ...


@dataclass(frozen=True)
class Tesseract:
    language: str = "eng"
    executable: str = "tesseract"
    name = "tesseract"

    def __post_init__(self):
        if not re.fullmatch(r"[a-z]{3}(?:\+[a-z]{3})*", self.language):
            raise ValueError("Expected Tesseract language codes such as eng+kor")

    def recognize(self, png: bytes) -> list[Word]:
        try:
            result = subprocess.run(
                [self.executable, "stdin", "stdout", "-l", self.language, "tsv"],
                input=png, capture_output=True, timeout=20, check=True,
            )
            rows = csv.DictReader(io.StringIO(result.stdout.decode("utf-8")), delimiter="\t",
                                  quoting=csv.QUOTE_NONE)
            return [
                Word(row["text"].strip(), int(row["left"]), int(row["top"]),
                     int(row["width"]), int(row["height"]), float(row["conf"]))
                for row in rows if row["level"] == "5" and row["text"] and row["text"].strip()
            ]
        except (OSError, subprocess.SubprocessError, UnicodeError, KeyError, ValueError) as exc:
            raise EngineError("Local OCR failed. Check Tesseract and its language pack.") from exc


def process_pdf(source: bytes, engine: OCREngine) -> list[Page]:
    if len(source) > MAX_BYTES or not source.startswith(b"%PDF-"):
        raise InvalidPDF("Expected a PDF within the upload size limit.")
    try:
        with fitz.open(stream=source, filetype="pdf") as doc:
            if doc.needs_pass or not 1 <= len(doc) <= MAX_PAGES:
                raise InvalidPDF("Expected an unencrypted PDF with 1–12 pages.")
            pages = []
            for page in doc:
                rect = page.rect
                if not all(math.isfinite(n) and n > 0 for n in (rect.width, rect.height)):
                    raise InvalidPDF("Invalid page dimensions.")
                scale = min(2.0, math.sqrt(MAX_PIXELS / (rect.width * rect.height)))
                if math.ceil(rect.width * scale) * math.ceil(rect.height * scale) > MAX_PIXELS:
                    scale *= 0.995
                bounds = (rect * fitz.Matrix(scale, scale)).irect
                if not 0 < bounds.width * bounds.height <= MAX_PIXELS:
                    raise InvalidPDF("Page exceeds render limits.")
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=False)
                png = pix.tobytes("png")
                words = engine.recognize(png)
                if any(not (word.text and 0 <= word.x < word.x + word.width <= pix.width
                            and 0 <= word.y < word.y + word.height <= pix.height
                            and 0 <= word.confidence <= 100) for word in words):
                    raise EngineError("OCR engine returned invalid word coordinates or confidence.")
                pages.append(Page(pix.width, pix.height, png, words))
            return pages
    except (RuntimeError, ValueError, OverflowError) as exc:
        if isinstance(exc, (InvalidPDF, EngineError)):
            raise
        raise InvalidPDF("Unable to render this PDF.") from exc
