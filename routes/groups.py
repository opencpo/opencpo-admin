"""Group management and member management."""
from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response

from shared import api, templates, CORE_API, CORE_API_KEY, logger

router = APIRouter()


@router.get("/groups", response_class=HTMLResponse)
async def groups_page(request: Request):
    """Group management page."""
    try:
        data = await api("/groups")
        groups = data.get("groups", [])
    except Exception:
        groups = []
    return templates.TemplateResponse(request, "groups.html", context={
        "groups": groups,
    })


@router.get("/groups/{group_id}", response_class=HTMLResponse)
async def group_detail_page(request: Request, group_id: str):
    """Group detail page."""
    try:
        data = await api(f"/groups/{group_id}")
    except Exception:
        return HTMLResponse('<div class="p-6 text-red-400">Group not found</div>', status_code=404)

    group = data["group"]
    real_group_id = group["id"]

    # Get members (driver accounts in this group)
    try:
        members_data = await api(f"/driver-accounts?group_id={real_group_id}")
        members = members_data.get("accounts", [])
    except Exception:
        members = []

    # Get all accounts NOT in this group (for the add dropdown)
    try:
        all_data = await api("/driver-accounts?limit=200")
        all_accounts = all_data.get("accounts", [])
        member_ids = {m["id"] for m in members}
        available_accounts = [a for a in all_accounts if a["id"] not in member_ids and not a.get("group_id")]
    except Exception:
        available_accounts = []

    return templates.TemplateResponse(request, "group_detail.html", context={
        "group": group,
        "tokens": data.get("tokens", []),
        "members": members,
        "available_accounts": available_accounts,
        "monthly_summary": data.get("monthly_summary", []),
        "current_month": datetime.now().strftime("%Y-%m"),
    })


@router.post("/groups/{group_id}/billing")
async def save_group_billing(request: Request, group_id: str):
    """Save billing configuration for a group via Core API (PUT)."""
    form = await request.form()

    def _str(key):
        v = form.get(key, "").strip()
        return v if v else None

    def _int(key, default=None):
        v = form.get(key, "").strip()
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    def _float(key, default=None):
        v = form.get(key, "").strip()
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    body = {}
    billing_method = _str("billing_method")
    if billing_method in ("invoice", "direct_debit", "prepaid"):
        body["billing_method"] = billing_method

    for field in ("iban", "bic", "kvk_number", "btw_number"):
        v = _str(field)
        if v is not None:
            body[field] = v

    pt = _int("payment_terms_days")
    if pt is not None:
        body["payment_terms_days"] = pt

    mia = _float("max_invoice_amount")
    if mia is not None:
        body["max_invoice_amount"] = mia

    try:
        await api(f"/groups/{group_id}", method="PUT", json=body)
    except Exception as e:
        logger.warning("Failed to save billing for group %s: %s", group_id, e)

    return RedirectResponse(f"/groups/{group_id}", status_code=303)


@router.get("/groups/{group_id}/invoice", response_class=Response)
async def group_invoice_download(request: Request, group_id: str, month: str = None):
    """Proxy group invoice PDF download."""
    if not month:
        month = datetime.now().strftime("%Y-%m")
    headers = {"X-API-Key": CORE_API_KEY} if CORE_API_KEY else {}
    async with httpx.AsyncClient(base_url=CORE_API, timeout=30, headers=headers) as client:
        r = await client.get(f"/api/v1/groups/{group_id}/invoice?month={month}")
        r.raise_for_status()
    return Response(
        content=r.content,
        media_type="application/pdf",
        headers={"Content-Disposition": r.headers.get("content-disposition", f'attachment; filename="invoice-{month}.pdf"')},
    )


# ── Group HTMX actions ───────────────────────────────────────────────────────

@router.post("/action/group/create", response_class=HTMLResponse)
async def action_group_create(request: Request):
    form = await request.form()
    body = {"name": form.get("name", "").strip()}
    for f in ("billing_email", "billing_address", "billing_reference", "contact_name", "contact_phone"):
        v = form.get(f, "").strip()
        if v:
            body[f] = v
    if not body["name"]:
        return HTMLResponse('<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Name required</div>')
    try:
        await api("/groups", method="POST", json=body)
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Group created</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.put("/action/group/update/{group_id}", response_class=HTMLResponse)
async def action_group_update(request: Request, group_id: str):
    form = await request.form()
    body = {}
    for f in ("name", "billing_email", "billing_address", "billing_reference", "contact_name", "contact_phone", "notes"):
        v = form.get(f)
        if v is not None:
            body[f] = v.strip() or None
    try:
        await api(f"/groups/{group_id}", method="PUT", json=body)
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Saved</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.post("/action/group/{group_id}/add-member", response_class=HTMLResponse)
async def action_add_member(request: Request, group_id: str):
    """Add a driver account to a group."""
    form = await request.form()
    account_id = form.get("account_id", "").strip()
    if not account_id:
        return HTMLResponse('<span class="text-red-400 text-xs">Select a driver account</span>')
    try:
        await api(f"/driver-accounts/{account_id}", method="PUT", json={"group_id": group_id})
        return HTMLResponse('<span class="text-green-400 text-xs">✓ Member added</span><script>setTimeout(()=>location.reload(),800)</script>')
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400 text-xs">Error: {e}</span>')


@router.post("/action/group/{group_id}/remove-member", response_class=HTMLResponse)
async def action_remove_member(request: Request, group_id: str):
    """Remove a driver account from a group."""
    account_id = request.query_params.get("account_id", "")
    if not account_id:
        return HTMLResponse('<span class="text-red-400 text-xs">Missing account ID</span>')
    try:
        await api(f"/driver-accounts/{account_id}", method="PUT", json={"group_id": ""})
        return HTMLResponse('<span class="text-green-400 text-xs">✓ Member removed</span><script>setTimeout(()=>location.reload(),800)</script>')
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400 text-xs">Error: {e}</span>')


@router.delete("/action/group/delete/{group_id}", response_class=HTMLResponse)
async def action_group_delete(request: Request, group_id: str):
    try:
        await api(f"/groups/{group_id}", method="DELETE")
        return HTMLResponse('<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">🗑 Group deleted</div><script>setTimeout(()=>location.href=location.pathname+"?t="+Date.now(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')
