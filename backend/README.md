# backend/ (Dennis · branch `backend-dennis`)

Owns: **APIs** (`/ngao/v1`, including the USSD contract Louisa calls), **alert engine** wiring, **Wasiliana SMS** (outbound REST with API key + sender ID, delivery reports, inbound SMS once confirmed), **reply reader** (OCI GenAI → JSON), **dryer router**, action endpoints `/ngao/v1/jobs/*`.

USSD menus and the Wasiliana USSD callback live in [`ussd/`](../ussd/README.md) (Louisa, `ussd-louisa`). This folder implements the endpoints she calls; it does not render `CON`/`END` screens.

Writes to the shared ADB schema `NGAO` ([db/schema.sql](../db/schema.sql)); payloads and paths are fixed in [docs/API_CONTRACT.md](../docs/API_CONTRACT.md).

**Open decision D1:** Django/DRF service (`python-oracledb` → ADB, hosted on an OCI Always Free VM) **or** ORDS handlers + PL/SQL inside ADB. Suggested layout if Django:

```text
backend/
├── manage.py
├── ngao_core/        settings, urls (/api/v1)
├── sms/              Wasiliana REST send, delivery reports, inbound adapter
├── ussd_api/         /ngao/v1/ussd/* for the ussd/ service
├── reply_reader/     OCI GenAI prompt + JSON schema validation
├── alerts/           calls PKG_ALERT_ENGINE or Python engine
├── routing/          greedy dryer router
├── requirements.txt  optional: pytek-wasiliana
└── .env.example      WASILIANA_API_KEY, WASILIANA_SENDER_ID, USSD_SERVICE_TOKEN, WEBHOOK_SECRET, DB_DSN, OCI_* (no real values)
```

Outbound SMS uses the Wasiliana REST API (`WASILIANA_API_KEY` + `WASILIANA_SENDER_ID`). **`pytek-wasiliana`** is an optional Python client. Confirm the exact send URL and JSON against [docs.wasiliana.com](https://docs.wasiliana.com).

Delivery reports (`POST /sms/delivery`) and inbound SMS (`POST /sms/inbound`): **confirm exact field names against Wasiliana docs (docs.wasiliana.com)**. Inbound SMS forwarding is an open item. Keep one adapter and do not guess the keys.

If ORDS: put handler SQL in `backend/ords/` and PL/SQL packages in `db/`.
Run locally: `python -m venv .venv && pip install -r requirements.txt && python manage.py runserver`.
