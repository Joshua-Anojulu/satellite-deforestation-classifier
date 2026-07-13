"""Deterministic four-month CHIRPS windows fixed before imagery download."""

from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np

from .config import assert_feature_years


def driest_four_month_window(monthly_precipitation: Iterable[float]) -> int:
    """Return the 1-based start month; circular ties go to the earliest month."""
    values = np.asarray(tuple(monthly_precipitation), dtype=np.float64)
    if values.shape != (12,) or not np.isfinite(values).all():
        raise ValueError("Expected twelve finite CHIRPS climatology values.")
    totals = np.array([sum(values[(start + offset) % 12] for offset in range(4))
                       for start in range(12)])
    minimum = totals.min()
    return int(np.flatnonzero(np.isclose(totals, minimum, rtol=0.0, atol=1e-12))[0] + 1)


def feature_period(feature_year: int, start_month: int) -> tuple[str, str]:
    """Build an inclusive period while enforcing the <=2020 imagery firewall.

    For a circular window crossing December, the nominal feature year is the
    year in which the window ends (e.g. Nov 2019--Feb 2020).  This is the only
    interpretation that satisfies both L1's circular calendar rule and L10's
    assertion that feature imagery never extends into 2021.
    """
    assert_feature_years((feature_year,))
    if not 1 <= start_month <= 12:
        raise ValueError(start_month)
    end_month = ((start_month - 1 + 3) % 12) + 1
    crosses_year = end_month < start_month
    start_year = feature_year - 1 if crosses_year else feature_year
    end_year = feature_year
    start = date(start_year, start_month, 1)
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    if end.year > 2020:
        raise AssertionError("Feature period crossed the 2020 temporal firewall.")
    return start.isoformat(), end.isoformat()


def chirps_point_climatology(netcdf_path: str | Path, lon: float, lat: float) -> np.ndarray:
    """Read CHIRPS v2.0 monthly values for 1991--2020 at one box centre."""
    import xarray as xr

    with xr.open_dataset(netcdf_path) as dataset:
        variable_name = "precip" if "precip" in dataset.data_vars else next(iter(dataset.data_vars))
        point = dataset[variable_name].sel(longitude=lon, latitude=lat, method="nearest")
        point = point.sel(time=slice("1991-01-01", "2020-12-31"))
        if point.sizes.get("time") != 360:
            raise ValueError(f"CHIRPS subset must contain exactly 360 months, got {point.sizes.get('time')}")
        # Long-term totals and means rank windows identically.  Sum preserves the
        # literal wording in L1.
        values = point.groupby("time.month").sum("time", skipna=False).values
    if np.asarray(values).shape != (12,):
        raise ValueError("Unexpected CHIRPS coordinate layout.")
    return np.asarray(values, dtype=np.float64)

