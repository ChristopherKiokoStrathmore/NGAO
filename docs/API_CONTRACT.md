# API & Data Contract (frontend ↔ backend)

This is the agreement that lets **Chris (APEX, `frontend-chris`)**, **Dennis (backend,
`backend-dennis`)**, **Trevor (data, `data-modelling-trevor`)**, **Louisa (USSD, `ussd-louisa`)**, and **Esther — Slides (`slides-esther`)**
build in parallel. **Change it only by PR to `main`, and tag the owners whose folders the change touches.**

```mermaid
flowchart LR
  WA["Wasiliana"] -- "USSD session POST" --> US["ussd/ (Louisa)"]
  US -- "plain text CON/END" --> WA
  US -- "§5 /ngao/v1/ussd" --> BE["Backend (Dennis)"]
  WA -- "SMS REST + callbacks" --> BE
  BE -- "§2 REST /ngao/v1" --> X["Demo controls · tests · router"]
  BE -- "writes §1.1 tables" --> DB[("ADB schema NGAO")]
  US -- "writes USSD_SESSIONS" --> DB
  DB -- "§1.2 V_* views" --> APEX["APEX app (Chris)"]
  APEX -- "§1.3 writes (review, demo)" --> DB
```

Four layers:
1. **Database contract** (primary): tables the backend writes, views APEX reads, sessions Louisa writes.
2. **REST API** `/ngao/v1`: actions (run scoring, send alerts, plan routes) and read endpoints for tests and the PWA.
3. **Wasiliana**: USSD callback to `ussd/`, outbound SMS from the backend, delivery reports and inbound SMS once the field names are confirmed.
4. **USSD to backend** (§5): Louisa calls Dennis for registration, reports, ward status, and unsubscribe. She does not send SMS.

## 0. Conventions

| Topic | Rule |
|---|---|
| Schema | `NGAO`. Tables UPPER_SNAKE plural (`RISK_SCORES`). Views prefixed `V_`. Packages `PKG_`. |
| Columns | snake_case; PK `<entity>_id`; timestamps `*_at` (`TIMESTAMP WITH TIME ZONE`, stored UTC); dates `*_date`. |
| Enums | Uppercase strings with CHECK constraints: `decision IN ('ACT','WATCH','ABSTAIN')`. |
| Phones | E.164 `+2547XXXXXXXX`. |
| JSON | snake_case keys, ISO-8601 times with offset (`2026-10-15T06:00:00+03:00`), probabilities 0–1, `confidence_pct` 0–100. |
| Versioning | URL prefix `/ngao/v1`. Breaking change → `/v2`; additive fields are non-breaking. Views: add columns freely, **never rename/drop** without a PR. |
| Alert codes | `A1`–`A5`, `B1`–`B4`, `C1`–`C3` (see [ARCHITECTURE §5](ARCHITECTURE.md#alert-catalogue-seed-rows-for-alert_types)). |
| Services | `FARM` (MvuaSmart), `HERD` (Mifugo), `HEALTH` (Afya). |

## 1. Database contract

### 1.1 Tables the backend (Dennis) writes

| Table | Written when | Required columns |
|---|---|---|
| `SUBSCRIBERS` | USSD registration via §5, language choice, STOP, SMS `LUGHA`/`LANG` | phone, preferred_lang; ward_id, role, consent_at, status once registered |
| `FARMS` / `HERDS` | Registration (optional detail) | subscriber_id, ward_id, crop/species |
| `MESSAGES` | Every inbound SMS (IN) and every send/DLR update (OUT) | direction, channel, phone, body, provider_msg_id, status |
| `REPORTS` | Reply reader / USSD menu 2 via §6 | message_id, ward_id, report_type, report_count, payload, ai_confidence, review_status |
| `ROUTES`, `ROUTE_STOPS`, `BOOKINGS` | Dryer router 18:00 / confirmations | see schema |
| `ALERTS` | Alert engine (if owned by backend; else PL/SQL) | score_id, subscriber_id, alert_type, status |

Louisa (`ussd/`) writes `USSD_SESSIONS` (session_id, phone, last_text, updated_at) on each hop. She does not write `SUBSCRIBERS`, `MESSAGES`, or `REPORTS`.

Trevor (`data/`) writes `WARDS`, `WARD_FEATURES_DAILY`, `FORECASTS`, `RISK_SCORES`.

### 1.2 Views APEX (Chris) reads

| View | APEX page | Key columns |
|---|---|---|
| `V_WARD_RISK_MAP` | Ward risk map | ward_id, ward_name, county, boundary_geojson, service, alert_type, score_date, probability, confidence_pct, decision, abstain_reason, colour |
| `V_WET_MAIZE_POINTS` | Wet maize & dryer planner | point_id, point_name, ward_id, lat, lon, wet_bags_3d, p_heavy_rain_48h, aflatoxin_class, urgency |
| `V_DRYER_PLAN` | Wet maize & dryer planner | route_date, dryer_id, stop_order, point_name, eta, planned_bags, bookings_confirmed |
| `V_REPORTS_INBOX` | Reports inbox | report_id, received_at, ward_name, report_type, report_count, ai_confidence, review_status, lat, lon (ward centroid) |
| `V_REVIEW_QUEUE` | Reports inbox (review tab) | report_id, raw_text, parsed_payload, ai_confidence, reason |
| `V_VET_PRIORITY` | Vet priority list | ward_id, ward_name, rvf_probability, decision, livestock_tlu, sick_reports_7d, rank |
| `V_HEALTH_WATCH` | Health watch list | ward_id, ward_name, cholera_index, rvf_human_decision, flood_flag, neighbour_outbreak (aggregates only) |
| `V_DROUGHT_GRAZING` | Drought & grazing | ward_id, vci3m_now, vci3m_forecast_6w, drought_class, option_id, area_name, score, weekly_tlu_cap, tlu_assigned |
| `V_SCORECARD` | Public scorecard | alert_type, period, alerts_sent, hits, false_alarms, hit_rate, false_alarm_rate, avg_lead_days, brier_skill |
| `V_CALIBRATION` | Scorecard chart | alert_type, prob_bin, predicted, observed, n |
| `V_RVF_REPLAY` | Garissa 2006 replay | replay_date, ward_id, ward_name, rvf_probability, decision, first_case_date, vaccination_date |
| `V_KPI` | Header tiles | wet_bags_today, tonnes_dried_season, alerts_sent_week, act_wards_today |

`colour` convention: ACT = red `#D32F2F`, WATCH = amber `#F9A825`, ABSTAIN = grey `#9E9E9E`, none = green `#388E3C`.

### 1.3 Writes APEX makes
- `REPORTS.review_status` (`ACCEPTED`/`CORRECTED`/`REJECTED`), `reviewed_by`, corrected `payload`.
- Demo controls call **PL/SQL packages or REST §2.2**, never insert alerts directly.
- `ASK_NGAO_LOG` inserts.

## 2. REST API `/ngao/v1`

Base URL (ORDS): `https://<adb-host>.adb.<region>.oraclecloudapps.com/ords/ngao/v1`
Base URL (Django, if chosen): `https://<vm-host>/api/v1` with the **same paths and payloads**.

### 2.0 Auth

| Caller | Mechanism |
|---|---|
| Wasiliana callbacks (USSD, and SMS once confirmed) | Public callback URL. If Wasiliana supports a shared secret, require `?k=<WEBHOOK_SECRET>` or the header they document. Confirm the exact check against [docs.wasiliana.com](https://docs.wasiliana.com) **[Assumption until confirmed]** |
| Louisa's USSD service calling §6 | `Authorization: Bearer <USSD_SERVICE_TOKEN>` |
| APEX / demo controls / router | OAuth2 client-credentials (ORDS `OAUTH` client) or `Authorization: Bearer <token>` (DRF token) |
| Public scorecard | Unauthenticated `GET /public/scorecard` |

### 2.1 Error format (all endpoints)

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "ward_id is required", "details": {"field": "ward_id"}, "request_id": "8f2c..." } }
```
Codes → HTTP: `VALIDATION_ERROR` 400 · `UNAUTHORIZED` 401 · `FORBIDDEN` 403 · `NOT_FOUND` 404 ·
`CONFLICT` 409 · `UPSTREAM_ERROR` 502 (Wasiliana/GenAI) · `INTERNAL` 500.
SMS webhook endpoints **always return 200** to Wasiliana (log errors). The USSD callback is the exception: it must return plain text within ~10 seconds.

### 2.2 Action endpoints (demo controls + scheduler)

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/jobs/score` | `{"as_of":"2026-10-15","county":"Uasin Gishu"}` | Score wards → `RISK_SCORES` |
| POST | `/jobs/send-alerts` | `{"as_of":"2026-10-15","dry_run":false}` | Act alerts → `ALERTS`, `MESSAGES` |
| POST | `/jobs/plan-routes` | `{"route_date":"2026-10-16"}` | Dryer router → routes, bookings, SMS |
| POST | `/jobs/replay` | `{"scenario":"garissa_rvf_2006","from":"2006-09-01","to":"2007-01-15"}` | Fill replay tables |
| POST | `/jobs/reset-demo` | `{}` | Reset demo subscribers/messages |

Response `202`:
```json
{ "job_id": 1042, "job": "send-alerts", "status": "DONE", "summary": {"alerts_created": 14, "messages_queued": 14, "suppressed_cooldown": 3} }
```

### 2.3 Read endpoints

`GET /wards?county=Uasin%20Gishu` →
```json
{ "items": [ {"ward_id": 12, "ward_name": "Moiben", "county": "Uasin Gishu", "centroid": {"lat": 0.82, "lon": 35.38}} ] }
```

`GET /wards/{ward_id}/risk?date=2026-10-15&service=FARM` →
```json
{ "ward_id": 12, "score_date": "2026-10-15",
  "risks": [ {"alert_type": "A1", "probability": 0.75, "confidence_pct": 75, "decision": "ACT", "abstain_reason": null, "model_version": "a1-xgb-2026-10-14-<git sha>"},
             {"alert_type": "A2", "probability": 0.41, "confidence_pct": 41, "decision": "WATCH", "abstain_reason": null} ] }
```

`GET /reports?status=NEEDS_REVIEW&since=2026-10-15T00:00:00+03:00` →
```json
{ "items": [ {"report_id": 77, "ward_id": 12, "report_type": "wet_bags", "report_count": 20, "ai_confidence": 0.62, "review_status": "NEEDS_REVIEW", "raw_text": "magunia 20 mabichi"} ] }
```

`PATCH /reports/{id}` `{"review_status":"CORRECTED","payload":{"report_type":"wet_bags","count":25}}` → `200` updated report.

`GET /routes?date=2026-10-16` →
```json
{ "route_date": "2026-10-16", "routes": [ {"route_id": 5, "dryer_id": 2, "stops": [ {"stop_order": 1, "point_id": 3, "point_name": "Moiben market", "eta": "2026-10-16T08:00:00+03:00", "planned_bags": 140, "urgency": 112.0} ] } ] }
```

`POST /bookings/{id}/confirm` → `{"booking_id": 91, "status": "CONFIRMED"}`

`GET /public/scorecard` → rows of `V_SCORECARD`.

### 2.4 Internal: reply-reader contract (OCI GenAI output)

The model must return **only** this JSON (validated server-side; anything else → `NEEDS_REVIEW`):

```json
{ "report_type": "wet_bags | sick_animals | dead_animals | flooding | water_point_dry | harvested | rain | bags_dried | rvf_signs | booking_confirm | stop | other",
  "count": 20, "unit": "bags | animals | null", "crop": "maize | null", "species": "cattle | goats | sheep | camels | null",
  "rain_reported": true, "moisture_pct": null, "language": "sw | en", "confidence": 0.92 }
```
Rules: `confidence < 0.7` or `report_type = other` → `review_status = NEEDS_REVIEW`. Exact keywords
(`STOP`, `1`, `NDIYO`, `RVF`, and `LUGHA` or `LANG` followed by `SW` or `EN`) are handled **before** the AI call. `language` in the JSON is `sw` or `en` (Swahili or English, chosen by the user).

## 3. Wasiliana (SMS and USSD)

Wasiliana is the Kenyan SMS, USSD, and airtime provider. Dennis has used it before.

Two callback surfaces, two owners:

| Surface | Who receives it | Owner |
|---|---|---|
| USSD session callback | `ussd/` public URL | Louisa |
| Outbound SMS, delivery reports, inbound SMS | `backend/` | Dennis |

### 3.1 USSD callback mode

Wasiliana does not let us dial the user. We register a service code and a callback URL. On each hop Wasiliana **POSTs the session to that URL**. Louisa's service answers with **`text/plain`**, the body prefixed **`CON `** (session continues) or **`END `** (session ends), **within ~10 seconds**. No OCI GenAI call on this path.

Examples when `preferred_lang` is `sw` (the same screens are sent in English when the user chose English):

```
CON Chagua kata:
1. Moiben
2. Kapseret
```

```
END Asante! Umesajiliwa.
```

**Confirm exact request field names against Wasiliana docs ([docs.wasiliana.com](https://docs.wasiliana.com)).** The handler needs a session id, the subscriber phone number, and the text entered so far. Do not hard-code a guessed JSON or form body; isolate the parse in one adapter in `ussd/`.

Screen text is in Swahili or English, chosen by the user. On a new number the first screen is the language prompt in §5; that choice is saved to `preferred_lang` before the menu below. Main menu: `1` Register / Jiandikishe → role (farmer / herder / both) → county → ward → consent; `2` Report / Ripoti → wet bags (count), sick or dead animals (type, count), flooding, water point dry, or other (ask them to send an SMS; Louisa does not send one); `3` Ward status / Hali ya kata yangu; `4` **Lugha / Language** (change `preferred_lang`, then continue in the new language).

Registration, reports, ward status, and unsubscribe go through [§5](#5-ussd-to-backend-contract). Louisa writes only `USSD_SESSIONS`.

### 3.2 Outbound SMS (Dennis → Wasiliana REST)

Dennis is the only sender. The alert engine and dryer router queue rows in `MESSAGES` (`direction=OUT`, `status=QUEUED`). A worker dequeues them and calls the **Wasiliana SMS REST API** with the **API key** and the registered **sender ID**.

Store the provider message id returned by Wasiliana in `MESSAGES.provider_msg_id`. **Confirm the exact URL, headers, and JSON against [docs.wasiliana.com](https://docs.wasiliana.com).** The Python package **`pytek-wasiliana`** is an optional client for this call; a thin `requests` wrapper is also fine. Either way the env vars are `WASILIANA_API_KEY` and `WASILIANA_SENDER_ID`.

### 3.3 Delivery reports

Wasiliana can POST a delivery report to a backend callback (`POST /sms/delivery`). **Confirm exact field names against Wasiliana docs ([docs.wasiliana.com](https://docs.wasiliana.com)).** The adapter maps the confirmed payload onto `MESSAGES.status` (`SENT` → `DELIVERED` / `FAILED`) using `provider_msg_id`. Until the field names are confirmed, log the raw body and do not guess the keys in the rest of the code.

Response: `200` empty. Failures are logged; do not return 4xx/5xx to Wasiliana for a payload we have not finished mapping.

### 3.4 Inbound SMS — open item

**Inbound SMS forwarding is an open item.** Confirm with Wasiliana whether they POST inbound SMS to our callback, and **confirm exact field names against Wasiliana docs ([docs.wasiliana.com](https://docs.wasiliana.com))** before the reply reader depends on them.

Intended backend path once that is confirmed: `POST /sms/inbound` → insert `MESSAGES` (`direction=IN`) → reply reader (§2.4). Processing may be async. The HTTP handler returns `200` immediately. Keywords `STOP`, `1`, `NDIYO`, `RVF`, and `LUGHA` or `LANG` followed by `SW` or `EN` (§5) are handled before any GenAI call. Until forwarding is confirmed, structured USSD menu 2 (via §5) is the path that does not depend on inbound SMS.

## 4. Message templates
Alerts are rendered from `ALERT_TEMPLATE` using the subscriber's `preferred_lang` (Swahili or English, chosen by the user). The unique key is `(hazard, severity, lang)` with `lang` in (`sw`, `en`) and `body` `VARCHAR2(160)`. Slots: `{ward}`, `{day}`, `{confidence}`, `{point}`, `{time}`, `{fee}`.
Example A1 (`lang` sw): `MvuaSmart: Siku 3 za jua zinatarajiwa kuanzia {day} katika kata yako (uhakika {confidence}%). Vuna mahindi sasa na uyakaushe. Jibu NDIYO ukivuna.`
The English row for the same hazard and severity is the `lang` `en` body. Keep to ≤ 2 SMS segments (the column is 160 characters). Each language's copy must be checked by a native speaker.

## 5. USSD to backend contract

Folder: **`ussd/`** at the repo root (Louisa, branch `ussd-louisa`), so her work has its own tree next to `backend/`. See [ussd/README.md](../ussd/README.md).

Louisa owns the Wasiliana callback, the menu state machine, and `USSD_SESSIONS`. Dennis owns durable rows and every SMS. Louisa calls the endpoints below on the same host and paths as §2 (`/ngao/v1` on ORDS or Django). Auth: `Authorization: Bearer <USSD_SERVICE_TOKEN>`.

The USSD reply to Wasiliana is still due within ~10 seconds, so these endpoints must answer in well under that (target under 2 seconds) and must not call OCI GenAI.

Menus and SMS are in Swahili or English, chosen by the user (`SUBSCRIBERS.preferred_lang`: `sw` or `en`, default `sw`).

**First session.** On a new number's first session, before any other menu, reply with exactly:

```
CON Chagua lugha / Choose language
1. Kiswahili
2. English
```

`1` saves `preferred_lang = 'sw'`. `2` saves `preferred_lang = 'en'`. Call `POST /ussd/language` (below) so the choice is stored before the next screen. Then show the main menu in that language.

**Change it later.** The main menu includes **Lugha / Language**. Choosing it shows the same two options, writes the new `preferred_lang`, and continues in the new language.

**SMS keywords.** An inbound SMS of `LUGHA` or `LANG` followed by `SW` or `EN` (case-insensitive; forms `LUGHA SW`, `LUGHA EN`, `LANG SW`, `LANG EN`) sets `preferred_lang` to `sw` or `en` and sends a confirmation in the new language (Kiswahili confirmation when the new value is `sw`, English confirmation when it is `en`). Do not change `preferred_lang` if the second token is missing. Handle these keywords before any GenAI call.

**Alerts.** Outbound alerts are rendered from `ALERT_TEMPLATE` (`body` for the matching `hazard`, `severity`, and `lang` = the subscriber's `preferred_lang`). See §4.

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/ussd/language` | `{"phone":"+254712345678","preferred_lang":"sw"}` | Set `SUBSCRIBERS.preferred_lang` to `sw` or `en`. Create the subscriber row when the phone is new (phone + `preferred_lang` + `status`) so the choice is saved before registration finishes; registration fills role, ward, and consent. `200` `{"preferred_lang":"sw"}` |
| POST | `/ussd/register` | `{"phone":"+254712345678","ward_id":12,"role":"farmer","preferred_lang":"sw","consent":true}` | MERGE `SUBSCRIBERS`, including `preferred_lang` (`sw` or `en`). `201` `{"subscriber_id":44,"status":"ACTIVE"}` |
| POST | `/ussd/report` | `{"phone":"+254712345678","session_id":"s1","report_type":"wet_bags","count":20,"unit":"bags"}` | INSERT `REPORTS` with `source=USSD`, `review_status=AUTO_ACCEPTED` (a structured menu, not an AI parse). `201` `{"report_id":77}` |
| GET | `/ussd/ward-status?phone=+254712345678` | — | Short line in Swahili or English, chosen by the user, for menu 3 (today's decision for the subscriber's ward, or a sentence that says we have no score). `200` `{"text":"Kata ya Moiben: siku za jua, uhakika 75%."}` when `preferred_lang` is `sw` |
| POST | `/ussd/unsubscribe` | `{"phone":"+254712345678"}` | `SUBSCRIBERS.status=STOPPED`. `200` `{"status":"STOPPED"}` |

`report_type` uses the same set as §2.4. Menu 2 only sends types the menu collected (wet bags, sick or dead animals, flooding, water point dry). "Other" tells the farmer to send an SMS; it does not call `/ussd/report`.

Errors use §2.1. A 4xx/5xx from these endpoints is Louisa's problem to turn into an `END` screen in Swahili or English, chosen by the user (for `sw`: `END Samahani, jaribu tena.`). She must not leave Wasiliana waiting.

Session rows stay in `ussd/`: each hop upserts `USSD_SESSIONS` (`session_id`, `phone`, `last_text`, `updated_at`). Dennis may read that table; he does not advance the menu.

## 6. Change log
| Version | Date | Change |
|---|---|---|
| v1-draft | 2026-10-14 | Initial contract |
| v1-draft.2 | 2026-10-14 | Wasiliana replaces Africa's Talking. USSD service is `ussd/` (Louisa); §5 is the USSD to backend contract. Inbound SMS forwarding and delivery-report field names left open pending docs.wasiliana.com |
| v1-draft.3 | 2026-10-14 | Language choice: `preferred_lang`, first-session prompt, main-menu Lugha / Language, SMS `LUGHA`/`LANG`, alerts rendered from `ALERT_TEMPLATE` |
