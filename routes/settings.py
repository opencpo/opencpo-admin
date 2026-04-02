"""Settings management — SMS provider, SMTP, OTP configuration."""
import html as _html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Render the settings page with current configuration."""
    try:
        data = await api("/settings")
    except Exception as exc:
        logger.warning("Failed to load settings from Core: %s", exc)
        data = {}

    sms  = data.get("sms",  {"provider": "demo"})
    smtp = data.get("smtp", {"port": 587, "tls": True})
    otp  = data.get("otp",  {"enabled": True, "demo_mode": False, "code_length": 6, "ttl_seconds": 300})
    ocpi = data.get("ocpi", {
        "country_code": "NL", "party_id": "OCP", "role": "CPO",
        "operator_name": "OpenCPO", "emsp_country_code": "NL", "emsp_party_id": "OCP",
        "base_url": "", "versions_path": "/ocpi/versions",
    })

    return templates.TemplateResponse(request, "settings.html", {
        "active": "settings",
        "sms":    sms,
        "smtp":   smtp,
        "otp":    otp,
        "ocpi":   ocpi,
    })


# ── SMS ───────────────────────────────────────────────────────────────────

@router.post("/action/settings/sms", response_class=HTMLResponse)
async def action_save_sms(request: Request):
    """Save SMS provider settings via Core API."""
    form = await request.form()
    body = {
        "provider":     form.get("provider", "demo"),
        "api_key":      form.get("api_key", ""),
        "workspace_id": form.get("workspace_id", ""),
        "channel_id":   form.get("channel_id", ""),
        "sender":       form.get("sender", ""),
    }
    try:
        await api("/settings/sms", method="PUT", json={"value": body})
        return HTMLResponse(_ok("SMS settings saved"))
    except Exception as exc:
        return HTMLResponse(_err(str(exc)))


@router.post("/action/settings/sms/test", response_class=HTMLResponse)
async def action_test_sms(request: Request):
    """Trigger a test SMS via Core API."""
    form = await request.form()
    phone = form.get("test_phone", "").strip()
    if not phone:
        return HTMLResponse(_err("Enter a phone number to send the test to"))
    try:
        await api("/settings/sms/test", method="POST", json={"phone": phone})
        return HTMLResponse(_ok(f"Test SMS sent to {_html.escape(phone)}"))
    except Exception as exc:
        return HTMLResponse(_err(str(exc)))


# ── SMTP ──────────────────────────────────────────────────────────────────

@router.post("/action/settings/smtp", response_class=HTMLResponse)
async def action_save_smtp(request: Request):
    """Save SMTP settings via Core API."""
    form = await request.form()
    body = {
        "host":         form.get("host", ""),
        "port":         int(form.get("port") or 587),
        "user":         form.get("user", ""),
        "password":     form.get("password", ""),
        "from_address": form.get("from_address", ""),
        "from_name":    form.get("from_name", "OpenCPO"),
        "tls":          form.get("tls") == "on",
    }
    try:
        await api("/settings/smtp", method="PUT", json={"value": body})
        return HTMLResponse(_ok("SMTP settings saved"))
    except Exception as exc:
        return HTMLResponse(_err(str(exc)))


@router.post("/action/settings/smtp/test", response_class=HTMLResponse)
async def action_test_smtp(request: Request):
    """Trigger a test email via Core API."""
    form = await request.form()
    to_email = form.get("test_email", "").strip()
    if not to_email:
        return HTMLResponse(_err("Enter an email address to send the test to"))
    try:
        await api("/settings/smtp/test", method="POST", json={"to_email": to_email})
        return HTMLResponse(_ok(f"Test email sent to {_html.escape(to_email)}"))
    except Exception as exc:
        return HTMLResponse(_err(str(exc)))


# ── OTP ───────────────────────────────────────────────────────────────────

@router.post("/action/settings/otp", response_class=HTMLResponse)
async def action_save_otp(request: Request):
    """Save OTP settings via Core API."""
    form = await request.form()
    body = {
        "enabled":     form.get("enabled") == "on",
        "demo_mode":   form.get("demo_mode") == "on",
        "code_length": int(form.get("code_length") or 6),
        "ttl_seconds": int(form.get("ttl_seconds") or 300),
    }
    try:
        await api("/settings/otp", method="PUT", json={"value": body})
        return HTMLResponse(_ok("OTP settings saved"))
    except Exception as exc:
        return HTMLResponse(_err(str(exc)))


# ── OCPI Identity ────────────────────────────────────────────────────────

@router.post("/action/settings/ocpi", response_class=HTMLResponse)
async def action_save_ocpi(request: Request):
    """Save OCPI identity settings via Core API."""
    form = await request.form()
    body = {
        "country_code":      form.get("country_code", "NL").strip().upper()[:2],
        "party_id":          form.get("party_id",     "OCP").strip().upper()[:3],
        "role":              form.get("role",          "CPO").strip().upper(),
        "operator_name":     form.get("operator_name", "").strip(),
        "emsp_country_code": form.get("emsp_country_code", "NL").strip().upper()[:2],
        "emsp_party_id":     form.get("emsp_party_id", "OCP").strip().upper()[:3],
        "base_url":          form.get("base_url",      "").strip().rstrip("/"),
        "versions_path":     form.get("versions_path", "/ocpi/versions").strip(),
    }
    try:
        await api("/settings/ocpi", method="PUT", json={"value": body})
        return HTMLResponse(_ok("OCPI identity saved"))
    except Exception as exc:
        return HTMLResponse(_err(str(exc)))


# ── UI helpers ────────────────────────────────────────────────────────────

def _ok(msg: str) -> str:
    return f'<div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">✓ {_html.escape(msg)}</div>'


def _err(msg: str) -> str:
    return f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">✗ {_html.escape(msg)}</div>'
