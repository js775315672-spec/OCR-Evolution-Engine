import hashlib
import os
import shutil
import sqlite3
import subprocess
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

from ocr_engine.core import EngineError, InvalidPDF, Page, Tesseract, Word, process_pdf
from ocr_engine.storage import Store
from tests.support import FakeEngine, sample_pdf


class CoreTests(unittest.TestCase):
    def test_renders_each_page(self):
        pages = process_pdf(sample_pdf(2), FakeEngine())
        self.assertEqual([(p.width, p.height) for p in pages], [(800, 320)] * 2)

    def test_rejects_malformed_and_excess_pages(self):
        for data in (b"not pdf", b"%PDF-broken", sample_pdf(13)):
            with self.subTest(length=len(data)), self.assertRaises(InvalidPDF):
                process_pdf(data, FakeEngine())

    def test_rejects_invalid_engine_coordinates(self):
        with patch.object(FakeEngine, "recognize", return_value=[Word("x", -1, 2, 20, 10, 99)]):
            with self.assertRaises(EngineError):
                process_pdf(sample_pdf(), FakeEngine())

    def test_tesseract_tsv_contract(self):
        tsv = (b"level\tleft\ttop\twidth\theight\tconf\ttext\n"
               b"4\t1\t1\t60\t30\t-1\t\n5\t2\t3\t40\t20\t96.5\thello\n")
        with patch("ocr_engine.core.subprocess.run", return_value=subprocess.CompletedProcess([], 0, tsv)) as run:
            self.assertEqual(Tesseract().recognize(b"png"), [Word("hello", 2, 3, 40, 20, 96.5)])
            self.assertEqual(run.call_args.args[0], ["tesseract", "stdin", "stdout", "-l", "eng", "tsv"])
        with self.assertRaises(ValueError):
            Tesseract("--help")

    def test_sqlite_round_trip_and_rollback(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ocr.sqlite3"
            store, engine, source = Store(path), FakeEngine(), sample_pdf()
            pages = process_pdf(source, engine)
            document_id = store.save(source, engine, pages, 8)
            reopened = Store(path)
            self.assertEqual(reopened.original(document_id), source)
            self.assertEqual(reopened.preview(document_id, 1), pages[0].png)
            self.assertEqual(reopened.result(document_id)["sha256"], hashlib.sha256(source).hexdigest())
            invalid = Page(24, 24, b"", [Word("bad", 0, 0, 1, 1, float("nan"))])
            with self.assertRaises(ValueError):
                store.save(source, engine, [pages[0], invalid], 1)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM documents").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM pages").fetchone()[0], 1)

    @unittest.skipUnless(shutil.which("tesseract") or os.environ.get("OCR_REQUIRE_TESSERACT") == "1",
                         "Tesseract absent on this machine")
    def test_real_tesseract(self):
        source = sample_pdf()
        start = perf_counter()
        page, = process_pdf(source, Tesseract())
        print(f'English smoke fixture, PDF render + OCR: {(perf_counter() - start) * 1000:.1f} ms', flush=True)
        self.assertEqual(" ".join(word.text for word in page.words), "HELLO OCR")

    def test_g0_repository_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / ".gitmodules").exists())
        protected = ("Harness-Ouroboros-MCP", "Cerberus", "Fenrir-Agent")
        files = [*root.joinpath("ocr_engine").rglob("*.py"), root / "pyproject.toml"]
        files += list(root.joinpath(".github/workflows").glob("*.yml"))
        for path in files:
            with self.subTest(file=path.name):
                content = path.read_text(encoding="utf-8")
                self.assertTrue(all(name.casefold() not in content.casefold() for name in protected))
                self.assertNotIn("schedule:", content)
                if path.suffix == ".yml":
                    self.assertIn("contents: read", content)
                    self.assertNotIn("pull_request_target", content)
