# data/pipelines/ (Trevor · `data-modelling-trevor`)
Ingestion jobs. Rules: GFS daily rain = sum of forecast hours that are multiples of 6; ERA5-Land rain ×1000 (m→mm), clip small negatives; NDVI ×0.0001; LST ×0.02 K. `available_date`: GFS = run date; CHIRPS = 1st of next month + 25 d; ERA5-Land +15 d; NDVI composite start +23 d; LST +13 d.
