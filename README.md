# OCPP Admin

**Network management dashboard for OCPP Core.**

FastAPI + Jinja2 + HTMX. No React, no npm, no build step.

---

## Features

| Feature | Description |
|---------|-------------|
| 📊 **Dashboard** | Network overview — charger status, session counts, PKI health |
| 🔌 **Chargers** | List, filter, manage chargers; remote control (start/stop/reset/unlock) |
| ⚡ **Sessions** | Live session monitoring with enriched data (RFID, energy, duration) |
| 💰 **Tariffs** | Create and manage pricing configurations |
| 🏷️ **RFID / Tokens** | Token management, whitelist/blacklist, group assignment |
| 👥 **Groups** | Charger groups and load-balancing configuration |
| 🧾 **Invoices** | Session-based invoicing and export |
| 🔐 **PKI** | Certificate lifecycle dashboard — issue, revoke, inspect |
| 📡 **OCPP Messages** | Real-time OCPP event stream viewer |
| 🛡️ **Security** | Security events, alert history, PKI health |
| 🎛️ **Features** | Feature flags and runtime configuration |
| 🚀 **Onboarding** | Self-service PKI onboarding for operators (Root CA + personal cert) |

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

At minimum you need:

```bash
DB_PASS=your_db_password
OCPP_CORE_API=http://localhost:8000
```

### 3. Run

```bash
# With .env file (recommended)
python-dotenv run -- python main.py

# Or export vars manually
export DB_PASS=secret OCPP_CORE_API=http://localhost:8000
python main.py
```

Open http://localhost:8080

---

## Configuration Reference

All configuration is via environment variables (`.env` file supported via `python-dotenv`).

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_TITLE` | `OCPP Admin` | Application name shown in UI |
| `HOST` | `127.0.0.1` | Bind address for uvicorn |
| `PORT` | `8080` | Bind port |
| `DB_HOST` | `127.0.0.1` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `ocppcore` | PostgreSQL database name |
| `DB_USER` | `ocpp` | PostgreSQL user |
| `DB_PASS` | *(required)* | PostgreSQL password |
| `OCPP_CORE_API` | `http://localhost:8000` | OCPP Core REST API base URL |
| `PKI_DATA_DIR` | `../ocpp-core/data/pki` | Path to PKI data dir (contains `root-ca.crt` and `users/`) |

---

## Architecture

```
Browser ←─HTMX─→ CPO Admin (FastAPI)
                        │
                        ├─ PostgreSQL (sessions, tokens, tariffs, groups)
                        │
                        └─ OCPP Core API (chargers, PKI, OCPP commands)
```

- **OCPP Core** handles the WebSocket charger connections and exposes a REST API
- **CPO Admin** is a pure UI layer — it reads from Postgres and calls OCPP Core
- **HTMX** powers live updates via SSE and partial HTML swaps (no WebSocket from browser)
- **Tailwind CSS** (CDN) — no build step required
- `python main.py` and it runs

---

## Skin Customization

The UI supports swappable skins via the `skins/` directory.

```
skins/
  base/          ← generic default skin
  stroomlijnen/  ← example branded skin
```

Set `SKIN=base` (default) to use the generic skin. To use a custom skin:

1. Copy `skins/base/` to `skins/my-brand/`
2. Edit colors, logo, and CSS in your skin directory
3. Set `SKIN=my-brand` in your `.env`

The `stroomlijnen/` skin is included as a reference example.

---

## PKI / Onboarding

The `/onboarding` page provides self-service certificate distribution:

1. Operators visit `/onboarding`
2. They download the Root CA certificate and install it in their OS trust store
3. They enter their email to request a personal certificate (PKCS#12 or PEM)
4. The admin authenticates via mutual TLS with their personal cert

PKI operations are delegated to OCPP Core via `POST /api/v1/pki/issue/user`.

The PKI data directory (cert storage) is configured via `PKI_DATA_DIR`.

---

## Requirements

- Python 3.11+
- PostgreSQL 14+
- OCPP Core service running (for charger control and PKI)
- `openssl` CLI available (for DER conversion in onboarding)

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
