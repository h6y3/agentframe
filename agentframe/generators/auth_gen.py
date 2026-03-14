from agentframe.generators.base import BaseGenerator
from agentframe.graph.store import Graph

_CSRF_MIDDLEWARE = """\
# generated/middleware/csrf.py — DO NOT EDIT
import hashlib
import hmac
import os
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SKIP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_SKIP_PATH_PREFIXES = ("/api/", "/auth/callback", "/health", "/mcp", "/_console")


class CSRFMiddleware(BaseHTTPMiddleware):
    \"\"\"Double-submit cookie CSRF protection for all HTML form routes.\"\"\"

    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self._secret = secret_key.encode() if isinstance(secret_key, str) else secret_key

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip safe methods and JSON API routes
        if request.method in _SKIP_METHODS:
            return await self._ensure_cookie(request, await call_next(request))

        for prefix in _SKIP_PATH_PREFIXES:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        # Validate token from form body or header
        token_cookie = request.cookies.get("csrf_token", "")
        form = None
        token_form = ""

        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            token_form = form.get("_csrf_token", "")
        else:
            token_form = request.headers.get("X-CSRF-Token", "")

        if not token_cookie or not token_form or not hmac.compare_digest(token_cookie, token_form):
            from starlette.responses import HTMLResponse
            return HTMLResponse("<h1>403 Forbidden</h1><p>CSRF token invalid.</p>", status_code=403)

        response = await call_next(request)
        return response

    async def _ensure_cookie(self, request: Request, response: Response) -> Response:
        if "csrf_token" not in request.cookies:
            token = secrets.token_hex(32)
            response.set_cookie("csrf_token", token, httponly=False, samesite="lax")
        return response
"""

_GOOGLE_AUTH = """\
# generated/middleware/google_auth.py — DO NOT EDIT
import os
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

router = APIRouter(prefix="/auth/google", tags=["auth"])

try:
    from authlib.integrations.starlette_client import OAuth
    _oauth = OAuth()
    _oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    _OAUTH_AVAILABLE = True
except ImportError:
    _OAUTH_AVAILABLE = False


@router.get("/login")
async def login(request: Request):
    if not _OAUTH_AVAILABLE:
        return {"error": "authlib not installed. Run: pip install authlib"}
    redirect_uri = request.url_for("auth_callback")
    return await _oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    if not _OAUTH_AVAILABLE:
        return {"error": "authlib not installed"}
    token = await _oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    request.session["user"] = {
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
        "provider": "google",
    }
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


def require_login(request: Request):
    \"\"\"FastAPI Depends() — raises redirect if not logged in.\"\"\"
    if "user" not in request.session:
        from fastapi import HTTPException
        raise HTTPException(status_code=307, headers={"Location": "/auth/google/login"})
    return request.session["user"]
"""

_EMAIL_AUTH = """\
# generated/middleware/email_auth.py — DO NOT EDIT
import os
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse

router = APIRouter(prefix="/auth/email", tags=["auth"])

try:
    from itsdangerous import URLSafeTimedSerializer
    _serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY", "dev-secret"))
    _ITSDANGEROUS_AVAILABLE = True
except ImportError:
    _ITSDANGEROUS_AVAILABLE = False


@router.get("/request")
async def request_link_form(request: Request):
    return HTMLResponse(\"\"\"<!DOCTYPE html>
<html><body>
<form method="POST" action="/auth/email/request">
    <input type="hidden" name="_csrf_token" value="{{ request.cookies.get('csrf_token','') }}">
    <label>Email: <input type="email" name="email" required></label>
    <button type="submit">Send Magic Link</button>
</form>
</body></html>\"\"\")


@router.post("/request")
async def send_magic_link(request: Request):
    if not _ITSDANGEROUS_AVAILABLE:
        return {"error": "itsdangerous not installed"}
    form = await request.form()
    email = form.get("email", "")
    token = _serializer.dumps(email, salt="magic-link")
    magic_url = str(request.url_for("verify_magic_link", token=token))

    # Send email via Resend (if configured)
    resend_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("MAGIC_LINK_FROM_EMAIL", "noreply@example.com")
    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            resend.Emails.send({
                "from": from_email,
                "to": email,
                "subject": "Your login link",
                "html": f'<p><a href="{magic_url}">Click here to log in</a></p>',
            })
        except Exception as e:
            print(f"Failed to send magic link email: {e}")

    return HTMLResponse(f"<p>Magic link sent to {email}. Check your inbox.</p>")


@router.get("/verify/{token}", name="verify_magic_link")
async def verify_magic_link(token: str, request: Request):
    if not _ITSDANGEROUS_AVAILABLE:
        return {"error": "itsdangerous not installed"}
    try:
        email = _serializer.loads(token, salt="magic-link", max_age=3600)
    except Exception:
        return HTMLResponse("<p>Link expired or invalid.</p>", status_code=400)
    request.session["user"] = {"email": email, "provider": "email"}
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


def require_login(request: Request):
    \"\"\"FastAPI Depends() — raises redirect if not logged in.\"\"\"
    if "user" not in request.session:
        from fastapi import HTTPException
        raise HTTPException(status_code=307, headers={"Location": "/auth/email/request"})
    return request.session["user"]
"""


def _has_provider(graph: Graph, provider: str) -> bool:
    return any(
        n.attrs.get("provider") == provider
        for n in graph.list_nodes("integration")
    )


class AuthGenerator(BaseGenerator):
    """Generates auth middleware and routes based on integration nodes.

    Always generates CSRF middleware (required for any form-based app).
    Generates Google OAuth or email magic link routes only if the
    corresponding integration node exists.
    """

    def generate(self, graph: Graph) -> dict[str, str]:
        files: dict[str, str] = {}

        # CSRF is always generated
        files["middleware/csrf.py"] = _CSRF_MIDDLEWARE

        if _has_provider(graph, "google_oauth"):
            files["middleware/google_auth.py"] = _GOOGLE_AUTH

        if _has_provider(graph, "email_magic_link"):
            files["middleware/email_auth.py"] = _EMAIL_AUTH

        return files
