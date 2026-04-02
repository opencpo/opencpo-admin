"""OCPP message viewer routes."""
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import StreamingResponse

from shared import api, templates, CORE_API, CORE_API_KEY

router = APIRouter()


@router.get("/ocpp", response_class=HTMLResponse)
async def ocpp_page(request: Request):
    """OCPP protocol message viewer."""
    try:
        data = await api("/chargers?limit=200")
        chargers = data.get("chargers", [])
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to load chargers for OCPP viewer: %s", e)
        chargers = []

    return templates.TemplateResponse(request, "ocpp.html", context={
        "chargers": chargers,
    })


@router.get("/partials/ocpp-messages", response_class=JSONResponse)
async def ocpp_messages_partial(request: Request, limit: int = 200, cp_id: str = None):
    """Recent OCPP messages — queries the ocpp_messages table directly for raw protocol data."""
    import asyncpg
    from shared import CORE_API_KEY

    # Try the events/history API first (high-level events)
    events = []
    try:
        qs = f"?limit={limit}"
        if cp_id:
            qs += f"&charge_point={cp_id}"
        data = await api(f"/events/history{qs}")
        events = data.get("events", [])
    except Exception:
        pass

    # Also query raw OCPP messages from the database
    try:
        db = request.app.state.db
        cp_filter = "AND charge_point = $2" if cp_id else ""
        params = [limit]
        if cp_id:
            params.append(cp_id)
        rows = await db.fetch(f"""
            SELECT time, charge_point, direction, action, message_id, 
                   payload::text, response::text, latency_ms
            FROM ocpp.ocpp_messages
            ORDER BY time DESC
            LIMIT $1
            {cp_filter if not cp_id else ''}
        """, *params) if not cp_id else await db.fetch("""
            SELECT time, charge_point, direction, action, message_id,
                   payload::text, response::text, latency_ms
            FROM ocpp.ocpp_messages
            WHERE charge_point = $2
            ORDER BY time DESC
            LIMIT $1
        """, limit, cp_id)

        import json as _json
        for row in reversed(rows):  # oldest first
            events.append({
                "type": row["action"],
                "charge_point": row["charge_point"],
                "timestamp": row["time"].isoformat() if row["time"] else None,
                "direction": row["direction"],
                "data": _json.loads(row["payload"]) if row["payload"] else {},
                "response": _json.loads(row["response"]) if row["response"] else None,
                "latency_ms": row["latency_ms"],
                "message_id": row["message_id"],
            })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to query ocpp_messages: %s", e)

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
