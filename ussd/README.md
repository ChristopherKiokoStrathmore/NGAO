# ussd/ (Louisa · branch `ussd-louisa`)

Owns the **Wasiliana USSD callback**, the menu state machine, and `USSD_SESSIONS`.

Wasiliana is callback-only: they POST each session to our callback URL. This service replies with `text/plain` prefixed `CON ` (continue) or `END ` (end) within about 10 seconds. No OCI GenAI call on this path.

It does **not** send SMS and it does **not** write `SUBSCRIBERS`, `MESSAGES`, or `REPORTS`. Those go through the backend contract in [docs/API_CONTRACT.md §5](../docs/API_CONTRACT.md#5-ussd-to-backend-contract):

| Call | When |
|---|---|
| `POST /ngao/v1/ussd/register` | Menu 1 finishes with consent |
| `POST /ngao/v1/ussd/report` | Menu 2 collects a structured report |
| `GET /ngao/v1/ussd/ward-status` | Menu 3, "Hali ya kata yangu" |
| `POST /ngao/v1/ussd/unsubscribe` | The farmer stops |

Auth: `Authorization: Bearer <USSD_SERVICE_TOKEN>`. Each hop also upserts `USSD_SESSIONS` (`session_id`, `phone`, `last_text`, `updated_at`).

**Confirm exact USSD request field names against Wasiliana docs ([docs.wasiliana.com](https://docs.wasiliana.com)).** Parse them in one adapter. The handler needs a session id, the phone number, and the text entered so far.

```text
ussd/
├── README.md
├── callback.py       POST /ussd → CON / END (Flask), GET /healthz
├── menus.py          Jiandikishe, Ripoti, Hali, Lugha, Acha: state machine + all screen text (sw/en)
├── wasiliana.py      request adapter (field names: assumption until confirmed, overridable by env)
├── backend.py        §5 client (BackendClient) + DevBackend stub for local runs
├── store.py          USSD_SESSIONS upsert; read-only SUBSCRIBERS.preferred_lang and WARDS
├── simulate.py       walk the menus in a terminal like a feature phone
├── tests/            pytest: adapter + every menu path
├── requirements.txt
└── .env.example      USSD_PUBLIC_URL, USSD_SERVICE_TOKEN, BACKEND_BASE_URL, DB_* (no real values)
```

The callback must be a public HTTPS URL (ngrok for the demo, or the host from decision D2). Point that URL at Wasiliana's USSD service settings.

## Menu tree

```text
(new number) Chagua lugha / Choose language → 1 Kiswahili · 2 English      → POST /ussd/language
MvuaSmart
├── 1 Jiandikishe / Register → role → county → ward → consent              → POST /ussd/register
├── 2 Ripoti / Report → 1 wet bags (count) · 2 sick/dead animals (count)
│                      · 3 flooding · 4 water point dry                    → POST /ussd/report
│                      · 5 other → "send us an SMS" (no call)
├── 3 Hali ya kata yangu / My ward status                                  → GET  /ussd/ward-status
├── 4 Lugha / Language → choose again, continue in the new language        → POST /ussd/language
└── 5 Acha ujumbe / Stop alerts → confirm                                  → POST /ussd/unsubscribe
```

Each screen is rebuilt from the whole input path (`1*2*20`) on every hop. An invalid entry shows the same screen again with "Chaguo si sahihi / Invalid choice". Long county and ward lists page with `98`. A backend error ends the session with `Samahani, jaribu tena.` / `Sorry, please try again.`

## Run

```bash
cd ussd
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q tests          # all menu paths
.venv/bin/python simulate.py +254712345678   # try it in the terminal
```

Without `BACKEND_BASE_URL` the service uses `DevBackend` (logs calls, writes nothing). Without `DB_DSN` it uses an in-memory store with a **dev ward list whose ids do not match `WARDS`**.

For the live callback, set the env vars from `.env.example`, then:

```bash
.venv/bin/gunicorn -w 1 --threads 8 -b 0.0.0.0:8080 callback:app
ngrok http 8080        # register https://<ngrok-host>/ussd (add ?k=<WEBHOOK_SECRET> if set) with Wasiliana
```

Run **one worker process**. Whether a session started with the language prompt is kept in process memory, since `USSD_SESSIONS` has no column for it.

## Open items

- **Wasiliana field names.** `wasiliana.py` assumes `sessionId`, `phoneNumber`, `serviceCode`, and a cumulative `text` joined by `*`. Confirm them against docs.wasiliana.com or a logged live request, then override with `WASILIANA_FIELD_*` and `WASILIANA_TEXT_MODE`.
- **Is this number new?** §5 has no lookup endpoint, so this service reads `SUBSCRIBERS.preferred_lang` read-only. If the team prefers, add `GET /ussd/subscriber?phone=` to §5 and swap it in `store.py`.
- **Swahili copy** in `menus.py` needs a native speaker's check.
