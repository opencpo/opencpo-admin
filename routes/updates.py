"""Update panel routes — check version, trigger update, postpone, and history."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates, CORE_API, CORE_API_KEY
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/partials/update-status", response_class=HTMLResponse)
async def update_status_partial(request: Request):
    """HTMX partial: enhanced update status card for settings page."""
    try:
        status = await api("/admin/update/status", method="GET")
        current = status.get("current", "unknown")
        latest = status.get("latest", "unknown")
        needs_update = status.get("needs_update", False)
        script_available = status.get("script_available", True)
        changelog = status.get("changelog", "")
    except Exception as e:
        logger.warning("Update status check failed: %s", e)
        return templates.TemplateResponse(request, "partials/update_panel.html", {
            "current": "unknown",
            "latest": "unknown",
            "needs_update": False,
            "changelog": "",
            "error": "Update check unavailable — core API not reachable.",
        })

    if not script_available:
        return templates.TemplateResponse(request, "partials/update_panel.html", {
            "current": current,
            "latest": latest,
            "needs_update": False,
            "changelog": "",
            "error": "Update mechanism not available. Ensure the install directory is mounted and Docker socket is accessible.",
        })

    return templates.TemplateResponse(request, "partials/update_panel.html", {
        "current": current,
        "latest": latest,
        "needs_update": needs_update,
        "changelog": changelog,
    })


@router.get("/partials/update-banner", response_class=HTMLResponse)
async def update_banner_partial(request: Request):
    """HTMX partial: proactive update banner shown at top of every page."""
    try:
        status = await api("/admin/update/status", method="GET")
        current = status.get("current", "unknown")
        latest = status.get("latest", "unknown")
        needs_update = status.get("needs_update", False)
    except Exception as e:
        logger.warning("Update banner check failed: %s", e)
        # Return empty — no banner when core unreachable
        return HTMLResponse("")

    return templates.TemplateResponse(request, "_update_banner.html", {
        "current": current,
        "latest": latest,
        "needs_update": needs_update,
    })


@router.get("/partials/update-history", response_class=HTMLResponse)
async def update_history_partial(request: Request):
    """HTMX partial: activity history table (last 10 events)."""
    try:
        data = await api("/admin/update/history", method="GET")
        events = data.get("events", [])
    except Exception as e:
        logger.warning("Failed to load update history: %s", e)
        events = []

    if not events:
        return HTMLResponse("""
            <div class="text-xs text-gray-500 py-2 text-center border border-dashed border-gray-800 rounded-lg">
                No activity recorded yet.
            </div>
        """)

    rows = ""
    for ev in events:
        ts = ev.get("timestamp", "")
        ev_type = ev.get("type", "unknown")
        desc = ev.get("description", "")
        status = ev.get("status", "unknown")

        # Color-code the status badge
        if status == "success" or status == "completed":
            badge = '<span class="text-green-400">●</span>'
        elif status == "failed":
            badge = '<span class="text-red-400">●</span>'
        elif status == "running" or status == "in_progress":
            badge = '<span class="text-yellow-400 animate-pulse">●</span>'
        else:
            badge = '<span class="text-gray-500">●</span>'

        # Type icon
        type_icons = {
            "update": "⬆",
            "backup": "⚡",
            "restore": "↩",
            "check": "🔄",
            "postpone": "⏰",
        }
        icon = type_icons.get(ev_type, "•")

        rows += f"""
            <tr class="hover:bg-gray-800/30 transition-colors">
                <td class="py-2 pr-3 text-xs text-gray-500 font-mono whitespace-nowrap">{ts}</td>
                <td class="py-2 pr-3 text-xs">{icon} <span class="text-gray-300">{ev_type.capitalize()}</span></td>
                <td class="py-2 pr-3 text-xs text-gray-400">{desc}</td>
                <td class="py-2 text-xs text-right">{badge}</td>
            </tr>"""

    return HTMLResponse(f"""
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-gray-500 text-xs uppercase tracking-wider border-b border-gray-800">
                        <th class="text-left py-2 pr-3">Time</th>
                        <th class="text-left py-2 pr-3">Type</th>
                        <th class="text-left py-2 pr-3">Description</th>
                        <th class="text-right py-2">Status</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/50">
                    {rows}
                </tbody>
            </table>
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
            return HTMLResponse('<div class="text-green-400 text-sm whitespace-pre-wrap font-mono mt-1">✅ Update complete. Reloading... <script>setTimeout(() => location.reload(), 3000)</script></div>')
        else:
            err = data.get("error", data.get("log", "Unknown error"))[:500]
            return HTMLResponse(f'<div class="text-red-400 text-sm mt-1">Update failed: {err}</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="text-red-400 text-sm mt-1">Update failed: {e}</div>')


@router.post("/action/update/postpone", response_class=HTMLResponse)
async def action_update_postpone(request: Request):
    """Postpone the update notification for a given number of hours.
    
    Accepts 'hours' in form body (default: 24).
    Returns empty response (dismisses banner) or refreshes update panel.
    """
    form = await request.form()
    hours_raw = form.get("hours", "24")
    try:
        hours = int(str(hours_raw))
    except (ValueError, TypeError):
        hours = 24

    try:
        result = await api("/admin/update/postpone", method="POST", json_data={"hours": hours})
        if result.get("ok"):
            logger.info("Update postponed for %d hours", hours)
        else:
            logger.warning("Postpone API returned not-ok: %s", result)
    except Exception as e:
        logger.warning("Failed to postpone update: %s", e)

    # Returning empty HTML effectively dismisses the banner / refreshes the panel
    # If this was called from the banner, it replaces the banner with nothing.
    # If from the settings panel, the JS triggers a refresh via hx-get.
    return HTMLResponse("")
