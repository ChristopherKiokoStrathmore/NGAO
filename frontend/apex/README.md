# Ngao — MvuaSmart frontend (Oracle APEX app 100)

APEX dashboard + farmer PWA for Ngao, built on Oracle APEX 26ai on an Always Free Autonomous Database (workspace `NGAO`, schema `WKSP_NGAO`).

Run URL: https://g93fcef1cec31ea-ngaodb.adb.eu-frankfurt-1.oraclecloudapps.com/ords/r/ngao/ngao-mvuasmart/home

## Pages
| # | Page | Notes |
|---|------|-------|
| 1 | Risk Overview | KPI cards + charts, mobile-friendly |
| 2 | Ward Risk Map | colour by risk level, county picker (default Uasin Gishu) |
| 3 | Alert Approvals | approve / reject pending alerts |
| 4 | Ward Risk | risk scores per ward |
| 5 | Rain & Soil | rainfall and soil moisture |
| 6 | Garissa Replay | 2006 Rift Valley fever replay |
| 7–10 | Farmers and Cooperatives | subscriber and cooperative management |
| 11 | Alert Templates | Kiswahili / English templates |
| 20 | My Ward Alerts | farmer PWA view, Kiswahili/English switch |
| 30 | Insurer View | wards ranked by risk, county picker |

## PWA
The app is installable as the **Ngao** PWA: open page 20 in Chrome (⋮ → Install app) or Safari (Share → Add to Home Screen).

## Import
1. Sign in to your APEX workspace.
2. SQL Workshop / App Builder → **Import**, choose `apex/f100.sql` (type: Application).
3. Install, keeping or changing the application ID. The app expects the Ngao tables (wards, alerts, subscribers, risk_scores, …) in the parsing schema.

No credentials are stored in this folder.
