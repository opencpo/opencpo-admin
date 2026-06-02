"""
Authentication routes for OpenCPO Admin.

Handles login/logout via the OCPP Core demo-login endpoint.
Session is stored in a signed cookie (itsdangerous URLSafeTimedSerializer).
"""
import logging

import httpx
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from shared import templates, CORE_API, SESSION_SECRET

logger = logging.getLogger(__name__)

router = APIRouter()


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SESSION_SECRET, salt="opencpo-session")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login page. Redirect to / if already authenticated."""
    cookie = request.cookies.get("opencpo_session")
    if cookie:
        try:
            _signer().loads(cookie, max_age=86400)
            return RedirectResponse("/", status_code=302)
        except (BadSignature, SignatureExpired):
            pass
    return templates.TemplateResponse(request, "login.html", context={"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Validate credentials against OCPP Core and issue a session cookie."""
    error = None
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
            r = await client.post(
                "/api/auth/demo-login",
                json={"username": username, "password": password},
            )
            data = r.json()

        if r.status_code == 200 and data.get("ok"):
            payload = {
                "token": data.get("token", ""),
                "name": data.get("name", ""),
                "company": data.get("company", ""),
            }
            cookie_value = _signer().dumps(payload)
            response = RedirectResponse("/", status_code=302)
            response.set_cookie(
                key="opencpo_session",
                value=cookie_value,
                max_age=86400,          # 24 hours
                httponly=True,
                samesite="lax",
            )
            return response

        error = data.get("detail", "Invalid username or password.")

    except httpx.RequestError:
        error = "Could not connect to authentication service. Please try again."
    except Exception:
        logger.exception("Unexpected error during login")
        error = "An unexpected error occurred. Please try again."

    return templates.TemplateResponse(
        request, "login.html", context={"error": error}
    )


@router.get("/logout")
async def logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("opencpo_session")
    return response
