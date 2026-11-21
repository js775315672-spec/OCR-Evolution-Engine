import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from ocr_engine.app import create_app
from ocr_engine.core import EngineError
from tests.support import FakeEngine, sample_pdf


class APITests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)
        self.engine = FakeEngine()
        self.client = TestClient(create_app(self.path / "ocr.sqlite3", self.engine))
        self.addCleanup(self.client.close)

    def upload(self, source=None):
        return self.client.post("/api/documents", content=source if source is not None else sample_pdf(),
                                headers={"Content-Type": "application/pdf"})

    def test_comparison_flow(self):
        source = sample_pdf(2)
        upload = self.upload(source)
        self.assertEqual(upload.status_code, 201)
        url = "/api/documents/" + upload.json()["id"]
        result = self.client.get(url)
        pages = result.json()["pages"]
        self.assertEqual([page["number"] for page in pages], [1, 2])
        self.assertEqual(pages[0]["words"][0]["x"], 1)
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertIn("default-src 'none'", self.client.get("/").headers["content-security-policy"])
        self.assertIn("words.textContent", self.client.get("/app.js").text)
        self.assertEqual(self.client.get(url + "/pages/2").headers["content-type"], "image/png")
        self.assertEqual(self.client.get(url + "/pages/3").status_code, 404)
        original = self.client.get(url + "/original")
        self.assertEqual(original.content, source)
        self.assertIn("attachment", original.headers["content-disposition"])

    def test_security_and_error_contract(self):
        self.assertEqual(self.upload(b"bad").status_code, 422)
        with patch("ocr_engine.app.MAX_BYTES", 8):
            self.assertEqual(self.upload(b"%PDF-long-data").status_code, 413)
        self.assertEqual(self.client.post("/api/documents", content=b"x").status_code, 415)
        self.assertEqual(self.client.get("/api/documents/bad-id").status_code, 422)
        self.assertEqual(self.client.get("/", headers={"host": "example.org"}).status_code, 400)
        self.assertEqual(self.client.post("/api/documents", content=b"x", headers={
            "Content-Type": "application/pdf", "Origin": "https://example.org",
        }).status_code, 403)
        with patch.object(self.engine, "recognize", side_effect=EngineError("local failure")):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.upload().status_code, 201)

    def test_independent_storage(self):
        document_id = self.upload().json()["id"]
        with TestClient(create_app(self.path / "other.sqlite3", FakeEngine())) as other:
            self.assertEqual(other.get("/api/documents/" + document_id).status_code, 404)
