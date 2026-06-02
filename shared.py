"""Shared helpers for CPO Admin route modules.

All route modules import from here — never from main.py.
"""
import os
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import Request
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# OCPP Core API (internal — used by server-side Python code)
CORE_API = os.getenv("OCPP_CORE_API_URL", os.getenv("OCPP_CORE_API", "http://localhost:8000"))
CORE_API_KEY = os.getenv("CORE_API_KEY", "")
APP_TITLE = os.getenv("APP_TITLE", "OpenCPO Admin")

# PKI data directory (shared volume with ocpp-core)
PKI_DATA_DIR = os.getenv("PKI_DATA_DIR", "/app/data/pki")

# Public URLs — used by the frontend (top nav, JS, docs links).
# These MUST be configurable: never hardcode production domains.
# Default to localhost for local installs; set env vars for production/public deployments.
CHARGE_APP_URL = os.getenv("CHARGE_APP_URL", "http://localhost:8003")
CHARGER_FARM_URL = os.getenv("CHARGER_FARM_URL", "http://localhost:8087")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", "http://localhost:8090")
CORE_API_PUBLIC_URL = os.getenv("CORE_API_PUBLIC_URL", "http://localhost:8000")

# Templates (shared instance)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["app_title"] = APP_TITLE
templates.env.globals["charge_app_url"] = CHARGE_APP_URL
templates.env.globals["charger_farm_url"] = CHARGER_FARM_URL
templates.env.globals["compliance_url"] = COMPLIANCE_URL
templates.env.globals["core_api_public_url"] = CORE_API_PUBLIC_URL

# ── Local JWT verification (avoids calling core /me on every request) ─────
_JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("CORE_API_KEY", ""))
_JWT_ALGO = "HS256"


def _verify_token_local(token: str) -> dict | None:
    """Decode and verify a JWT locally. Returns payload dict or None."""
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        # Check expiry manually (pyjwt raises on expiry, but belt-and-suspenders)
        exp = payload.get("exp", 0)
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            logger.warning("verify_session: token expired")
            return None
        return payload
    except Exception as exc:
        logger.warning("verify_session: local JWT verify failed: %s", exc)
        return None


async def get_setup_status() -> dict:
    """Check if the platform has been configured (first-time setup)."""
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=5) as client:
            r = await client.get("/api/v1/admin/setup/status")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return {"complete": False, "steps": {}}


def get_session_token(request: Request) -> str | None:
    """Extract JWT from the session cookie."""
    return request.cookies.get("opencpo_session")


async def verify_session(request: Request) -> dict | None:
    """Verify the JWT session cookie locally (no core API call).
    
    Decodes and validates the JWT expiry right here. Falls back to calling
    core /me only if local verification fails (e.g. different secret key).
    Returns a user dict or None.
    """
    token = get_session_token(request)
    if not token:
        logger.warning("verify_session: no opencpo_session cookie found")
        return None

    # Try local JWT verification first — avoids rate limiting core auth
    payload = _verify_token_local(token)
    if payload:
        return {
            "id": int(payload.get("sub", 0)),
            "email": payload.get("email", ""),
            "name": payload.get("name", payload.get("email", "")),
            "role": payload.get("role", "admin"),
        }

    # Fallback: call core /me (different secret, key rotation, etc.)
    logger.info("verify_session: local verify failed, falling back to core /me")
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=5) as client:
            r = await client.get(
                "/api/v1/admin/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code == 200:
                return r.json()
            logger.warning("verify_session: core /me returned %s", r.status_code)
    except Exception as exc:
        logger.warning("verify_session: exception calling core /me: %s", exc)
    return None


async def api(path: str, method: str = "GET", json_data: dict = None,
              token: str = None) -> dict | httpx.Response:
    """Call OCPP Core API. Returns parsed JSON response.
    Set raw=True to get the raw httpx.Response object.
    Sends CORE_API_KEY as X-API-Key header if available.
    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if CORE_API_KEY:
        headers["X-API-Key"] = CORE_API_KEY
    async with httpx.AsyncClient(base_url=CORE_API, timeout=10, headers=headers) as client:
        if method == "GET":
            r = await client.get(f"/api/v1{path}")
        elif method == "POST":
            r = await client.post(f"/api/v1{path}", json=json_data)
        elif method == "PUT":
            r = await client.put(f"/api/v1{path}", json=json_data)
        elif method == "DELETE":
            r = await client.delete(f"/api/v1{path}")
        r.raise_for_status()
        return r.json()
