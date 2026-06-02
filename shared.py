"""
Shared helpers for CPO Admin route modules.

All route modules import from here — never from main.py.
"""
import os
import json
import logging

import httpx
from fastapi import Request
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# OCPP Core API
CORE_API = os.getenv("OCPP_CORE_API_URL", os.getenv("OCPP_CORE_API", "http://localhost:8000"))
CORE_API_KEY = os.getenv("CORE_API_KEY", "")
APP_TITLE = os.getenv("APP_TITLE", "OpenCPO Admin")

# PKI data directory (shared volume with ocpp-core)
PKI_DATA_DIR = os.getenv("PKI_DATA_DIR", "/app/data/pki")

# Templates (shared instance)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["app_title"] = APP_TITLE


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
    """Verify the JWT session cookie against the core API. Returns user dict or None."""
    token = get_session_token(request)
    if not token:
        return None
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=5) as client:
            r = await client.get(
                "/api/v1/admin/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return None


async def api(path: str, method: str = "GET", json_data: dict = None,
              token: str = None) -> dict | httpx.Response:
    """Call OCPP Core API. Returns parsed JSON response.
    Set raw=True to get the raw httpx.Response object.
    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
