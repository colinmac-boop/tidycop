"""Configuration for the five-city crime map site.

Cities are the MVP-5 with populated tidycop-spotcrime classifier maps:
chicago, seattle, san_francisco, detroit, pittsburgh.

The window_days field is tuned per-city to compensate for upstream
publishing lag (chicago/pittsburgh especially lag 2-6 weeks).
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
]
