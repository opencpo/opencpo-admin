"""
Setup Wizard — first-time platform configuration.

Renders the multi-step setup wizard and proxies API calls to ocpp-core.
All steps are skippable.
"""
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from shared import templates, CORE_API, get_setup_status

logger = logging.getLogger(__name__)

router = APIRouter()

STEPS = ["admin", "tailscale", "org", "branding", "smtp", "pki", "pricing", "features"]

STEP_LABELS = {
    "admin": "Admin Account",
    "tailscale": "Tailscale",
    "org": "Organization",
    "branding": "Branding",
    "smtp": "Email (SMTP)",
    "pki": "Security (PKI)",
    "pricing": "Pricing",
    "features": "Features",
}

STEP_DESCRIPTIONS = {
    "admin": "Create the first administrator account to sign into the platform.",
    "tailscale": "Connect OpenCPO to your tailnet for secure remote access.",
    "org": "Set your organization name, timezone, currency, and public URL.",
    "branding": "Customize the look and feel of your platform.",
    "smtp": "Configure email sending for notifications and invitations.",
    "pki": "Initialize the Public Key Infrastructure for charger certificates.",
    "pricing": "Set a default charging tariff and pricing tiers.",
    "features": "Enable optional platform modules like OCPI roaming and billing.",
}

STEP_ICONS = {
    "admin": "👤",
    "tailscale": "🔗",
    "org": "🏢",
    "branding": "🎨",
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
        return templates.TemplateResponse(request, "setup.html", context={
            "error": "Could not connect to the backend. Is OCPP Core running?",
            "steps": [],
            "current_step": None,
            "step_labels": STEP_LABELS,
            "step_icons": STEP_ICONS,
            "step_descriptions": STEP_DESCRIPTIONS,
            "show_welcome": False,
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
        return RedirectResponse("/", status_code=302)

    # Show welcome screen if NO step has any progress yet
    all_pending = all(steps_state.get(s, "pending") == "pending" for s in STEPS)

    if all_pending:
        return templates.TemplateResponse(request, "setup.html", context={
            "error": None,
            "steps": STEPS,
            "current_step": None,
            "steps_state": steps_state,
            "step_labels": STEP_LABELS,
            "step_icons": STEP_ICONS,
            "step_descriptions": STEP_DESCRIPTIONS,
            "show_welcome": True,
        })

    return templates.TemplateResponse(request, "setup.html", context={
        "error": None,
        "steps": STEPS,
        "current_step": current_step,
        "steps_state": steps_state,
        "step_labels": STEP_LABELS,
        "step_icons": STEP_ICONS,
        "step_descriptions": STEP_DESCRIPTIONS,
        "show_welcome": False,
    })


@router.get("/setup/start", response_class=HTMLResponse)
async def setup_start(request: Request):
    """Start the setup wizard from the welcome screen. Returns the first step."""
    try:
        status = await get_setup_status()
        steps_state = status.get("steps", {})
    except Exception:
        steps_state = {}

    current_step = None
    for name in STEPS:
        if steps_state.get(name, "pending") == "pending":
            current_step = name
            break

    return templates.TemplateResponse(request, "setup.html", context={
        "error": None,
        "steps": STEPS,
        "current_step": current_step,
        "steps_state": steps_state,
        "step_labels": STEP_LABELS,
        "step_icons": STEP_ICONS,
        "step_descriptions": STEP_DESCRIPTIONS,
        "show_welcome": False,
    })


@router.post("/setup/step/{step_name}")
async def setup_step(request: Request, step_name: str):
    """Handle form submission for a setup step and return HTMX partial."""
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
    elif step_name == "tailscale":
        payload = {
            "enable_admin": form.get("enable_admin", "off") == "on",
            "enable_ocpp16": form.get("enable_ocpp16", "off") == "on",
            "enable_ocpp201": form.get("enable_ocpp201", "off") == "on",
            "enable_api": form.get("enable_api", "off") == "on",
            "enable_charge_app": form.get("enable_charge_app", "off") == "on",
            "tags": form.get("tags", ""),
        }
    elif step_name == "org":
        payload = {
            "name": form.get("name", "My CPO"),
            "timezone": form.get("timezone", "Europe/Amsterdam"),
            "currency": form.get("currency", "EUR"),
            "public_url": form.get("public_url", "http://localhost"),
        }
    elif step_name == "branding":
        payload = {
            "accent_color": form.get("accent_color", "#00B0E4"),
            "logo_url": form.get("logo_url", ""),
            "skin": form.get("skin", "default"),
            "charge_app_name": form.get("charge_app_name", "OpenCPO Charge"),
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
