"""Update panel routes — check version and trigger update."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates, CORE_API, CORE_API_KEY
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/partials/update-status", response_class=HTMLResponse)
async def update_status_partial(request: Request):
    """HTMX partial: update status card for settings page."""
    try:
        status = await api("/admin/update/status", method="GET")
        current = status.get("current", "unknown")
        latest = status.get("latest", "unknown")
        needs_update = status.get("needs_update", False)
        script_available = status.get("script_available", True)
    except Exception as e:
        logger.warning("Update status check failed: %s", e)
        return HTMLResponse("""
            <div class="p-4 text-sm text-gray-400">
                Update check unavailable — core API not reachable.
            </div>
        """)

    if not script_available:
        return HTMLResponse(f"""
            <div class="p-4 text-sm text-gray-400">
                Update mechanism not available. Ensure the install directory
                is mounted into the core container and Docker socket is accessible.
                <br><span class="text-xs">Current: {current}</span>
            </div>
        """)

    if needs_update:
        return HTMLResponse(f"""
            <div class="p-4">
                <div class="bg-yellow-900/30 border border-yellow-800 rounded-lg p-4 mb-3">
                    <div class="flex items-center gap-3">
                        <span class="text-2xl">🔄</span>
                        <div>
                            <div class="text-sm font-semibold text-yellow-200">Update Available</div>
                            <div class="text-xs text-gray-400 mt-1">
                                {current} → <span class="text-yellow-300 font-mono">{latest}</span>
                            </div>
                        </div>
                    </div>
                </div>
                <button hx-post="/action/update/run"
                        hx-target="#update-result"
                        hx-swap="innerHTML"
                        hx-confirm="Update to {latest}? The platform will restart. Continue?"
                        class="px-5 py-2 bg-yellow-700 hover:bg-yellow-600 text-white font-bold rounded-lg text-sm transition-colors">
                    ⬆ Update Now
                </button>
                <div id="update-result" class="mt-3"></div>
            </div>
        """)
    else:
        return HTMLResponse(f"""
            <div class="p-4">
                <div class="flex items-center gap-3 mb-2">
                    <span class="text-lg">✅</span>
                    <div>
                        <div class="text-sm font-semibold text-green-300">Up to Date</div>
                        <div class="text-xs text-gray-500 mt-0.5">
                            Running <span class="font-mono text-gray-400">{current}</span>
                        </div>
                    </div>
                </div>
                <button hx-post="/action/update/check"
                        hx-target="#update-result"
                        hx-swap="innerHTML"
                        class="text-xs text-brand-blue hover:underline mt-1">
                    Check for updates
                </button>
                <div id="update-result" class="mt-2"></div>
            </div>
        """)


@router.post("/action/update/check", response_class=HTMLResponse)
async def action_update_check(request: Request):
    """Re-check update status."""
    try:
        status = await api("/admin/update/status", method="GET")
        latest = status.get("latest", "unknown")
        current = status.get("current", "unknown")
        needs = status.get("needs_update", False)
        if needs:
            return HTMLResponse(f'<div class="text-yellow-300 text-sm mt-1">Update available: {current} → <b>{latest}</b></div>')
        return HTMLResponse(f'<div class="text-green-400 text-sm mt-1">Already at latest ({latest})</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="text-red-400 text-sm mt-1">Check failed: {e}</div>')


@router.post("/action/update/run", response_class=HTMLResponse)
async def action_update_run(request: Request):
    """Trigger update."""
    headers = {}
    if CORE_API_KEY:
        headers["X-API-Key"] = CORE_API_KEY
    try:
        async with httpx.AsyncClient(base_url=CORE_API, timeout=600) as client:
            r = await client.post("/api/v1/admin/update/run", headers=headers)
            data = r.json()
        if data.get("ok"):
            log = data.get("log", "")
            # Truncate log to last 1000 chars
            if len(log) > 1000:
                log = "..." + log[-1000:]
            return HTMLResponse(f'<div class="text-green-400 text-sm whitespace-pre-wrap font-mono mt-1">✅ Update complete. Reloading... <script>setTimeout(() => location.reload(), 3000)</script></div>')
        else:
            err = data.get("error", data.get("log", "Unknown error"))[:500]
            return HTMLResponse(f'<div class="text-red-400 text-sm mt-1">Update failed: {err}</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="text-red-400 text-sm mt-1">Update failed: {e}</div>')
