"""
OpenCPO Admin — Network management dashboard.

FastAPI + Jinja2 + HTMX. No React, no npm, no build step.
Consumes OCPP Core via REST API.

Route modules live in routes/. Shared helpers in shared.py.
"""
import os
import logging
from contextlib import asynccontextmanager

import asyncpg
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "ocppcore")
DB_USER = os.getenv("DB_USER", "ocpp")
DB_PASS = os.getenv("DB_PASS")
if not DB_PASS:
    raise RuntimeError("DB_PASS environment variable is required")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB pool on startup, close on shutdown."""
    logger.info("Connecting to PostgreSQL %s@%s:%s/%s", DB_USER, DB_HOST, DB_PORT, DB_NAME)
    app.state.db = await asyncpg.create_pool(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASS,
        min_size=2, max_size=10,
    )
    logger.info("DB pool ready")
    yield
    await app.state.db.close()
    logger.info("DB pool closed")


app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None, lifespan=lifespan)
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


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
