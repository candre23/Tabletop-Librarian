from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import authenticate, create_initial_gm, ensure_server_config, is_configured
from app.config import APP_NAME, APP_VERSION, STATIC_DIR, TEMPLATE_DIR
from app.library.manager import add_folder, get_folder, list_folders, remove_folder, scan_folder

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
    role = request.session.get("role")

    if not username or not role:
        return None

    return {"username": username, "role": role}


def require_login(request: Request) -> dict[str, str] | RedirectResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return user


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

    visible_folders = [
        folder
        for folder in list_folders()
        if folder.get("visibility") == "players" or user["role"] == "gm"
    ]

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "folders": visible_folders,
        },
    )


@app.get("/library/{folder_name}", response_class=HTMLResponse)
async def library_folder(request: Request, folder_name: str):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    folder = get_folder(folder_name)
    if not folder:
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "user": user,
                "title": "Folder not found",
                "message": "That library folder does not exist.",
            },
            status_code=404,
        )

    if folder.get("visibility") == "gm" and user["role"] != "gm":
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "user": user,
                "title": "Access denied",
                "message": "You do not have access to this folder.",
            },
            status_code=403,
        )

    scan = scan_folder(folder)

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


@app.get("/admin/library", response_class=HTMLResponse)
async def admin_library(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin_library.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "user": user,
            "folders": list_folders(),
            "error": request.query_params.get("error"),
        },
    )


@app.post("/admin/library/add")
async def admin_library_add(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    visibility: str = Form("players"),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "gm":
        return RedirectResponse("/", status_code=303)

    try:
        add_folder(name, path, visibility)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/library?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse("/admin/library", status_code=303)


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
