"""Core incident fetching logic."""

from datetime import date
from typing import Literal

import pandas as pd


def get_incidents(
    city: str,
    start_date: str | date,
    end_date: str | date,
    view: Literal["comparable", "city_full", "city_raw"] = "comparable",
    limit: int = 1000,
    as_gdf: bool = False,
) -> pd.DataFrame:
    """Fetch incidents for a supported city.
    
    Args:
        city: City key (e.g. "chicago", "seattle")
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        view: Output mode
            - "comparable": standardized std_* columns only
            - "city_full": all native fields + std_* columns
            - "city_raw": untouched source payload
        limit: Maximum records to return
        as_gdf: Return as geopandas GeoDataFrame (requires geopandas)
    
    Returns:
        DataFrame with incident records
    """
    raise NotImplementedError("Port in progress")
