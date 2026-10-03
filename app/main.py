from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import current_user, require_user
from .config import get_settings
from .db import init_db
from .routers import auth, projects, search

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
}

settings = get_settings()
if not settings.secret_key:
    raise RuntimeError(
        "SECRET_KEY is not set. Generate one with: "
        "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


docs = {} if settings.enable_docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="NVD Checker", lifespan=lifespan, **docs)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="nvd_checker_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.cookie_secure,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


protected = [Depends(require_user)]
app.include_router(auth.router)
app.include_router(projects.router, dependencies=protected)
app.include_router(search.router, dependencies=protected)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/", include_in_schema=False)
def index(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")
