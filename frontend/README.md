# frontend/ (Chris · branch `frontend-chris`)

Owns the **APEX dashboard + PWA**.

The dashboard is an **Oracle APEX** app on the shared Autonomous Database, made installable on phones with APEX's built-in **PWA** setting. No React/Next.js (decision recorded in root README).

- `apex/`: APEX app export (SQLcl `apex export -split`). Generated; don't hand-edit.
- `pwa/`: PWA icons, manifest settings, install instructions for officers.

Reads only the `V_*` views in [docs/API_CONTRACT.md §1.2](../docs/API_CONTRACT.md#12-views-apex-chris-reads). Setup: [docs/ORACLE_APEX.md](../docs/ORACLE_APEX.md).
