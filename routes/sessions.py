"""Session monitoring."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    """Session monitoring."""
    data = await api("/sessions?limit=100")
    return templates.TemplateResponse(request, "sessions.html", context={
        "sessions": data.get("sessions", []),
        "total": data.get("total", 0),
    })
