"""
OpenCPO Admin — Network management dashboard.

FastAPI + Jinja2 + HTMX. No React, no npm, no build step.
Consumes OCPP Core via REST API only — no direct DB or Redis access.

Route modules live in routes/. Shared helpers in shared.py.
"""
import os
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shared import APP_TITLE

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)
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


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
