"""Configuration for the CityCrimeMap site (citycrimemap.us).

Cities listed here are the ones currently shipped on the site. A city
belongs in this file only when its tidycop registry source has a
populated spotcrime_category_map (so the renderer doesn't show a sea
of Unclassified dots) and the upstream open-data feed is actively
publishing recent rows.

The window_days field is tuned per-city to compensate for upstream
publishing lag (chicago/pittsburgh especially lag 2-6 weeks).

Wave order tracked in docs/citymap-rollout-plan.md.
"""

CITIES = [
    {
        "key": "chicago",
        "name": "Chicago",
        "slug": "chicago",
        "state_abbrev": "IL",
        "state_name": "Illinois",
        "timezone": "America/Chicago",
        # Chicago Socrata "ijzp-q8t2" lags ~7-14 days; widen to 45d.
        "window_days": 45,
        "map_center": [41.8781, -87.6298],
        "map_zoom": 11,
        # SpotCrime alerts URL pattern: spotcrime.com/<state>/<city>
        "spotcrime_alerts_url": "https://spotcrime.com/il/chicago",
        "data_source": "City of Chicago Data Portal (Socrata)",
        "data_source_url": "https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present/ijzp-q8t2",
    },
    {
        "key": "seattle",
        "name": "Seattle",
        "slug": "seattle",
        "state_abbrev": "WA",
        "state_name": "Washington",
        "timezone": "America/Los_Angeles",
        "window_days": 14,
        "map_center": [47.6062, -122.3321],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/wa/seattle",
        "data_source": "Seattle Police Department SPD Crime Data",
        "data_source_url": "https://data.seattle.gov/Public-Safety/SPD-Crime-Data-2008-Present/tazs-3rd5",
        # SPD publishes a "Not Reportable to NIBRS" bucket for admin
        # records (warrants served, court orders, etc.). Drop pre-map
        # to stop them inflating the Unclassified count. Added
        # 2026-06-28 alongside the Seattle classifier expansion.
        "drop_descriptions": ["Not Reportable to NIBRS"],
    },
    {
        "key": "san_francisco",
        "name": "San Francisco",
        "slug": "san-francisco",
        "state_abbrev": "CA",
        "state_name": "California",
        "timezone": "America/Los_Angeles",
        "window_days": 14,
        "map_center": [37.7749, -122.4194],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/ca/san-francisco",
        "data_source": "DataSF — SFPD Incident Reports",
        "data_source_url": "https://data.sfgov.org/Public-Safety/Police-Department-Incident-Reports-2018-to-Present/wg3w-h783",
    },
    {
        "key": "detroit",
        "name": "Detroit",
        "slug": "detroit",
        "state_abbrev": "MI",
        "state_name": "Michigan",
        "timezone": "America/Detroit",
        "window_days": 14,
        "map_center": [42.3314, -83.0458],
        "map_zoom": 11,
        "spotcrime_alerts_url": "https://spotcrime.com/mi/detroit",
        "data_source": "Detroit Open Data Portal — RMS Crime Incidents",
        "data_source_url": "https://data.detroitmi.gov/datasets/rms-crime-incidents",
    },
    {
        "key": "pittsburgh",
        "name": "Pittsburgh",
        "slug": "pittsburgh",
        "state_abbrev": "PA",
        "state_name": "Pennsylvania",
        "timezone": "America/New_York",
        # Pittsburgh WPRDC lags ~45d; widen accordingly.
        "window_days": 75,
        "map_center": [40.4406, -79.9959],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/pa/pittsburgh",
        "data_source": "Western Pennsylvania Regional Data Center (WPRDC)",
        "data_source_url": "https://data.wprdc.org/dataset/uniform-crime-reporting-data",
    },
    # ---- Wave 1 (2026-06-04) ----
    {
        "key": "washington_dc",
        "name": "Washington, DC",
        "slug": "washington-dc",
        "state_abbrev": "DC",
        "state_name": "District of Columbia",
        "timezone": "America/New_York",
        "window_days": 21,
        "map_center": [38.9072, -77.0369],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/dc/washington",
        "data_source": "DC MPD Crime Incidents (ArcGIS)",
        "data_source_url": "https://opendata.dc.gov/datasets/DCGIS::crime-incidents-in-2026/about",
    },
    {
        "key": "houston",
        "name": "Houston",
        "slug": "houston",
        "state_abbrev": "TX",
        "state_name": "Texas",
        "timezone": "America/Chicago",
        "window_days": 21,
        "map_center": [29.7604, -95.3698],
        "map_zoom": 11,
        "spotcrime_alerts_url": "https://spotcrime.com/tx/houston",
        "data_source": "HPD NIBRS Recent Crime Reports (ArcGIS)",
        "data_source_url": "https://mycity2.houstontx.gov/pubgis02/rest/services/HPD/NIBRS_Recent_Crime_Reports/FeatureServer",
    },
    # San Antonio: classifier map landed in registry, but SAPD CKAN
    # dataset publishes only zip_code (no lat/lng, no street address)
    # so it can't render on a Leaflet map. Library entry stays; the
    # frontend defers until a geocoded SA feed surfaces. See
    # docs/citymap-rollout-plan.md § "Blocked".
    # Boston: same problem — ArcGIS Boston_Incidents_View is type=Table
    # with no geometry and no Lat/Long columns (only BLOCK address
    # strings). Library entry stays; frontend deferred. Could be
    # unblocked with geocoding (separate project) or by adding a
    # second Boston source if upstream R tidycops gains one.
    {
        "key": "rochester",
        "name": "Rochester",
        "slug": "rochester",
        "state_abbrev": "NY",
        "state_name": "New York",
        "timezone": "America/New_York",
        "window_days": 21,
        "map_center": [43.1566, -77.6088],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/ny/rochester",
        "data_source": "RPD Part I Crime (ArcGIS)",
        "data_source_url": "https://data-rpdny.opendata.arcgis.com/datasets/rpd-part-i-crime-2011-to-present",
    },
    {
        "key": "cleveland",
        "name": "Cleveland",
        "slug": "cleveland",
        "state_abbrev": "OH",
        "state_name": "Ohio",
        "timezone": "America/New_York",
        "window_days": 21,
        "map_center": [41.4993, -81.6944],
        "map_zoom": 11,
        "spotcrime_alerts_url": "https://spotcrime.com/oh/cleveland",
        "data_source": "Cleveland Division of Police P1RMS Crime Incidents (ArcGIS)",
        "data_source_url": "https://data.clevelandohio.gov/datasets/crime-incidents",
    },
    # ---- Wave 2 (2026-06-04) ----
    {
        "key": "indianapolis",
        "name": "Indianapolis",
        "slug": "indianapolis",
        "state_abbrev": "IN",
        "state_name": "Indiana",
        "timezone": "America/Indiana/Indianapolis",
        "window_days": 21,
        "map_center": [39.7684, -86.1581],
        "map_zoom": 11,
        "spotcrime_alerts_url": "https://spotcrime.com/in/indianapolis",
        "data_source": "IMPD Incidents Public (ArcGIS)",
        "data_source_url": "https://data.indy.gov/datasets/IndyGIS::impd-incidents-public/about",
    },
    {
        "key": "hartford",
        "name": "Hartford",
        "slug": "hartford",
        "state_abbrev": "CT",
        "state_name": "Connecticut",
        "timezone": "America/New_York",
        # 10-day reporting lag per registry note; 30d window for density.
        "window_days": 30,
        "map_center": [41.7658, -72.6734],
        "map_zoom": 13,
        "spotcrime_alerts_url": "https://spotcrime.com/ct/hartford",
        "data_source": "Hartford Open Data — Police Incidents (ArcGIS)",
        "data_source_url": "https://data.hartford.gov/datasets/police-incidents",
    },
    {
        "key": "minneapolis",
        "name": "Minneapolis",
        "slug": "minneapolis",
        "state_abbrev": "MN",
        "state_name": "Minnesota",
        "timezone": "America/Chicago",
        "window_days": 21,
        "map_center": [44.9778, -93.2650],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/mn/minneapolis",
        "data_source": "MPD Police Incidents — Last 2 Years (ArcGIS)",
        "data_source_url": "https://opendata.minneapolismn.gov/datasets/cityoflakes::police-incidents-last-2-years/about",
    },
    # ---- Wave 3 (2026-06-05) ----
    # Coord pre-check dropped dallas / providence / new_orleans — all
    # three publish without lat/lng. See docs/citymap-rollout-plan.md
    # § "Blocked". Cincinnati / gainesville / denver passed.
    {
        "key": "cincinnati",
        "name": "Cincinnati",
        "slug": "cincinnati",
        "state_abbrev": "OH",
        "state_name": "Ohio",
        "timezone": "America/New_York",
        "window_days": 21,
        "map_center": [39.1031, -84.5120],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/oh/cincinnati",
        "data_source": "City of Cincinnati — STARS Crime Incidents (Socrata)",
        "data_source_url": "https://data.cincinnati-oh.gov/safety/-PDI-Police-Data-Initiative-Crime-Incidents/7aqy-xrv9",
    },
    {
        "key": "gainesville",
        "name": "Gainesville",
        "slug": "gainesville",
        "state_abbrev": "FL",
        "state_name": "Florida",
        "timezone": "America/New_York",
        # Gainesville CFS feed is mostly admin calls; ≈56% of rows
        # classify into 8-cat. The classified rows are real crimes.
        "window_days": 21,
        "map_center": [29.6516, -82.3248],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/fl/gainesville",
        "data_source": "City of Gainesville — Crime Responses (Socrata)",
        "data_source_url": "https://data.cityofgainesville.org/Public-Safety/Crime-Responses/gvua-xt9q",
    },
    {
        "key": "denver",
        "name": "Denver",
        "slug": "denver",
        "state_abbrev": "CO",
        "state_name": "Colorado",
        "timezone": "America/Denver",
        "window_days": 14,
        "map_center": [39.7392, -104.9903],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/co/denver",
        "data_source": "Denver Open Data — Crime Offenses (ArcGIS)",
        "data_source_url": "https://opendata-geospatialdenver.hub.arcgis.com/datasets/crime/about",
    },
    # ──────────────────────────────────────────────────────────────────
    # Wave 4 (geocoded): Boston. BPD publishes block-level addresses but
    # no coordinates. web/scripts/geocode.py resolves "N BLOCK MAIN ST"
    # to lat/lng via the Census batch geocoder (cached in
    # web/data/geocode_cache.sqlite).
    # ──────────────────────────────────────────────────────────────────
    {
        "key": "boston",
        "name": "Boston",
        "slug": "boston",
        "state_abbrev": "MA",
        "state_name": "Massachusetts",
        "timezone": "America/New_York",
        "window_days": 21,
        "map_center": [42.3601, -71.0589],
        "map_zoom": 12,
        "spotcrime_alerts_url": "https://spotcrime.com/ma/boston",
        "data_source": "Boston Police Incidents (ArcGIS, geocoded via Census)",
        "data_source_url": "https://data.boston.gov/dataset/boston-incidents",
        # BPD’s feed is ~75% non-criminal admin calls (MEDICAL ASSISTANCE,
        # MV CRASH RESPONSE, INVESTIGATE PERSON, TOWED, etc.). Drop
        # Unclassified rows pre-geocode to (a) avoid a sea of slate dots
        # on the map and (b) save Census batch calls.
        "drop_unclassified": True,
    },
]
