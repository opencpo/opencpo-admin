"""OCPP message viewer routes."""
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import StreamingResponse

from shared import api, templates, CORE_API, CORE_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ocpp", response_class=HTMLResponse)
async def ocpp_page(request: Request):
    """OCPP protocol message viewer."""
    try:
        data = await api("/chargers?limit=200")
        chargers = data.get("chargers", [])
    except Exception as e:
        logger.error("Failed to load chargers for OCPP viewer: %s", e)
        chargers = []

    return templates.TemplateResponse(request, "ocpp.html", context={
        "chargers": chargers,
    })


@router.get("/partials/ocpp-messages", response_class=JSONResponse)
async def ocpp_messages_partial(request: Request, limit: int = 200, cp_id: str = None):
    """Recent OCPP events — fetched from Core API event history."""
    qs = f"?limit={limit}"
    if cp_id:
        qs += f"&charge_point={cp_id}"

    try:
        data = await api(f"/events/history{qs}")
        events = data.get("events", [])
    except Exception as e:
        logger.error("Failed to fetch event history from Core API: %s", e)
        events = []

    return JSONResponse({"events": events})


@router.get("/api/events/stream")
async def events_stream_proxy(request: Request):
    """Proxy SSE stream from OCPP Core to the browser (avoids CORS/port issues)."""
    headers = {"X-API-Key": CORE_API_KEY} if CORE_API_KEY else {}

    async def stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET", f"{CORE_API}/api/v1/events/stream", headers=headers
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")
