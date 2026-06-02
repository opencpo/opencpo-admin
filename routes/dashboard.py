"""Dashboard, stats partials, and charger/session row partials."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — network overview."""
    try:
        chargers = await api("/chargers?limit=100")
    except Exception:
        chargers = {"chargers": [], "total": 0}
    try:
        sessions = await api("/sessions/stats/summary")
    except Exception:
        sessions = {}
    try:
        pki = await api("/pki/stats")
    except Exception:
        pki = {}
    try:
        events = await api("/events/info")
    except Exception:
        events = {}

    return templates.TemplateResponse(request, "dashboard.html", context={
        "chargers": chargers.get("chargers", []),
        "charger_count": chargers.get("total", 0),
        "stats": sessions,
        "pki": pki,
        "events": events,
    })


@router.get("/partials/charger-rows", response_class=HTMLResponse)
async def charger_rows(request: Request):
    """HTMX partial: charger table rows (auto-refresh)."""
    try:
        data = await api("/chargers?limit=100")
    except Exception:
        data = {"chargers": []}
    return templates.TemplateResponse(request, "partials/charger_rows.html", context={
        "chargers": data.get("chargers", []),
    })


@router.get("/partials/session-rows", response_class=HTMLResponse)
async def session_rows(request: Request):
    """HTMX partial: session table rows (auto-refresh)."""
    try:
        data = await api("/sessions?limit=50")
    except Exception:
        data = {"sessions": []}
    return templates.TemplateResponse(request, "partials/session_rows.html", context={
        "sessions": data.get("sessions", []),
    })


@router.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """HTMX partial: dashboard stats cards."""
    try:
        stats = await api("/sessions/stats/summary")
    except Exception:
        stats = {}
    try:
        chargers = await api("/chargers?limit=1")
    except Exception:
        chargers = {"total": 0}
    return templates.TemplateResponse(request, "partials/stats.html", context={
        "stats": stats,
        "charger_count": chargers.get("total", 0),
    })
