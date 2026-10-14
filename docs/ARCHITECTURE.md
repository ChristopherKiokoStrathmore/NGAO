# Ngao / MvuaSmart: Architecture

> Source: *Ngao — Full Project Blueprint (MvuaSmart merged)*, 13 Oct 2026 (60 pp.), plus the original
> repo README. Items marked **[Assumption]** are design choices made for this repo, not stated in the brief.

## 1. Principles

1. **One Oracle Autonomous Database (ADB) is the single source of truth.** Data, scores, alerts,
   replies, dryer plans and outcomes all live in schema `NGAO`. Nothing to keep in sync.
2. **Integrate through the database, not through each other.** APEX (Chris) reads **views**; the
   backend (Dennis) **writes tables** and sends SMS. The USSD service (Louisa) owns menus and
   sessions and calls the backend's USSD contract for registration and reports. The contract is in
   [API_CONTRACT.md](API_CONTRACT.md).
3. **Models run next to the data.** OML4Py in-DB scoring (fallback: train in Python and write scores
   into tables), so scores are queryable by SQL, APEX and Select AI.
4. **Generative AI only reads.** OCI GenAI turns replies into JSON. Replies and outgoing messages are in
   Swahili or English, chosen by the user. Every outgoing message is a vetted per-language template
   (`ALERT_TEMPLATE`, selected by `preferred_lang`) with slots. AI never writes advice.
5. **Honest alerts.** Calibrated probability → **Act / Watch / Abstain**; cooldowns and caps; public scorecard.
6. **Leakage-safe replays.** Every feature row has `feature_date` and `available_date`; replays read
   only `available_date <= :t`.

## 2. Modules and responsibilities

| # | Module | Tech | Owner | Reads | Writes |
|---|---|---|---|---|---|
| M1 | Ingestion pipeline | Python, Earth Engine API, Copernicus EWDS, OCI Object Storage | **Trevor** | GEE, GloFAS, files | `WARD_FEATURES_DAILY`, `FORECASTS`, `WARDS` |
| M2 | Models & calibration | pandas, scikit-learn, XGBoost, OML4Py, SQL rules | **Trevor** (+ Chris for loading) | features | `RISK_SCORES` |
| M3 | Alert engine | PL/SQL (+ Python) | **Dennis** (wiring), Chris (tables) | `RISK_SCORES`, `ALERT_TYPES`, `ALERT_TEMPLATE`, `SUBSCRIBERS` | `ALERTS`, `MESSAGES` (queued) |
| M4 | SMS gateway | Wasiliana REST (API key + sender ID) + Django/DRF **or** ORDS. Optional client: `pytek-wasiliana` | **Dennis** | Wasiliana SMS API, delivery reports | `MESSAGES`, `SUBSCRIBERS` (STOP) |
| M4b | USSD menus | Wasiliana callback → `ussd/` | **Louisa** | Wasiliana session POST; backend `/ngao/v1/ussd/*` | `USSD_SESSIONS`; registration and reports via Dennis |
| M5 | Reply reader | OCI Generative AI (Cohere Command A) | **Dennis** | inbound `MESSAGES` | `REPORTS` (or review queue) |
| M6 | Dryer router | Python greedy plan (OR-Tools later) | **Dennis** (+ Trevor for simulation) | `REPORTS`, `RISK_SCORES`, `DRYERS`, `COLLECTION_POINTS` | `ROUTES`, `ROUTE_STOPS`, `BOOKINGS`, `MESSAGES` |
| M7 | Dashboard + PWA | Oracle APEX, APEX map region, PWA | **Chris** | `V_*` views | `REPORTS.review_status`, demo actions |
| M8 | Ask Ngao | Select AI (`DBMS_CLOUD_AI`) | **Chris** | views | `ASK_NGAO_LOG` |
| M9 | Scheduler & scorecard | `DBMS_SCHEDULER`, SQL | Chris / Dennis | `ALERTS`, `OUTCOMES` | `V_SCORECARD` |

## 3. System context

```mermaid
flowchart TB
  farmer(["Smallholder farmer / herder<br/>feature phone"])
  promoter(["Community health promoter"])
  officer(["County agri / vet / health / disaster officer"])
  coop(["Cooperative · dryer operator"])
  judge(["Hackathon judge"])

  ngao["NGAO platform<br/>Oracle Cloud (ADB + APEX + ORDS + GenAI)<br/>+ backend service"]

  gee["Google Earth Engine"]
  glofas["Copernicus EWDS / GloFAS"]
  ndma["NDMA drought bulletins<br/>census · HDX · OSM"]
  wa["Wasiliana<br/>SMS + USSD"]

  farmer -- "USSD register/report · SMS reply" --> wa
  wa -- "SMS alerts · booking SMS" --> farmer
  promoter <--> wa
  wa <-- "USSD callback · SMS API" --> ngao
  officer <-- "APEX dashboard / PWA" --> ngao
  coop <-- "PWA + SMS stop list" --> ngao
  judge -- "APEX app URL" --> ngao
  gee --> ngao
  glofas --> ngao
  ndma --> ngao
```

## 4. Component diagram

```mermaid
flowchart LR
  subgraph OCI["Oracle Cloud Infrastructure (Always Free)"]
    direction TB
    subgraph ADB["Autonomous Database · schema NGAO"]
      direction TB
      T1[("Reference<br/>WARDS · COLLECTION_POINTS · DRYERS<br/>ALERT_TYPES · ALERT_TEMPLATE · APP_USERS")]
      T2[("Time series<br/>WARD_FEATURES_DAILY · FORECASTS")]
      T3[("Decisions<br/>RISK_SCORES · ALERTS · ROUTES · BOOKINGS")]
      T4[("Conversations<br/>SUBSCRIBERS · USSD_SESSIONS<br/>MESSAGES · REPORTS")]
      T5[("Truth<br/>OUTCOMES · ASK_NGAO_LOG")]
      V["V_* views<br/>(read contract for APEX)"]
      OML["OML4Py models<br/>+ isotonic calibration lookup"]
      PLSQL["PKG_ALERT_ENGINE<br/>PKG_DEMO (PL/SQL)"]
      SCHED["DBMS_SCHEDULER jobs"]
      SAI["Select AI profile NGAO_AI"]
      ORDSN["ORDS module /ngao/v1"]
    end
    APEXN["APEX app 'Ngao'<br/>+ PWA"]
    GENAI["OCI Generative AI"]
    OSTORE[("Object Storage<br/>raw CSV exports")]
    VM["Always Free VM<br/>ingestion + (optional) Django"]
  end
  subgraph EXT["External"]
    GEE["Earth Engine"]
    EWDS["GloFAS"]
    WA["Wasiliana"]
  end
  USSDAPP["ussd/ (Louisa)<br/>menus · sessions"]

  GEE --> VM --> OSTORE --> T2
  EWDS --> VM
  T2 --> OML --> T3
  SCHED --> OML
  SCHED --> PLSQL
  PLSQL --> T3
  PLSQL --> T4
  T1 & T2 & T3 & T4 & T5 --> V
  V --> APEXN
  APEXN --> SAI --> V
  APEXN -- "demo buttons" --> PLSQL
  WA <--> USSDAPP
  WA <--> VM
  USSDAPP --> VM
  WA <--> ORDSN
  VM <--> T4
  USSDAPP --> T4
  ORDSN <--> T4
  VM <--> GENAI
```

`VM` hosts the Django service **if** we keep Django (Dennis: SMS, alert engine, router, reply reader).
USSD callbacks always land on `ussd/` (Louisa), which calls the backend contract and writes
`USSD_SESSIONS`. SMS send and delivery reports stay on the backend (or ORDS, if that is the
[open decision](#open-decisions)). `pytek-wasiliana` is an optional Python client for the SMS API.

## 5. Data pipeline: GEE → ADB → OML scoring → alerts

```mermaid
flowchart LR
  subgraph GEE["Earth Engine (ward averages, daily)"]
    C["CHIRPS daily<br/>UCSB-CHG/CHIRPS/DAILY"]
    G["GFS 0.25°<br/>NOAA/GFS0P25"]
    E["ERA5-Land<br/>ECMWF/ERA5_LAND/DAILY_AGGR"]
    M["MODIS NDVI / LST<br/>MOD13Q1 · MOD11A2"]
    S["Sentinel-1 flood maps"]
    J["JRC water · MERIT HAND<br/>ESA WorldCover"]
  end
  GL["GloFAS (EWDS)<br/>Tana @ Garissa ensemble"]
  ND["NDMA VCI3M bulletins<br/>census WASH · WorldPop · GLW4"]

  EXP["Export CSV per ward-day<br/>+ available_date rule"]
  LOAD["Load to ADB<br/>(DBMS_CLOUD.COPY_DATA)"]
  F[("WARD_FEATURES_DAILY<br/>FORECASTS")]
  QA{"QA + leakage tests<br/>available_date ≤ t"}
  SC["Score<br/>A1/A2 XGBoost (OML4Py)<br/>A3 A4 B1–B4 C1–C3 SQL rules"]
  CAL["Isotonic calibration<br/>+ split-conformal abstain"]
  R[("RISK_SCORES<br/>prob · decision")]
  ENG["Alert engine<br/>threshold · cooldown 48h<br/>3 routine SMS/week cap"]
  OUT["ALERTS + MESSAGES (queued)<br/>→ Wasiliana SMS"]
  W["Watch / Abstain<br/>→ dashboard only"]

  C & G & E & M & S & J --> EXP
  GL --> EXP
  ND --> EXP
  EXP --> LOAD --> F --> QA --> SC --> CAL --> R --> ENG
  ENG -- "Act" --> OUT
  ENG -- "Watch / Abstain" --> W
```

Key dataset facts (from the brief, checked 13 Oct 2026): GFS rain totals = sum of forecast hours that
are multiples of 6; ERA5-Land rain in metres (×1000); NDVI × 0.0001; LST × 0.02 K. Availability lags:
GFS = run date; CHIRPS = 1st of next month + 25 d; ERA5-Land = +15 d; MODIS NDVI = composite start + 23 d;
MODIS LST = +13 d. Live "recent rain" therefore comes from previous GFS day-1 forecasts.

### Alert catalogue (seed rows for `ALERT_TYPES`)

| Code | Service | Trigger (starting rule) | Audience | Friday |
|---|---|---|---|---|
| A1 | MvuaSmart | P(3+ dry days starting ≤5 d) ≥ 70% | Farmers | **Live** |
| A2 | MvuaSmart | P(>20 mm/day within 48 h) ≥ 60% | Farmers, dryer operators | **Live** |
| A3 | MvuaSmart | Ward aflatoxin risk class high | Farmers, cooperatives | If time |
| A4 | MvuaSmart | P(cropland flood ≤3 d) ≥ 60% | Farmers | If time |
| A5 | MvuaSmart | Point chosen in tonight's route plan | Farmers near point | **Live** |
| B1 | Mifugo | >30% GloFAS members > 5-yr level | Herders, disaster officers | If time |
| B2 | Mifugo | P(flash flood ≤2 d) ≥ 60% | Herders, all | Designed |
| B3 | Mifugo | NDVI anomaly > +0.1 over 3 months after above-normal rain (NASA rule) | Herders, vets | **Replay** |
| B4 | Mifugo | Forecast VCI3M < 35 within 4–8 wk | Herders, committees, NDMA | Designed |
| C1 | Afya | Cholera conditions index high + flood / neighbour outbreak | Health teams, promoters | Static map if time |
| C2 | Afya | Same signal as B3 | Health teams | Replay |
| C3 | Afya | High ward aflatoxin risk after wet harvest | Food-safety officers, millers | Designed |

Decisions: **Act** = calibrated prob ≥ threshold and inputs agree → SMS + dashboard.
**Watch** = rising but below threshold → officers only. **Abstain** = GFS/ECMWF disagree, inputs
missing, or conformal set has both outcomes → officers, with reason.

Each subscriber stores `preferred_lang` (`sw` or `en`): Swahili or English, chosen by the user
(default `sw`). The alert engine renders the Act SMS from `ALERT_TEMPLATE`, one body per
`(hazard, severity, lang)`, using `lang` = `preferred_lang`. A later SMS of `LUGHA` or `LANG`
followed by `SW` or `EN` switches `preferred_lang` and sends a confirmation in the new language.
USSD changes the same column from the main-menu item **Lugha / Language**.

## 6. Sequence diagrams

### 6.1 Farmer USSD registration → morning SMS alert

```mermaid
sequenceDiagram
  autonumber
  actor F as Farmer (feature phone)
  participant WA as Wasiliana
  participant US as USSD service (Louisa)
  participant BE as Backend (Dennis)
  participant DB as Autonomous DB
  participant SCH as DBMS_SCHEDULER / Demo controls
  participant ENG as PKG_ALERT_ENGINE

  F->>WA: Dial USSD code (new number, first session)
  WA->>US: POST session to callback URL
  US-->>WA: CON Chagua lugha / Choose language, 1. Kiswahili, 2. English
  F->>WA: 1 or 2
  US->>BE: POST /ngao/v1/ussd/language
  BE->>DB: set SUBSCRIBERS.preferred_lang to sw or en
  US-->>WA: CON main menu in Swahili or English, chosen by the user (includes Lugha / Language)
  F->>WA: 1, then role, county, ward, consent
  WA->>US: POST session (text so far)
  US->>BE: POST /ngao/v1/ussd/register
  BE->>DB: MERGE SUBSCRIBERS (phone, ward, role=farmer, preferred_lang, consent_at)
  US->>DB: UPDATE USSD_SESSIONS
  US-->>WA: END confirmation in Swahili or English, chosen by the user
  Note over F,BE: Later, menu item Lugha / Language, or SMS LUGHA or LANG followed by SW or EN, updates preferred_lang and confirms in the new language
  Note over SCH,DB: 05:00 pull data · ~05:30 score (or "Run morning scoring")
  SCH->>DB: score wards → RISK_SCORES (A1 prob 0.75, decision=ACT)
  SCH->>ENG: run_alerts(today) at 06:00 (or "Send alerts")
  ENG->>DB: match subscribers by ward+role, apply cooldown and weekly cap
  ENG->>DB: render ALERT_TEMPLATE.body where lang = preferred_lang
  ENG->>DB: INSERT ALERTS + MESSAGES(direction=OUT, status=QUEUED)
  BE->>DB: poll / dequeue QUEUED messages
  BE->>WA: Wasiliana SMS REST (API key, sender ID, to, message)
  WA-->>F: SMS in Swahili or English, chosen by the user
  WA->>BE: delivery report (confirm field names)
  BE->>DB: UPDATE MESSAGES status=DELIVERED
```

### 6.2 Farmer SMS reply → GenAI parse → review queue → APEX

```mermaid
sequenceDiagram
  autonumber
  actor F as Farmer
  participant WA as Wasiliana
  participant BE as Backend reply reader
  participant AI as OCI Generative AI
  participant DB as Autonomous DB
  participant AP as APEX (Reports inbox)
  actor O as County officer

  F->>WA: "Nimevuna magunia 20, mvua imenyesha, mahindi yana unyevu"
  Note over WA,BE: Inbound SMS forwarding is an open item. Confirm the callback and field names against docs.wasiliana.com
  WA->>BE: POST /sms/inbound (normalized after the adapter)
  BE->>DB: INSERT MESSAGES(direction=IN)
  BE->>AI: fixed prompt "extract, don't advise" + text
  AI-->>BE: {"report_type":"wet_bags","count":20,"unit":"bags","crop":"maize","rain_reported":true,"language":"sw","confidence":0.92}
  BE->>BE: validate JSON schema
  alt confidence >= 0.7 and known type
    BE->>DB: INSERT REPORTS(review_status=AUTO_ACCEPTED)
    DB->>DB: report feeds ward features / dryer demand
  else unsure or unknown type or GenAI fails
    BE->>DB: INSERT REPORTS(review_status=NEEDS_REVIEW)
  end
  AP->>DB: SELECT V_REPORTS_INBOX / V_REVIEW_QUEUE
  O->>AP: Accept / correct / reject
  AP->>DB: UPDATE REPORTS SET review_status, reviewed_by
```

Fallback if parsing replies in Swahili or English, chosen by the user, is weak (brief risk): keyword + number matching, plus structured USSD
reports (menu 2) which skip the AI entirely.

### 6.3 Dryer booking / routing (18:00)

```mermaid
sequenceDiagram
  autonumber
  participant SCH as Scheduler 18:00 / "Plan tomorrow's routes"
  participant RT as Dryer router (Python)
  participant DB as Autonomous DB
  participant BE as Backend SMS sender (Dennis)
  participant WA as Wasiliana
  actor OP as Dryer operator
  actor F as Farmers near point

  SCH->>RT: plan(date = tomorrow)
  RT->>DB: SELECT wet bags per collection point (last 3 days)
  RT->>DB: SELECT A2 heavy-rain prob (48 h) + A3 aflatoxin class per ward
  RT->>RT: urgency = wet_bags × P(heavy rain 48h) × aflatoxin boost
  RT->>RT: greedy fill each dryer (bags/day = t/h × hours ÷ 0.09)
  RT->>DB: INSERT ROUTES, ROUTE_STOPS, BOOKINGS(status=OFFERED)
  RT->>DB: queue MESSAGES: A5 booking SMS + operator stop list
  BE->>WA: Wasiliana SMS REST (API key + sender ID)
  WA-->>F: "Mashine ya kukausha itafika soko la Moiben Jumanne saa 2 asubuhi. Jibu 1"
  WA-->>OP: stop list
  F->>WA: "1"
  WA->>BE: inbound SMS callback (confirm forwarding + field names)
  BE->>DB: UPDATE BOOKINGS status=CONFIRMED
  OP->>WA: "Dried 120 bags, 13%"
  WA->>BE: inbound SMS callback (confirm forwarding + field names)
  BE->>DB: INSERT REPORTS(type=bags_dried) → OUTCOMES (tonnes dried before rain)
```

Fee shown in the SMS: (start − target moisture points) × ~KES 30 per 90 kg bag (NCPB rate; confirm).

### 6.4 Officer dashboard + Ask Ngao (Select AI)

```mermaid
sequenceDiagram
  autonumber
  actor O as County officer (browser / PWA)
  participant AP as APEX app
  participant DB as Autonomous DB (views)
  participant SAI as Select AI (DBMS_CLOUD_AI)
  participant LLM as OCI GenAI (Select AI provider)

  O->>AP: Sign in (APEX accounts, role = AGRI_OFFICER)
  AP->>DB: SELECT * FROM V_WARD_RISK_MAP WHERE service = :P1_SERVICE
  DB-->>AP: ward polygons + hazard + decision colour
  O->>AP: Toggle farm → herd → health
  O->>AP: Ask Ngao: "Which wards in Uasin Gishu have > 1,000 wet bags and rain likely in 48 h?"
  AP->>SAI: DBMS_CLOUD_AI.GENERATE(prompt, profile=>'NGAO_AI', action=>'showsql'/'runsql')
  SAI->>LLM: prompt + metadata of allowed views only
  LLM-->>SAI: SQL
  SAI->>DB: run SQL (read-only views)
  DB-->>AP: rows
  AP->>DB: INSERT ASK_NGAO_LOG(question, sql, user)
  AP-->>O: table/chart + the generated SQL shown as source
```

## 7. Core schema (ER diagram)

Full DDL: [`db/schema.sql`](../db/schema.sql).

```mermaid
erDiagram
  WARDS ||--o{ WARD_FEATURES_DAILY : has
  WARDS ||--o{ FORECASTS : has
  WARDS ||--o{ RISK_SCORES : scored
  WARDS ||--o{ SUBSCRIBERS : lives_in
  WARDS ||--o{ COLLECTION_POINTS : contains
  WARDS ||--o{ GRAZING_OPTIONS : contains
  SUBSCRIBERS ||--o{ FARMS : owns
  SUBSCRIBERS ||--o{ HERDS : owns
  FARMS }o--|| WARDS : in
  HERDS }o--|| WARDS : in
  ALERT_TYPES ||--o{ RISK_SCORES : defines
  RISK_SCORES ||--o{ ALERTS : triggers
  SUBSCRIBERS ||--o{ ALERTS : receives
  ALERTS ||--o| MESSAGES : sent_as
  SUBSCRIBERS ||--o{ MESSAGES : exchanges
  SUBSCRIBERS ||--o{ USSD_SESSIONS : opens
  MESSAGES ||--o| REPORTS : parsed_into
  WARDS ||--o{ REPORTS : about
  DRYERS ||--o{ ROUTES : runs
  ROUTES ||--o{ ROUTE_STOPS : has
  COLLECTION_POINTS ||--o{ ROUTE_STOPS : visited
  ROUTE_STOPS ||--o{ BOOKINGS : has
  SUBSCRIBERS ||--o{ BOOKINGS : books
  ALERTS ||--o{ OUTCOMES : graded_by
  APP_USERS ||--o{ REPORTS : reviews
  APP_USERS ||--o{ ASK_NGAO_LOG : asks

  WARDS {
    number ward_id PK
    varchar county
    varchar ward_name
    sdo_geometry boundary
    number centroid_lat
    number centroid_lon
  }
  WARD_FEATURES_DAILY {
    number ward_id PK
    date feature_date PK
    date available_date
    number rain_1d_mm
    number rain_7d_mm
    number rain_anom_30d
    number soil_moist_top
    number ndvi
    number vci3m
    number flood_extent_pct
    number glofas_p_5yr
  }
  FORECASTS {
    number ward_id PK
    varchar source PK
    date issue_date PK
    number lead_day PK
    date available_date
    number rain_mm
  }
  ALERT_TYPES {
    varchar alert_type PK
    varchar service
    number act_threshold
    number watch_threshold
    number cooldown_hours
    varchar audience_roles
    varchar template_sw
    varchar template_en
  }
  ALERT_TEMPLATE {
    number template_id PK
    varchar hazard
    varchar severity
    char lang "sw en"
    varchar body
  }
  RISK_SCORES {
    number score_id PK
    number ward_id FK
    date score_date
    varchar alert_type FK
    number raw_score
    number probability
    number confidence_pct
    varchar decision "ACT WATCH ABSTAIN"
    varchar abstain_reason
    varchar model_version
  }
  SUBSCRIBERS {
    number subscriber_id PK
    varchar phone UK
    number ward_id FK
    varchar role "farmer herder both health_promoter"
    varchar language
    char preferred_lang "sw en"
    timestamp consent_at
    varchar status
  }
  FARMS {
    number farm_id PK
    number subscriber_id FK
    number ward_id FK
    varchar crop
    number est_bags
  }
  HERDS {
    number herd_id PK
    number subscriber_id FK
    number ward_id FK
    varchar species
    number head_count
    number tlu
  }
  ALERTS {
    number alert_id PK
    number score_id FK
    number subscriber_id FK
    varchar alert_type
    number ward_id
    varchar status
    timestamp created_at
  }
  MESSAGES {
    number message_id PK
    varchar direction "IN OUT"
    varchar channel "SMS USSD"
    varchar phone
    number subscriber_id FK
    varchar body
    varchar provider_msg_id
    varchar status
    timestamp created_at
  }
  USSD_SESSIONS {
    varchar session_id PK
    number subscriber_id FK
    varchar phone
    varchar last_text
    timestamp updated_at
  }
  REPORTS {
    number report_id PK
    number message_id FK
    number ward_id FK
    varchar report_type
    number report_count
    varchar unit
    json payload
    number ai_confidence
    varchar review_status
    number reviewed_by FK
  }
  COLLECTION_POINTS {
    number point_id PK
    number ward_id FK
    varchar point_name
    number lat
    number lon
    varchar kind
  }
  DRYERS {
    number dryer_id PK
    varchar operator_phone
    number tonnes_per_hour
    number hours_per_day
    varchar is_placeholder
  }
  ROUTES {
    number route_id PK
    number dryer_id FK
    date route_date
    varchar status
  }
  ROUTE_STOPS {
    number stop_id PK
    number route_id FK
    number point_id FK
    number stop_order
    timestamp eta
    number urgency
    number planned_bags
  }
  BOOKINGS {
    number booking_id PK
    number stop_id FK
    number subscriber_id FK
    number bags
    number fee_kes
    varchar status
  }
  GRAZING_OPTIONS {
    number option_id PK
    number ward_id FK
    varchar area_name
    number score
    number weekly_tlu_cap
    number tlu_assigned
  }
  OUTCOMES {
    number outcome_id PK
    number alert_id FK
    varchar outcome_type
    varchar hit "Y N"
    number lead_days
    number tonnes_dried
  }
  APP_USERS {
    number user_id PK
    varchar username
    varchar app_role
    varchar county
  }
  ASK_NGAO_LOG {
    number log_id PK
    number user_id FK
    varchar question
    clob generated_sql
    timestamp asked_at
  }
```

**[Assumption]** `FARMS`, `HERDS`, `ROUTE_STOPS`, `BOOKINGS`, `GRAZING_OPTIONS`, `APP_USERS`,
`ASK_NGAO_LOG`, `USSD_SESSIONS`, `FORECASTS`, `ALERT_TYPES` and `ALERT_TEMPLATE` refine the brief's table list
(WARDS, WARD_FEATURES_DAILY, RISK_SCORES, SUBSCRIBERS, ALERTS, REPLIES/REPORTS, DRYERS,
COLLECTION_POINTS, ROUTES, OUTCOMES). The brief's `REPLIES` = inbound rows in `MESSAGES`.

## 8. Security & data protection

- Store only phone, ward, role, and language preference (`preferred_lang`: Swahili or English, chosen by the user). **No GPS.** Consent at USSD registration; `STOP` unsubscribes.
- Health reports appear **aggregated by ward**, never by person (views enforce this).
- Kenya Data Protection Act 2019: register with ODPC before any real deployment.
- Secrets (Wasiliana API key, OCI keys) in `.env` / OCI Vault, never in git.
- Select AI profile is limited to `V_*` views; it can't reach `SUBSCRIBERS.phone`.
- Officers decide; Ngao advises.

## Open decisions

| # | Decision | Options | Recommendation (for discussion) | Owners |
|---|---|---|---|---|
| D1 | **Webhook/API runtime** | (a) **ORDS** REST handlers + PL/SQL, as the brief has it. (b) **Django/DRF** service, as the original README planned, writing to ADB via `python-oracledb` | Either honours this contract. ORDS has a public HTTPS URL out of the box and scores better on "Oracle adoption". Django is faster if Dennis already knows it. A hybrid also works: Django for Wasiliana SMS webhooks + GenAI, PL/SQL for the alert engine. USSD menus stay in `ussd/` either way | Chris + Dennis, **Wed** |
| D2 | Django hosting (if D1=b), and the public URL for the USSD callback | OCI Always Free VM + HTTPS, or ngrok tunnel for demo | VM on OCI (Oracle adoption), tunnel as backup | Dennis (API host), Louisa (USSD callback URL) |
| D3 | OML4Py on Always Free | in-DB XGBoost vs Python-trained scores loaded to table | Check day one; fallback is fine | Trevor + Chris |
| D4 | Map rendering in APEX | Native Map region (GeoJSON/SDO) vs static choropleth | Native Map region | Chris |
| D5 | Who sends SMS | backend dequeues `MESSAGES` and calls the Wasiliana REST API (API key + sender ID) vs PL/SQL calls Wasiliana via `APEX_WEB_SERVICE` | Backend dequeues (one sender). Louisa does not send SMS. Optional client: `pytek-wasiliana` | Dennis |
| D6 | OCI region / services availability (GenAI, Select AI) | n/a | Check home region on first sign-in | Chris |
| — | **Inbound SMS forwarding** | Confirm with Wasiliana whether inbound SMS is POSTed to our callback, and the exact field names, at [docs.wasiliana.com](https://docs.wasiliana.com). Delivery-report field names are the same check | Do not code the reply reader against guessed fields. One adapter normalizes the body | Dennis |
