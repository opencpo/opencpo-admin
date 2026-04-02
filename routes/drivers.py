"""Driver account management."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_cert_status(email: str) -> dict:
    """Fetch cert status for a driver from PKI certificates list."""
    try:
        certs = await api(f"/pki/certificates?search={email}&type=user")
        active = [c for c in certs.get("certificates", []) if c.get("status") == "active"]
        if active:
            latest = max(active, key=lambda c: c.get("issued_at", ""))
            return {
                "status": "active",
                "serial": latest.get("serial", ""),
                "expires": latest.get("not_after", "")[:10] if latest.get("not_after") else "",
                "count": len(active),
            }
    except Exception:
        pass
    return {"status": "none", "serial": "", "expires": "", "count": 0}


@router.get("/drivers", response_class=HTMLResponse)
async def drivers_page(request: Request):
    """Driver accounts management — view and manage certs."""
    accounts = await api("/driver-accounts")
    account_list = accounts.get("accounts", [])

    # Enrich with cert status
    for acct in account_list:
        acct["cert"] = await _get_cert_status(acct.get("email", ""))

    return templates.TemplateResponse(request, "drivers.html", {
        "accounts": account_list,
        "total": accounts.get("total", 0),
    })


@router.post("/action/driver/cert/issue", response_class=HTMLResponse)
async def action_issue_cert(request: Request):
    """HTMX action: create setup token + return setup link."""
    form = await request.form()
    email = form.get("email", "")
    if not email:
        return HTMLResponse('<span class="text-red-400 text-xs">❌ No email</span>')

    try:
        result = await api("/public/cert-setup/create-token", method="POST", json={"email": email})
        setup_url = result.get("setup_url", "")
        return HTMLResponse(
            f'<div class="flex flex-col gap-1">'
            f'<span class="text-green-400 text-xs">✅ Token created</span>'
            f'<input type="text" value="{setup_url}" readonly '
            f'class="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1 w-64 font-mono" '
            f'onclick="this.select();navigator.clipboard.writeText(this.value)" />'
            f'<span class="text-gray-500 text-[10px]">Click to copy • Expires in 72h</span>'
            f'</div>'
        )
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return HTMLResponse(f'<span class="text-red-400 text-xs">❌ {detail}</span>')


@router.post("/action/driver/cert/revoke", response_class=HTMLResponse)
async def action_revoke_certs(request: Request):
    """HTMX action: revoke all certs for a driver."""
    form = await request.form()
    email = form.get("email", "")
    if not email:
        return HTMLResponse('<span class="text-red-400 text-xs">❌ No email</span>')

    try:
        await api("/pki/revoke-account", method="POST", json={"email": email, "reason": "admin_revoked"})
        return HTMLResponse('<span class="text-yellow-400 text-xs">🚫 All certs revoked</span>')
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return HTMLResponse(f'<span class="text-red-400 text-xs">❌ {detail}</span>')
