"""Skin gallery — browse, preview, and activate charge app skins."""
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from shared import templates

router = APIRouter()
logger = logging.getLogger(__name__)

CHARGE_APP_DIR = os.getenv(
    "CHARGE_APP_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "stroomlijnen-charge-app"),
)


def _skins_dir() -> Path:
    return Path(CHARGE_APP_DIR) / "skins"


def _read_active_skin() -> str:
    """Read current SKIN= from charge app .env file."""
    env_file = Path(CHARGE_APP_DIR) / ".env"
    if not env_file.exists():
        return "default"
    for line in env_file.read_text().splitlines():
        m = re.match(r"^SKIN\s*=\s*(.+)$", line.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return "default"


def _load_skins() -> list[dict]:
    """Scan skins/ directory and load metadata for each skin."""
    skins_root = _skins_dir()
    if not skins_root.is_dir():
        return []

    skins = []
    for entry in sorted(skins_root.iterdir()):
        if not entry.is_dir():
            continue
        skin_json = entry / "skin.json"
        if not skin_json.exists():
            continue
        try:
            meta = json.loads(skin_json.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Collect preview images
        previews = []
        previews_dir = entry / "previews"
        if previews_dir.is_dir():
            for img in sorted(previews_dir.iterdir()):
                if img.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    previews.append(img.name)

        has_design = (entry / "DESIGN.md").exists()
        css_path = entry / "static" / "style.css"
        css_size = css_path.stat().st_size if css_path.exists() else 0

        skins.append({
            "id": entry.name,
            "name": meta.get("name", entry.name),
            "version": meta.get("version", "1.0"),
            "mode": meta.get("mode", "dark"),
            "colors": meta.get("colors", {}),
            "fonts": meta.get("fonts", {}),
            "previews": previews,
            "has_design": has_design,
            "css_size": css_size,
        })

    return skins


@router.get("/skins", response_class=HTMLResponse)
async def skins_gallery(request: Request):
    """Render the skin gallery page."""
    skins = _load_skins()
    active = _read_active_skin()
    return templates.TemplateResponse(request, "skins.html", {
        "active": "skins",
        "skins": skins,
        "active_skin": active,
        "total": len(skins),
    })


@router.get("/skins/{name}/preview/{filename}")
async def skin_preview_image(name: str, filename: str):
    """Serve a skin preview image from the charge app skins directory."""
    # Sanitize path components
    if ".." in name or ".." in filename or "/" in name or "/" in filename:
        return HTMLResponse("Not found", status_code=404)
    path = _skins_dir() / name / "previews" / filename
    if not path.exists() or not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path, media_type="image/png")


@router.post("/action/skins/activate/{name}", response_class=HTMLResponse)
async def action_activate_skin(name: str):
    """Set the active skin by updating the charge app .env file."""
    # Validate skin exists
    skin_dir = _skins_dir() / name
    if not skin_dir.is_dir() or not (skin_dir / "skin.json").exists():
        return HTMLResponse(_err(f"Skin '{name}' not found"))

    env_file = Path(CHARGE_APP_DIR) / ".env"
    try:
        if env_file.exists():
            lines = env_file.read_text().splitlines()
            found = False
            new_lines = []
            for line in lines:
                if re.match(r"^SKIN\s*=", line.strip()):
                    new_lines.append(f"SKIN={name}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"SKIN={name}")
            env_file.write_text("\n".join(new_lines) + "\n")
        else:
            env_file.write_text(f"SKIN={name}\n")

        logger.info("Activated skin: %s", name)
        return HTMLResponse(_ok(f"Skin '{name}' activated. Restart the charge app to apply."))
    except Exception as exc:
        return HTMLResponse(_err(f"Failed to activate: {exc}"))


def _ok(msg: str) -> str:
    return f'<div class="p-3 bg-green-900/50 border border-green-800 rounded text-green-300 text-sm">✓ {msg}</div>'


def _err(msg: str) -> str:
    return f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">✗ {msg}</div>'
