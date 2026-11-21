"""Transactional document storage. All paths are configuration-owned."""
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .core import OCREngine, Page


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, source BLOB NOT NULL, sha256 TEXT NOT NULL,
                    engine TEXT NOT NULL, language TEXT NOT NULL, elapsed_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pages (
                    document_id TEXT NOT NULL REFERENCES documents(id),
                    number INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    png BLOB NOT NULL, words TEXT NOT NULL,
                    PRIMARY KEY(document_id, number)
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def save(self, source: bytes, engine: OCREngine, pages: list[Page], elapsed_ms: int) -> str:
        document_id = str(uuid4())
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)", (
                document_id, source, sha256(source).hexdigest(), engine.name, engine.language, elapsed_ms,
            ))
            db.executemany("INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?)", (
                (document_id, number, page.width, page.height, page.png,
                 json.dumps([asdict(word) for word in page.words], ensure_ascii=False, allow_nan=False))
                for number, page in enumerate(pages, 1)
            ))
        return document_id

    def result(self, document_id: str):
        with closing(self.connect()) as db:
            document = db.execute(
                "SELECT sha256, engine, language, elapsed_ms FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if document is None:
                return None
            rows = db.execute(
                "SELECT number, width, height, words FROM pages WHERE document_id = ? ORDER BY number",
                (document_id,),
            )
            digest, engine, language, elapsed_ms = document
            return dict(id=document_id, sha256=digest, engine=engine, language=language,
                        elapsed_ms=elapsed_ms, pages=[
                            dict(number=n, width=w, height=h, words=json.loads(words))
                            for n, w, h, words in rows
                        ])

    def original(self, document_id: str):
        with closing(self.connect()) as db:
            row = db.execute("SELECT source FROM documents WHERE id = ?", (document_id,)).fetchone()
        return row[0] if row else None

    def preview(self, document_id: str, number: int):
        with closing(self.connect()) as db:
            row = db.execute("SELECT png FROM pages WHERE document_id = ? AND number = ?",
                             (document_id, number)).fetchone()
        return row[0] if row else None
