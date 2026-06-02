"""Token and RFID management."""
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from shared import api, templates

router = APIRouter()


@router.get("/rfid", response_class=HTMLResponse)
async def rfid_page(request: Request):
    """Legacy RFID page — redirect to /tokens."""
    return RedirectResponse("/tokens", status_code=302)


@router.get("/tokens", response_class=HTMLResponse)
async def tokens_page(request: Request):
    """Token management page."""
    status = request.query_params.get("status", "")
    group = request.query_params.get("group", "")
    search = request.query_params.get("search", "")

    params = "?limit=500"
    if status:
        params += f"&status={status}"
    if group:
        params += f"&group_id={group}"
    if search:
        params += f"&search={search}"

    try:
        token_data = await api(f"/tokens{params}")
        tokens = token_data.get("tokens", [])
        total = token_data.get("total", 0)
    except Exception:
        tokens = []
        total = 0

    try:
        groups_data = await api("/groups")
        groups = groups_data.get("groups", [])
    except Exception:
        groups = []

    all_list = []
    all_total = 0
    try:
        all_tokens = await api("/tokens?limit=500")
        all_list = all_tokens.get("tokens", [])
        all_total = all_tokens.get("total", len(all_list))
    except Exception:
        pass
    now_iso = datetime.utcnow().isoformat()
    stats = {
        "total": all_total,
        "active": sum(1 for t in all_list if t["status"] == "active"),
        "blocked": sum(1 for t in all_list if t["status"] == "blocked"),
        "expired": sum(1 for t in all_list if t["status"] == "expired" or (
            t.get("valid_until") and t["valid_until"] < now_iso and t["status"] == "active"
        )),
        "groups": len(groups),
    }

    return templates.TemplateResponse(request, "tokens.html", context={
        "tokens": tokens,
        "total": total,
        "groups": groups,
        "stats": stats,
        "current_status": status,
        "current_group": group,
        "current_search": search,
        "request": request,
    })


@router.get("/tokens/{token_id}", response_class=HTMLResponse)
async def token_detail_page(request: Request, token_id: str):
    """Token detail page."""
    try:
        data = await api(f"/tokens/{token_id}")
    except Exception:
        return HTMLResponse('<div class="p-6 text-red-400">Token not found</div>', status_code=404)

    groups_data = await api("/groups")
    return templates.TemplateResponse(request, "token_detail.html", context={
        "token": data["token"],
        "sessions": data.get("sessions", []),
        "events": data.get("events", []),
        "groups": groups_data.get("groups", []),
    })


# ── Token HTMX actions ───────────────────────────────────────────────────────

@router.post("/action/token/create", response_class=HTMLResponse)
async def action_token_create(request: Request):
    form = await request.form()
    body = {
        "uid": form.get("uid", "").strip(),
        "type": form.get("type", "rfid"),
        "status": form.get("status", "active"),
    }
    for f in ("driver_name", "driver_email", "group_id", "label"):
        v = form.get(f, "").strip()
        if v:
            body[f] = v
    try:
        await api("/tokens", method="POST", json=body)
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Token created</div><script>setTimeout(()=>{closeModal("modal-create");location.href=location.pathname+"?t="+Date.now()},1200)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.put("/action/token/update/{token_id}", response_class=HTMLResponse)
async def action_token_update(request: Request, token_id: str):
    form = await request.form()
    body = {}
    for f in ("driver_name", "driver_email", "driver_phone", "group_id", "label", "card_number"):
        v = form.get(f)
        if v is not None:
            body[f] = v.strip() or None
    for f in ("valid_from", "valid_until"):
        v = form.get(f, "").strip()
        body[f] = v if v else None
    if not body:
        return HTMLResponse('<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">Nothing to update</div>')
    try:
        await api(f"/tokens/{token_id}", method="PUT", json=body)
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Saved</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.post("/action/token/block/{token_id}", response_class=HTMLResponse)
async def action_token_block(request: Request, token_id: str):
    form = await request.form()
    reason = form.get("reason", "").strip() or "manual block"
    try:
        await api(f"/tokens/{token_id}/block", method="POST", json={"reason": reason})
        return HTMLResponse('<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">🚫 Token blocked</div><script>setTimeout(()=>location.href=location.pathname+"?t="+Date.now(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.post("/action/token/unblock/{token_id}", response_class=HTMLResponse)
async def action_token_unblock(request: Request, token_id: str):
    try:
        await api(f"/tokens/{token_id}/unblock", method="POST")
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Token unblocked</div><script>setTimeout(()=>location.href=location.pathname+"?t="+Date.now(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.post("/action/token/replace/{token_id}", response_class=HTMLResponse)
async def action_token_replace(request: Request, token_id: str):
    form = await request.form()
    new_uid = form.get("new_uid", "").strip()
    label = form.get("label", "").strip() or None
    if not new_uid:
        return HTMLResponse('<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">New UID required</div>')
    try:
        result = await api(f"/tokens/{token_id}/replace", method="POST",
                           json={"new_uid": new_uid, "label": label})
        new_id = result.get("new_id", "")
        return HTMLResponse(f'<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Replaced → <a href="/tokens/{new_id}" class="underline">new token</a></div><script>setTimeout(()=>location.href=location.pathname+"?t="+Date.now(),2000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.delete("/action/token/delete/{token_id}", response_class=HTMLResponse)
async def action_token_delete(request: Request, token_id: str):
    try:
        await api(f"/tokens/{token_id}", method="DELETE")
        return HTMLResponse('<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">🗑 Token revoked</div><script>setTimeout(()=>location.href=location.pathname+"?t="+Date.now(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@router.post("/action/token/purge-test", response_class=HTMLResponse)
async def action_token_purge_test(request: Request):
    """Remove all test tokens."""
    try:
        prefixes = ["STRESS-%", "SIM-%", "VAL-%", "CHAOS-%", "E2E-%"]
        result = await api("/tokens/purge-test", method="POST", json={"prefixes": prefixes})
        deleted = result.get("deleted", 0)
        return HTMLResponse(f'<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">🗑 {deleted} test tokens removed</div><script>setTimeout(()=>location.href=location.pathname+"?t="+Date.now(),1500)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')
