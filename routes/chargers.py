"""Charger management, remote control, and OCPP commands."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()


@router.get("/chargers", response_class=HTMLResponse)
async def chargers_page(request: Request):
    """Charger management."""
    try:
        data = await api("/chargers?limit=100")
        chargers = data.get("chargers", [])
        total = data.get("total", 0)
    except Exception:
        chargers = []
        total = 0
    return templates.TemplateResponse(request, "chargers.html", context={
        "chargers": chargers,
        "total": total,
    })


@router.get("/partials/charger-rows", response_class=HTMLResponse)
async def charger_rows_partial(request: Request):
    """HTMX partial: charger table rows (polled every 5s)."""
    data = await api("/chargers?limit=100")
    return templates.TemplateResponse(
        request, "partials/charger_rows.html",
        {"chargers": data.get("chargers", [])},
    )


@router.get("/remote/{cp_id}", response_class=HTMLResponse)
async def remote_control(request: Request, cp_id: str):
    """Remote control panel for a specific charge point."""
    try:
        charger = await api(f"/chargers/{cp_id}")
    except Exception:
        return HTMLResponse('<div class="p-6 text-red-400">Charger not found</div>', status_code=404)

    return templates.TemplateResponse(request, "remote.html", context={
        "cp": charger,
        "connectors": charger.get("connectors", []),
    })


@router.get("/partials/remote/sessions/{cp_id}", response_class=HTMLResponse)
async def remote_sessions_partial(request: Request, cp_id: str, limit: int = 10):
    """HTMX partial: session history for a charger."""
    try:
        data = await api(f"/chargers/{cp_id}/sessions?limit={limit}")
        sessions = data.get("sessions", [])
    except Exception:
        sessions = []

    rows = ""
    for s in sessions:
        status_badge = {
            "active": '<span class="px-2 py-0.5 bg-green-900 text-green-300 rounded text-xs">Active</span>',
            "completed": '<span class="px-2 py-0.5 bg-blue-900 text-blue-300 rounded text-xs">Done</span>',
        }.get(s.get("status", ""), f'<span class="px-2 py-0.5 bg-gray-800 text-gray-400 rounded text-xs">{s.get("status","")}</span>')

        rows += f'''<tr class="border-b border-gray-800 text-sm hover:bg-gray-800/50">
            <td class="p-3 text-xs text-gray-400">{s.get("start_time","—")}</td>
            <td class="p-3 text-xs text-gray-400">{s.get("stop_time","—")}</td>
            <td class="p-3">{status_badge}</td>
            <td class="p-3 text-right font-mono">{s.get("energy_kwh",0):.2f}</td>
            <td class="p-3 text-xs text-gray-400">{s.get("auth_id","—")}</td>
            <td class="p-3 text-xs text-gray-400">{s.get("stop_reason","—")}</td>
        </tr>'''

    if not rows:
        rows = '<tr><td colspan="6" class="p-6 text-center text-gray-500 text-sm">No sessions yet</td></tr>'

    return HTMLResponse(f'''
        <table class="w-full border-collapse">
            <thead><tr class="border-b border-gray-800 text-gray-500 text-[10px] tracking-[1px]">
                <th class="p-3 text-left">STARTED</th><th class="p-3 text-left">ENDED</th>
                <th class="p-3 text-left">STATUS</th><th class="p-3 text-right">kWh</th>
                <th class="p-3 text-left">AUTH</th><th class="p-3 text-left">REASON</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
    ''')


@router.get("/partials/remote/connectors/{cp_id}", response_class=HTMLResponse)
async def remote_connectors_partial(request: Request, cp_id: str):
    """HTMX partial: auto-refreshing connector cards."""
    try:
        charger = await api(f"/chargers/{cp_id}")
        connectors = charger.get("connectors", [])
        is_online = charger.get("status") == "online"
    except Exception:
        return HTMLResponse('<div class="text-gray-500 text-sm p-4">Failed to load connectors</div>')

    html = ""
    for conn in connectors:
        status = conn.get("status", "Unknown")
        is_charging = status in ("Charging", "SuspendedEV")
        can_start = is_online and status in ("Available", "Preparing")
        can_stop = is_online and is_charging

        border_color = {"Available": "#22c55e", "Charging": "#3b82f6", "Preparing": "#f59e0b", "Faulted": "#ef4444"}.get(status, "#64748b")
        dot_class = {"Available": "bg-green-500", "Charging": "bg-blue-500 animate-pulse", "Preparing": "bg-yellow-500", "Faulted": "bg-red-500"}.get(status, "bg-gray-500")

        html += f'''
        <div class="rounded-xl p-4 mb-3 border {"border-green-800 bg-green-900/10" if is_charging else "border-gray-700"}" style="border-top:3px solid {border_color};">
            <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full {dot_class}"></span>
                    <span class="font-bold">Connector {conn.get("connector_id")}</span>
                    <span class="text-xs text-gray-400">{status}</span>
                </div>
            </div>
            <div class="grid grid-cols-2 gap-2">
                <button hx-post="/action/start/{cp_id}?connector={conn.get("connector_id")}" hx-swap="outerHTML"
                    class="py-3 rounded-lg font-bold text-sm {"bg-gradient-to-br from-green-600 to-green-500 text-white shadow-lg shadow-green-500/30" if can_start else "bg-gray-800 text-gray-500 cursor-not-allowed"}"
                    {"" if can_start else "disabled"}>▶ Start</button>
                <button hx-post="/action/stop/{cp_id}?connector={conn.get("connector_id")}" hx-swap="outerHTML"
                    class="py-3 rounded-lg font-bold text-sm {"bg-gradient-to-br from-red-600 to-red-500 text-white shadow-lg shadow-red-500/30" if can_stop else "bg-gray-800 text-gray-500 cursor-not-allowed"}"
                    {"" if can_stop else "disabled"}>■ Stop</button>
            </div>
        </div>'''

    return HTMLResponse(html or '<div class="text-sm text-gray-500 py-4">No connector data</div>')


@router.get("/partials/remote/pki/{cp_id}", response_class=HTMLResponse)
async def remote_pki_partial(request: Request, cp_id: str):
    """HTMX partial: PKI status for a charger."""
    try:
        stats = await api("/pki/stats")
    except Exception:
        stats = {}

    return HTMLResponse(f'''
        <div class="grid grid-cols-3 gap-4 text-center">
            <div><div class="text-2xl font-bold text-green-400">{stats.get("active", 0)}</div><div class="text-xs text-gray-500">Active</div></div>
            <div><div class="text-2xl font-bold text-red-400">{stats.get("revoked", 0)}</div><div class="text-xs text-gray-500">Revoked</div></div>
            <div><div class="text-2xl font-bold text-yellow-400">{stats.get("expiring_30d", 0)}</div><div class="text-xs text-gray-500">Expiring</div></div>
        </div>
    ''')


# ── Charger CRUD actions ─────────────────────────────────────────────────────

@router.post("/action/charger/assign-tariff/{cp_id}", response_class=HTMLResponse)
async def action_charger_assign_tariff(request: Request, cp_id: str):
    """Assign a tariff to a charger (updates tariff_kwh via Core API)."""
    form = await request.form()
    tariff_id = form.get("tariff_id", "").strip()

    try:
        energy_rate = None
        if tariff_id:
            tariff_data = await api("/tariffs")
            tariffs = tariff_data.get("tariffs", [])
            t = next((x for x in tariffs if x["id"] == tariff_id), None)
            energy_rate = t["energy_rate"] if t else None

        await api(f"/chargers/{cp_id}", method="PUT", json={"tariff_kwh": energy_rate})
        rate_str = f"€{energy_rate:.4f}" if energy_rate else "none"
        return HTMLResponse(f'''
            <td class="p-3" colspan="1">
                <span class="text-green-400 text-xs">✓ Tariff updated ({rate_str})</span>
            </td>
        ''')
    except Exception as e:
        return HTMLResponse(f'''
            <td class="p-3">
                <span class="text-red-400 text-xs">Error: {e}</span>
            </td>
        ''')


@router.post("/action/charger/create", response_class=HTMLResponse)
async def action_charger_create(request: Request):
    """Create a new charge point via Core API."""
    form = await request.form()
    body = {
        "id": form.get("id", "").strip(),
        "vendor": form.get("vendor", "").strip(),
        "model": form.get("model", "").strip(),
        "serial_number": form.get("serial_number", "").strip(),
        "ocpp_version": form.get("ocpp_version", "1.6").strip(),
        "site": form.get("site", "").strip(),
        "simulated": form.get("simulated") == "on",
    }
    if not body["id"]:
        return HTMLResponse('<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">ID is required</div>')
    try:
        await api("/chargers", method="POST", json=body)
        return HTMLResponse('''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                ✓ Charger created
            </div>
            <script>setTimeout(() => { closeModal('modal-charger-create'); location.href=location.pathname+"?t="+Date.now(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@router.post("/action/charger/update/{cp_id}", response_class=HTMLResponse)
async def action_charger_update(request: Request, cp_id: str):
    """Update a charge point via Core API."""
    form = await request.form()

    def _str(key):
        v = form.get(key, "").strip()
        return v if v else None

    body = {k: v for k, v in {
        "vendor": _str("vendor"),
        "model": _str("model"),
        "serial_number": _str("serial_number"),
        "ocpp_version": _str("ocpp_version"),
        "site": _str("site"),
        "display_name": _str("display_name"),
    }.items() if v is not None}

    try:
        await api(f"/chargers/{cp_id}", method="PUT", json=body)
        return HTMLResponse('''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                ✓ Changes saved
            </div>
            <script>setTimeout(() => { closeModal('modal-charger-edit'); location.href=location.pathname+"?t="+Date.now(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@router.post("/action/charger/delete/{cp_id}", response_class=HTMLResponse)
async def action_charger_delete(request: Request, cp_id: str):
    """Delete a charge point via Core API."""
    try:
        await api(f"/chargers/{cp_id}", method="DELETE")
        return HTMLResponse('''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                🗑 Charger deleted
            </div>
            <script>setTimeout(() => location.href=location.pathname+"?t="+Date.now(), 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@router.post("/action/charger/purge-virtual", response_class=HTMLResponse)
async def action_charger_purge_virtual(request: Request):
    """Bulk delete simulated charge points via Core API."""
    try:
        result = await api("/chargers?simulated=true", method="DELETE")
        deleted = result.get("deleted", 0)
        return HTMLResponse(f'''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                🗑 {deleted} virtual charger(s) deleted
            </div>
            <script>setTimeout(() => location.href=location.pathname+"?t="+Date.now(), 1500);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


# ── Remote OCPP commands ──────────────────────────────────────────────────────

@router.post("/action/start/{cp_id}", response_class=HTMLResponse)
async def action_start(cp_id: str, request: Request):
    connector = int(request.query_params.get("connector", 1))
    result = await api(f"/chargers/{cp_id}/start", method="POST", json={"connector_id": connector, "id_tag": "REMOTE"})
    status = result.get("status", result.get("detail", "Error"))
    if "detail" in result:
        return HTMLResponse(f'<span class="text-red-400">✗ {status}</span>')
    return HTMLResponse(f'<span class="text-green-400">✓ {status}</span>')


@router.post("/action/stop/{cp_id}", response_class=HTMLResponse)
async def action_stop(cp_id: str, request: Request):
    connector = request.query_params.get("connector")
    qs = f"?connector_id={connector}" if connector else ""
    result = await api(f"/chargers/{cp_id}/stop{qs}", method="POST")
    status = result.get("status", result.get("detail", "Error"))
    if "detail" in result:
        return HTMLResponse(f'<span class="text-red-400">✗ {status}</span>')
    return HTMLResponse(f'<span class="text-yellow-400">⏹ {status}</span>')


@router.post("/action/reset/{cp_id}", response_class=HTMLResponse)
async def action_reset(cp_id: str, request: Request):
    reset_type = request.query_params.get("type", "Soft")
    result = await api(f"/chargers/{cp_id}/reset?reset_type={reset_type}", method="POST")
    status = result.get("status", result.get("detail", "Error"))
    if "detail" in result:
        return HTMLResponse(f'<span class="text-red-400">✗ {status}</span>')
    return HTMLResponse(f'<span class="text-blue-400">↻ {status}</span>')


@router.post("/action/getconfig/{cp_id}", response_class=HTMLResponse)
async def action_getconfig(cp_id: str, request: Request):
    result = await api(f"/chargers/{cp_id}/command", method="POST", json={"action": "GetConfiguration", "payload": {"key": []}})
    if "detail" in result:
        return HTMLResponse(f'<span class="text-red-400">✗ {result["detail"]}</span>')
    return HTMLResponse(f'<span class="text-green-400">✓ GetConfiguration sent (msg_id: {result.get("msg_id", "?")})</span>')


@router.post("/action/command/{cp_id}")
async def action_command(cp_id: str, request: Request):
    """Generic OCPP command — used by the terminal UI."""
    body = await request.json()
    action = body.get("action", "")
    payload = body.get("payload", {})
    if not action:
        return {"ok": False, "error": "Missing action"}
    result = await api(f"/chargers/{cp_id}/command", method="POST", json={"action": action, "payload": payload})
    return result
