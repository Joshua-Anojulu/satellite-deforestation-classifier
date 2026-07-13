"""CLI that freezes L1 windows and applies L13.4/L13.5b before downloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import FRAME_DIR
from .frame import finalize_analysis_sites


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize frame + screened legacy sites before imagery.")
    parser.add_argument("selected_sites", type=Path)
    parser.add_argument("chirps", type=Path)
    parser.add_argument("--output", type=Path, default=FRAME_DIR / "analysis_sites.json")
    args = parser.parse_args()
    frame = json.loads(args.selected_sites.read_text(encoding="utf-8"))
    result = finalize_analysis_sites(frame, args.chirps, args.output)
    print(f"Finalized {len(result['sites'])} sites -> {args.output}")


if __name__ == "__main__":
    main()
