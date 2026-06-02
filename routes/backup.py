"""Backup and restore API proxy routes — HTMX endpoints for the backup UI."""
import html as _html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from shared import api, templates

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/partials/backup-panel", response_class=HTMLResponse)
async def backup_panel_partial(request: Request):
    """HTMX partial: backup & restore panel for settings page."""
    try:
        data = await api("/admin/backups", method="GET")
        backups = data.get("backups", [])
    except Exception as e:
        logger.warning("Failed to load backups: %s", e)
        backups = []

    return templates.TemplateResponse(request, "partials/backup_panel.html", {
        "backups": backups,
    })


@router.post("/action/backup/create", response_class=HTMLResponse)
async def action_backup_create(request: Request):
    """Trigger a backup via the core API."""
    try:
        result = await api("/admin/backups", method="POST", json_data={})
        if result.get("ok"):
            return HTMLResponse(_ok("Backup created successfully. Refreshing list...") +
                                '<script>setTimeout(() => htmx.trigger("#backup-panel", "load"), 1500)</script>')
        else:
            return HTMLResponse(_err(result.get("error", "Backup failed")))
    except Exception as e:
        logger.warning("Backup creation failed: %s", e)
        return HTMLResponse(_err(f"Backup failed: {str(e)}"))


@router.post("/action/backup/restore", response_class=HTMLResponse)
async def action_backup_restore(request: Request):
    """Restore a backup via the core API."""
    form = await request.form()
    backup_id = form.get("backup_id", "").strip()
    if not backup_id:
        return HTMLResponse(_err("No backup ID provided"))

    try:
        result = await api(f"/admin/backups/{backup_id}/restore", method="POST")
        if result.get("ok"):
            return HTMLResponse(_ok(f"Restore initiated. The platform will reload shortly.") +
                                '<script>setTimeout(() => location.reload(), 3000)</script>')
        else:
            return HTMLResponse(_err(result.get("error", "Restore failed")))
    except Exception as e:
        logger.warning("Backup restore failed: %s", e)
        return HTMLResponse(_err(f"Restore failed: {str(e)}"))


@router.post("/action/backup/delete/{backup_id}", response_class=HTMLResponse)
async def action_backup_delete(request: Request, backup_id: str):
    """Delete a backup via the core API."""
    try:
        result = await api(f"/admin/backups/{backup_id}", method="DELETE")
        if result.get("ok"):
            return HTMLResponse(_ok("Backup deleted. Refreshing list...") +
                                '<script>setTimeout(() => htmx.ajax("GET", "/partials/backup-panel", {target: "#backup-panel", swap: "outerHTML"}), 500)</script>')
        else:
            return HTMLResponse(_err(result.get("error", "Delete failed")))
    except Exception as e:
        logger.warning("Backup delete failed: %s", e)
        return HTMLResponse(_err(f"Delete failed: {str(e)}"))


@router.post("/action/backup/upload", response_class=HTMLResponse)
async def action_backup_upload(request: Request):
    """Import/upload a backup file via the core API."""
    form = await request.form()
    backup_file = form.get("backup_file")

    if not backup_file or not hasattr(backup_file, "filename") or not backup_file.filename:
        return HTMLResponse(_err("No file selected"))

    try:
        import httpx
        from shared import CORE_API, CORE_API_KEY

        # Read file bytes
        content = await backup_file.read()
        filename = backup_file.filename

        # Upload to core API
        headers = {}
        if CORE_API_KEY:
            headers["X-API-Key"] = CORE_API_KEY

        async with httpx.AsyncClient(base_url=CORE_API, timeout=120) as client:
            files = {"backup_file": (filename, content, "application/octet-stream")}
            r = await client.post("/api/v1/admin/backups/upload", files=files, headers=headers)
            result = r.json()

        if result.get("ok"):
            return HTMLResponse(_ok(f"Backup '{_html.escape(filename)}' imported. Refreshing list...") +
                                '<script>setTimeout(() => htmx.ajax("GET", "/partials/backup-panel", {target: "#backup-panel", swap: "outerHTML"}), 1000)</script>')
        else:
            return HTMLResponse(_err(result.get("error", "Import failed")))
    except Exception as e:
        logger.warning("Backup upload failed: %s", e)
        return HTMLResponse(_err(f"Import failed: {str(e)}"))


# ── UI helpers ───────────────────────────────────────────────────────────

def _ok(msg: str) -> str:
    return f'<div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">✓ {_html.escape(msg)}</div>'


def _err(msg: str) -> str:
    return f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">✗ {_html.escape(msg)}</div>'
