-- Ngao / MvuaSmart: shared schema DRAFT (Oracle Autonomous Database, schema NGAO)
-- Matches docs/ARCHITECTURE.md §7. Oracle 19c+/23ai syntax. Run as NGAO in SQL Worksheet.
-- Status: v1-draft 2026-10-14. Changes via PR to main only.

-- ===== Reference =====
CREATE TABLE wards (
  ward_id        NUMBER PRIMARY KEY,
  county         VARCHAR2(60)  NOT NULL,
  ward_name      VARCHAR2(100) NOT NULL,
  boundary       SDO_GEOMETRY,
  centroid_lat   NUMBER(9,6),
  centroid_lon   NUMBER(9,6)
);

CREATE TABLE alert_types (
  alert_type      VARCHAR2(3) PRIMARY KEY,           -- A1..A5, B1..B4, C1..C3
  service         VARCHAR2(10) NOT NULL CHECK (service IN ('FARM','HERD','HEALTH')),
  name            VARCHAR2(60) NOT NULL,
  act_threshold   NUMBER(4,3),
  watch_threshold NUMBER(4,3),
  cooldown_hours  NUMBER DEFAULT 48,
  overrides_cap   CHAR(1) DEFAULT 'N' CHECK (overrides_cap IN ('Y','N')),  -- floods/disease
  audience_roles  VARCHAR2(200),
  template_sw     VARCHAR2(480),
  template_en     VARCHAR2(480)
);

-- Per-language alert copy. The send path renders body for the subscriber's preferred_lang.
CREATE TABLE alert_template (
  template_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  hazard      VARCHAR2(30) NOT NULL,
  severity    VARCHAR2(16) NOT NULL,
  lang        CHAR(2) NOT NULL CHECK (lang IN ('sw','en')),
  body        VARCHAR2(160) NOT NULL,
  CONSTRAINT uq_alert_template UNIQUE (hazard, severity, lang)
);

CREATE TABLE app_users (
  user_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username  VARCHAR2(100) UNIQUE NOT NULL,
  app_role  VARCHAR2(20) NOT NULL CHECK (app_role IN ('ADMIN','AGRI_OFFICER','VET','HEALTH','DISASTER','COOP','OPERATOR','COMMITTEE','JUDGE')),
  county    VARCHAR2(60)
);

-- ===== Time series =====
CREATE TABLE ward_features_daily (
  ward_id          NUMBER NOT NULL REFERENCES wards,
  feature_date     DATE   NOT NULL,      -- day the value describes
  available_date   DATE   NOT NULL,      -- first day it could be known (leakage guard)
  rain_1d_mm NUMBER, rain_3d_mm NUMBER, rain_7d_mm NUMBER, rain_14d_mm NUMBER, rain_30d_mm NUMBER,
  rain_anom_30d    NUMBER,
  gfs_rain_d1_mm NUMBER, gfs_rain_d2_mm NUMBER, gfs_rain_d3_mm NUMBER, gfs_rain_d5_mm NUMBER, gfs_rain_d7_mm NUMBER,
  ecmwf_agreement  NUMBER,
  soil_moist_top   NUMBER, soil_moist_root NUMBER,
  ndvi NUMBER, ndvi_anom NUMBER, vci3m NUMBER, lst_k NUMBER,
  flood_extent_pct NUMBER, glofas_p_5yr NUMBER,
  wet_bag_reports_3d NUMBER, sick_animal_reports_7d NUMBER,
  CONSTRAINT pk_wfd PRIMARY KEY (ward_id, feature_date)
);

CREATE TABLE forecasts (
  ward_id        NUMBER NOT NULL REFERENCES wards,
  source         VARCHAR2(10) NOT NULL CHECK (source IN ('GFS','ECMWF','GLOFAS')),
  issue_date     DATE NOT NULL,
  lead_day       NUMBER NOT NULL,
  available_date DATE NOT NULL,
  rain_mm        NUMBER,
  value_json     JSON,                  -- e.g. GloFAS ensemble stats
  CONSTRAINT pk_fc PRIMARY KEY (ward_id, source, issue_date, lead_day)
);

-- ===== Decisions =====
CREATE TABLE risk_scores (
  score_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ward_id        NUMBER NOT NULL REFERENCES wards,
  score_date     DATE   NOT NULL,
  alert_type     VARCHAR2(3) NOT NULL REFERENCES alert_types,
  raw_score      NUMBER,
  probability    NUMBER(5,4),                       -- calibrated 0..1
  confidence_pct NUMBER(3),                         -- shown in the SMS, in Swahili or English, chosen by the user
  decision       VARCHAR2(7) NOT NULL CHECK (decision IN ('ACT','WATCH','ABSTAIN')),
  abstain_reason VARCHAR2(200),
  model_version  VARCHAR2(60),
  is_replay      CHAR(1) DEFAULT 'N' CHECK (is_replay IN ('Y','N')),
  created_at     TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
  CONSTRAINT uq_rs UNIQUE (ward_id, score_date, alert_type, is_replay)
);

-- ===== People & conversations =====
CREATE TABLE subscribers (
  subscriber_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  phone          VARCHAR2(16) UNIQUE NOT NULL,       -- E.164
  ward_id        NUMBER REFERENCES wards,
  role           VARCHAR2(16) CHECK (role IN ('farmer','herder','both','health_promoter','operator','committee')), -- null until registration; language choice may insert first
  language       VARCHAR2(2) DEFAULT 'sw' CHECK (language IN ('sw','en')),
  preferred_lang CHAR(2) DEFAULT 'sw' NOT NULL CHECK (preferred_lang IN ('sw','en')), -- sw or en, chosen by the user
  consent_at    TIMESTAMP WITH TIME ZONE,
  status        VARCHAR2(10) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','STOPPED')),
  is_demo       CHAR(1) DEFAULT 'N'
);

CREATE TABLE farms (
  farm_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subscriber_id NUMBER NOT NULL REFERENCES subscribers,
  ward_id       NUMBER NOT NULL REFERENCES wards,
  crop          VARCHAR2(30) DEFAULT 'maize',
  est_bags      NUMBER
);

CREATE TABLE herds (
  herd_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subscriber_id NUMBER NOT NULL REFERENCES subscribers,
  ward_id       NUMBER NOT NULL REFERENCES wards,
  species       VARCHAR2(10) CHECK (species IN ('cattle','goats','sheep','camels')),
  head_count    NUMBER,
  tlu           NUMBER                               -- cattle 0.7, shoat 0.1, camel 1.0
);

CREATE TABLE messages (
  message_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  direction       VARCHAR2(3) NOT NULL CHECK (direction IN ('IN','OUT')),
  channel         VARCHAR2(4) NOT NULL CHECK (channel IN ('SMS','USSD')),
  phone           VARCHAR2(16) NOT NULL,
  subscriber_id   NUMBER REFERENCES subscribers,
  body            VARCHAR2(1000),
  provider_msg_id VARCHAR2(100),
  status          VARCHAR2(12) DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','SENT','DELIVERED','FAILED','RECEIVED')),
  created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

CREATE TABLE alerts (
  alert_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  score_id      NUMBER NOT NULL REFERENCES risk_scores,
  subscriber_id NUMBER NOT NULL REFERENCES subscribers,
  alert_type    VARCHAR2(3) NOT NULL REFERENCES alert_types,
  ward_id       NUMBER NOT NULL REFERENCES wards,
  message_id    NUMBER REFERENCES messages,
  status        VARCHAR2(12) DEFAULT 'CREATED' CHECK (status IN ('CREATED','QUEUED','SENT','SUPPRESSED')),
  created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

CREATE TABLE ussd_sessions (
  session_id    VARCHAR2(100) PRIMARY KEY,
  subscriber_id NUMBER REFERENCES subscribers,
  phone         VARCHAR2(16) NOT NULL,
  last_text     VARCHAR2(200),
  updated_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

CREATE TABLE reports (
  report_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  message_id    NUMBER REFERENCES messages,         -- null for USSD menu reports
  ward_id       NUMBER REFERENCES wards,
  report_type   VARCHAR2(20) NOT NULL,
  report_count  NUMBER,
  unit          VARCHAR2(10),
  payload       JSON,
  ai_confidence NUMBER(4,3),
  source        VARCHAR2(10) DEFAULT 'SMS_AI' CHECK (source IN ('SMS_AI','SMS_KEYWORD','USSD')),
  review_status VARCHAR2(14) DEFAULT 'NEEDS_REVIEW' CHECK (review_status IN ('AUTO_ACCEPTED','NEEDS_REVIEW','ACCEPTED','CORRECTED','REJECTED')),
  reviewed_by   NUMBER REFERENCES app_users,
  created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

-- ===== Dryers =====
CREATE TABLE collection_points (
  point_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ward_id    NUMBER NOT NULL REFERENCES wards,
  point_name VARCHAR2(100) NOT NULL,
  lat NUMBER(9,6), lon NUMBER(9,6),
  kind       VARCHAR2(20) CHECK (kind IN ('market','coop_store','school','depot'))
);

CREATE TABLE dryers (
  dryer_id        NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name            VARCHAR2(60),
  operator_phone  VARCHAR2(16),
  tonnes_per_hour NUMBER,
  hours_per_day   NUMBER,
  is_placeholder  CHAR(1) DEFAULT 'Y' CHECK (is_placeholder IN ('Y','N'))  -- label demo data honestly
);

CREATE TABLE routes (
  route_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dryer_id   NUMBER NOT NULL REFERENCES dryers,
  route_date DATE NOT NULL,
  status     VARCHAR2(10) DEFAULT 'PLANNED' CHECK (status IN ('PLANNED','NOTIFIED','DONE'))
);

CREATE TABLE route_stops (
  stop_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  route_id     NUMBER NOT NULL REFERENCES routes,
  point_id     NUMBER NOT NULL REFERENCES collection_points,
  stop_order   NUMBER NOT NULL,
  eta          TIMESTAMP WITH TIME ZONE,
  urgency      NUMBER,
  planned_bags NUMBER
);

CREATE TABLE bookings (
  booking_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  stop_id       NUMBER NOT NULL REFERENCES route_stops,
  subscriber_id NUMBER NOT NULL REFERENCES subscribers,
  bags          NUMBER,
  fee_kes       NUMBER,
  status        VARCHAR2(10) DEFAULT 'OFFERED' CHECK (status IN ('OFFERED','CONFIRMED','DRIED','NO_SHOW'))
);

-- ===== Drought =====
CREATE TABLE grazing_options (
  option_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ward_id        NUMBER NOT NULL REFERENCES wards,
  area_name      VARCHAR2(100),
  score          NUMBER,
  weekly_tlu_cap NUMBER,
  tlu_assigned   NUMBER DEFAULT 0,
  week_start     DATE
);

-- ===== Truth & logs =====
CREATE TABLE outcomes (
  outcome_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  alert_id     NUMBER REFERENCES alerts,
  score_id     NUMBER REFERENCES risk_scores,       -- grade Watch/no-alert too
  outcome_type VARCHAR2(30),
  hit          CHAR(1) CHECK (hit IN ('Y','N')),
  lead_days    NUMBER,
  tonnes_dried NUMBER,
  observed_at  DATE
);

CREATE TABLE ask_ngao_log (
  log_id        NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       NUMBER REFERENCES app_users,
  question      VARCHAR2(1000),
  generated_sql CLOB,
  asked_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

CREATE INDEX ix_rs_date   ON risk_scores (score_date, alert_type);
CREATE INDEX ix_msg_phone ON messages (phone, created_at);
CREATE INDEX ix_rep_ward  ON reports (ward_id, created_at);

-- ===== Core views (read contract for APEX; see docs/API_CONTRACT.md §1.2) =====
CREATE OR REPLACE VIEW v_ward_risk_map AS
SELECT w.ward_id, w.ward_name, w.county,
       SDO_UTIL.TO_GEOJSON(w.boundary) AS boundary_geojson,
       t.service, r.alert_type, r.score_date, r.probability, r.confidence_pct,
       r.decision, r.abstain_reason,
       CASE r.decision WHEN 'ACT' THEN '#D32F2F' WHEN 'WATCH' THEN '#F9A825'
                       WHEN 'ABSTAIN' THEN '#9E9E9E' ELSE '#388E3C' END AS colour
FROM wards w
JOIN risk_scores r ON r.ward_id = w.ward_id AND r.is_replay = 'N'
JOIN alert_types t ON t.alert_type = r.alert_type;

CREATE OR REPLACE VIEW v_reports_inbox AS
SELECT p.report_id, p.created_at AS received_at, w.ward_name, p.report_type, p.report_count,
       p.ai_confidence, p.review_status, w.centroid_lat AS lat, w.centroid_lon AS lon
FROM reports p LEFT JOIN wards w ON w.ward_id = p.ward_id;

CREATE OR REPLACE VIEW v_review_queue AS
SELECT p.report_id, m.body AS raw_text, p.payload AS parsed_payload, p.ai_confidence,
       CASE WHEN p.ai_confidence < 0.7 THEN 'LOW_CONFIDENCE' ELSE 'UNKNOWN_TYPE' END AS reason
FROM reports p LEFT JOIN messages m ON m.message_id = p.message_id
WHERE p.review_status = 'NEEDS_REVIEW';

CREATE OR REPLACE VIEW v_wet_maize_points AS
SELECT c.point_id, c.point_name, c.ward_id, c.lat, c.lon,
       NVL((SELECT SUM(p.report_count) FROM reports p
             WHERE p.ward_id = c.ward_id AND p.report_type = 'wet_bags'
               AND p.review_status IN ('AUTO_ACCEPTED','ACCEPTED','CORRECTED')
               AND p.created_at > SYSTIMESTAMP - INTERVAL '3' DAY), 0) AS wet_bags_3d,
       (SELECT MAX(r.probability) FROM risk_scores r
         WHERE r.ward_id = c.ward_id AND r.alert_type = 'A2' AND r.score_date = TRUNC(SYSDATE)) AS p_heavy_rain_48h
FROM collection_points c;
-- [Assumption] wet bags attributed to the ward's points; refine to nearest point later.

CREATE OR REPLACE VIEW v_scorecard AS
SELECT a.alert_type, TRUNC(a.created_at, 'IW') AS period,
       COUNT(*) AS alerts_sent,
       SUM(CASE WHEN o.hit = 'Y' THEN 1 ELSE 0 END) AS hits,
       SUM(CASE WHEN o.hit = 'N' THEN 1 ELSE 0 END) AS false_alarms,
       ROUND(AVG(o.lead_days), 1) AS avg_lead_days
FROM alerts a LEFT JOIN outcomes o ON o.alert_id = a.alert_id
WHERE a.status = 'SENT'
GROUP BY a.alert_type, TRUNC(a.created_at, 'IW');

-- TODO (next PRs): v_dryer_plan, v_vet_priority, v_health_watch, v_drought_grazing,
-- v_calibration, v_rvf_replay, v_kpi; PKG_ALERT_ENGINE; PKG_DEMO; seed alert_types A1..C3.
