from __future__ import annotations
import asyncio
import time
import uuid

import logging
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    authenticate,
    create_initial_gm,
    create_user,
    delete_user,
    ensure_server_config,
    get_user,
    is_configured,
    list_users,
    reset_password,
    set_user_enabled,
)
from app.config import APP_NAME, APP_VERSION, STATIC_DIR, TEMPLATE_DIR
from app.knowledgebase import knowledgebase_status
from app.library.covers import (
    cached_cover_path,
    get_cover_path,
    remove_manual_cover,
    save_manual_cover,
)
from app.library.manager import (
    add_folder,
    add_source,
    get_document,
    get_folder,
    list_folders,
    player_can_see_folder,
    remove_folder,
    remove_source,
    scan_folder,
    set_file_visibility,
    set_folder_cover,
    set_folder_visibility,
)
from app.readers.base import safe_document_path
from app.readers.comic import comic_page, comic_pages
from app.readers.image import serve_image
from app.readers.pdf import stream_pdf
from app.readers.text import read_plain_text, render_markdown
from app.uploads import list_uploads, supported_upload, unique_upload_path
from app.search.extract import build_text_cache, clear_text_cache, text_cache_status
from app.search.query import search_library
from app.rag.chunks import build_chunk_cache, chunk_cache_status, clear_chunk_cache
from app.rag.retrieve import available_rag_scope, retrieve_chunks
from app.rag.embeddings import (
    clear_embeddings,
    embedding_build_status,
    embedding_status,
    model_options,
    set_embedding_model,
    start_embedding_build,
)
from app.ai.provider import (
    chat_completion,
    provider_settings_for_ui,
    save_provider_settings,
    test_provider_connection,
)
from app.ai.markdown_render import render_answer_markdown
from app.ai.citations import attach_citation_excerpts

logger = logging.getLogger(__name__)
server_config = ensure_server_config()

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=server_config["session_secret"],
    session_cookie="ttlibrarian_session",
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 12,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals["knowledgebase_status"] = knowledgebase_status


_source_scan_jobs: dict[str, dict] = {}
_source_scan_lock = threading.Lock()


def _source_scan_job_snapshot(job_id: str) -> dict | None:
    with _source_scan_lock:
        job = _source_scan_jobs.get(job_id)
        if job is None:
            return None
        return {
            key: value
            for key, value in job.items()
            if key != "scan_result"
        }


def _set_source_scan_job(job_id: str, **updates) -> None:
    with _source_scan_lock:
        job = _source_scan_jobs.setdefault(job_id, {})
        job.update(updates)


def _run_source_scan_job(
    job_id: str,
    folder_name: str,
    source_path: str,
) -> None:
    try:
        _set_source_scan_job(
            job_id,
            state="adding",
            message="Discovering source folders...",
            current="",
            documents_seen=0,
        )

        result = add_source(folder_name, source_path)
        added_count = int(result.get("added_count") or 1)

        _set_source_scan_job(
            job_id,
            sources_added=added_count,
            state="scanning",
            message="Scanning documents...",
        )

        folder = get_folder(folder_name)
        if folder is None:
            raise ValueError("Virtual folder not found after source assignment.")

        def progress(kind, path, count):
            _set_source_scan_job(
                job_id,
                state="scanning",
                current=path.name,
                documents_seen=count,
                message=f"Scanning document {count}: {path.name}",
            )

        scan_result = scan_folder(
            folder,
            generate_covers=True,
            progress_callback=progress,
        )

        documents = len(scan_result.get("documents", []))
        with _source_scan_lock:
            job = _source_scan_jobs[job_id]
            job.update(
                {
                    "state": "done",
                    "message": (
                        f"Complete. {added_count} source folder"
                        f"{'s' if added_count != 1 else ''} added; "
                        f"{documents} documents found."
                    ),
                    "documents_seen": documents,
                    "scan_result": scan_result,
                }
            )

    except Exception as exc:
        logger.exception("Physical source scan job failed: %s", source_path)
        _set_source_scan_job(
            job_id,
            state="error",
            error=str(exc),
            message=f"Source scan failed: {exc}",
        )



def current_user(request: Request) -> dict[str, str] | None:
    username = request.session.get("username")

    if not username:
        return None

    user = get_user(username)

    if not user or not user.get("enabled", False):
        request.session.clear()
        return None

    request.session["role"] = user["role"]

    return {
        "username": user["username"],
        "role": user["role"],
    }


def folder_visible_to_user(user: dict[str, str], folder: dict) -> bool:
    if user["role"] == "gm":
        return True
    return player_can_see_folder(folder)


def document_visible_to_user(user: dict[str, str], document: dict) -> bool:
    return user["role"] == "gm" or document.get("visibility") == "players"


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("%s v%s initialized", APP_NAME, APP_VERSION)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not is_configured():
        return RedirectResponse("/setup", status_code=303)

    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    folder_cards = []

    for folder in list_folders():
        if not folder_visible_to_user(user, folder):
            continue

        cover_key = None
        cover_path = folder.get("cover")

        if cover_path:
            scan = scan_folder(folder, generate_covers=True)
            cover_doc = next(
                (doc for doc in scan["documents"] if doc["path"] == cover_path),
                None,
            )
            if cover_doc and document_visible_to_user(user, cover_doc):
                cover_key = cover_doc["key"]

        folder_cards.append({**folder, "cover_key": cover_key})

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "folders": folder_cards,
        },
    )


@app.get("/library/{folder_name}", response_class=HTMLResponse)
async def library_folder(request: Request, folder_name: str):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    folder = get_folder(folder_name)
    if not folder or not folder_visible_to_user(user, folder):
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "user": user,
                "title": "Folder not found",
                "message": "That library folder is not available.",
            },
            status_code=404,
        )

    scan = scan_folder(folder)
    scan["documents"] = [
        doc for doc in scan["documents"] if document_visible_to_user(user, doc)
    ]

    return templates.TemplateResponse(
        request=request,
        name="library_folder.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "folder": folder,
            "scan": scan,
        },
    )


@app.get("/cover/{folder_name}/{doc_key}")
async def document_cover(request: Request, folder_name: str, doc_key: str):
    user = current_user(request)
    if not user:
        return Response(status_code=401)

    folder = get_folder(folder_name)
    if not folder or not folder_visible_to_user(user, folder):
        return Response(status_code=404)

    document = get_document(folder, doc_key, generate_cover=True)

    if not document or not document_visible_to_user(user, document):
        return Response(status_code=404)

    source_path = Path(document["path"])
    cover = get_cover_path(str(source_path.parent), source_path.name)

    if not cover or not cover.exists():
        return Response(status_code=404)

    return FileResponse(
        cover,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/read/{folder_name}/{doc_key}", response_class=HTMLResponse)
async def read_document(request: Request, folder_name: str, doc_key: str):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    folder = get_folder(folder_name)
    if not folder or not folder_visible_to_user(user, folder):
        return Response(status_code=404)

    document = get_document(folder, doc_key, generate_cover=False)

    if not document or not document_visible_to_user(user, document):
        return Response(status_code=404)

    path = Path(document["path"])
    common = {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "user": user,
        "folder": folder,
        "document": document,
    }

    if document["type"] == "PDF":
        return templates.TemplateResponse(
            request=request,
            name="reader_pdf.html",
            context=common,
        )

    if document["type"] == "Image":
        return templates.TemplateResponse(
            request=request,
            name="reader_image.html",
            context=common,
        )

    if document["type"] in {"CBZ", "CBR"}:
        try:
            page_count = len(comic_pages(path))
        except Exception:
            logger.exception("Unable to inspect comic archive %s", path)
            page_count = 0

        return templates.TemplateResponse(
            request=request,
            name="reader_comic.html",
            context={**common, "page_count": page_count},
        )

    if document["type"] == "Text":
        return templates.TemplateResponse(
            request=request,
            name="reader_text.html",
            context={**common, "content": read_plain_text(path), "markdown": False},
        )

    if document["type"] == "Markdown":
        return templates.TemplateResponse(
            request=request,
            name="reader_text.html",
            context={**common, "content": render_markdown(path), "markdown": True},
        )

    return Response(status_code=415)


@app.get("/content/{folder_name}/{doc_key}")
async def document_content(request: Request, folder_name: str, doc_key: str):
    user = current_user(request)
    if not user:
        return Response(status_code=401)

    folder = get_folder(folder_name)
    if not folder or not folder_visible_to_user(user, folder):
        return Response(status_code=404)

    document = get_document(folder, doc_key, generate_cover=False)

    if not document or not document_visible_to_user(user, document):
        return Response(status_code=404)

    path = Path(document["path"])

    if document["type"] == "PDF":
        return stream_pdf(request, path)

    if document["type"] == "Image":
        return serve_image(path)

    return Response(status_code=404)


@app.get("/comic-page/{folder_name}/{doc_key}/{page_index}")
async def comic_page_content(
    request: Request,
    folder_name: str,
    doc_key: str,
    page_index: int,
):
    user = current_user(request)
    if not user:
        return Response(status_code=401)

    folder = get_folder(folder_name)
    if not folder or not folder_visible_to_user(user, folder):
        return Response(status_code=404)

    document = get_document(folder, doc_key, generate_cover=False)

    if (
        not document
        or not document_visible_to_user(user, document)
        or document["type"] not in {"CBZ", "CBR"}
    ):
        return Response(status_code=404)

    try:
        return comic_page(Path(document["path"]), page_index)
    except Exception:
        logger.exception(
            "Unable to render comic page %s from %s",
            page_index,
            document["path"],
        )
        return Response(status_code=500)


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    user = current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    search_data = {
        "query": q,
        "results": [],
        "searched_documents": 0,
        "uncached_documents": 0,
    }

    if q.strip():
        search_data = search_library(q.strip(), user["role"], limit=100)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            **search_data,
        },
    )


@app.get("/uploads", response_class=HTMLResponse)
async def uploads_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    uploads = list_uploads()

    if user["role"] != "gm":
        uploads = [
            item
            for item in uploads
            if item["username"].casefold() == user["username"].casefold()
        ]

    return templates.TemplateResponse(
        request=request,
        name="uploads.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "uploads": uploads,
            "folders": list_folders() if user["role"] == "gm" else [],
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@app.post("/uploads/add")
async def upload_file(
    request: Request,
    upload: UploadFile = File(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not upload.filename or not supported_upload(upload.filename):
        return RedirectResponse(
            f"/uploads?error={quote('Unsupported file type.')}",
            status_code=303,
        )

    destination = unique_upload_path(user["username"], upload.filename)

    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)

    await upload.close()

    logger.info("Upload received from %s: %s", user["username"], destination)

    return RedirectResponse(
        f"/uploads?message={quote('Upload complete.')}",
        status_code=303,
    )


@app.post("/uploads/assign")
async def assign_upload(
    request: Request,
    upload_path: str = Form(...),
    folder_name: str = Form(...),
):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    allowed = {item["path"] for item in list_uploads()}

    if upload_path not in allowed:
        return RedirectResponse(
            f"/uploads?error={quote('Upload not found.')}",
            status_code=303,
        )

    try:
        add_source(folder_name, upload_path)
    except ValueError as exc:
        return RedirectResponse(
            f"/uploads?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/uploads?message={quote('Upload added to virtual folder.')}",
        status_code=303,
    )


@app.post("/admin/library/manual-cover")
async def admin_manual_cover(
    request: Request,
    name: str = Form(...),
    doc_key: str = Form(...),
    cover_file: UploadFile = File(...),
):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    folder = get_folder(name)
    document = get_document(folder, doc_key) if folder else None

    if not document:
        return RedirectResponse(
            f"/admin/library?error={quote('Document not found.')}",
            status_code=303,
        )

    suffix = Path(cover_file.filename or "").suffix.casefold()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        return RedirectResponse(
            f"/admin/library?error={quote('Cover must be PNG, JPG, JPEG, or WebP.')}",
            status_code=303,
        )

    temp_path = Path(document["path"]).parent / f".ttlibrarian_cover_upload_{document['key']}{suffix}"

    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await cover_file.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

        source = Path(document["path"])
        save_manual_cover(str(source.parent), source.name, temp_path)
    finally:
        await cover_file.close()
        temp_path.unlink(missing_ok=True)

    return RedirectResponse("/admin/library", status_code=303)


@app.post("/admin/library/manual-cover/remove")
async def admin_manual_cover_remove(
    request: Request,
    name: str = Form(...),
    doc_key: str = Form(...),
):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    folder = get_folder(name)
    document = get_document(folder, doc_key) if folder else None

    if document:
        source = Path(document["path"])
        remove_manual_cover(str(source.parent), source.name)

    return RedirectResponse("/admin/library", status_code=303)


@app.get("/admin/search", response_class=HTMLResponse)
async def admin_search(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/admin/knowledgebase", status_code=303)


@app.post("/admin/search/build")
async def admin_search_build(
    request: Request,
    force: str = Form("false"),
):
    user = current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    summary = build_text_cache(force=(force == "true"))

    message = (
        f"Processed {summary['documents_seen']} documents: "
        f"{summary['extracted']} extracted, "
        f"{summary['cached']} already current, "
        f"{summary['skipped_scanned']} scanned PDFs skipped, "
        f"{summary['errors']} errors."
    )

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote(message)}",
        status_code=303,
    )


@app.post("/admin/search/clear")
async def admin_search_clear(request: Request):
    user = current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    clear_text_cache()

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote('Extracted-text cache cleared.')}",
        status_code=303,
    )



@app.get("/admin/knowledgebase", response_class=HTMLResponse)
async def admin_knowledgebase(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_knowledgebase.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "knowledgebase": knowledgebase_status(),
            "text_status": text_cache_status(),
            "chunk_status": chunk_cache_status(),
            "embedding_status": embedding_status(),
            "embedding_models": model_options(),
            "ai_settings": provider_settings_for_ui(),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@app.get("/admin/rag", response_class=HTMLResponse)
async def admin_rag(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/admin/knowledgebase", status_code=303)


@app.post("/admin/knowledgebase/update")
async def admin_knowledgebase_update(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        text_summary = build_text_cache(force=False)
        if text_summary["errors"]:
            raise RuntimeError(
                f"Text extraction completed with {text_summary['errors']} error(s); "
                "fix those before rebuilding downstream knowledgebase stages."
            )
        chunk_summary = build_chunk_cache()
        start_embedding_build()
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )

    message = (
        f"Knowledgebase update started: {text_summary['documents_seen']} library documents scanned, "
        f"{chunk_summary['documents']} context documents / {chunk_summary['chunks']} chunks built. "
        "Semantic embeddings are building in the background."
    )
    return RedirectResponse(
        f"/admin/knowledgebase?message={quote(message)}",
        status_code=303,
    )


@app.post("/admin/rag/build")
async def admin_rag_build(request: Request):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    summary = build_chunk_cache()

    message = (
        f"Context chunks built: {summary['documents']} documents, "
        f"{summary['pages']} pages, {summary['chunks']} chunks."
    )

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote(message)}",
        status_code=303,
    )


@app.post("/admin/rag/embeddings/model")
async def admin_rag_embeddings_model(request: Request):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    form = await request.form()
    model_key = str(form.get("model_key", "")).strip()

    try:
        selected = set_embedding_model(model_key)
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )

    message = (
        f"Embedding model changed to {selected['label']}. "
        "Build embeddings before using semantic retrieval."
    )

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote(message)}",
        status_code=303,
    )


@app.post("/admin/rag/embeddings/build")
async def admin_rag_embeddings_build(request: Request):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        start_embedding_build()
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        "/admin/knowledgebase?message=Embedding+build+started",
        status_code=303,
    )


@app.get("/admin/rag/embeddings/status")
async def admin_rag_embeddings_status(request: Request):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    return JSONResponse({
        "build": embedding_build_status(),
        "embedding": embedding_status(),
    })


@app.post("/admin/rag/embeddings/clear")
async def admin_rag_embeddings_clear(request: Request):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    clear_embeddings()

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote('Embedding cache cleared.')}",
        status_code=303,
    )

@app.post("/admin/rag/clear")
async def admin_rag_clear(request: Request):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    clear_chunk_cache()

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote('Context chunk cache cleared.')}",
        status_code=303,
    )


@app.post("/admin/ai/save")
async def admin_ai_save(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    form = await request.form()
    try:
        save_provider_settings(
            base_url=str(form.get("base_url", "")),
            model=str(form.get("model", "")),
            api_key=str(form.get("api_key", "")),
            timeout=str(form.get("timeout", "120")),
            temperature=str(form.get("temperature", "0.2")),
            max_tokens=str(form.get("max_tokens", "1200")),
        )
    except Exception as exc:
        return RedirectResponse(f"/admin/knowledgebase?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(f"/admin/knowledgebase?message={quote('AI provider settings saved.')}", status_code=303)


@app.post("/admin/ai/test")
async def admin_ai_test(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    form = await request.form()
    try:
        save_provider_settings(
            base_url=str(form.get("base_url", "")),
            model=str(form.get("model", "")),
            api_key=str(form.get("api_key", "")),
            timeout=str(form.get("timeout", "120")),
            temperature=str(form.get("temperature", "0.2")),
            max_tokens=str(form.get("max_tokens", "1200")),
        )
        result = await asyncio.to_thread(test_provider_connection)
    except Exception as exc:
        return RedirectResponse(f"/admin/knowledgebase?error={quote(str(exc))}", status_code=303)

    models = result.get("models", [])
    message = "AI provider connected successfully."
    if models:
        message = "AI provider connected. Available model: " + ", ".join(models[:5])

    return RedirectResponse(f"/admin/knowledgebase?message={quote(message)}", status_code=303)


@app.get("/ask", response_class=HTMLResponse)
async def ask_page(
    request: Request,
    folder: str = "",
    embed: str = "",
    doc: str = "",
    split: str = "",
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    scope = available_rag_scope(
        user["role"],
        selected_folder=folder,
        selected_documents=[],
        selected_document_keys=[doc] if doc.strip() else [],
    )
    response_id = uuid.uuid4().hex
    return templates.TemplateResponse(
        request=request,
        name="ask.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "question": "",
            "answer": "",
            "answer_html": "",
            "answer_model": "",
            "elapsed_seconds": None,
            "sources": [],
            "scope": scope,
            "provider_configured": provider_settings_for_ui()["configured"],
            "embed": embed == "1",
            "split": split == "1",
            "locked_folder": bool(folder.strip()),
            "locked_document_key": doc.strip(),
            "response_id": response_id,
            "error": None,
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.post("/ask", response_class=HTMLResponse)
async def ask_question(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    question = str(form.get("question", "")).strip()
    folder = str(form.get("folder", "")).strip()
    embed = str(form.get("embed", "")).strip() == "1"
    split = str(form.get("split", "")).strip() == "1"
    locked_document_key = str(form.get("locked_document_key", "")).strip()
    selected_document_keys = [str(value) for value in form.getlist("docs") if str(value).strip()]

    if locked_document_key:
        selected_document_keys = [locked_document_key]

    scope = available_rag_scope(
        user["role"],
        selected_folder=folder,
        selected_documents=[],
        selected_document_keys=selected_document_keys,
    )

    provider_configured = provider_settings_for_ui()["configured"]
    error = None
    answer = ""
    answer_html = ""
    answer_model = ""
    elapsed_seconds = None
    sources = []

    if not question:
        error = "Enter a question."
    elif not provider_configured:
        error = "The AI provider has not been configured."
    else:
        document_scope = scope["selected_document_paths"] or None
        folder_scope = scope["selected_folder"] or None

        try:
            sources = retrieve_chunks(
                question,
                user["role"],
                limit=8,
                folder_scope=folder_scope,
                document_paths=document_scope,
            )

            if not sources:
                raise RuntimeError("No relevant source passages were found in the selected scope.")

            source_blocks = []
            for index, source in enumerate(sources, start=1):
                page = source.get("page")
                page_label = f", page {page}" if page else ""
                revision_label = (
                    " [REVISION/UPDATE CANDIDATE]"
                    if source.get("revision_candidate")
                    else ""
                )
                source_blocks.append(
                    f"[{index}] {source['display_name']}{page_label}{revision_label}\n"
                    f"{source.get('context_text') or source.get('text', '').strip()}"
                )

            system_prompt = (
                "You are Tabletop Librarian, a tabletop RPG rules and reference assistant. "
                "Answer the user's question using only the supplied source passages. "
                "Do not invent rules, classifications, relationships, facts, names, or interpretations "
                "that the passages do not explicitly support. "
                "Treat each numbered source as evidence, not as permission to extrapolate beyond its text. "
                "For comparisons, compare only attributes explicitly stated in the sources. "
                "Do not infer that one creature, rule, class, category, or option is stronger, more dangerous, "
                "higher-ranked, or otherwise superior merely from a label unless the sources explicitly establish "
                "that relationship. "
                "If sources conflict, describe the conflict rather than silently choosing or merging them. "
                "A source marked [REVISION/UPDATE CANDIDATE] must be checked first for explicit language that a rule is now, revised, updated, changed, replaced, or no longer used. "
                "When that language clearly applies to the user's question, treat the revised rule as controlling and do not present the older formula as the current rule. "
                "If one source explicitly says a rule is revised, updated, changed, replaced, or now calculated "
                "differently, identify that as the newer rule and mention the older conflicting rule when relevant. "
                "Adjacent passages may be included around a primary retrieved passage; use them only when they "
                "actually support the answer. "
                "If the evidence is insufficient to answer the question, say exactly what cannot be established. "
                "When making factual claims, cite the supporting numbered sources using [1], [2], etc. "
                "Do not add a mechanical explanation, causal explanation, formula, interaction, or consequence unless a supplied passage explicitly states it. "
                "Do not combine modifiers or invent calculation procedures from separate facts unless the text explicitly tells the reader to do so. "
                "For direct comparisons, prefer explicit comparable statistics, scores, quantities, or stated rankings over descriptive flavor text. "
                "Do not override a clear numerical comparison with narrative adjectives unless a source explicitly states that the narrative distinction supersedes the statistic. "
                "When the question asks for a specific rule, preparation note, procedure, or encounter fact, answer that directly and omit tangential rules even if they are related. "
                "Prefer the shortest answer that completely answers the user's question, and omit unrelated details."
            )

            user_prompt = f"Question:\n{question}\n\nSource passages:\n\n" + "\n\n".join(source_blocks)
            started = time.perf_counter()
            completion = await asyncio.to_thread(
                chat_completion,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            elapsed_seconds = time.perf_counter() - started
            answer = completion["content"]
            attach_citation_excerpts(answer, sources)
            answer_html = render_answer_markdown(answer, source_count=len(sources))
            answer_model = completion["model"]
        except Exception as exc:
            error = str(exc)

    response_id = uuid.uuid4().hex
    return templates.TemplateResponse(
        request=request,
        name="ask.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "question": question,
            "answer": answer,
            "answer_html": answer_html,
            "answer_model": answer_model,
            "elapsed_seconds": elapsed_seconds,
            "sources": sources,
            "scope": scope,
            "provider_configured": provider_configured,
            "embed": embed,
            "split": split,
            "locked_folder": bool(folder.strip()) and embed,
            "locked_document_key": locked_document_key,
            "response_id": response_id,
            "error": error,
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/rag-test", response_class=HTMLResponse)
async def rag_test(request: Request, q: str = "", folder: str = ""):
    user = current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    selected_documents = request.query_params.getlist("docs")
    scope = available_rag_scope(
        user["role"],
        selected_folder=folder,
        selected_documents=selected_documents,
    )

    document_scope = scope["selected_document_paths"] or None
    folder_scope = scope["selected_folder"] or None

    results = (
        retrieve_chunks(
            q.strip(),
            user["role"],
            limit=8,
            folder_scope=folder_scope,
            document_paths=document_scope,
        )
        if q.strip()
        else []
    )

    return templates.TemplateResponse(
        request=request,
        name="rag_test.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "query": q,
            "results": results,
            "scope": scope,
        },
    )


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "users": list_users(),
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@app.post("/admin/users/add")
async def admin_users_add(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        create_user(username, password, "player")
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/users?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/admin/users?message={quote('Player account created.')}",
        status_code=303,
    )


@app.post("/admin/users/toggle")
async def admin_users_toggle(
    request: Request,
    username: str = Form(...),
    enabled: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        set_user_enabled(username, enabled == "true")
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/users?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/password")
async def admin_users_password(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        if not reset_password(username, password):
            raise ValueError("User not found.")
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/users?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/admin/users?message={quote('Password updated.')}",
        status_code=303,
    )


@app.post("/admin/users/delete")
async def admin_users_delete(
    request: Request,
    username: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        if not delete_user(username):
            raise ValueError("User not found.")
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/users?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/admin/users?message={quote('Player account deleted.')}",
        status_code=303,
    )


@app.get("/admin/library", response_class=HTMLResponse)
async def admin_library(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    folder_data = []
    source_job_id = request.query_params.get("source_job")
    completed_job = None

    if source_job_id:
        with _source_scan_lock:
            candidate = _source_scan_jobs.get(source_job_id)
            if candidate and candidate.get("state") == "done":
                completed_job = candidate

    for folder in list_folders():
        if (
            completed_job
            and str(folder.get("name", "")).casefold()
            == str(completed_job.get("folder_name", "")).casefold()
            and completed_job.get("scan_result") is not None
        ):
            scan = completed_job["scan_result"]
        else:
            scan = scan_folder(folder)

        folder_data.append(
            {
                **folder,
                "scan": scan,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="admin_library.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "folders": folder_data,
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@app.post("/admin/library/add")
async def admin_library_add(
    request: Request,
    name: str = Form(...),
    visibility: str = Form("players"),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        add_folder(name, visibility)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/library?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        f"/admin/library?message={quote('Virtual folder created.')}",
        status_code=303,
    )


@app.post("/admin/library/remove")
async def admin_library_remove(
    request: Request,
    name: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    remove_folder(name)
    return RedirectResponse("/admin/library", status_code=303)


@app.post("/admin/library/visibility")
async def admin_library_visibility(
    request: Request,
    name: str = Form(...),
    visibility: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    set_folder_visibility(name, visibility)
    return RedirectResponse("/admin/library", status_code=303)


@app.post("/admin/library/source/add")
async def admin_library_source_add(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
):
    user = current_user(request)
    if not user:
        if request.headers.get("X-TTL-Source-Scan") == "1":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    if user["role"] != "gm":
        if request.headers.get("X-TTL-Source-Scan") == "1":
            return JSONResponse({"error": "Unauthorized"}, status_code=403)
        return RedirectResponse("/", status_code=303)

    # AJAX path: return immediately and do the expensive scan in a worker.
    if request.headers.get("X-TTL-Source-Scan") == "1":
        job_id = uuid.uuid4().hex
        _set_source_scan_job(
            job_id,
            state="queued",
            folder_name=name,
            source_path=path,
            message="Preparing scan...",
            current="",
            documents_seen=0,
            sources_added=0,
            error=None,
        )

        asyncio.create_task(
            asyncio.to_thread(
                _run_source_scan_job,
                job_id,
                name,
                path,
            )
        )

        return JSONResponse({"job_id": job_id})

    # Non-JavaScript fallback keeps the old synchronous behavior.
    try:
        result = add_source(name, path)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/library?error={quote(str(exc))}",
            status_code=303,
        )

    added_count = int(result.get("added_count") or 1)
    if result.get("type") == "directory":
        message = (
            f"Added {added_count} physical source folder"
            f"{'s' if added_count != 1 else ''}."
        )
    else:
        message = "Physical source added."

    return RedirectResponse(
        f"/admin/library?message={quote(message)}",
        status_code=303,
    )


@app.get("/admin/library/source/status/{job_id}")
async def admin_library_source_status(
    request: Request,
    job_id: str,
):
    user = current_user(request)

    if not user or user["role"] != "gm":
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    job = _source_scan_job_snapshot(job_id)
    if job is None:
        return JSONResponse({"error": "Scan job not found."}, status_code=404)

    return JSONResponse(job)


@app.post("/admin/library/source/remove")
async def admin_library_source_remove(
    request: Request,
    name: str = Form(...),
    source_type: str = Form(...),
    source_path: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    remove_source(name, source_type, source_path)
    return RedirectResponse("/admin/library", status_code=303)


@app.post("/admin/library/file-visibility")
async def admin_library_file_visibility(
    request: Request,
    name: str = Form(...),
    doc_key: str = Form(...),
    visibility: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    folder = get_folder(name)
    document = get_document(folder, doc_key) if folder else None

    if document:
        set_file_visibility(name, document["path"], visibility)

    return RedirectResponse("/admin/library", status_code=303)


@app.post("/admin/library/cover")
async def admin_library_cover(
    request: Request,
    name: str = Form(...),
    doc_key: str = Form(""),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    folder = get_folder(name)

    if folder:
        if doc_key:
            document = get_document(folder, doc_key)
            if not document:
                return RedirectResponse(
                    f"/admin/library?error={quote('Selected cover file is not available.')}",
                    status_code=303,
                )
            set_folder_cover(name, document["path"])
        else:
            set_folder_cover(name, None)

    return RedirectResponse("/admin/library", status_code=303)


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if is_configured():
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "error": None,
        },
    )


@app.post("/setup", response_class=HTMLResponse)
async def setup_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if is_configured():
        return RedirectResponse("/login", status_code=303)

    error = None

    if password != confirm_password:
        error = "Passwords do not match."
    else:
        try:
            user = create_initial_gm(username, password)
            request.session["username"] = user["username"]
            request.session["role"] = user["role"]
            return RedirectResponse("/", status_code=303)
        except ValueError as exc:
            error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "error": error,
            "username": username,
        },
        status_code=400,
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not is_configured():
        return RedirectResponse("/setup", status_code=303)

    if current_user(request):
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "error": None,
        },
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not is_configured():
        return RedirectResponse("/setup", status_code=303)

    user = authenticate(username, password)

    if user:
        request.session.clear()
        request.session["username"] = user["username"]
        request.session["role"] = user["role"]
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "error": "Invalid username or password.",
            "username": username,
        },
        status_code=401,
    )


@app.post("/logout")
async def logout(request: Request):
    username = request.session.get("username")
    request.session.clear()

    if username:
        logger.info("User %s logged out", username)

    return RedirectResponse("/login", status_code=303)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "application": APP_NAME,
        "version": APP_VERSION,
    }

# Character editor routes (v0.4.3)
from app.characters.web import router as characters_router
app.include_router(characters_router)
