"""
Documentation page — "How to become a modern CPO"
Static page, no API calls needed.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import templates

router = APIRouter()


@router.get("/docs", response_class=HTMLResponse)
async def docs_page(request: Request):
    return templates.TemplateResponse(request, "docs.html", {})
