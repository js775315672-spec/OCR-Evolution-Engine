import pymupdf as fitz

from ocr_engine.core import Word


def sample_pdf(pages=1):
    with fitz.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=400, height=160)
            page.insert_text((30, 70), "HELLO OCR", fontsize=32)
        return doc.tobytes()


class FakeEngine:
    name = "fixture"
    language = "eng"

    def recognize(self, png):
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        return [Word("<script>fixture</script>", 1, 2, 20, 10, 99.0)]
