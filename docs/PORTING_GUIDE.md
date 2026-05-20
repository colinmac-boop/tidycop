# Porting Guide

## R → Python Translation Notes

### Key R Files to Port

1. **R/incident_registry.R** → `registry/cities.yaml` + `tidycop/registry.py`
   - City key normalization
   - Source specifications (endpoint URLs, field maps)
   - Multi-year handling (Kansas City, New Orleans)

2. **R/standardized_incidents.R** → `tidycop/schema.py`
   - Standard column definitions
   - Field coalescing logic (first_present_field)
   - Date parsing with timezone handling

3. **R/data_utils.R** → `tidycop/platform/*.py`
   - Socrata fetcher (SoQL $where, paging)
   - ArcGIS REST fetcher (resultOffset, outFields)
   - CKAN datastore fetcher

4. **R/get_incidents.R** → `tidycop/core.py`
   - Main entry point
   - View mode switching (comparable/city_full/city_raw)
   - Optional sf conversion → geopandas

### Translation Patterns

| R | Python |
|---|---|
| `tibble` | `pd.DataFrame` |
| `sf` | `gpd.GeoDataFrame` |
| `lubridate::ymd_hms()` | `pd.to_datetime()` |
| `stringr::str_trim()` | `.str.strip()` |
| `dplyr::coalesce()` | `pd.DataFrame.combine_first()` |
| `httr::GET()` | `requests.get()` with retry |

### Testing Strategy

1. Pick 1 city per platform: Chicago (Socrata), Detroit (ArcGIS), Pittsburgh (CKAN)
2. Fetch same date range in R tidycops and Python tidycop
3. Compare row counts + schema
4. Spot-check 10 random rows for field equality

### Priority Order

1. Socrata fetcher (covers 10+ cities)
2. Schema normalization + field coalescing
3. Chicago smoke test (full pipeline)
4. ArcGIS fetcher (covers 8+ cities)
5. CKAN fetcher (covers 2 cities)
