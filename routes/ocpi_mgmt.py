"""
OCPI Roaming Management — admin UI routes.

Thin client: every handler calls the Core API via shared.api() and renders
a template. No DB, no Redis, no business logic here.
"""
import html as _html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Main page ─────────────────────────────────────────────────────────────

@router.get("/ocpi", response_class=HTMLResponse)
async def ocpi_page(request: Request):
    """OCPI overview + partner list."""
    try:
        status = await api("/ocpi/status")
    except Exception as e:
        logger.error("OCPI status fetch failed: %s", e)
        status = {}

    try:
        data = await api("/ocpi/partners")
        partners = data.get("partners", [])
    except Exception as e:
        logger.error("OCPI partners fetch failed: %s", e)
        partners = []

    try:
        tariff_data = await api("/tariffs")
        tariffs = tariff_data.get("tariffs", [])
    except Exception as e:
        logger.error("Tariffs fetch failed: %s", e)
        tariffs = []

    return templates.TemplateResponse(request, "ocpi.html", context={
        "status":   status,
        "partners": partners,
        "tariffs":  tariffs,
        "active":   "ocpi",
    })


# ── HTMX partials ────────────────────────────────────────────────────────

@router.get("/partials/ocpi/partners", response_class=HTMLResponse)
async def ocpi_partners_partial(request: Request):
    """Refreshable partner table body rows (HTMX swap target)."""
    try:
        data = await api("/ocpi/partners")
        partners = data.get("partners", [])
    except Exception as e:
        return HTMLResponse(
            f'<tr><td colspan="7" class="p-4 text-red-400 text-sm text-center">'
            f'Could not load partners: {_html.escape(str(e))}</td></tr>'
        )
    return templates.TemplateResponse(request, "partials/ocpi_partner_rows.html", context={
        "partners": partners,
    })


@router.post("/partials/ocpi/test/{partner_id}", response_class=HTMLResponse)
async def ocpi_test_partial(request: Request, partner_id: int):
    """Run a connection test and return an inline result badge (HTMX)."""
    try:
        result = await api(f"/ocpi/partners/{partner_id}/test", method="POST")
    except Exception as e:
        return HTMLResponse(
            f'<span style="color:#ef4444;font-size:12px;">Error: {_html.escape(str(e))}</span>'
        )

    if result.get("ok"):
        ms = result.get("elapsed_ms", "?")
        versions = ", ".join(
            v.get("version", "?") for v in result.get("versions", [])
        ) or "—"
        return HTMLResponse(
            f'<span style="color:#84BD00;font-size:12px;">'
            f'Connected — {ms} ms &nbsp;&middot;&nbsp; versions: {_html.escape(versions)}'
            f'</span>'
        )
    else:
        err = _html.escape(result.get("error", "Unknown error"))
        code = result.get("status_code", "")
        detail = f" (HTTP {code})" if code else ""
        return HTMLResponse(
            f'<span style="color:#ef4444;font-size:12px;">Failed{detail}: {err}</span>'
        )


@router.post("/partials/ocpi/sync/{partner_id}", response_class=HTMLResponse)
async def ocpi_sync_partial(request: Request, partner_id: int):
    """Trigger a partner sync and return an inline status (HTMX)."""
    try:
        result = await api(f"/ocpi/partners/{partner_id}/sync", method="POST")
        return HTMLResponse(
            f'<span style="color:#84BD00;font-size:12px;">Sync queued for {_html.escape(result.get("partner_name","?"))}</span>'
        )
    except Exception as e:
        return HTMLResponse(
            f'<span style="color:#ef4444;font-size:12px;">Sync failed: {_html.escape(str(e))}</span>'
        )


# ── OCPI Log page ─────────────────────────────────────────────────────────

@router.get("/ocpi/log", response_class=HTMLResponse)
async def ocpi_log_page(request: Request, partner_id: int = None):
    """OCPI request log viewer."""
    qs = f"?limit=200"
    if partner_id:
        qs += f"&partner_id={partner_id}"

    try:
        log_data = await api(f"/ocpi/log{qs}")
        entries = log_data.get("entries", [])
        log_note = log_data.get("note")
    except Exception as e:
        logger.error("OCPI log fetch failed: %s", e)
        entries = []
        log_note = str(e)

    try:
        partner_data = await api("/ocpi/partners")
        partners = partner_data.get("partners", [])
    except Exception:
        partners = []

    return templates.TemplateResponse(request, "ocpi_log.html", context={
        "entries": entries,
        "partners": partners,
        "selected_partner": partner_id,
        "log_note": log_note,
        "active": "ocpi",
    })


# ── Actions ───────────────────────────────────────────────────────────────

@router.post("/action/ocpi/partner/create", response_class=HTMLResponse)
async def action_create_partner(request: Request):
    """Create a new OCPI partner via Core API."""
    form = await request.form()
    body = {
        "party_id":     form.get("party_id", "").strip().upper(),
        "country_code": form.get("country_code", "").strip().upper(),
        "role":         form.get("role", "EMSP").strip().upper(),
        "name":         form.get("name", "").strip(),
        "url":          form.get("url", "").strip(),
    }
    token_b = form.get("token_b", "").strip()
    if token_b:
        body["token_b"] = token_b

    # Roaming markup fields
    if form.get("base_tariff_id", "").strip():
        body["base_tariff_id"] = form.get("base_tariff_id").strip()
    for fee_field in ("roaming_fee_kwh", "roaming_fee_flat", "roaming_fee_time"):
        val = form.get(fee_field, "").strip()
        if val:
            try:
                body[fee_field] = float(val)
            except ValueError:
                pass

    if not all([body["party_id"], body["country_code"], body["name"], body["url"]]):
        return HTMLResponse(
            '<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">'
            'Party ID, country code, name, and versions URL are required.</div>'
        )

    try:
        result = await api("/ocpi/partners", method="POST", json=body)
        token_a = result.get("token_a", "")
        name = _html.escape(result.get("partner", {}).get("name", body["name"]))
        token_display = _html.escape(token_a)
        return HTMLResponse(f'''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                Partner <strong>{name}</strong> registered.
                <br><br>
                <strong>Token to send them:</strong><br>
                <code style="font-family:monospace;font-size:11px;color:#e8edf2;background:#0a1221;padding:4px 8px;border-radius:4px;display:inline-block;margin-top:4px;word-break:break-all;">{token_display}</code>
                <br><span style="font-size:11px;color:#4a6580;">Copy this now — it will not be shown again.</span>
            </div>
            <script>setTimeout(() => {{ closeModal('modal-add-partner'); location.reload(); }}, 6000);</script>
        ''')
    except Exception as e:
        return HTMLResponse(
            f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">'
            f'Error: {_html.escape(str(e))}</div>'
        )


@router.post("/action/ocpi/partner/delete/{partner_id}", response_class=HTMLResponse)
async def action_delete_partner(request: Request, partner_id: int):
    """Delete an OCPI partner via Core API."""
    try:
        await api(f"/ocpi/partners/{partner_id}", method="DELETE")
        return HTMLResponse('''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                Partner removed.
            </div>
            <script>setTimeout(() => { closeModal('modal-partner-detail'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(
            f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">'
            f'Error: {_html.escape(str(e))}</div>'
        )


@router.post("/action/ocpi/partner/update/{partner_id}", response_class=HTMLResponse)
async def action_update_partner(request: Request, partner_id: int):
    """Update partner details via Core API."""
    form = await request.form()
    body = {}
    for field in ("name", "url", "token_b", "status"):
        val = form.get(field, "").strip()
        if val:
            body[field] = val

    # Roaming markup — always include these (empty string means "clear/zero")
    base_tariff_id = form.get("base_tariff_id", "").strip()
    if base_tariff_id:
        body["base_tariff_id"] = base_tariff_id
    elif "base_tariff_id" in form:
        body["base_tariff_id"] = None

    for fee_field in ("roaming_fee_kwh", "roaming_fee_flat", "roaming_fee_time"):
        val = form.get(fee_field, "").strip()
        if val:
            try:
                body[fee_field] = float(val)
            except ValueError:
                pass
        elif fee_field in form:
            body[fee_field] = 0.0

    if not body:
        return HTMLResponse(
            '<div class="p-3 bg-gray-800 rounded text-gray-400 text-sm">Nothing to update.</div>'
        )
    try:
        await api(f"/ocpi/partners/{partner_id}", method="PUT", json=body)
        return HTMLResponse('''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                Changes saved.
            </div>
            <script>setTimeout(() => { closeModal('modal-partner-detail'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(
            f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">'
            f'Error: {_html.escape(str(e))}</div>'
        )
