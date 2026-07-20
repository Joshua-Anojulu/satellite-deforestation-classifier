"""Within-frontier deforestation-risk study.

This package is deliberately separate from :mod:`deforestation`: the detector
paper must remain reproducible, while this study uses a different cloud mask,
grid, outcome, feature support, model family, and sampling design.
"""

from .config import FEATURE_YEARS, SEED

__all__ = ["FEATURE_YEARS", "SEED"]

