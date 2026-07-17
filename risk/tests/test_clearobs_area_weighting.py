"""Regression: clearobs_native_statistics must area-weight the CORRECT native pixels.

The L2 clear-observation gate decides whether a site enters the cohort at all, and
AMENDMENT-3 already showed how expensive a wrong clear-observation number is: a sign
error nearly declared the study unviable. The counts are 20 m native and must never be
bilinearly interpolated, so `_area_weighted_values` windows them by exact rectangle
overlap.

`_area_weighted_values(array, support, transform, bounds)` needs the geotransform of
the array it is windowing. Both call sites in `clearobs_native_statistics` originally
omitted it and passed the projected bounds into the `transform` slot, so the whole
prepare path raised TypeError the first time it ran. Nothing caught it because no test
exercised prepare_site.

This test pins the behaviour with a raster whose answer is computable by hand: a
column gradient where selecting the wrong window yields a visibly different median,
so a silently mis-placed window fails here rather than in the cohort numbers.
"""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from risk.prepare import clearobs_native_statistics

# 4x4 pixels, 1 unit each, covering x 0..4 / y 0..4 in EPSG:4326.
# Every CRS in the fixture is EPSG:4326 so the reprojections are identities and the
# test isolates the windowing/area-weighting, which is what broke.
CRS = "EPSG:4326"
TRANSFORM = from_origin(0, 4, 1, 1)
COUNTS = np.array(
    [
        [1, 2, 3, 4],
        [1, 2, 3, 4],
        [1, 2, 3, 4],
        [1, 2, 3, 4],
    ],
    dtype=np.float32,
)


def _write_counts(tmp_path):
    path = tmp_path / "2020_clearobs.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1,
        dtype="float32", crs=CRS, transform=TRANSFORM,
    ) as destination:
        destination.write(COUNTS, 1)
    return path


def test_clearobs_statistics_weight_the_pixels_the_bounds_actually_cover(tmp_path):
    path = _write_counts(tmp_path)
    eligible = np.ones((4, 4), dtype=bool)
    # Cell A covers only column 0 (value 1); cell B only column 3 (value 4).
    cell_bounds = np.array([[0.0, 0.0, 1.0, 1.0], [3.0, 3.0, 4.0, 4.0]])
    # Analysis box covers columns 2--3 only: values 3 and 4, so the median is 3.
    # If the window were mis-placed onto columns 0--1 this would be 1 instead.
    analysis_bounds_wgs84 = (2.0, 0.0, 4.0, 4.0)

    site_median, cell_medians, on_hansen = clearobs_native_statistics(
        path, eligible, TRANSFORM, CRS, cell_bounds, CRS, analysis_bounds_wgs84,
    )

    assert site_median == 3.0
    np.testing.assert_array_equal(cell_medians, np.array([1.0, 4.0]))
    # The Hansen-grid average is an identity reprojection here.
    np.testing.assert_allclose(on_hansen, COUNTS, rtol=0, atol=1e-6)


def test_clearobs_statistics_ignore_pixels_outside_the_eligible_support(tmp_path):
    """Support is a fixed-support firewall: ineligible pixels must not vote."""
    path = _write_counts(tmp_path)
    eligible = np.ones((4, 4), dtype=bool)
    eligible[:, 3] = False  # drop the value-4 column from the support

    site_median, cell_medians, _ = clearobs_native_statistics(
        path, eligible, TRANSFORM, CRS,
        np.array([[3.0, 3.0, 4.0, 4.0]]), CRS,
        (2.0, 0.0, 4.0, 4.0),
    )

    # Column 3 is out of support, so only column 2 (value 3) counts.
    assert site_median == 3.0
    # The only cell sits entirely on the excluded column -> no eligible pixels at all.
    assert np.isnan(cell_medians[0])
