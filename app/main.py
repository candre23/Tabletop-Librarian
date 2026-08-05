from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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
from app.library.covers import cached_cover_path
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
    cover = cached_cover_path(str(source_path.parent), source_path.name)

    if not cover.exists():
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

    for folder in list_folders():
        folder_data.append(
            {
                **folder,
                "scan": scan_folder(folder),
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
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        add_source(name, path)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/library?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse("/admin/library", status_code=303)


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
