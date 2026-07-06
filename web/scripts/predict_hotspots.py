#!/usr/bin/env python3
"""Train per-city hot spot models and emit a GeoJSON risk grid.

For each city in cities.py that has ``hotspots_enabled=True``:

1. Load the incidents that fetch_data.py already wrote to
   ``web/data/<slug>.json``.
2. Reconstruct a DataFrame in the shape tidycop-hotspots expects
   (``std_latitude`` / ``std_longitude`` / ``std_datetime``).
3. Split ~2/3 train / ~1/3 test by date (best we can do with the
   short windows the site currently pulls).
4. Build a grid via ``th.from_tidycop`` and train a
   ``HotspotForest`` on the KDE feature.
5. Predict per-cell risk on ALL rows (train + test combined) and
   emit ``web/data/<slug>_hotspots.geojson`` with one Feature per
   cell whose ``risk`` property is a 0..1-scaled risk score.

Design choices (documented for future readers):

- We fit on training-window KDE only (Wheeler-style leakage-free
  setup), but the exported risk surface is scored on the KDE built
  from *all* rows so the user sees where things are hot right now,
  not where they were hot last month. This is a per-cell inference
  step: the fitted tree is applied to a freshly-computed feature
  matrix.
- Cells with 0 predicted risk are dropped before writing to keep
  the GeoJSON payload small — a full square grid over Chicago at
  250 m has ~15k cells, but only a few hundred carry meaningful
  risk.
- We DON'T use the CityCrimeMap-side incidents as the whole training
  set forever. Once we have longer history stored somewhere, the
  right move is to train on 6-12 months at a time. This script is
  designed to swap in that training set later via
  ``TRAIN_HISTORY_LOADER``.

Run with the tidycop venv:
  ~/Projects/tidycop/.venv/bin/python web/scripts/predict_hotspots.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).parent))

from cities import CITIES  # type: ignore

import tidycop_hotspots as th  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / "data"

# City-level knobs. Only cities present here get hotspot layers.
# Grid cell size trades off resolution vs. payload size / model
# variance. 250 m is Wheeler's default for DC-scale cities; 300 m
# is a comfortable default for large, dense cities; 200 m works
# better for smaller cities where a 300 m grid is too coarse to
# show meaningful contrast.
#
# Rule of thumb used here:
#   ≥900 rows in-window  → 300 m / 500 m bw
#   400-900 rows         → 250 m / 400 m bw
#   <400 rows            → 200 m / 350 m bw
# top_pct = 0.10 everywhere: emit the top 10% of positive-risk
# cells. Adjust per-city if a map looks too sparse or too busy.
HOTSPOT_CONFIG: dict[str, dict] = {
    # Dense, high-volume cities
    "chicago":       {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "detroit":       {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "san_francisco": {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "seattle":       {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "pittsburgh":    {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "washington_dc": {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "houston":       {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "cleveland":     {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "indianapolis":  {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "hartford":      {"cell_size_m": 250, "bandwidth_m": 400, "top_pct": 0.10},
    "minneapolis":   {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    "denver":        {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
    # Mid-volume
    "rochester":     {"cell_size_m": 250, "bandwidth_m": 400, "top_pct": 0.10},
    "cincinnati":    {"cell_size_m": 250, "bandwidth_m": 400, "top_pct": 0.10},
    "gainesville":   {"cell_size_m": 250, "bandwidth_m": 400, "top_pct": 0.10},
    # Low-volume — smaller cells, tighter bandwidth so the map has
    # contrast instead of one big warm blob.
    "boston":        {"cell_size_m": 200, "bandwidth_m": 350, "top_pct": 0.10},
}

# Minimum share of the window that must have gone by before we
# split anything into "test". Guards against a scenario where the
# window is short and all the data lives in the last few days.
_MIN_TEST_ROWS = 30


def _load_incidents(slug: str) -> pd.DataFrame | None:
    path = DATA_DIR / f"{slug}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    incidents = payload.get("incidents") or []
    if not incidents:
        return None
    df = pd.DataFrame(incidents)
    df = df.rename(columns={"lat": "std_latitude", "lng": "std_longitude"})
    if "datetime" in df.columns:
        df["std_datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    df = _drop_bad_coords(df, slug)
    return df


def _drop_bad_coords(df: pd.DataFrame, slug: str) -> pd.DataFrame:
    """Drop obvious garbage coordinates before they blow up the grid.

    Guards against two failure modes:

    1. Sentinel values like (-1, -1) or (0, 0). Seattle SPD publishes
       (-1, -1) for redacted-address incidents; other portals use
       null-island. Left in, they stretch the bounding box across
       continents — a 300 m grid on that box has billions of cells
       and pins CPU at 100% forever.
    2. Legitimate-looking outliers that are still far from the rest
       of the incidents (a Chicago row in the middle of Lake
       Michigan, or a copy-paste of the wrong city's data). Filter
       against the median +/- 5° which is generously larger than any
       real US metro but tight enough to catch clerical errors.
    """
    if "std_latitude" not in df.columns or "std_longitude" not in df.columns:
        return df
    lat = pd.to_numeric(df["std_latitude"], errors="coerce")
    lng = pd.to_numeric(df["std_longitude"], errors="coerce")
    # Rough plausible CONUS+HI+AK bounds
    plausible = (
        lat.notna() & lng.notna()
        & (lat > 17) & (lat < 72)     # HI south of 20, AK north of 70
        & (lng > -180) & (lng < -60)  # PR eastern edge ~-65
    )
    dropped_sentinel = (~plausible).sum()
    df = df.loc[plausible].copy()
    if len(df) == 0:
        return df
    # Then tighten around the city's own median. 5° is ~550 km at 40°N,
    # which is bigger than any single US metro but small enough to
    # exclude e.g. a Houston row that landed in New Mexico.
    med_lat = df["std_latitude"].median()
    med_lng = df["std_longitude"].median()
    tight = (
        (df["std_latitude"] - med_lat).abs() < 5.0
    ) & (
        (df["std_longitude"] - med_lng).abs() < 5.0
    )
    dropped_outlier = (~tight).sum()
    df = df.loc[tight].copy()
    dropped_total = int(dropped_sentinel + dropped_outlier)
    if dropped_total > 0:
        print(f"[hotspots] {slug}: dropped {dropped_total} rows with bad coords "
              f"({dropped_sentinel} sentinel/OOB, {dropped_outlier} far-outlier)")
    return df


def _pick_train_end(df: pd.DataFrame) -> pd.Timestamp | None:
    """Pick a 2/3 cutoff by row count that also leaves a real test set."""
    if "std_datetime" not in df.columns:
        return None
    dt = df["std_datetime"].dropna().sort_values()
    if len(dt) < 50:
        return None
    idx = int(len(dt) * 2 / 3)
    candidate = dt.iloc[idx]
    # Sanity-check that the test side has at least _MIN_TEST_ROWS
    test_rows = (df["std_datetime"] > candidate).sum()
    if test_rows < _MIN_TEST_ROWS:
        return None
    return candidate


def _normalize_risk(pred: np.ndarray) -> np.ndarray:
    """Grid-wide 0..1 scaling for the initial risk surface.

    Used only to decide which cells make the top-10% cut. The final
    display value is a rank-based recomputation on the emitted
    subset (see ``_rank_scale``) because RF predictions on aggregated
    counts often collapse the top cells to indistinguishable ties
    when normalized against the global max.
    """
    if len(pred) == 0:
        return pred
    hi = float(pred.max())
    if hi <= 0:
        return np.zeros_like(pred)
    if len(pred) > 200:
        p95 = float(np.percentile(pred, 95))
        if p95 > 0 and hi > 3.0 * p95:
            # heavy tail — clip to p99.5 so the map has contrast
            hi = float(np.percentile(pred, 99.5))
            if hi <= 0:
                hi = float(pred.max())
    return np.clip(pred / hi, 0.0, 1.0)


def _rank_scale(values: np.ndarray) -> np.ndarray:
    """Map values to (0, 1] by rank: highest = 1.0, lowest = 1/n.

    Motivation: a RandomForestRegressor trained on aggregated crime
    counts often produces predictions that all round to the same
    value at the top of the distribution (many trees average to the
    same leaf mean). When we then normalize against the max, the
    top-10% slice ends up with 40+ cells all coloured identically
    (see Cleveland/Detroit/Pittsburgh: every hot cell was exactly
    1.000 before this fix). Rank-based scaling guarantees a distinct
    display value per cell so the map has visible contrast, at the
    cost of implying more precision between adjacent ranks than the
    underlying model actually has. That trade is worth it for a
    top-N heatmap where the user needs to see contour, not decimals.
    """
    if len(values) == 0:
        return values
    n = len(values)
    # argsort ascending, then invert so highest gets rank n-1
    order = np.argsort(values)
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(n)
    # Map 0..n-1 -> 1/n .. 1.0. Lowest still visible, highest = 1.
    return (ranks + 1.0) / n


def predict_city(city: dict, cfg: dict) -> dict | None:
    slug = city["slug"]
    key = city["key"]
    df = _load_incidents(slug)
    if df is None or len(df) < 100:
        print(f"[hotspots] {key}: skip (need ≥100 incidents, got {0 if df is None else len(df)})")
        return None

    print(f"[hotspots] {key}: {len(df)} incidents")

    train_end = _pick_train_end(df)
    if train_end is None:
        # Not enough temporal spread → treat it all as training
        bundle = th.from_tidycop(
            df,
            cell_size_m=cfg["cell_size_m"],
            bandwidth_m=cfg["bandwidth_m"],
        )
        print(f"[hotspots] {key}: no split (short window), fitting on full set")
    else:
        bundle = th.from_tidycop(
            df,
            train_end=train_end.isoformat(),
            cell_size_m=cfg["cell_size_m"],
            bandwidth_m=cfg["bandwidth_m"],
        )
        print(
            f"[hotspots] {key}: split @ {train_end.date()} "
            f"train={bundle.metadata['train_rows']} test={bundle.metadata['test_rows']}"
        )

    if bundle.y_train.sum() == 0:
        print(f"[hotspots] {key}: no training targets in grid, skipping")
        return None

    # KDE from scipy comes out in the 1e-10 range for city-scale
    # grids — rescale to something the RF can actually split on.
    # Log1p keeps zeros as zeros and compresses the heavy tail.
    def _rescale(s):
        v = s.to_numpy(dtype=float)
        if v.max() > 0:
            v = v / v.max()
        return np.log1p(v * 1000.0)

    # Add centroid X/Y and lagged train count as features (Wheeler
    # 2020: XY coords are legitimate when we're forecasting the
    # same city we trained on).
    # Compute centroids in a metric CRS to silence the geographic-
    # CRS warning and get real metres, then use whatever units the
    # RF wants — relative ordering is what matters here.
    metric_grid = bundle.grid.to_crs(3857)
    centroids = metric_grid.geometry.centroid
    feature_matrix = bundle.features.copy()
    feature_matrix["kde_train"] = _rescale(feature_matrix["kde_train"])
    feature_matrix["cent_x"] = centroids.x.to_numpy()
    feature_matrix["cent_y"] = centroids.y.to_numpy()
    feature_matrix["train_count"] = bundle.y_train.to_numpy()

    # Train on the enriched features
    model = th.HotspotForest(
        n_estimators=400,
        max_depth=None,
        min_samples_leaf=5,
        random_state=42,
    )
    model.fit(feature_matrix, bundle.y_train)

    # For inference, refresh KDE against *all* rows so the risk
    # surface reflects "now", not just the training slice.
    all_points = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(
            df["std_longitude"].dropna().to_numpy(),
            df["std_latitude"].dropna().to_numpy(),
        ),
        crs="EPSG:4326",
    )
    if len(all_points) > 0:
        current_kde = th.kernel_density(
            bundle.grid, all_points, bandwidth_m=cfg["bandwidth_m"]
        )
        infer_features = feature_matrix.copy()
        infer_features["kde_train"] = _rescale(current_kde)
    else:
        infer_features = feature_matrix

    pred = np.asarray(model.predict(infer_features))
    risk = _normalize_risk(pred)

    # Report a validation number if we had a test split
    metrics: dict = {}
    if bundle.y_test is not None and bundle.y_test.sum() > 0:
        try:
            pai = th.predictive_accuracy_index(
                bundle.y_test.to_numpy(),
                pred,
                area_pct=cfg.get("top_pct", 0.10),
            )
            metrics["pai"] = float(pai)
            print(f"[hotspots] {key}: PAI@{int(cfg.get('top_pct', 0.10)*100)}% = {pai:.2f}")
        except Exception as e:  # noqa: BLE001
            print(f"[hotspots] {key}: PAI failed ({e})")

    # Ensure WGS84 for Leaflet consumption, then keep only the
    # top ~10% of positive-risk cells so the overlay stays
    # compact and reads as "where things are hot" instead of
    # "every cell in the grid."
    grid = bundle.grid.to_crs("EPSG:4326").copy()
    grid["risk_raw"] = risk           # global 0..1 (max-normalized)
    grid["pred_count"] = pred          # RF raw prediction (≈ incidents/cell)
    positive = grid[grid["risk_raw"] > 0].copy()
    if len(positive) == 0:
        print(f"[hotspots] {key}: no positive-risk cells, skipping")
        return None
    top_n = max(1, int(len(positive) * 0.10))
    hot = positive.nlargest(top_n, "pred_count").copy()
    # Rank-scale the emitted subset so the map has visible contrast
    # even when the RF gives many top cells identical predictions.
    # See _rank_scale for why this matters.
    hot["risk"] = _rank_scale(hot["pred_count"].to_numpy())
    # Integer rank (1 = hottest) for the popup.
    hot = hot.sort_values("risk", ascending=False).reset_index(drop=True)
    hot["rank"] = np.arange(1, len(hot) + 1)
    n_hot = len(hot)
    print(f"[hotspots] {key}: emitting top {n_hot} of {len(positive)} positive cells")

    features = []
    for _, row in hot.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "cell_id": int(row["cell_id"]),
                "risk": round(float(row["risk"]), 4),
                "rank": int(row["rank"]),
                "rank_of": n_hot,
                "pred_count": round(float(row["pred_count"]), 3),
            },
            "geometry": mapping(geom),
        })

    payload = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "city": city["name"],
            "slug": slug,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cell_size_m": cfg["cell_size_m"],
            "bandwidth_m": cfg["bandwidth_m"],
            "grid_shape": "square",
            "model": "RandomForestRegressor",
            "n_train": bundle.metadata["train_rows"],
            "n_test": bundle.metadata["test_rows"],
            "n_cells_total": int(len(grid)),
            "n_cells_hot": len(features),
            "metrics": metrics,
            "notes": (
                "Cells shown are the top 10% of the grid by RF-predicted "
                "incident count. `pred_count` is the raw model output. "
                "`risk` is a rank-based 0..1 recomputed on this subset so "
                "the map has visible contrast (RF predictions on aggregated "
                "counts often tie many top cells). `rank`/`rank_of` are the "
                "cell's position among displayed cells (1 = hottest). "
                "Training window is ~2/3 of the fetched data by date; "
                "inference re-scores against KDE of the full window."
            ),
        },
    }
    return payload


def main() -> int:
    out_summary = []
    for city in CITIES:
        key = city["key"]
        cfg = HOTSPOT_CONFIG.get(key)
        if not cfg:
            continue
        try:
            payload = predict_city(city, cfg)
        except Exception as e:  # noqa: BLE001
            print(f"[hotspots] {key}: ERROR {e}", file=sys.stderr)
            import traceback; traceback.print_exc(file=sys.stderr)
            continue
        if payload is None:
            continue
        out_path = DATA_DIR / f"{city['slug']}_hotspots.geojson"
        out_path.write_text(json.dumps(payload, separators=(",", ":")))
        print(f"[hotspots] {key}: wrote {out_path.name} ({len(payload['features'])} cells)")
        out_summary.append({
            "slug": city["slug"],
            "cells": len(payload["features"]),
            "metrics": payload["properties"].get("metrics", {}),
        })

    print(f"[hotspots] done: {len(out_summary)} cities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
