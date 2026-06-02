"""
Setup Wizard — first-time platform configuration.

Renders the multi-step setup wizard and proxies API calls to ocpp-core.
All steps are skippable.
"""
import logging

import httpx
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from shared import templates, CORE_API, get_setup_status

logger = logging.getLogger(__name__)

router = APIRouter()

STEPS = ["admin", "org", "smtp", "pki", "pricing", "features"]

STEP_LABELS = {
    "admin": "Admin Account",
    "org": "Organization",
    "smtp": "Email (SMTP)",
    "pki": "Security (PKI)",
    "pricing": "Pricing",
    "features": "Features",
}

STEP_DESCRIPTIONS = {
    "admin": "Create the first administrator account.",
    "org": "Set your organization name, currency, and public URL.",
    "smtp": "Configure email sending for notifications and invitations.",
    "pki": "Initialize the Public Key Infrastructure for charger certificates.",
    "pricing": "Set a default charging tariff.",
    "features": "Enable optional platform modules.",
}

STEP_ICONS = {
    "admin": "👤",
    "org": "🏢",
    "smtp": "📧",
    "pki": "🔐",
    "pricing": "💰",
    "features": "⚙️",
}


@router.get("/setup", response_class=HTMLResponse)
async def setup_wizard(request: Request):
    """Render the setup wizard. Redirect to / if setup is complete."""
    try:
        status = await get_setup_status()
    except Exception:
        # If core is unreachable, show a friendly error
        return templates.TemplateResponse(request, "setup.html", context={
            "error": "Could not connect to the backend. Is OCPP Core running?",
            "steps": [],
            "current_step": None,
            "step_labels": STEP_LABELS,
            "step_icons": STEP_ICONS,
            "step_descriptions": STEP_DESCRIPTIONS,
        })

    if status.get("complete", False):
        return RedirectResponse("/", status_code=302)

    steps_state = status.get("steps", {})

    # Find the first pending step
    current_step = None
    for name in STEPS:
        if steps_state.get(name, "pending") == "pending":
            current_step = name
            break

    if not current_step:
        # All are done/skipped — redirect to dashboard
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(request, "setup.html", context={
        "error": None,
        "steps": STEPS,
        "current_step": current_step,
        "steps_state": steps_state,
        "step_labels": STEP_LABELS,
        "step_icons": STEP_ICONS,
        "step_descriptions": STEP_DESCRIPTIONS,
    })


@router.post("/setup/step/{step_name}")
async def setup_step(request: Request, step_name: str):
    """Handle form submission for a setup step and return HTMX partial."""
    from shared import templates
    form = await request.form()

    # Build the API payload and endpoint based on step
    api_path = f"/api/v1/admin/setup/step/{step_name}"
    payload = {}

    if step_name == "admin":
        payload = {
            "email": form.get("email", ""),
            "password": form.get("password", ""),
            "name": form.get("name", "Admin"),
        }
    elif step_name == "org":
        payload = {
            "name": form.get("name", "My CPO"),
            "timezone": form.get("timezone", "Europe/Amsterdam"),
            "currency": form.get("currency", "EUR"),
            "public_url": form.get("public_url", "http://localhost"),
        }
    elif step_name == "smtp":
        payload = {
            "host": form.get("host", ""),
            "port": int(form.get("port", 587)),
            "username": form.get("username", ""),
            "password": form.get("password", ""),
            "from_email": form.get("from_email", ""),
            "use_tls": form.get("use_tls", "on") == "on",
        }
    elif step_name == "pki":
        payload = {
            "org_name": form.get("org_name", ""),
            "country": form.get("country", "NL"),
        }
    elif step_name == "pricing":
        payload = {
            "currency": form.get("currency", "EUR"),
            "default_rate_kwh": float(form.get("default_rate_kwh", 0.35)),
            "tariff_name": form.get("tariff_name", "Standard Rate"),
        }
    elif step_name == "features":
        payload = {
            "ocpi": form.get("ocpi", "off") == "on",
            "billing": form.get("billing", "off") == "on",
            "ems": form.get("ems", "off") == "on",
            "iso15118": form.get("iso15118", "off") == "on",
        }

    error = None
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
            r = await client.post(api_path, json=payload)
            if r.status_code != 200:
                data = r.json()
                error = data.get("detail", f"Step failed (HTTP {r.status_code})")
    except httpx.RequestError:
        error = "Could not connect to the backend. Please try again."

    # Re-check status to advance to next step
    try:
        status = await get_setup_status()
        complete = status.get("complete", False)
        steps_state = status.get("steps", {})
    except Exception:
        status = {"complete": False, "steps": {}}
        complete = False
        steps_state = {}

    # Find next pending step
    current_step = None
    for name in STEPS:
        if steps_state.get(name, "pending") == "pending":
            current_step = name
            break

    if complete or not current_step:
        return templates.TemplateResponse(request, "_setup_done.html")

    return templates.TemplateResponse(request, "_setup_step.html", context={
        "error": error,
        "step": current_step,
        "step_labels": STEP_LABELS,
        "step_icons": STEP_ICONS,
        "step_descriptions": STEP_DESCRIPTIONS,
    })


@router.post("/setup/skip/{step_name}")
async def skip_step(request: Request, step_name: str):
    """Skip a setup step."""
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
            await client.post(f"/api/v1/admin/setup/skip/{step_name}")
    except Exception:
        pass

    # Re-check status to advance
    try:
        status = await get_setup_status()
        complete = status.get("complete", False)
        steps_state = status.get("steps", {})
    except Exception:
        complete = False
        steps_state = {}

    current_step = None
    for name in STEPS:
        if steps_state.get(name, "pending") == "pending":
            current_step = name
            break

    if complete or not current_step:
        return templates.TemplateResponse(request, "_setup_done.html")

    return templates.TemplateResponse(request, "_setup_step.html", context={
        "error": None,
        "step": current_step,
        "step_labels": STEP_LABELS,
        "step_icons": STEP_ICONS,
        "step_descriptions": STEP_DESCRIPTIONS,
    })
