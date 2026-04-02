"""Security dashboard, feature flags, and OCPP message viewer."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()


@router.get("/ocpp", response_class=HTMLResponse)
async def ocpp_page(request: Request):
    """OCPP message viewer."""
    return templates.TemplateResponse(request, "ocpp.html", context={})


@router.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    """Security dashboard."""
    return templates.TemplateResponse(request, "security.html", context={})


@router.get("/features", response_class=HTMLResponse)
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


@router.post("/action/feature/toggle/{key}", response_class=HTMLResponse)
async def action_feature_toggle(key: str):
    """Toggle a feature flag via Core API — returns HTMX card partial."""
    try:
        await api(f"/features/{key}/toggle", method="POST")
        flag = await api(f"/features/{key}")
        return HTMLResponse(_flag_card_html(flag))
    except Exception as e:
        return HTMLResponse(f'<div id="flag-{key}" class="p-4 rounded-xl border border-red-800 bg-red-900/20 text-red-400 text-sm">Error: {e}</div>')
