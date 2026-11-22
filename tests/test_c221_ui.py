"""Static security regression for offline-only human review user interface.

This tests the contract, not the authenticity of real human submissions.
"""
from html.parser import HTMLParser
from pathlib import Path
import unittest


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.external = []
        self.csp = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "meta" and values.get("http-equiv") == "Content-Security-Policy":
            self.csp.append(values.get("content",""))
        if tag in ("script","link","iframe") and ("src" in values or "href" in values):
            self.external.append((tag,values))


class OfflineReviewerStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("tools/c221_offline_reviewer.html").read_text(encoding="utf-8")
        cls.parsed = Inputs()
        cls.parsed.feed(cls.source)

    def test_no_external_scripts_iframes_or_css(self):
        self.assertFalse(self.parsed.external)
        self.assertEqual(len(self.parsed.csp), 1)
        self.assertIn("connect-src 'none'", self.parsed.csp[0])
        self.assertIn("default-src 'none'", self.parsed.csp[0])
        self.assertNotIn("fetch(", self.source)
        self.assertNotIn("XMLHttpRequest", self.source)

    def test_manual_visual_review_fields(self):
        self.assertTrue({"photo", "reviewer", "case", "transcription",
                         "visual", "blind", "noocr", "save"} <= self.parsed.ids)
        self.assertIn("crypto.subtle.digest", self.source)
        self.assertIn("no_ocr_assistance_attested:true", self.source)
        self.assertIn("new Blob", self.source)

    def test_no_preapproved_human_text(self):
        self.assertIn("if(!transcript.trim())", self.source)
        self.assertIn("if(!($(\"visual\").checked", self.source)
        self.assertIn("각자", self.source)


if __name__ == "__main__":
    unittest.main()
