"""Session monitoring."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    """Charging sessions overview."""
    try:
        data = await api("/sessions?limit=100")
        sessions = data.get("sessions", [])
        total = data.get("total", 0)
    except Exception:
        sessions = []
        total = 0
    return templates.TemplateResponse(request, "sessions.html", context={
        "sessions": sessions,
        "total": total,
    })
