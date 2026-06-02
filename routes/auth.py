"""
Authentication routes for OpenCPO Admin.

Handles login/logout via OCPP Core's JWT-based admin auth endpoint.
Session is stored in a signed cookie (JWT).
"""
import logging

import httpx
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from shared import templates, CORE_API, verify_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login page. Redirect to / if already authenticated."""
    user = await verify_session(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", context={"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """Validate credentials against OCPP Core and issue a JWT session cookie."""
    error = None
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
            r = await client.post(
                "/api/v1/admin/auth/login",
                json={"email": email, "password": password},
            )
            data = r.json()

        if r.status_code == 200:
            token = data.get("token", "")
            user = data.get("user", {})
            cookie_value = token
            response = RedirectResponse("/", status_code=302)
            response.set_cookie(
                key="opencpo_session",
                value=cookie_value,
                max_age=86400,          # 24 hours
                httponly=True,
                samesite="lax",
            )
            return response

        error = data.get("detail", "Invalid email or password.")

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
