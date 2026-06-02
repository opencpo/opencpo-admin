"""Tariff configuration — pricing management."""
import html as _html
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()


@router.get("/tariffs", response_class=HTMLResponse)
async def tariffs_page(request: Request):
    """Tariff configuration — manage pricing structures."""
    from datetime import datetime, timezone
    try:
        tariff_data = await api("/tariffs")
        tariffs = tariff_data.get("tariffs", [])
    except Exception:
        tariffs = []
    try:
        charger_data = await api("/chargers?limit=100")
        chargers = charger_data.get("chargers", [])
    except Exception:
        chargers = []
    now_iso = datetime.now(timezone.utc).isoformat()
    return templates.TemplateResponse(request, "tariffs.html", context={
        "tariffs": tariffs,
        "chargers": chargers,
        "now_iso": now_iso,
    })


@router.get("/partials/tariff/edit/{tariff_id}", response_class=HTMLResponse)
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
        <h3 class="font-semibold text-gray-100">✏️ Edit {_html.escape(t["name"])}</h3>
        <button onclick="closeModal('modal-edit')" class="text-gray-500 hover:text-gray-300 text-xl">✕</button>
    </div>
    <form hx-post="/action/tariff/update/{t["id"]}"
          hx-target="#edit-result"
          hx-swap="innerHTML"
          class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
            <div class="col-span-2">
                <label class="block text-xs text-gray-400 mb-1">Name</label>
                <input name="name" value="{_html.escape(t.get("name",""))}" required
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


@router.post("/action/tariff/create", response_class=HTMLResponse)
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
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {_html.escape(str(e))}</div>')


@router.post("/action/tariff/update/{tariff_id}", response_class=HTMLResponse)
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
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {_html.escape(str(e))}</div>')


@router.post("/action/tariff/delete/{tariff_id}", response_class=HTMLResponse)
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
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {_html.escape(str(e))}</div>')
