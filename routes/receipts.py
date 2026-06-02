"""Receipt management — download session receipts."""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from shared import api, templates, CORE_API, CORE_API_KEY

router = APIRouter()


@router.get("/receipts", response_class=HTMLResponse)
async def receipts_page(request: Request):
    """List all completed sessions with receipt download."""
    try:
        data = await api("/public-sessions/receipts?limit=100")
        sessions = data.get("sessions", [])
        total = data.get("total", 0)
    except Exception:
        sessions = []
        total = 0
    return templates.TemplateResponse(request, "receipts.html", {
        "sessions": sessions,
        "total": total,
        "active": "receipts",
    })


@router.get("/receipts/{session_id}/download")
async def receipt_download(session_id: str):
    """Proxy receipt PDF download from Core API."""
    headers = {"X-API-Key": CORE_API_KEY} if CORE_API_KEY else {}
    async with httpx.AsyncClient(base_url=CORE_API, timeout=30, headers=headers) as client:
        resp = await client.get(f"/api/v1/public/sessions/{session_id}/pdf")
    if resp.status_code != 200:
        return HTMLResponse(f"Error: {resp.status_code}", status_code=resp.status_code)
    return Response(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Receipt-{session_id[:8].upper()}.pdf"'},
    )
