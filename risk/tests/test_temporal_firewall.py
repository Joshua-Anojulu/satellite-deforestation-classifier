import numpy as np
from affine import Affine

import risk.hansen as hansen
from risk.frame import Candidate, screen_candidate


def test_frame_reader_never_exposes_lossyear_above_20(monkeypatch):
    raw_loss = np.array([[0, 1, 16], [20, 21, 24]], dtype=np.uint8)
    transform = Affine(0.00025, 0, 0, 0, -0.00025, 1)

    def fake_read(band, tile, bounds, opener):
        if band == "lossyear":
            values = raw_loss.copy()
        elif band == "treecover2000":
            values = np.full(raw_loss.shape, 100, dtype=np.uint8)
        else:
            values = np.ones(raw_loss.shape, dtype=np.uint8)
        return values, transform, "EPSG:4326"

    monkeypatch.setattr(hansen, "_read_tile_band", fake_read)
    values, _, _ = hansen._read_frame_tile("00N_000E", (0, 0, 1, 1), opener=object())
    assert "lossyear" not in values
    assert values["prior"].dtype == np.bool_
    assert values["recent"].dtype == np.bool_
    assert values["prior"].tolist() == [[False, True, True], [True, False, False]]
    assert values["recent"].tolist() == [[False, False, True], [True, False, False]]


def test_frame_activity_shares_use_valid_land_not_treecover_universe():
    transform = Affine(0.5, 0, 0, 0, -0.5, 1)
    window = hansen.FrameHansenWindow(
        datamask=np.ones((2, 2), dtype=np.uint8),
        # The one loss is deliberately on a <30 treecover pixel. L13.3 still
        # counts it in cumulative/recent loss divided by valid land.
        treecover2000=np.array([[0, 100], [100, 100]], dtype=np.uint8),
        prior_loss_2001_2020=np.array([[True, False], [False, False]]),
        recent_loss_2016_2020=np.array([[True, False], [False, False]]),
        transform=transform, crs="EPSG:4326",
    )
    candidate = Candidate("x", "amazon_moist", 0.5, 0.5, 0, 0, 1, 1)
    screened = screen_candidate(candidate, reader=lambda _: window)
    assert screened is not None
    assert screened.cumulative_loss_share == 0.25
    assert screened.recent_loss_share == 0.25
