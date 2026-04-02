"""PKI certificate management — dashboard, cert table, issue, revoke."""
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from shared import api, templates, CORE_API

router = APIRouter()


def _parse_subject(subject: str) -> dict:
    """Extract CN, OU, email from an X.509 subject string."""
    parts = {}
    for match in re.finditer(r"(\w+)=([^,]+)", subject or ""):
        parts[match.group(1)] = match.group(2).strip()
    return parts


@router.get("/pki", response_class=HTMLResponse)
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


@router.get("/partials/pki/cert-rows", response_class=HTMLResponse)
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
        return HTMLResponse('<tr><td colspan="7" class="p-6 text-center text-red-400 text-sm">Failed to load certificates</td></tr>')

    certs = data.get("certificates", [])
    total = data.get("total", 0)
    pages = data.get("pages", 1)

    rows = ""
    for c in certs:
        serial_short = c["serial"][:8] + "…"
        subject_short = c["subject"][:40] + "…" if len(c.get("subject") or "") > 40 else (c.get("subject") or "—")
        cp = c.get("charge_point") or ""

        status_val = c.get("status", "")
        status_dot = {
            "active":   '<span class="inline-block w-2 h-2 rounded-full bg-green-400" title="Active"></span>',
            "revoked":  '<span class="inline-block w-2 h-2 rounded-full bg-red-400" title="Revoked"></span>',
            "expired":  '<span class="inline-block w-2 h-2 rounded-full bg-gray-500" title="Expired"></span>',
            "expiring": '<span class="inline-block w-2 h-2 rounded-full bg-yellow-400 animate-pulse" title="Expiring"></span>',
        }.get(status_val, '<span class="inline-block w-2 h-2 rounded-full bg-gray-600"></span>')

        type_val = c.get("type", "")
        type_icon = {"secc": "🔌", "contract": "📄", "user": "👤"}.get(type_val, "📋")

        subj = _parse_subject(c.get("subject", ""))
        cn = subj.get("CN", "")
        ou = subj.get("OU", "")

        if type_val == "user" and cn:
            name_part = cn.split("@")[0].replace(".", " ").title()
            identity = f'''<div class="text-gray-200 font-medium">{name_part}</div>
                <div class="text-gray-500 text-[11px]">{cn}</div>'''
            if ou:
                identity += f'<div class="text-gray-600 text-[10px]">{ou}</div>'
        elif type_val == "secc" and cp:
            identity = f'''<div class="text-gray-200 font-medium">{cp}</div>
                <div class="text-gray-500 text-[11px]">Charger certificate</div>'''
        elif type_val == "contract" and cn:
            identity = f'''<div class="text-gray-200 font-medium">{cn}</div>
                <div class="text-gray-500 text-[11px]">Contract / EMAID</div>'''
        else:
            identity = f'<div class="text-gray-400">{cn or "—"}</div>'

        expires_raw = c.get("not_after") or ""
        expires_date = expires_raw[:10]
        days_left = ""
        if expires_raw:
            try:
                exp = datetime.fromisoformat(expires_raw)
                now = datetime.now(timezone.utc)
                delta = (exp - now).days
                if delta < 0:
                    days_left = f'<span class="text-red-400 text-[10px]">{abs(delta)}d ago</span>'
                elif delta <= 30:
                    days_left = f'<span class="text-yellow-400 text-[10px]">{delta}d left</span>'
                elif delta <= 90:
                    days_left = f'<span class="text-gray-400 text-[10px]">{delta}d</span>'
                else:
                    days_left = f'<span class="text-gray-600 text-[10px]">{delta}d</span>'
            except Exception:
                pass

        issued = (c.get("issued_at") or "")[:10]

        can_revoke = status_val == "active"
        revoke_btn = f'''<button onclick="event.stopPropagation();openRevokeModal('{c["serial"]}', '{subject_short.replace("'","&apos;")}')"
            class="px-2 py-1 bg-red-900/50 hover:bg-red-800 text-red-300 rounded text-xs transition-colors">Revoke</button>''' if can_revoke else ""

        rows += f'''<tr class="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer text-sm"
            hx-get="/partials/pki/cert-detail/{c["serial"]}"
            hx-target="#cert-detail-panel"
            hx-swap="innerHTML"
            onclick="document.getElementById('cert-detail-panel').classList.remove('hidden')">
            <td class="p-3">{status_dot}</td>
            <td class="p-3 text-base">{type_icon}</td>
            <td class="p-3">{identity}</td>
            <td class="p-3 text-xs text-gray-500">{issued}</td>
            <td class="p-3 text-xs">
                <div class="text-gray-400">{expires_date}</div>
                {days_left}
            </td>
            <td class="p-3 font-mono text-[11px] text-gray-600" title="{c["serial"]}">{serial_short}</td>
            <td class="p-3">
                <div class="flex gap-1">
                    <a href="/pki/certificates/{c["serial"]}/download" onclick="event.stopPropagation()"
                       class="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-xs transition-colors">PEM</a>
                    {revoke_btn}
                </div>
            </td>
        </tr>'''

    if not rows:
        rows = '<tr><td colspan="7" class="p-6 text-center text-gray-500 text-sm">No certificates found</td></tr>'

    pagination = ""
    if pages > 1:
        prev_disabled = "opacity-40 cursor-not-allowed" if page <= 1 else ""
        next_disabled = "opacity-40 cursor-not-allowed" if page >= pages else ""
        prev_page = max(1, page - 1)
        next_page = min(pages, page + 1)
        qs = f"&status={status}&type={type}&charge_point={charge_point}&search={search}"
        pagination = f'''
        <tr class="border-t border-gray-800">
            <td colspan="7" class="p-3">
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


@router.get("/partials/pki/cert-detail/{serial}", response_class=HTMLResponse)
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


@router.get("/partials/pki/audit-log", response_class=HTMLResponse)
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


@router.get("/pki/certificates/{serial}/download")
async def download_cert(serial: str):
    """Proxy: download certificate PEM."""
    async with httpx.AsyncClient(base_url=CORE_API, timeout=10) as client:
        r = await client.get(f"/api/v1/pki/certificates/{serial}/download")
        r.raise_for_status()
    return Response(
        content=r.content,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": r.headers.get("content-disposition", f'attachment; filename="cert-{serial[:16]}.pem"')},
    )


# ── PKI Actions ───────────────────────────────────────────────────────────────

@router.post("/action/pki/issue-secc", response_class=HTMLResponse)
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
                htmx.trigger('#cert-tbody', 'refresh');
                setTimeout(() => document.getElementById('issue-panel').classList.add('hidden'), 2000);
                showToast('SECC certificate issued successfully', 'success');
            </script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@router.post("/action/pki/issue-contract", response_class=HTMLResponse)
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


@router.post("/action/pki/issue-user", response_class=HTMLResponse)
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


@router.post("/action/pki/revoke-account", response_class=HTMLResponse)
async def action_revoke_account(request: Request):
    """Revoke ALL active certificates for an account (email)."""
    form = await request.form()
    email = form.get("email", "").strip()
    reason = form.get("reason", "account_revoked").strip()

    if not email:
        return HTMLResponse('<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Email required</div>')

    try:
        result = await api("/pki/revoke-account", method="POST", json={"email": email, "reason": reason})
        count = result.get("count", 0)
        return HTMLResponse(f'''
            <div class="p-3 bg-yellow-900/50 border border-yellow-800 rounded text-yellow-300 text-sm">
                ✓ Revoked {count} certificate(s) for {email}
            </div>
            <script>
                showToast('Revoked {count} certs for {email}', 'warning');
                const tbody = document.getElementById('cert-tbody');
                if (tbody) htmx.trigger(tbody, 'refresh');
            </script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')


@router.post("/action/pki/revoke", response_class=HTMLResponse)
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
                const tbody = document.getElementById('cert-tbody');
                if (tbody) htmx.trigger(tbody, 'refresh');
            </script>
        ''')
    except Exception as e:
        return HTMLResponse(f'<div class="p-3 bg-red-900/50 border border-red-800 rounded text-red-300 text-sm">Error: {e}</div>')
