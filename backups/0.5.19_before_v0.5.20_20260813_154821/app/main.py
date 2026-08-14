from __future__ import annotations
import asyncio
import time
import uuid

import logging
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
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
from app.ocr import cancel_ocr_job, ocr_job_status, ocr_status, start_ocr_job
from app.characters.ai_context import build_character_ai_context, character_retrieval_query
from app.characters.storage import CharacterStorageError, list_characters
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
from app.readers.comic import comic_page, comic_pages, cbr_cache_status, cleanup_cbr_cache
from app.readers.image import serve_image
from app.readers.pdf import stream_pdf
from app.readers.text import read_plain_text, render_markdown
from app.uploads import delete_upload, list_uploads, supported_upload, unique_upload_path
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
    AIRequestCancelled,
    chat_completion,
    provider_health_check,
    provider_settings_for_ui,
    save_provider_settings,
    test_provider_connection,
)
from app.ai.requests import (
    ai_request_progress,
    cancel_ai_request,
    finish_ai_request,
    register_ai_request,
    update_ai_request_progress,
)
from app.ai.markdown_render import render_answer_markdown
from app.ai.query_planner import plan_retrieval_queries
from app.ai.evidence_ranker import rank_evidence
from app.ai.pipelines import (
    PipelinePresetError,
    execute_advanced_pipeline,
    get_pipeline_preset,
    pipeline_options_for_ui,
)
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

_ERROR_TITLES = {
    400: "Request could not be completed",
    401: "Sign in required",
    403: "Access denied",
    404: "Page not found",
    405: "Action not allowed",
    409: "Conflict",
    413: "Upload too large",
    422: "Invalid request",
    500: "Something went wrong",
}


def _browser_wants_html(request: Request) -> bool:
    """Use HTML for browser navigation/forms while preserving JSON APIs."""
    return "text/html" in request.headers.get("accept", "").lower()


def _error_message(status_code: int, detail) -> str:
    if status_code >= 500:
        return (
            "Tabletop Librarian encountered an unexpected error while processing "
            "this request. The error has been logged."
        )
    if status_code == 401:
        text = str(detail or "").strip()
        if not text or text.casefold() == "login required.":
            return "Your session is not signed in. Sign in to continue."
        return text
    if status_code == 403:
        return str(detail or "You do not have permission to use this page.")
    if status_code == 404:
        return str(detail or "The requested page or item could not be found.")
    if status_code == 422:
        return "The submitted request was incomplete or contained invalid values."
    return str(detail or "The request could not be completed.")


def _html_error_response(
    request: Request,
    *,
    status_code: int,
    detail=None,
    request_id: str | None = None,
):
    title = _ERROR_TITLES.get(
        status_code,
        "Request error" if status_code < 500 else "Something went wrong",
    )
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "status_code": status_code,
            "error_title": title,
            "error_message": _error_message(status_code, detail),
            "request_id": request_id,
            "error_page": True,
            "show_login": status_code == 401,
            "show_back": status_code != 401,
            "show_home": status_code != 401,
        },
        status_code=status_code,
    )


@app.exception_handler(StarletteHTTPException)
async def ttl_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if _browser_wants_html(request):
        return _html_error_response(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def ttl_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    if _browser_wants_html(request):
        return _html_error_response(
            request,
            status_code=422,
            detail="The submitted request was incomplete or invalid.",
        )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def ttl_unexpected_exception_handler(request: Request, exc: Exception):
    request_id = uuid.uuid4().hex[:10]
    logger.exception(
        "Unhandled request error [%s] %s %s",
        request_id,
        request.method,
        request.url.path,
    )
    if _browser_wants_html(request):
        return _html_error_response(
            request,
            status_code=500,
            request_id=request_id,
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": request_id},
    )



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
    try:
        summary = cleanup_cbr_cache()
        if summary["removed"]:
            logger.info(
                "CBR cache startup cleanup removed %s item(s), freeing %.1f MB",
                summary["removed"],
                summary["bytes_freed"] / 1048576,
            )
    except Exception:
        logger.exception("CBR cache startup cleanup failed")


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
async def read_document(
    request: Request,
    folder_name: str,
    doc_key: str,
    embed: str = "",
    workspace: str = "",
):
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
        "embed": embed == "1",
        "workspace": workspace == "1",
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
        from app.ocr import current_ocr_pdf, cached_ocr_pdf_for_unavailable_source

        ocr_pdf = current_ocr_pdf(path)
        if ocr_pdf is None and document.get("source_available") is False:
            ocr_pdf = cached_ocr_pdf_for_unavailable_source(path)

        if ocr_pdf is not None:
            # The archive remains the canonical library object, but its valid
            # OCR derivative is the preferred reader representation.
            return templates.TemplateResponse(
                request=request,
                name="reader_pdf.html",
                context={**common, "ocr_derivative": True},
            )

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

    if document["type"] in {"CBZ", "CBR"}:
        from app.ocr import current_ocr_pdf, cached_ocr_pdf_for_unavailable_source

        ocr_pdf = current_ocr_pdf(path)
        if ocr_pdf is None and document.get("source_available") is False:
            ocr_pdf = cached_ocr_pdf_for_unavailable_source(path)
        if ocr_pdf is not None:
            return stream_pdf(request, ocr_pdf)

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


@app.post("/uploads/delete")
async def delete_staged_upload(
    request: Request,
    upload_path: str = Form(...),
):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    allowed = {
        str(Path(item["path"]).resolve())
        for item in list_uploads()
    }

    try:
        resolved = str(Path(upload_path).resolve(strict=True))
    except OSError:
        resolved = ""

    if not resolved or resolved not in allowed:
        return RedirectResponse(
            f"/uploads?error={quote('Upload not found.')}",
            status_code=303,
        )

    # Assigned uploads are authoritative library sources. Do not allow the
    # staging UI to silently break a virtual-folder source reference.
    assigned_folders = []
    for folder in list_folders():
        for source in folder.get("sources", []):
            if source.get("type") != "file":
                continue
            try:
                source_path = str(Path(str(source.get("path", ""))).resolve())
            except OSError:
                continue
            if source_path == resolved:
                assigned_folders.append(str(folder.get("name") or "Unnamed folder"))
                break

    if assigned_folders:
        folder_list = ", ".join(assigned_folders)
        return RedirectResponse(
            "/uploads?error="
            + quote(
                "This upload is currently used as a library source by "
                f"{folder_list}. Remove that source from Library management "
                "before deleting the staged file."
            ),
            status_code=303,
        )

    if not delete_upload(resolved):
        return RedirectResponse(
            f"/uploads?error={quote('Could not delete the upload.')}",
            status_code=303,
        )

    logger.info("Staged upload deleted by %s: %s", user["username"], resolved)

    return RedirectResponse(
        f"/uploads?message={quote('Upload deleted.')}",
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
            "pipeline_options": pipeline_options_for_ui(),
            "ocr": ocr_status(),
            "comic_cache": cbr_cache_status(),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@app.post("/admin/ocr/start-all")
async def admin_ocr_start_all(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)
    try:
        start_ocr_job()
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/knowledgebase?message={quote('OCR job started in the background.')}",
        status_code=303,
    )


@app.post("/admin/ocr/start/{document_key}")
async def admin_ocr_start_one(document_key: str, request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)
    try:
        start_ocr_job([document_key])
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/knowledgebase?message={quote('OCR job started in the background.')}",
        status_code=303,
    )


@app.post("/admin/ocr/cancel")
async def admin_ocr_cancel(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return JSONResponse(cancel_ocr_job())


@app.get("/admin/ocr/status")
async def admin_ocr_status(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return JSONResponse(ocr_job_status())


@app.get("/admin/rag", response_class=HTMLResponse)
async def admin_rag(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/admin/knowledgebase", status_code=303)


@app.post("/admin/cache/cleanup")
async def admin_cache_cleanup(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)
    try:
        summary = cleanup_cbr_cache()
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )
    message = (
        f"Cache cleanup complete: removed {summary['removed']} temporary/orphaned CBR "
        f"cache item{'s' if summary['removed'] != 1 else ''}, freeing "
        f"{summary['bytes_freed'] / 1048576:.1f} MB. "
        f"{summary['kept']} active fallback cache item{'s' if summary['kept'] != 1 else ''} kept."
    )
    return RedirectResponse(
        f"/admin/knowledgebase?message={quote(message)}",
        status_code=303,
    )


@app.post("/admin/knowledgebase/update")
async def admin_knowledgebase_update(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        if embedding_build_status()["running"]:
            raise RuntimeError("Wait for the current embedding build to finish before updating the knowledgebase.")
        text_summary = build_text_cache(force=False)
        if text_summary["errors"]:
            raise RuntimeError(
                f"Text extraction completed with {text_summary['errors']} error(s); "
                "fix those before updating downstream knowledgebase stages."
            )

        changed_paths = set(text_summary.get("changed_paths", []))
        removed_paths = set(text_summary.get("removed_paths", []))
        chunk_summary = build_chunk_cache(
            changed_paths=changed_paths,
            removed_paths=removed_paths,
            force=False,
        )
        start_embedding_build(
            changed_paths=set(chunk_summary.get("changed_paths", [])),
            removed_chunk_ids=set(chunk_summary.get("removed_chunk_ids", [])),
            force=bool(chunk_summary.get("full_rebuild")),
        )
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )

    if chunk_summary.get("full_rebuild"):
        message = (
            f"Knowledgebase rebuild started because no compatible chunk cache was available: "
            f"{chunk_summary['documents']} documents / {chunk_summary['chunks']} chunks. "
            "Semantic embeddings are rebuilding in the background."
        )
    else:
        changed_count = len(changed_paths)
        removed_count = len(removed_paths)
        if changed_count == 0 and removed_count == 0:
            message = (
                "Knowledgebase scan found no document changes. "
                "The existing chunks and vectors are being verified in the background."
            )
        else:
            message = (
                f"Incremental knowledgebase update started: {changed_count} added/changed "
                f"document{'s' if changed_count != 1 else ''}, {removed_count} removed. "
                "Unchanged chunks and semantic vectors are being reused."
            )

    return RedirectResponse(
        f"/admin/knowledgebase?message={quote(message)}",
        status_code=303,
    )


@app.post("/admin/knowledgebase/rebuild")
async def admin_knowledgebase_rebuild(request: Request):
    user = current_user(request)
    if not user or user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        if embedding_build_status()["running"]:
            raise RuntimeError("Wait for the current embedding build to finish before rebuilding the knowledgebase.")
        text_summary = build_text_cache(force=True)
        if text_summary["errors"]:
            raise RuntimeError(
                f"Text extraction completed with {text_summary['errors']} error(s); "
                "fix those before rebuilding downstream knowledgebase stages."
            )
        chunk_summary = build_chunk_cache(force=True)
        start_embedding_build(force=True)
    except Exception as exc:
        return RedirectResponse(
            f"/admin/knowledgebase?error={quote(str(exc))}",
            status_code=303,
        )

    message = (
        f"Full knowledgebase rebuild started: {text_summary['documents_seen']} library documents scanned, "
        f"{chunk_summary['documents']} context documents / {chunk_summary['chunks']} chunks rebuilt. "
        "All semantic embeddings are rebuilding in the background."
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

    summary = build_chunk_cache(force=True)

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
        start_embedding_build(force=True)
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
            pipeline_preset=get_pipeline_preset(str(form.get("pipeline_preset", "") or "").strip()).preset_id,
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
            pipeline_preset=get_pipeline_preset(str(form.get("pipeline_preset", "") or "").strip()).preset_id,
        )
        result = await asyncio.to_thread(test_provider_connection)
    except Exception as exc:
        return RedirectResponse(f"/admin/knowledgebase?error={quote(str(exc))}", status_code=303)

    models = result.get("models", [])
    message = "AI provider connected successfully."
    if models:
        message = "AI provider connected. Available model: " + ", ".join(models[:5])

    return RedirectResponse(f"/admin/knowledgebase?message={quote(message)}", status_code=303)



@app.get("/ai/status")
async def ai_backend_status(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "message": "Login required."},
        )

    status = await asyncio.to_thread(provider_health_check, timeout=2.0)
    return JSONResponse(
        status_code=200 if status.get("ok") else 503,
        content=status,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/ai/progress/{request_id}")
async def ai_progress(request: Request, request_id: str):
    user = current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "message": "Login required."},
        )

    status = ai_request_progress(request_id)
    return JSONResponse(
        content={"ok": True, **status},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/ai/cancel/{request_id}")
async def ai_cancel(request: Request, request_id: str):
    user = current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"ok": False, "message": "Login required."},
        )

    cancelled = cancel_ai_request(request_id)
    return JSONResponse(
        content={
            "ok": True,
            "cancelled": cancelled,
            "message": (
                "Cancellation requested."
                if cancelled
                else "Request was no longer active."
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


def _ask_character_options(user: dict[str, str]) -> list[dict[str, str]]:
    owners = [user["username"]]
    if user["role"] == "gm":
        all_owners = [
            str(item.get("username") or "").strip()
            for item in list_users()
            if str(item.get("username") or "").strip()
        ]
        owners = [user["username"]] + [
            owner
            for owner in all_owners
            if owner.casefold() != user["username"].casefold()
        ]

    result = []
    for owner in owners:
        for row in list_characters(owner, character_root=Path("data/characters")):
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            name = str(
                data.get("name")
                or data.get("character_name")
                or row.get("character_id")
            ).strip()
            selection = f"{owner}\t{row['character_id']}"
            result.append(
                {
                    "value": selection,
                    "owner": owner,
                    "character_id": row["character_id"],
                    "name": name,
                    "system_id": str(row.get("system_id") or ""),
                    "label": (
                        name
                        if owner.casefold() == user["username"].casefold()
                        else f"{owner} — {name}"
                    ),
                }
            )
    return result


def _resolve_ask_character(
    user: dict[str, str],
    selection: str,
):
    selection = str(selection or "")
    if not selection.strip():
        return None
    if "\t" not in selection:
        raise CharacterStorageError("Selected character is invalid.")

    owner, character_id = selection.split("\t", 1)
    owner = owner.strip()
    character_id = character_id.strip()
    if not owner or not character_id:
        raise CharacterStorageError("Selected character is invalid.")

    if user["role"] != "gm" and owner.casefold() != user["username"].casefold():
        raise CharacterStorageError("You do not have access to that character.")

    if user["role"] == "gm":
        known = {
            str(item.get("username") or "").strip().casefold()
            for item in list_users()
            if str(item.get("username") or "").strip()
        }
        if owner.casefold() not in known:
            raise CharacterStorageError("Character owner no longer exists.")

    return build_character_ai_context(
        owner,
        character_id,
        character_root=Path("data/characters"),
        pack_root=Path("data/system_packs"),
    )



def _workspace_document_options(user: dict[str, str]) -> list[dict[str, str]]:
    scope = available_rag_scope(user["role"])
    return [
        {
            "value": f"{item['folder_name']}\t{item['doc_key']}",
            "folder": item["folder_name"],
            "doc_key": item["doc_key"],
            "display_name": item["display_name"],
            "type": item["type"],
            "label": f"{item['folder_name']} — {item['display_name']}",
        }
        for item in scope["documents"]
    ]


@app.get("/workspace", response_class=HTMLResponse)
async def play_workspace(
    request: Request,
    character: str = "",
    document: str = "",
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    character_options = _ask_character_options(user)
    document_options = _workspace_document_options(user)

    selected_character = character if any(
        item["value"] == character
        for item in character_options
    ) else (character_options[0]["value"] if character_options else "")

    selected_document = document if any(
        item["value"] == document
        for item in document_options
    ) else (document_options[0]["value"] if document_options else "")

    selected_character_row = next(
        (item for item in character_options if item["value"] == selected_character),
        None,
    )
    selected_document_row = next(
        (item for item in document_options if item["value"] == selected_document),
        None,
    )

    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "character_options": character_options,
            "document_options": document_options,
            "selected_character": selected_character,
            "selected_document": selected_document,
            "selected_character_row": selected_character_row,
            "selected_document_row": selected_document_row,
            "workspace_page": True,
        },
    )


@app.get("/ask", response_class=HTMLResponse)
async def ask_page(
    request: Request,
    folder: str = "",
    embed: str = "",
    doc: str = "",
    split: str = "",
    character: str = "",
    lock_character: str = "",
    workspace_compact: str = "",
    reasoning_mode: str = "basic",
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
    character_options = _ask_character_options(user)
    selected_character = character if any(
        option["value"] == character
        for option in character_options
    ) else ""
    reasoning_mode = (
        "advanced"
        if str(reasoning_mode or "").strip().lower() == "advanced"
        else "basic"
    )
    pipeline_options = pipeline_options_for_ui()
    configured_pipeline = str(provider_settings_for_ui().get("pipeline_preset", "") or "").strip()
    try:
        selected_pipeline = get_pipeline_preset(configured_pipeline).preset_id
    except PipelinePresetError:
        selected_pipeline = pipeline_options[0]["id"] if pipeline_options else ""

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
            "character_options": character_options,
            "selected_character": selected_character,
            "character_locked": lock_character == "1" and bool(selected_character),
            "workspace_compact": workspace_compact == "1",
            "reasoning_mode": reasoning_mode,
            "selected_pipeline": selected_pipeline,
            "selected_character_context": None,
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
    selected_character = str(form.get("character", "") or "")
    character_locked = str(form.get("lock_character", "") or "") == "1"
    workspace_compact = str(form.get("workspace_compact", "") or "") == "1"
    reasoning_mode = (
        "advanced"
        if str(form.get("reasoning_mode", "") or "").strip().lower() == "advanced"
        else "basic"
    )
    pipeline_options = pipeline_options_for_ui()
    configured_pipeline = str(provider_settings_for_ui().get("pipeline_preset", "") or "").strip()
    try:
        selected_pipeline = get_pipeline_preset(configured_pipeline).preset_id
    except PipelinePresetError:
        selected_pipeline = pipeline_options[0]["id"] if pipeline_options else ""
    ai_request_id = str(form.get("ai_request_id", "") or "").strip() or uuid.uuid4().hex
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
    character_options = _ask_character_options(user)
    selected_character_context = None

    if selected_character and not any(
        option["value"] == selected_character
        for option in character_options
    ):
        error = "Selected character is not available."

    if error:
        pass
    elif not question:
        error = "Enter a question."
    elif not provider_configured:
        error = "The AI provider has not been configured."
    else:
        backend_status = await asyncio.to_thread(
            provider_health_check,
            timeout=2.0,
        )
        if not backend_status.get("ok"):
            error = backend_status.get("message") or "AI backend is unavailable."

    if not error:
        document_scope = scope["selected_document_paths"] or None
        folder_scope = scope["selected_folder"] or None
        cancel_event = register_ai_request(ai_request_id)

        try:
            update_ai_request_progress(ai_request_id, 16, "Loading character context")
            if selected_character:
                selected_character_context = _resolve_ask_character(
                    user,
                    selected_character,
                )

            if reasoning_mode == "advanced":
                preset = get_pipeline_preset(selected_pipeline)
                selected_pipeline = preset.preset_id
                started = time.perf_counter()

                def pipeline_progress(value: int, stage: str) -> None:
                    update_ai_request_progress(ai_request_id, value, stage)

                pipeline_result = await asyncio.to_thread(
                    execute_advanced_pipeline,
                    preset=preset,
                    question=question,
                    role=user["role"],
                    character_context=selected_character_context,
                    folder_scope=folder_scope,
                    document_paths=document_scope,
                    cancel_event=cancel_event,
                    progress=pipeline_progress,
                )
                answer = pipeline_result["answer"]
                answer_model = pipeline_result["model"]
                sources = pipeline_result["sources"]
                elapsed_seconds = time.perf_counter() - started
                update_ai_request_progress(ai_request_id, 99, "Finalizing answer")
                attach_citation_excerpts(answer, sources)
                answer_html = render_answer_markdown(answer, source_count=len(sources))
            else:
                update_ai_request_progress(ai_request_id, 30, "Retrieving sources")
                retrieval_query = character_retrieval_query(
                    question,
                    selected_character_context,
                )
                sources = retrieve_chunks(
                    retrieval_query,
                    user["role"],
                    limit=8,
                    folder_scope=folder_scope,
                    document_paths=document_scope,
                )

                if not sources and selected_character_context is None:
                    raise RuntimeError("No relevant source passages were found in the selected scope.")

                update_ai_request_progress(ai_request_id, 52, "Assembling evidence")
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
                    "You are Tabletop Librarian, a tabletop RPG rules assistant. "
                    "Answer using only the selected character context and the supplied numbered source passages. "
                    "Character context tells you what the selected character currently has; numbered sources tell you the rules. "
                    "Apply explicit rules literally, including exceptions, defaults, and untrained rules. "
                    "A missing skill, item, trait, or other entry on the character sheet does not by itself forbid an action unless a supplied rule says it does. "
                    "Do not invent restrictions, classifications, interactions, or rules that are not stated in the supplied sources. "
                    "If a supplied rule directly answers the question, follow that rule even if a simpler assumption would suggest a different answer. "
                    "If sources conflict, briefly identify the conflict instead of silently resolving it. "
                    "If the supplied evidence does not establish the answer, say what cannot be established. "
                    "Give the direct answer first, then the minimum explanation needed. "
                    "Cite rules claims with the numbered source that supports them, using [1], [2], etc. "
                    "Do not cite character-sheet context as a numbered source. "
                    "Do not pad the answer with unrelated character details or rules."
                )
                character_block = (
                    "Selected character context (authoritative current sheet state; not a numbered source):\n"
                    + selected_character_context["text"]
                    if selected_character_context is not None
                    else "Selected character context: none"
                )
                source_text = "\n\n".join(source_blocks) if source_blocks else "(No relevant numbered source passages were retrieved.)"
                user_prompt = (
                    f"Question:\n{question}\n\n"
                    "Retrieval mode: Basic single-query retrieval.\n\n"
                    f"{character_block}\n\n"
                    f"Numbered source passages:\n\n{source_text}"
                )
                started = time.perf_counter()
                update_ai_request_progress(ai_request_id, 58, "Generating answer")
                completion = await asyncio.to_thread(
                    chat_completion,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    cancel_event=cancel_event,
                )
                answer = completion["content"]
                answer_model = completion["model"]
                elapsed_seconds = time.perf_counter() - started
                update_ai_request_progress(ai_request_id, 97, "Finalizing answer")
                attach_citation_excerpts(answer, sources)
                answer_html = render_answer_markdown(answer, source_count=len(sources))
        except AIRequestCancelled:
            error = "AI request cancelled."
        except Exception as exc:
            error = str(exc)
        finally:
            finish_ai_request(ai_request_id)

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
            "character_options": character_options,
            "selected_character": selected_character,
            "character_locked": character_locked and bool(selected_character),
            "workspace_compact": workspace_compact,
            "reasoning_mode": reasoning_mode,
            "selected_pipeline": selected_pipeline,
            "selected_character_context": selected_character_context,
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
