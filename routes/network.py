"""Network & Sites — Tailscale zero-trust network management page."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/network", response_class=HTMLResponse)
async def network_page(request: Request):
    """Render the network management page."""
    try:
        status = await api("/network/status")
    except Exception as exc:
        logger.warning("Failed to fetch network status: %s", exc)
        status = {
            "enabled": False,
            "configured": False,
            "connected": False,
            "backend_state": "error",
            "hostname": None,
            "tailscale_ip": None,
            "tailnet": None,
            "peer_count": 0,
        }

    try:
        nodes_data = await api("/network/nodes")
        nodes     = nodes_data.get("nodes", [])
        demo_mode = nodes_data.get("demo_mode", True)
        demo_msg  = nodes_data.get("message", "")
    except Exception as exc:
        logger.warning("Failed to fetch network nodes: %s", exc)
        nodes     = []
        demo_mode = True
        demo_msg  = "Could not reach Core API."

    return templates.TemplateResponse(request, "network.html", {
        "active":    "network",
        "status":    status,
        "nodes":     nodes,
        "demo_mode": demo_mode,
        "demo_msg":  demo_msg,
    })


# ── HTMX actions ─────────────────────────────────────────────────────────

@router.post("/action/network/generate-key", response_class=HTMLResponse)
async def action_generate_key(request: Request):
    """Generate a pre-auth key and return the install command snippet."""
    form = await request.form()
    site_type = form.get("site_type", "charger")

    try:
        result = await api("/network/add-site", method="POST", json={
            "site_type": site_type,
        })
        command    = result.get("command", "")
        auth_key   = result.get("auth_key", "")
        demo_mode  = result.get("demo_mode", True)
        demo_note  = ""
        if demo_mode:
            demo_note = (
                '<p class="text-xs text-yellow-400 mt-2">'
                'This is an example command. Configure your Tailscale API key in Settings to generate real keys.'
                '</p>'
            )

        html = f"""
<div class="space-y-3">
    <p class="text-sm text-gray-300">
        Run this command on your device. It installs Tailscale and connects it to your network.
        The key expires in 1 hour and can only be used once.
    </p>
    <div class="bg-gray-950 border border-gray-700 rounded-lg p-3 font-mono text-xs text-green-400 overflow-x-auto whitespace-pre-wrap break-all" id="install-cmd">{command}</div>
    <button type="button"
            onclick="navigator.clipboard.writeText(document.getElementById('install-cmd').textContent.trim())"
            class="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded text-gray-200 transition-colors">
        Copy command
    </button>
    {demo_note}
</div>
"""
        return HTMLResponse(html)

    except Exception as exc:
        return HTMLResponse(
            f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">'
            f'Failed to generate key: {str(exc)}'
            f'</div>'
        )


@router.post("/action/network/check-connected", response_class=HTMLResponse)
async def action_check_connected(request: Request):
    """Poll for newly connected nodes (used in wizard Step 3)."""
    try:
        nodes_data = await api("/network/nodes")
        nodes      = nodes_data.get("nodes", [])
        online     = [n for n in nodes if n.get("online")]
        count      = len(online)

        if count > 0:
            names = ", ".join(n.get("hostname", "unnamed") for n in online[:3])
            html = (
                f'<div class="p-4 bg-green-900/40 border border-green-700 rounded-lg">'
                f'<p class="text-green-300 font-semibold text-sm">Site connected.</p>'
                f'<p class="text-green-400 text-xs mt-1">'
                f'{count} node(s) online: {names}. '
                f'Your chargers at this location can now reach the OCPP server.'
                f'</p>'
                f'</div>'
            )
        else:
            html = (
                '<div class="flex items-center gap-2 text-gray-400 text-sm">'
                '<svg class="animate-spin h-4 w-4 text-brand-blue" fill="none" viewBox="0 0 24 24">'
                '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>'
                '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>'
                '</svg>'
                'Waiting for device to connect... Run the command above, then wait a few seconds.'
                '</div>'
            )
        return HTMLResponse(html)

    except Exception as exc:
        return HTMLResponse(
            f'<div class="text-yellow-400 text-sm">Could not check status: {str(exc)}</div>'
        )
