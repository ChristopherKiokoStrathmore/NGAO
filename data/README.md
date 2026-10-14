# data/ (Trevor · branch `data-modelling-trevor`)

Owns data pipelines, Google Earth Engine exports, OML4Py models, and risk scoring.
- `pipelines/`: Earth Engine exports (CHIRPS, GFS, ERA5-Land, MODIS, Sentinel-1, JRC, WorldCover), GloFAS pull, NDMA/census loaders → `WARD_FEATURES_DAILY`, `FORECASTS`. Every row carries `feature_date` + `available_date`.
- `models/`: A1 dry window, A2 heavy rain (logistic → XGBoost/OML4Py), isotonic calibration + split-conformal abstain, SQL rules (A3, A4, B1–B4, C1–C3), replay harness `run_as_of(day)`, leakage tests.
Spec files from the brief (NGAO_DATA_PIPELINE.md, NGAO_FEATURES_REPLAY.md, NGAO_MODELS.md) go in this folder.
Raw data is not committed; exports land in OCI Object Storage.
