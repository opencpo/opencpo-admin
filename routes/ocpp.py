"""OCPP message viewer routes."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from shared import api, templates

router = APIRouter()


@router.get("/ocpp", response_class=HTMLResponse)
async def ocpp_page(request: Request):
    """OCPP protocol message viewer."""
    try:
        data = await api("/chargers?limit=200")
        chargers = data.get("chargers", [])
    except Exception:
        chargers = []

    return templates.TemplateResponse(request, "ocpp.html", context={
        "chargers": chargers,
    })


@router.get("/partials/ocpp-messages", response_class=JSONResponse)
async def ocpp_messages_partial(request: Request, limit: int = 200, cp_id: str = None):
    """Recent events for initial page load."""
    try:
        qs = f"?limit={limit}"
        if cp_id:
            qs += f"&charge_point={cp_id}"
        data = await api(f"/events/history{qs}")
        events = data.get("events", [])
    except Exception:
        events = []

    return JSONResponse({"events": events})
