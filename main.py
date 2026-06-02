"""
OpenCPO Admin — Network management dashboard.

FastAPI + Jinja2 + HTMX. No React, no npm, no build step.
Consumes OCPP Core via REST API only — no direct DB or Redis access.

Route modules live in routes/. Shared helpers in shared.py.
"""
import os
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from shared import APP_TITLE, verify_session, get_setup_status

# Route modules
from routes.dashboard import router as dashboard_router
from routes.chargers import router as chargers_router
from routes.sessions import router as sessions_router
from routes.tariffs import router as tariffs_router
from routes.tokens import router as tokens_router
from routes.groups import router as groups_router
from routes.drivers import router as drivers_router
from routes.receipts import router as receipts_router
from routes.pki import router as pki_router
from routes.security import router as security_router
from routes.onboarding import router as onboarding_router
from routes.ocpp import router as ocpp_router
from routes.settings import router as settings_router
from routes.ocpi_mgmt import router as ocpi_mgmt_router
from routes.docs import router as docs_router
from routes.network import router as network_router
from routes.skins import router as skins_router
from routes.auth import router as auth_router
from routes.setup import router as setup_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths that don't require authentication
_PUBLIC_PREFIXES = ("/login", "/logout", "/setup", "/static", "/favicon.ico")


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate requests. Redirects unauthenticated users to setup wizard
    if the platform hasn't been configured yet, or to login otherwise."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Allow public paths through unconditionally
        if any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        user = await verify_session(request)
        if user is None:
            logger.warning("AuthMiddleware: redirecting to /login from %s", path)
            return RedirectResponse("/login", status_code=302)

        request.state.user = user
        return await call_next(request)


class SetupCheckMiddleware(BaseHTTPMiddleware):
    """Check if platform setup is complete. Redirect to /setup if not.
    Runs BEFORE AuthMiddleware so that first-time visitors get the
    setup wizard instead of the login page."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Skip for static files, setup routes, login
        if any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # Check setup status — redirect ANYONE (authed or not) to /setup
        # if the platform hasn't been configured yet.
        try:
            status = await get_setup_status()
            if not status.get("complete", False):
                return RedirectResponse("/setup", status_code=302)
        except Exception:
            # If core is unreachable, let the request through
            pass

        return await call_next(request)


app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)
app.add_middleware(AuthMiddleware)
app.add_middleware(SetupCheckMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register all route modules
app.include_router(dashboard_router)
app.include_router(chargers_router)
app.include_router(sessions_router)
app.include_router(tariffs_router)
app.include_router(tokens_router)
app.include_router(groups_router)
app.include_router(drivers_router)
app.include_router(receipts_router)
app.include_router(pki_router)
app.include_router(security_router)
app.include_router(onboarding_router)
app.include_router(ocpp_router)
app.include_router(settings_router)
app.include_router(ocpi_mgmt_router)
app.include_router(docs_router)
app.include_router(network_router)
app.include_router(skins_router)
app.include_router(auth_router)
app.include_router(setup_router)


# ── Health Endpoint ──────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Liveness check — verifies the service is running and core API is reachable."""
    from shared import CORE_API
    import httpx
    core_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{CORE_API}/health")
            core_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok" if core_ok else "starting",
        "service": "cpo-admin",
        "core_api": "reachable" if core_ok else "waiting",
    }


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
