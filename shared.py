"""
Shared helpers for CPO Admin route modules.

All route modules import from here — never from main.py.
"""
import os
import logging

import httpx
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# OCPP Core API
CORE_API = os.getenv("OCPP_CORE_API_URL", os.getenv("OCPP_CORE_API", "http://localhost:8000"))
CORE_API_KEY = os.getenv("MANAGEMENT_API_KEY", "")
APP_TITLE = os.getenv("APP_TITLE", "OpenCPO Admin")
PKI_DATA_DIR = os.getenv("PKI_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "ocpp-core", "data", "pki"))

# Templates (shared instance)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["app_title"] = APP_TITLE


async def api(path: str, method: str = "GET", json: dict = None) -> dict:
    """Call OCPP Core API."""
    headers = {"X-API-Key": CORE_API_KEY} if CORE_API_KEY else {}
    async with httpx.AsyncClient(base_url=CORE_API, timeout=10, headers=headers) as client:
        if method == "GET":
            r = await client.get(f"/api/v1{path}")
        elif method == "POST":
            r = await client.post(f"/api/v1{path}", json=json)
        elif method == "PUT":
            r = await client.put(f"/api/v1{path}", json=json)
        elif method == "DELETE":
            r = await client.delete(f"/api/v1{path}")
        r.raise_for_status()
        return r.json()
