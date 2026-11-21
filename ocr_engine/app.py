import asyncio
import os
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import ClientDisconnect

from .core import EngineError, InvalidPDF, MAX_BYTES, OCREngine, Tesseract, process_pdf
from .storage import Store

WEB = Path(__file__).with_name("web")


def create_app(db_path: Path | None = None, engine: OCREngine | None = None) -> FastAPI:
    app = FastAPI(title="OCR Evolution Engine", version="1.1.0", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    store = Store(db_path or Path(os.environ.get("OCR_DB_PATH", "ocr-data/ocr.sqlite3")))
    engine = engine if engine is not None else Tesseract(os.environ.get("OCR_LANGUAGE", "eng"))
    busy = Lock()

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        return response

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/app.js")
    def script():
        return FileResponse(WEB / "app.js", media_type="text/javascript")

    @app.get("/app.css")
    def stylesheet():
        return FileResponse(WEB / "app.css", media_type="text/css")

    def ingest(source: bytes):
        start = perf_counter()
        pages = process_pdf(source, engine)
        elapsed = round((perf_counter() - start) * 1000)
        return store.save(source, engine, pages, elapsed)

    @app.post("/api/documents", status_code=201)
    async def upload(request: Request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/pdf":
            raise HTTPException(415, "Send application/pdf.")
        origin = request.headers.get("origin")
        if origin is not None and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Cross-origin upload is disabled.")
        if not busy.acquire(blocking=False):
            raise HTTPException(503, "An OCR job is already running.")
        try:
            content = bytearray()
            async with asyncio.timeout(30):
                async for chunk in request.stream():
                    if len(content) + len(chunk) > MAX_BYTES:
                        raise HTTPException(413, "PDF exceeds 16 MiB.")
                    content.extend(chunk)
            document_id = await run_in_threadpool(ingest, bytes(content))
            return {"id": document_id}
        except TimeoutError as exc:
            raise HTTPException(408, "Upload timed out.") from exc
        except ClientDisconnect as exc:
            raise HTTPException(400, "Upload disconnected.") from exc
        except InvalidPDF as exc:
            raise HTTPException(422, str(exc)) from exc
        except EngineError as exc:
            raise HTTPException(503, str(exc)) from exc
        finally:
            busy.release()

    @app.get("/api/documents/{document_id}")
    def result(document_id: UUID):
        value = store.result(str(document_id))
        if value is None:
            raise HTTPException(404, "Document not found.")
        return value

    @app.get("/api/documents/{document_id}/original")
    def original(document_id: UUID):
        source = store.original(str(document_id))
        if source is None:
            raise HTTPException(404, "Document not found.")
        return Response(source, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="original.pdf"'})

    @app.get("/api/documents/{document_id}/pages/{number}")
    def preview(document_id: UUID, number: int):
        png = store.preview(str(document_id), number)
        if png is None:
            raise HTTPException(404, "Page not found.")
        return Response(png, media_type="image/png")

    return app
