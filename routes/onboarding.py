"""Certificate onboarding — no auth required for new users."""
import os
import subprocess

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from shared import api, templates, CORE_API, PKI_DATA_DIR, logger

router = APIRouter()


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    """Certificate onboarding page — no authentication required."""
    return templates.TemplateResponse(request, "onboarding.html", context={})


@router.get("/onboarding/ca.crt")
async def download_root_ca(format: str = "der"):
    """
    Serve the Root CA certificate.

    ?format=der  (default) — DER (.cer) for macOS/iOS/Windows
    ?format=pem            — PEM (.crt) for Linux
    """
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


@router.post("/onboarding/my-cert")
async def download_my_cert(request: Request):
    """
    Issue a fresh user certificate via the OCPP Core PKI API.

    Accepts form field `os_type`:
        macos / macos-legacy / ios / windows / windows-legacy / linux / android
    Returns JSON with password + download_url.
    """
    form = await request.form()
    email = form.get("email", "").strip().lower()
    os_type = form.get("os_type", "macos").strip().lower()

    if not email:
        raise HTTPException(status_code=400, detail="Email address is required")

    _os_map = {
        "macos":          ("legacy",  "p12"),
        "macos-legacy":   ("legacy",  "p12"),
        "ios":            ("legacy",  "p12"),
        "windows":        ("legacy",  "pfx"),
        "windows-legacy": ("legacy",  "pfx"),
        "linux":          ("pem",     "tar.gz"),
        "android":        ("modern",  "p12"),
    }
    cert_format, file_ext_hint = _os_map.get(os_type, ("modern", "p12"))

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
        raise HTTPException(status_code=503, detail="Internal system unreachable. Please try again later.")

    if r.status_code != 200:
        logger.error("PKI issue failed: %s %s", r.status_code, r.text)
        raise HTTPException(status_code=502, detail="Could not create certificate. Contact your administrator.")

    data = r.json()
    password = data.get("p12_password", "")
    serial = data.get("serial", "")

    return JSONResponse({
        "email": email,
        "serial": serial,
        "os_type": os_type,
        "cert_format": cert_format,
        "file_ext": file_ext_hint,
        "download_url": f"/onboarding/cert-download/{serial}",
        "password": password,
    })


@router.get("/onboarding/cert-download/{serial}")
async def onboarding_cert_download(serial: str):
    """Stream the cert bundle (p12 / pfx / tar.gz) stored on disk by the PKI engine."""
    users_dir = os.path.join(PKI_DATA_DIR, "users")
    fmt_path = os.path.join(users_dir, f"{serial}.fmt")

    cert_format = "modern"
    if os.path.exists(fmt_path):
        cert_format = open(fmt_path).read().strip()

    ext = "tar.gz" if cert_format == "pem" else "p12"
    bundle_path = os.path.join(users_dir, f"{serial}.{ext}")

    if not os.path.exists(bundle_path):
        raise HTTPException(404, "Certificate not found")

    content = open(bundle_path, "rb").read()
    media = "application/x-tar" if cert_format == "pem" else "application/x-pkcs12"
    disposition = f'attachment; filename="ocpp-cert.{ext}"'

    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": disposition})
