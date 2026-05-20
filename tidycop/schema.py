"""Standardized incident schema and normalization."""

# Standard columns (ported from tidycops standardized_incidents.R)
STD_COLUMNS = [
    "std_city",
    "std_city_display",
    "std_source_id",
    "std_source_name",
    "std_source_dataset",
    "std_source_url",
    "std_source_record_id",
    "std_incident_id",
    "std_incident_number",
    "std_incident_date",
    "std_reported_date",
    "std_offense_code",
    "std_offense_description",
    "std_offense_category",
    "std_disposition",
    "std_address",
    "std_zip_code",
    "std_neighborhood",
    "std_district",
    "std_beat",
    "std_division",
    "std_latitude",
    "std_longitude",
]

# SpotCrime extension (optional)
SPOTCRIME_COLUMNS = [
    "std_spotcrime_category",  # Arrest, Arson, Assault, Burglary, Homicide, Robbery, Shooting, Theft, Vandalism
]
