"""
CPO Admin — Network management dashboard.

FastAPI + Jinja2 + HTMX. No React, no npm, no build step.
Consumes OCPP Core via REST API + Redis for live data.
"""
import os
import logging
from contextlib import asynccontextmanager

import asyncpg
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "ocppcore")
DB_USER = os.getenv("DB_USER", "ocpp")
DB_PASS = os.getenv("DB_PASS")
if not DB_PASS:
    raise RuntimeError("DB_PASS environment variable is required")

APP_TITLE = os.getenv("APP_TITLE", "OCPP Admin")
# PKI data directory (where root-ca.crt and users/ certs live)
PKI_DATA_DIR = os.getenv("PKI_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "ocpp-core", "data", "pki"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB pool on startup, close on shutdown."""
    logger.info("Connecting to PostgreSQL %s@%s:%s/%s", DB_USER, DB_HOST, DB_PORT, DB_NAME)
    app.state.db = await asyncpg.create_pool(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASS,
        min_size=2, max_size=10,
    )
    logger.info("DB pool ready")
    yield
    await app.state.db.close()
    logger.info("DB pool closed")


app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Inject APP_TITLE into every template context
templates.env.globals["app_title"] = APP_TITLE

# Additional tools can be configured and linked via skins

# OCPP Core API base URL
CORE_API = os.getenv("OCPP_CORE_API", "http://localhost:8000")


# ── Helpers ──────────────────────────────────────────────────────────────

async def api(path: str, method: str = "GET", json: dict = None) -> dict:
    """Call OCPP Core API."""
    async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
        if method == "GET":
            r = await client.get(f"/api/v1{path}")
        elif method == "POST":
            r = await client.post(f"/api/v1{path}", json=json)
        elif method == "PUT":
            r = await client.put(f"/api/v1{path}", json=json)
        elif method == "DELETE":
            r = await client.delete(f"/api/v1{path}")
        r.raise_for_status()
        return r.json()


# ── Pages ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — network overview."""
    chargers = await api("/chargers?limit=100")
    sessions = await api("/sessions/stats/summary")
    pki = await api("/pki/stats")
    events = await api("/events/info")

    return templates.TemplateResponse(request, "dashboard.html", context={
        "chargers": chargers.get("chargers", []),
        "charger_count": chargers.get("total", 0),
        "stats": sessions,
        "pki": pki,
        "events": events,
    })


@app.get("/remote/{cp_id}", response_class=HTMLResponse)
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


@app.get("/partials/remote/sessions/{cp_id}", response_class=HTMLResponse)
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


@app.get("/partials/remote/connectors/{cp_id}", response_class=HTMLResponse)
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

        border_color = {"Available":"#22c55e","Charging":"#3b82f6","Preparing":"#f59e0b","Faulted":"#ef4444"}.get(status, "#64748b")
        dot_class = {"Available":"bg-green-500","Charging":"bg-blue-500 animate-pulse","Preparing":"bg-yellow-500","Faulted":"bg-red-500"}.get(status, "bg-gray-500")

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
                <button hx-post="/action/stop/{cp_id}" hx-swap="outerHTML"
                    class="py-3 rounded-lg font-bold text-sm {"bg-gradient-to-br from-red-600 to-red-500 text-white shadow-lg shadow-red-500/30" if can_stop else "bg-gray-800 text-gray-500 cursor-not-allowed"}"
                    {"" if can_stop else "disabled"}>■ Stop</button>
            </div>
        </div>'''

    return HTMLResponse(html or '<div class="text-sm text-gray-500 py-4">No connector data</div>')


@app.get("/partials/remote/pki/{cp_id}", response_class=HTMLResponse)
async def remote_pki_partial(request: Request, cp_id: str):
    """HTMX partial: PKI status for a charger."""
    try:
        stats = await api("/pki/stats")
    except Exception:
        stats = {}

    return HTMLResponse(f'''
        <div class="grid grid-cols-3 gap-4 text-center">
            <div><div class="text-2xl font-bold text-green-400">{stats.get("active",0)}</div><div class="text-xs text-gray-500">Active</div></div>
            <div><div class="text-2xl font-bold text-red-400">{stats.get("revoked",0)}</div><div class="text-xs text-gray-500">Revoked</div></div>
            <div><div class="text-2xl font-bold text-yellow-400">{stats.get("expiring_30d",0)}</div><div class="text-xs text-gray-500">Expiring</div></div>
        </div>
    ''')


@app.get("/chargers", response_class=HTMLResponse)
async def chargers_page(request: Request):
    """Charger management."""
    data = await api("/chargers?limit=100")
    return templates.TemplateResponse(request, "chargers.html", context={
        "chargers": data.get("chargers", []),
        "total": data.get("total", 0),
    })


@app.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    """Session monitoring."""
    data = await api("/sessions?limit=100")
    return templates.TemplateResponse(request, "sessions.html", context={
        "sessions": data.get("sessions", []),
        "total": data.get("total", 0),
    })


@app.get("/tariffs", response_class=HTMLResponse)
async def tariffs_page(request: Request):
    """Tariff configuration — rich pricing management panel."""
    from datetime import datetime, timezone
    tariff_data = await api("/tariffs")
    charger_data = await api("/chargers?limit=100")
    now_iso = datetime.now(timezone.utc).isoformat()
    return templates.TemplateResponse(request, "tariffs.html", context={
        "tariffs": tariff_data.get("tariffs", []),
        "chargers": charger_data.get("chargers", []),
        "now_iso": now_iso,
    })


# ── Tariff HTMX Partials & Actions ────────────────────────────────────────

@app.get("/partials/tariff/edit/{tariff_id}", response_class=HTMLResponse)
async def tariff_edit_partial(request: Request, tariff_id: str):
    """HTMX partial: edit form for an existing tariff."""
    try:
        data = await api("/tariffs")
        tariffs = data.get("tariffs", [])
        t = next((x for x in tariffs if x["id"] == tariff_id), None)
    except Exception:
        t = None

    if not t:
        return HTMLResponse('<div class="p-4 text-red-400 text-sm">Tariff not found</div>')

    vf = (t.get("valid_from") or "")[:16].replace(" ", "T")
    vu = (t.get("valid_until") or "")[:16].replace(" ", "T")

    return HTMLResponse(f'''
    <div class="flex justify-between items-center mb-5 border-b border-gray-800 pb-4">
        <h3 class="font-semibold text-gray-100">✏️ Edit {t["name"]}</h3>
        <button onclick="closeModal('modal-edit')" class="text-gray-500 hover:text-gray-300 text-xl">✕</button>
    </div>
    <form hx-post="/action/tariff/update/{t["id"]}"
          hx-target="#edit-result"
          hx-swap="innerHTML"
          class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
            <div class="col-span-2">
                <label class="block text-xs text-gray-400 mb-1">Name</label>
                <input name="name" value="{t.get("name","")}" required
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Energy Rate (€/kWh)</label>
                <input name="energy_rate" type="number" step="0.0001" min="0" value="{t.get("energy_rate") or 0}" required
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Time Rate (€/min)</label>
                <input name="time_rate" type="number" step="0.0001" min="0" value="{t.get("time_rate") or 0}"
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Idle Rate (€/min)</label>
                <input name="idle_rate" type="number" step="0.0001" min="0" value="{t.get("idle_rate") or 0}"
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Start Fee (€)</label>
                <input name="flat_fee" type="number" step="0.01" min="0" value="{t.get("flat_fee") or 0}"
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Valid From</label>
                <input name="valid_from" type="datetime-local" value="{vf}"
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Valid Until</label>
                <input name="valid_until" type="datetime-local" value="{vu}"
                    class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            </div>
        </div>
        <div id="edit-result"></div>
        <div class="flex gap-3 pt-2">
            <button type="button"
                hx-post="/action/tariff/delete/{t["id"]}"
                hx-confirm="Delete tariff '{t["name"]}'?"
                hx-target="#edit-result"
                hx-swap="innerHTML"
                class="px-4 py-2 bg-red-900/40 hover:bg-red-900/70 text-red-300 border border-red-800 rounded-lg text-sm transition-colors">
                🗑 Delete
            </button>
            <div class="flex-1"></div>
            <button type="button" onclick="closeModal('modal-edit')"
                class="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors">
                Cancel
            </button>
            <button type="submit"
                class="px-6 py-2 bg-brand-green text-black font-bold rounded-lg text-sm hover:opacity-90 transition-opacity">
                Save
            </button>
        </div>
    </form>
    ''')


@app.post("/action/tariff/create", response_class=HTMLResponse)
async def action_tariff_create(request: Request):
    """Create a new tariff via Core API."""
    form = await request.form()
    tariff_id = form.get("id", "").strip() or form.get("name", "").lower().replace(" ", "-").replace("/", "-")
    body = {
        "id": tariff_id,
        "name": form.get("name", "").strip(),
        "currency": "EUR",
        "energy_rate": float(form.get("energy_rate") or 0),
        "time_rate": float(form.get("time_rate") or 0),
        "idle_rate": float(form.get("idle_rate") or 0),
        "flat_fee": float(form.get("flat_fee") or 0),
    }
    if form.get("valid_from"):
        body["valid_from"] = form.get("valid_from").replace("T", " ")
    if form.get("valid_until"):
        body["valid_until"] = form.get("valid_until").replace("T", " ")

    try:
        await api("/tariffs", method="POST", json=body)
        return HTMLResponse('''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                ✓ Tariff created
            </div>
            <script>setTimeout(() => { closeModal('modal-create'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/tariff/update/{tariff_id}", response_class=HTMLResponse)
async def action_tariff_update(request: Request, tariff_id: str):
    """Update an existing tariff via Core API."""
    form = await request.form()
    body = {
        "name": form.get("name", "").strip(),
        "energy_rate": float(form.get("energy_rate") or 0),
        "time_rate": float(form.get("time_rate") or 0),
        "idle_rate": float(form.get("idle_rate") or 0),
        "flat_fee": float(form.get("flat_fee") or 0),
    }
    if form.get("valid_from"):
        body["valid_from"] = form.get("valid_from").replace("T", " ")
    if form.get("valid_until"):
        body["valid_until"] = form.get("valid_until").replace("T", " ")

    try:
        await api(f"/tariffs/{tariff_id}", method="PUT", json=body)
        return HTMLResponse('''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                ✓ Changes saved
            </div>
            <script>setTimeout(() => { closeModal('modal-edit'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/tariff/delete/{tariff_id}", response_class=HTMLResponse)
async def action_tariff_delete(request: Request, tariff_id: str):
    """Delete a tariff via Core API."""
    try:
        await api(f"/tariffs/{tariff_id}", method="DELETE")
        return HTMLResponse('''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                🗑 Tariff deleted
            </div>
            <script>setTimeout(() => { closeModal('modal-edit'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/charger/assign-tariff/{cp_id}", response_class=HTMLResponse)
async def action_charger_assign_tariff(request: Request, cp_id: str):
    """Assign a tariff to a charger (updates tariff_kwh via Core API)."""
    form = await request.form()
    tariff_id = form.get("tariff_id", "").strip()

    try:
        # Fetch the tariff to get its energy_rate
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


@app.post("/action/charger/create", response_class=HTMLResponse)
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
            <script>setTimeout(() => { closeModal('modal-charger-create'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/charger/update/{cp_id}", response_class=HTMLResponse)
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
            <script>setTimeout(() => { closeModal('modal-charger-edit'); location.reload(); }, 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/charger/delete/{cp_id}", response_class=HTMLResponse)
async def action_charger_delete(request: Request, cp_id: str):
    """Delete a charge point via Core API."""
    try:
        await api(f"/chargers/{cp_id}", method="DELETE")
        return HTMLResponse('''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                🗑 Charger deleted
            </div>
            <script>setTimeout(() => location.reload(), 1200);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/charger/purge-virtual", response_class=HTMLResponse)
async def action_charger_purge_virtual(request: Request):
    """Bulk delete simulated charge points via Core API."""
    try:
        result = await api("/chargers?simulated=true", method="DELETE")
        deleted = result.get("deleted", 0)
        return HTMLResponse(f'''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                🗑 {deleted} virtual charger(s) deleted
            </div>
            <script>setTimeout(() => location.reload(), 1500);</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.get("/rfid", response_class=HTMLResponse)
async def rfid_page(request: Request):
    """Legacy RFID page — redirect to /tokens."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/tokens", status_code=302)


# ── Token pages (new) ────────────────────────────────────────────────────────

@app.get("/tokens", response_class=HTMLResponse)
async def tokens_page(request: Request):
    """Token management page."""
    from datetime import datetime
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

    token_data = await api(f"/tokens{params}")
    tokens = token_data.get("tokens", [])
    total = token_data.get("total", 0)

    groups_data = await api("/groups")
    groups = groups_data.get("groups", [])

    # Summary stats
    all_tokens = await api("/tokens?limit=500")
    all_list = all_tokens.get("tokens", [])
    now_iso = datetime.utcnow().isoformat()
    stats = {
        "total": all_tokens.get("total", len(all_list)),
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


@app.get("/tokens/{token_id}", response_class=HTMLResponse)
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


# ── Group pages ──────────────────────────────────────────────────────────────

@app.get("/groups", response_class=HTMLResponse)
async def groups_page(request: Request):
    """Group management page."""
    data = await api("/groups")
    return templates.TemplateResponse(request, "groups.html", context={
        "groups": data.get("groups", []),
    })


@app.get("/groups/{group_id}", response_class=HTMLResponse)
async def group_detail_page(request: Request, group_id: str):
    """Group detail page."""
    from datetime import datetime
    try:
        data = await api(f"/groups/{group_id}")
    except Exception:
        return HTMLResponse('<div class="p-6 text-red-400">Group not found</div>', status_code=404)

    return templates.TemplateResponse(request, "group_detail.html", context={
        "group": data["group"],
        "tokens": data.get("tokens", []),
        "monthly_summary": data.get("monthly_summary", []),
        "current_month": datetime.now().strftime("%Y-%m"),
    })


@app.post("/groups/{group_id}/billing")
async def save_group_billing(request: Request, group_id: str):
    """Save billing configuration for a group via Core API (PUT)."""
    from fastapi.responses import RedirectResponse as RR
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
    # Billing method
    billing_method = _str("billing_method")
    if billing_method in ("invoice", "direct_debit", "prepaid"):
        body["billing_method"] = billing_method

    # SEPA fields
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
        # Note: Core API PUT endpoint may not yet support all billing fields
        # (billing_method, iban, bic, etc. not in GroupUpdate model).
        # These will be added when DB migration 002_billing.sql runs.

    return RR(f"/groups/{group_id}", status_code=303)


@app.post("/groups/{group_id}/mandate")
async def setup_mandate(request: Request, group_id: str):
    """Proxy: create SEPA mandate setup (Mollie first payment)."""
    from fastapi.responses import JSONResponse
    try:
        result = await api(f"/groups/{group_id}/mandate", method="POST", json={})
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ── Invoices pages ──────────────────────────────────────────────────────────

@app.get("/invoices", response_class=HTMLResponse)
async def invoices_page(request: Request):
    """Invoice management page."""
    group_id = request.query_params.get("group_id", "")
    status = request.query_params.get("status", "")

    params = "?limit=200"
    if group_id:
        params += f"&group_id={group_id}"
    if status:
        params += f"&status={status}"

    try:
        inv_data = await api(f"/invoices{params}")
        invoices = inv_data if isinstance(inv_data, list) else inv_data.get("invoices", [])
    except Exception:
        invoices = []

    try:
        groups_data = await api("/groups")
        groups = groups_data.get("groups", [])
    except Exception:
        groups = []

    # Build group name lookup for display
    group_map = {str(g["id"]): g["name"] for g in groups}
    for inv in invoices:
        gid = str(inv.get("group_id", ""))
        if gid and not inv.get("group_name"):
            inv["group_name"] = group_map.get(gid, gid[:8])

    return templates.TemplateResponse(request, "invoices.html", {
        "invoices": invoices,
        "groups": groups,
        "CORE_API": CORE_API,
    })


@app.post("/invoices/generate")
async def generate_invoice(request: Request):
    """Generate a new invoice for a group+period."""
    from fastapi.responses import RedirectResponse as RR
    form = await request.form()
    group_id = form.get("group_id", "").strip()
    period_start = form.get("period_start", "").strip()
    period_end = form.get("period_end", "").strip()

    if group_id and period_start and period_end:
        try:
            await api(
                f"/groups/{group_id}/invoices",
                method="POST",
                json={"period_start": period_start, "period_end": period_end},
            )
        except Exception as e:
            logger.warning("Invoice generation failed: %s", e)

    return RR("/invoices", status_code=303)


@app.post("/invoices/{invoice_id}/send")
async def send_invoice(request: Request, invoice_id: str):
    """Send an invoice by email."""
    from fastapi.responses import RedirectResponse as RR
    try:
        await api(f"/invoices/{invoice_id}/send", method="POST")
    except Exception as e:
        logger.warning("Invoice send failed %s: %s", invoice_id, e)
    return RR("/invoices", status_code=303)


@app.post("/invoices/{invoice_id}/collect")
async def collect_invoice(request: Request, invoice_id: str):
    """Trigger SEPA collection for an invoice."""
    from fastapi.responses import RedirectResponse as RR
    try:
        await api(f"/invoices/{invoice_id}/collect", method="POST")
    except Exception as e:
        logger.warning("Invoice collect failed %s: %s", invoice_id, e)
    return RR("/invoices", status_code=303)


@app.post("/invoices/{invoice_id}/mark-paid")
async def mark_paid_invoice(request: Request, invoice_id: str):
    """Manually mark an invoice as paid."""
    from fastapi.responses import RedirectResponse as RR
    try:
        await api(f"/invoices/{invoice_id}/mark-paid", method="POST")
    except Exception as e:
        logger.warning("Invoice mark-paid failed %s: %s", invoice_id, e)
    return RR("/invoices", status_code=303)


@app.get("/groups/{group_id}/invoice", response_class=Response)
async def group_invoice_download(request: Request, group_id: str, month: str = None):
    """Proxy group invoice PDF download."""
    from datetime import datetime
    if not month:
        month = datetime.now().strftime("%Y-%m")
    async with httpx.AsyncClient(base_url=CORE_API, timeout=30) as client:
        r = await client.get(f"/api/v1/groups/{group_id}/invoice?month={month}")
        r.raise_for_status()
    return Response(
        content=r.content,
        media_type="application/pdf",
        headers={"Content-Disposition": r.headers.get("content-disposition", f'attachment; filename="invoice-{month}.pdf"')},
    )


# ── Token HTMX actions (new API) ─────────────────────────────────────────────

@app.post("/action/token/create", response_class=HTMLResponse)
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
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Token created</div><script>setTimeout(()=>{closeModal("modal-create");location.reload()},1200)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@app.put("/action/token/update/{token_id}", response_class=HTMLResponse)
async def action_token_update_v2(request: Request, token_id: str):
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


@app.post("/action/token/block/{token_id}", response_class=HTMLResponse)
async def action_token_block(request: Request, token_id: str):
    form = await request.form()
    reason = form.get("reason", "").strip() or "manual block"
    try:
        await api(f"/tokens/{token_id}/block", method="POST", json={"reason": reason})
        return HTMLResponse('<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">🚫 Token blocked</div><script>setTimeout(()=>location.reload(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@app.post("/action/token/unblock/{token_id}", response_class=HTMLResponse)
async def action_token_unblock(request: Request, token_id: str):
    try:
        await api(f"/tokens/{token_id}/unblock", method="POST")
        return HTMLResponse('<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Token unblocked</div><script>setTimeout(()=>location.reload(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@app.post("/action/token/replace/{token_id}", response_class=HTMLResponse)
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
        return HTMLResponse(f'<div class="p-2 bg-green-900/50 text-green-300 rounded text-sm">✅ Replaced → <a href="/tokens/{new_id}" class="underline">new token</a></div><script>setTimeout(()=>location.reload(),2000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@app.delete("/action/token/delete/{token_id}", response_class=HTMLResponse)
async def action_token_delete(request: Request, token_id: str):
    try:
        await api(f"/tokens/{token_id}", method="DELETE")
        return HTMLResponse('<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">🗑 Token revoked</div><script>setTimeout(()=>location.reload(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@app.post("/action/token/purge-test", response_class=HTMLResponse)
async def action_token_purge_test(request: Request):
    """Remove all test tokens (STRESS-, SIM-, VAL-, CHAOS- prefixes) via bulk SQL."""
    try:
        # Use Core API bulk approach — delete by prefix pattern
        prefixes = ["STRESS-%", "SIM-%", "VAL-%", "CHAOS-%", "E2E-%"]
        result = await api("/tokens/purge-test", method="POST", json={"prefixes": prefixes})
        deleted = result.get("deleted", 0)
        return HTMLResponse(f'<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">🗑 {deleted} test tokens removed</div><script>setTimeout(()=>location.reload(),1500)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


# ── Group HTMX actions ───────────────────────────────────────────────────────

@app.post("/action/group/create", response_class=HTMLResponse)
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


@app.put("/action/group/update/{group_id}", response_class=HTMLResponse)
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


@app.delete("/action/group/delete/{group_id}", response_class=HTMLResponse)
async def action_group_delete(request: Request, group_id: str):
    try:
        await api(f"/groups/{group_id}", method="DELETE")
        return HTMLResponse('<div class="p-2 bg-yellow-900/50 text-yellow-300 rounded text-sm">🗑 Group deleted</div><script>setTimeout(()=>location.reload(),1000)</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="p-2 bg-red-900/50 text-red-300 rounded text-sm">Error: {e}</div>')


@app.get("/pki", response_class=HTMLResponse)
async def pki_page(request: Request):
    """PKI certificate dashboard."""
    stats = await api("/pki/stats")
    hierarchy = await api("/pki/ca-hierarchy")
    chargers = await api("/chargers?limit=200")
    return templates.TemplateResponse(request, "pki.html", context={
        "stats": stats,
        "hierarchy": hierarchy,
        "charger_ids": [c["id"] for c in chargers.get("chargers", [])],
    })


# ── PKI HTMX Partials ────────────────────────────────────────────────────

@app.get("/partials/pki/cert-rows", response_class=HTMLResponse)
async def pki_cert_rows(
    request: Request,
    status: str = "",
    type: str = "",
    charge_point: str = "",
    search: str = "",
    page: int = 1,
):
    """HTMX partial: certificate table rows with pagination."""
    params = f"?page={page}&limit=25"
    if status:
        params += f"&status={status}"
    if type:
        params += f"&type={type}"
    if charge_point:
        params += f"&charge_point={charge_point}"
    if search:
        params += f"&search={search}"

    try:
        data = await api(f"/pki/certificates{params}")
    except Exception:
        return HTMLResponse('<tr><td colspan="8" class="p-6 text-center text-red-400 text-sm">Failed to load certificates</td></tr>')

    certs = data.get("certificates", [])
    total = data.get("total", 0)
    pages = data.get("pages", 1)

    rows = ""
    for c in certs:
        serial_short = c["serial"][:16] + "…" if len(c["serial"]) > 16 else c["serial"]
        subject_short = c["subject"][:40] + "…" if len(c.get("subject") or "") > 40 else (c.get("subject") or "—")
        cp = c.get("charge_point") or "—"

        status_val = c.get("status", "")
        status_badge = {
            "active":   '<span class="px-2 py-0.5 bg-green-900 text-green-300 rounded-full text-xs font-medium">Active</span>',
            "revoked":  '<span class="px-2 py-0.5 bg-red-900 text-red-300 rounded-full text-xs font-medium">Revoked</span>',
            "expired":  '<span class="px-2 py-0.5 bg-gray-700 text-gray-400 rounded-full text-xs font-medium">Expired</span>',
            "expiring": '<span class="px-2 py-0.5 bg-yellow-900 text-yellow-300 rounded-full text-xs font-medium">Expiring</span>',
        }.get(status_val, f'<span class="px-2 py-0.5 bg-gray-800 text-gray-500 rounded-full text-xs">{status_val}</span>')

        type_val = c.get("type", "")
        type_badge = {
            "secc":     '<span class="px-2 py-0.5 bg-blue-900 text-blue-300 rounded text-xs">SECC</span>',
            "contract": '<span class="px-2 py-0.5 bg-purple-900 text-purple-300 rounded text-xs">Contract</span>',
            "user":     '<span class="px-2 py-0.5 bg-teal-900 text-teal-300 rounded text-xs">User</span>',
        }.get(type_val, f'<span class="px-2 py-0.5 bg-gray-800 text-gray-400 rounded text-xs">{type_val}</span>')

        issued = (c.get("issued_at") or "")[:10]
        expires = (c.get("not_after") or "")[:10]

        can_revoke = status_val == "active"
        revoke_btn = f'''<button onclick="openRevokeModal('{c["serial"]}', '{subject_short.replace("'","&apos;")}')"
            class="px-2 py-1 bg-red-900/50 hover:bg-red-800 text-red-300 rounded text-xs transition-colors">Revoke</button>''' if can_revoke else ""

        rows += f'''<tr class="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer text-sm"
            hx-get="/partials/pki/cert-detail/{c["serial"]}"
            hx-target="#cert-detail-panel"
            hx-swap="innerHTML"
            onclick="document.getElementById('cert-detail-panel').classList.remove('hidden')">
            <td class="p-3 font-mono text-xs text-gray-400">{serial_short}</td>
            <td class="p-3">{type_badge}</td>
            <td class="p-3 text-xs text-gray-300 max-w-xs truncate">{subject_short}</td>
            <td class="p-3 font-mono text-xs text-gray-400">{cp}</td>
            <td class="p-3">{status_badge}</td>
            <td class="p-3 text-xs text-gray-500">{issued}</td>
            <td class="p-3 text-xs text-gray-500">{expires}</td>
            <td class="p-3">
                <div class="flex gap-1">
                    <a href="/pki/certificates/{c["serial"]}/download"
                       class="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors">PEM</a>
                    {revoke_btn}
                </div>
            </td>
        </tr>'''

    if not rows:
        rows = '<tr><td colspan="8" class="p-6 text-center text-gray-500 text-sm">No certificates found</td></tr>'

    # Pagination
    pagination = ""
    if pages > 1:
        prev_disabled = "opacity-40 cursor-not-allowed" if page <= 1 else ""
        next_disabled = "opacity-40 cursor-not-allowed" if page >= pages else ""
        prev_page = max(1, page - 1)
        next_page = min(pages, page + 1)
        qs = f"&status={status}&type={type}&charge_point={charge_point}&search={search}"
        pagination = f'''
        <tr class="border-t border-gray-800">
            <td colspan="8" class="p-3">
                <div class="flex items-center justify-between text-sm text-gray-400">
                    <span>{total} certificates · page {page} of {pages}</span>
                    <div class="flex gap-2">
                        <button hx-get="/partials/pki/cert-rows?page={prev_page}{qs}"
                            hx-target="#cert-tbody" hx-swap="innerHTML"
                            class="px-3 py-1 bg-gray-800 rounded hover:bg-gray-700 {prev_disabled}">← Prev</button>
                        <button hx-get="/partials/pki/cert-rows?page={next_page}{qs}"
                            hx-target="#cert-tbody" hx-swap="innerHTML"
                            class="px-3 py-1 bg-gray-800 rounded hover:bg-gray-700 {next_disabled}">Next →</button>
                    </div>
                </div>
            </td>
        </tr>'''

    return HTMLResponse(rows + pagination)


@app.get("/partials/pki/cert-detail/{serial}", response_class=HTMLResponse)
async def pki_cert_detail(request: Request, serial: str):
    """HTMX partial: certificate detail panel."""
    try:
        cert = await api(f"/pki/certificates/{serial}")
    except Exception:
        return HTMLResponse('<div class="p-4 text-red-400 text-sm">Certificate not found</div>')

    status_val = cert.get("status", "")
    status_badge = {
        "active":  '<span class="px-2 py-1 bg-green-900 text-green-300 rounded-full text-xs">✓ Active</span>',
        "revoked": '<span class="px-2 py-1 bg-red-900 text-red-300 rounded-full text-xs">✗ Revoked</span>',
        "expired": '<span class="px-2 py-1 bg-gray-700 text-gray-400 rounded-full text-xs">Expired</span>',
    }.get(status_val, f'<span class="px-2 py-1 bg-gray-800 text-xs">{status_val}</span>')

    serial_full = cert.get("serial", "")
    fp = cert.get("fingerprint") or "—"
    # Format fingerprint with colons for readability
    if fp and fp != "—" and ":" not in fp:
        fp = ":".join(fp[i:i+2] for i in range(0, min(len(fp), 40), 2)) + "…"

    revoke_btn = ""
    if status_val == "active":
        revoke_btn = f'''<button onclick="openRevokeModal('{serial_full}', '{cert.get("subject","").replace("'","&apos;")}')"
            class="px-3 py-2 bg-red-900/50 hover:bg-red-800 text-red-300 rounded text-sm transition-colors">
            🚫 Revoke Certificate</button>'''

    revocation_info = ""
    if status_val == "revoked":
        revocation_info = f'''
        <div class="mt-3 p-3 bg-red-900/20 border border-red-800 rounded-lg text-sm">
            <div class="text-red-400 font-medium mb-1">Revocation Details</div>
            <div class="text-gray-300">Revoked: {(cert.get("revoked_at") or "")[:19].replace("T"," ")}</div>
            <div class="text-gray-300">Reason: {cert.get("revocation_reason") or "unspecified"}</div>
        </div>'''

    return HTMLResponse(f'''
    <div class="p-4">
        <div class="flex items-center justify-between mb-4">
            <h3 class="font-semibold text-gray-100">Certificate Detail</h3>
            <button onclick="document.getElementById('cert-detail-panel').classList.add('hidden')"
                class="text-gray-500 hover:text-gray-300 text-lg">✕</button>
        </div>
        <div class="space-y-2 text-sm">
            <div class="flex justify-between"><span class="text-gray-500">Status</span>{status_badge}</div>
            <div class="flex justify-between"><span class="text-gray-500">Type</span><span class="text-gray-300">{cert.get("type","—").upper()}</span></div>
            <div class="mt-1 pt-2 border-t border-gray-800">
                <div class="text-gray-500 text-xs mb-1">Serial</div>
                <div class="font-mono text-xs text-gray-400 break-all">{serial_full}</div>
            </div>
            <div class="pt-1">
                <div class="text-gray-500 text-xs mb-1">Subject</div>
                <div class="text-xs text-gray-300 break-all">{cert.get("subject","—")}</div>
            </div>
            <div class="pt-1">
                <div class="text-gray-500 text-xs mb-1">Issuer</div>
                <div class="text-xs text-gray-400 break-all">{cert.get("issuer","—")}</div>
            </div>
            <div class="pt-1">
                <div class="text-gray-500 text-xs mb-1">Fingerprint (SHA-256)</div>
                <div class="font-mono text-xs text-gray-500 break-all">{fp}</div>
            </div>
            <div class="flex justify-between pt-1 border-t border-gray-800">
                <span class="text-gray-500">Valid From</span>
                <span class="text-gray-300 text-xs">{(cert.get("not_before") or "")[:10]}</span>
            </div>
            <div class="flex justify-between">
                <span class="text-gray-500">Valid Until</span>
                <span class="text-gray-300 text-xs">{(cert.get("not_after") or "")[:10]}</span>
            </div>
            {f'<div class="flex justify-between"><span class="text-gray-500">Charge Point</span><span class="font-mono text-xs text-gray-300">{cert.get("charge_point")}</span></div>' if cert.get("charge_point") else ""}
        </div>
        {revocation_info}
        <div class="flex gap-2 mt-4 pt-3 border-t border-gray-800">
            <a href="/pki/certificates/{serial_full}/download"
               class="flex-1 text-center px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm transition-colors">
               ⬇ Download PEM</a>
            {revoke_btn}
        </div>
    </div>
    ''')


@app.get("/partials/pki/audit-log", response_class=HTMLResponse)
async def pki_audit_log_partial(request: Request, type: str = "", date_from: str = "", date_to: str = ""):
    """HTMX partial: audit log timeline."""
    params = "?limit=50"
    if type:
        params += f"&type={type}"
    if date_from:
        params += f"&date_from={date_from}"
    if date_to:
        params += f"&date_to={date_to}"
    try:
        data = await api(f"/pki/audit-log{params}")
    except Exception:
        return HTMLResponse('<div class="p-4 text-red-400 text-sm">Failed to load audit log</div>')

    events = data.get("events", [])
    if not events:
        return HTMLResponse('<div class="p-6 text-center text-gray-500 text-sm">No events found</div>')

    event_icons = {
        "issued": ("🟢", "text-green-400"),
        "revoked": ("🔴", "text-red-400"),
    }

    items = ""
    for e in events:
        event_type = e.get("event", "")
        base_event = event_type.split(":")[0]
        icon, color = event_icons.get(base_event, ("⚪", "text-gray-400"))
        ts = (e.get("event_time") or "")[:19].replace("T", " ")
        cert_type = e.get("type", "").upper()
        subject_short = (e.get("subject") or "—")[:50]

        items += f'''<div class="flex gap-3 py-2 border-b border-gray-800/50 last:border-0">
            <div class="text-lg mt-0.5">{icon}</div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                    <span class="{color} font-medium text-sm">{event_type}</span>
                    <span class="px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded text-xs">{cert_type}</span>
                    {f'<span class="text-xs text-gray-500 font-mono">{e.get("charge_point","")}</span>' if e.get("charge_point") else ""}
                </div>
                <div class="text-xs text-gray-400 truncate">{subject_short}</div>
            </div>
            <div class="text-xs text-gray-600 whitespace-nowrap">{ts}</div>
        </div>'''

    return HTMLResponse(f'<div class="divide-y divide-gray-800/50">{items}</div>')


@app.get("/pki/certificates/{serial}/download")
async def download_cert(serial: str):
    """Proxy: download certificate PEM."""
    import httpx
    async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
        r = await client.get(f"/api/v1/pki/certificates/{serial}/download")
        r.raise_for_status()
    return Response(
        content=r.content,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": r.headers.get("content-disposition", f'attachment; filename="cert-{serial[:16]}.pem"')},
    )


# ── PKI Actions (HTMX POST) ──────────────────────────────────────────────

@app.post("/action/pki/issue-secc", response_class=HTMLResponse)
async def action_issue_secc(request: Request):
    """Issue a SECC certificate for a charge point."""
    form = await request.form()
    charge_point_id = form.get("charge_point_id", "")
    csr_file = form.get("csr_file")

    if not charge_point_id:
        return HTMLResponse('<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Charge point ID required</div>')

    body = {"charge_point_id": charge_point_id}
    if csr_file and hasattr(csr_file, "read"):
        content = await csr_file.read()
        if content:
            body["csr_pem"] = content.decode()

    try:
        result = await api("/pki/issue/secc", method="POST", json=body)
        serial = result.get("serial", "")[:16]
        return HTMLResponse(f'''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm"
                 hx-swap-oob="true" id="issue-result">
                ✓ SECC cert issued for <span class="font-mono">{charge_point_id}</span>
                — serial: <span class="font-mono">{serial}…</span>
            </div>
            <script>
                // Refresh cert table
                htmx.trigger('#cert-tbody', 'refresh');
                setTimeout(() => document.getElementById('issue-panel').classList.add('hidden'), 2000);
                showToast('SECC certificate issued successfully', 'success');
            </script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/pki/issue-contract", response_class=HTMLResponse)
async def action_issue_contract(request: Request):
    """Issue a contract certificate."""
    form = await request.form()
    emaid = form.get("emaid", "")

    if not emaid:
        return HTMLResponse('<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">EMAID required</div>')

    try:
        result = await api("/pki/issue/contract", method="POST", json={"emaid": emaid})
        serial = result.get("serial", "")[:16]
        return HTMLResponse(f'''
            <div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">
                ✓ Contract cert issued for <span class="font-mono">{emaid}</span>
                — serial: <span class="font-mono">{serial}…</span>
            </div>
            <script>showToast('Contract certificate issued', 'success');</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/pki/issue-user", response_class=HTMLResponse)
async def action_issue_user(request: Request):
    """Issue a user certificate."""
    form = await request.form()
    name = form.get("name", "")
    email = form.get("email", "")
    role = form.get("role", "operator")

    if not email:
        return HTMLResponse('<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Email required</div>')

    try:
        result = await api("/pki/issue/user", method="POST", json={"name": name, "email": email, "role": role})
        serial = result.get("serial", "")[:16]
        password = result.get("p12_password", "")
        return HTMLResponse(f'''
            <div class="p-4 bg-green-900/50 border border-green-800 rounded text-sm space-y-2">
                <div class="text-green-300 font-medium">✓ User certificate issued for {email}</div>
                <div class="text-gray-300">Serial: <span class="font-mono">{serial}…</span></div>
                <div class="p-2 bg-yellow-900/30 border border-yellow-800 rounded text-yellow-300">
                    ⚠️ PKCS#12 password (save this now — shown once):<br>
                    <span class="font-mono font-bold">{password}</span>
                </div>
                <a href="/pki/certificates/{result.get("serial","")}/download"
                   class="inline-block px-3 py-1 bg-gray-800 text-gray-300 rounded text-xs hover:bg-gray-700">
                   ⬇ Download .p12</a>
            </div>
            <script>showToast('User certificate issued', 'success');</script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.post("/action/pki/revoke", response_class=HTMLResponse)
async def action_revoke_cert(request: Request):
    """Revoke a certificate."""
    form = await request.form()
    serial = form.get("serial", "")
    reason = form.get("reason", "unspecified")

    if not serial:
        return HTMLResponse('<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Serial required</div>')

    try:
        await api("/pki/revoke", method="POST", json={"serial": serial, "reason": reason})
        return HTMLResponse(f'''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                ✓ Certificate revoked (reason: {reason})
            </div>
            <script>
                closeRevokeModal();
                showToast('Certificate revoked: {reason}', 'warning');
                // Refresh cert table
                const tbody = document.getElementById('cert-tbody');
                if (tbody) htmx.trigger(tbody, 'refresh');
            </script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@app.get("/ocpp", response_class=HTMLResponse)
async def ocpp_page(request: Request):
    """OCPP message viewer."""
    return templates.TemplateResponse(request, "ocpp.html", context={})


@app.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    """Security dashboard."""
    return templates.TemplateResponse(request, "security.html", context={})


@app.get("/features", response_class=HTMLResponse)
async def features_page(request: Request):
    """Feature flag toggle panel."""
    data = await api("/features")
    details = data.get("details", [])
    enabled = [f for f in details if f["enabled"]]
    disabled = [f for f in details if not f["enabled"]]
    return templates.TemplateResponse(request, "features.html", context={
        "active": "features",
        "enabled_flags": enabled,
        "disabled_flags": disabled,
        "total": len(details),
        "active_count": len(enabled),
    })


def _flag_card_html(flag: dict) -> str:
    """Render a single feature flag card as HTML (used for HTMX partial swap)."""
    key = flag["key"]
    label = flag.get("label", key)
    desc = flag.get("description", "")
    enabled = flag["enabled"]
    border_color = "border-l-green-500" if enabled else "border-l-gray-600"
    bg_color = "bg-gray-900" if enabled else "bg-gray-900/60"
    toggle_track = "bg-brand-green" if enabled else "bg-gray-700"
    toggle_dot_pos = "translate-x-5" if enabled else "translate-x-0"
    status_text = "Active" if enabled else "Disabled"
    status_color = "text-green-400" if enabled else "text-gray-500"

    return f'''<div id="flag-{key}" class="relative rounded-xl border-l-4 {border_color} {bg_color} border border-gray-800 p-4 flex flex-col gap-2 transition-all">
    <div class="flex items-start justify-between gap-3">
        <div class="flex-1 min-w-0">
            <div class="font-semibold text-gray-100 text-sm">{label}</div>
            <div class="font-mono text-xs text-gray-500 mt-0.5">{key}</div>
            {f'<div class="text-xs text-gray-400 mt-1">{desc}</div>' if desc else ''}
        </div>
        <button
            hx-post="/action/feature/toggle/{key}"
            hx-target="#flag-{key}"
            hx-swap="outerHTML"
            class="flex-shrink-0 mt-0.5 focus:outline-none"
            title="Toggle {label}">
            <div class="relative inline-flex items-center cursor-pointer">
                <div class="w-10 h-5 rounded-full {toggle_track} transition-colors"></div>
                <div class="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transform transition-transform {toggle_dot_pos}"></div>
            </div>
        </button>
    </div>
    <div class="text-xs {status_color} font-medium">{status_text}</div>
</div>'''


@app.post("/action/feature/toggle/{key}", response_class=HTMLResponse)
async def action_feature_toggle(key: str):
    """Toggle a feature flag via Core API — returns HTMX card partial."""
    try:
        result = await api(f"/features/{key}/toggle", method="POST")
        flag = await api(f"/features/{key}")
        return HTMLResponse(_flag_card_html(flag))
    except Exception as e:
        return HTMLResponse(f'<div id="flag-{key}" class="p-4 rounded-xl border border-red-800 bg-red-900/20 text-red-400 text-sm">Error: {e}</div>')


# ── HTMX Partials ────────────────────────────────────────────────────────

@app.get("/partials/charger-rows", response_class=HTMLResponse)
async def charger_rows(request: Request):
    """HTMX partial: charger table rows (auto-refresh)."""
    data = await api("/chargers?limit=100")
    return templates.TemplateResponse(request, "partials/charger_rows.html", context={
        "chargers": data.get("chargers", []),
    })


@app.get("/partials/session-rows", response_class=HTMLResponse)
async def session_rows(request: Request):
    """HTMX partial: session table rows (auto-refresh)."""
    data = await api("/sessions?limit=50")
    return templates.TemplateResponse(request, "partials/session_rows.html", context={
        "sessions": data.get("sessions", []),
    })


@app.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """HTMX partial: dashboard stats cards."""
    stats = await api("/sessions/stats/summary")
    chargers = await api("/chargers?limit=1")
    return templates.TemplateResponse(request, "partials/stats.html", context={
        "stats": stats,
        "charger_count": chargers.get("total", 0),
    })


# ── Remote Commands (HTMX POST) ─────────────────────────────────────────

@app.post("/action/start/{cp_id}", response_class=HTMLResponse)
async def action_start(cp_id: str, request: Request):
    result = await api(f"/chargers/{cp_id}/start", method="POST", json={"connector_id": 1})
    return HTMLResponse(f'<span class="text-green-400">✓ {result.get("status")}</span>')


@app.post("/action/stop/{cp_id}", response_class=HTMLResponse)
async def action_stop(cp_id: str, request: Request):
    result = await api(f"/chargers/{cp_id}/stop", method="POST")
    return HTMLResponse(f'<span class="text-yellow-400">⏹ {result.get("status")}</span>')


@app.post("/action/reset/{cp_id}", response_class=HTMLResponse)
async def action_reset(cp_id: str, request: Request):
    result = await api(f"/chargers/{cp_id}/reset", method="POST")
    return HTMLResponse(f'<span class="text-blue-400">↻ {result.get("status")}</span>')


# ── Onboarding (no auth — new users need this before they can log in) ───

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    """Certificate onboarding page — no authentication required."""
    return templates.TemplateResponse(request, "onboarding.html", context={})


@app.get("/onboarding/ca.crt")
async def download_root_ca(format: str = "der"):
    """
    Serve the Root CA certificate.

    ?format=der  (default) — DER (.cer) for macOS/iOS/Windows
    ?format=pem            — PEM (.crt) for Linux
    """
    import subprocess
    from fastapi.responses import Response

    pem_path = os.path.join(PKI_DATA_DIR, "root-ca.crt")

    if format == "pem":
        content = open(pem_path, "rb").read()
        return Response(
            content=content,
            media_type="application/x-pem-file",
            headers={"Content-Disposition": "attachment; filename=root-ca.crt"},
        )

    # DER (default) — macOS Keychain / Windows / iOS prefer DER
    result = subprocess.run(
        ["openssl", "x509", "-in", pem_path, "-outform", "DER"],
        capture_output=True, timeout=5,
    )
    return Response(
        content=result.stdout,
        media_type="application/x-x509-ca-cert",
        headers={"Content-Disposition": "attachment; filename=root-ca.cer"},
    )


@app.post("/onboarding/my-cert")
async def download_my_cert(request: Request):
    """
    Issue a fresh user certificate via the OCPP Core PKI API.

    Accepts form field `os_type`:
        macos          → modern PKCS#12 (.p12)
        macos-legacy   → legacy 3DES PKCS#12 (.p12)
        ios            → legacy 3DES PKCS#12 (.p12)
        windows        → modern PKCS#12 (.pfx, same bytes as .p12)
        windows-legacy → legacy 3DES PKCS#12 (.pfx)
        linux          → PEM bundle tar.gz (.tar.gz)
        android        → modern PKCS#12 (.p12)
        (default)      → modern PKCS#12 (.p12)

    Returns JSON with password + download_url.
    """
    from fastapi.responses import JSONResponse

    form = await request.form()
    email = form.get("email", "").strip().lower()
    os_type = form.get("os_type", "macos").strip().lower()

    if not email:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Email address is required")

    # Map os_type → cert_format and file extension hint
    _os_map = {
        "macos":          ("legacy",  "p12"),   # macOS Keychain prefers 3DES
        "macos-legacy":   ("legacy",  "p12"),
        "ios":            ("legacy",  "p12"),
        "windows":        ("legacy",  "pfx"),   # Universal compat — 3DES works everywhere
        "windows-legacy": ("legacy",  "pfx"),
        "linux":          ("pem",     "tar.gz"),
        "android":        ("modern",  "p12"),   # Android handles modern fine
    }
    cert_format, file_ext_hint = _os_map.get(os_type, ("modern", "p12"))

    # Issue a fresh cert via PKI API
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=30) as client:
            r = await client.post("/api/v1/pki/issue/user", json={
                "name": email.split("@")[0].replace(".", " ").title(),
                "email": email,
                "role": "operator",
                "validity_days": 365,
                "cert_format": cert_format,
            })
    except Exception as exc:
        logger.error("OCPP Core unreachable: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Internal system unreachable. Please try again later.")

    if r.status_code != 200:
        logger.error("PKI issue failed: %s %s", r.status_code, r.text)
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Could not create certificate. Contact your administrator.")

    data = r.json()
    password = data.get("p12_password", "")
    serial = data.get("serial", "")

    # Return JSON so the JS can show the password and offer the download link
    return JSONResponse({
        "email": email,
        "serial": serial,
        "os_type": os_type,
        "cert_format": cert_format,
        "file_ext": file_ext_hint,
        "download_url": f"/onboarding/cert-download/{serial}",
        "password": password,
    })


@app.get("/onboarding/cert-download/{serial}")
async def onboarding_cert_download(serial: str):
    """
    Stream the cert bundle (p12 / pfx / tar.gz) stored on disk by the PKI engine.
    Uses the .fmt file written alongside the bundle to determine type.
    """
    from fastapi.responses import Response
    import os as _os

    users_dir = os.path.join(PKI_DATA_DIR, "users")
    fmt_path = _os.path.join(users_dir, f"{serial}.fmt")

    # Determine format from saved metadata
    cert_format = "modern"
    if _os.path.exists(fmt_path):
        cert_format = open(fmt_path).read().strip()

    ext = "tar.gz" if cert_format == "pem" else "p12"
    bundle_path = _os.path.join(users_dir, f"{serial}.{ext}")

    if not _os.path.exists(bundle_path):
        from fastapi import HTTPException
        raise HTTPException(404, "Certificate not found")

    content = open(bundle_path, "rb").read()
    media = "application/x-tar" if cert_format == "pem" else "application/x-pkcs12"
    disposition = f'attachment; filename="ocpp-cert.{ext}"'

    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": disposition})


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
