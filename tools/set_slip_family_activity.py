"""Enable or disable a complete slip-system family in materials.h5."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pyhrebsd.slip_systems import set_family_activity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("material", help="material key, e.g. vanadium")
    parser.add_argument("family", help="family label, e.g. {110}<111>")
    parser.add_argument("--path", type=Path, default=Path(__file__).resolve().parents[1] / "pyhrebsd" / "materials.h5")
    parser.add_argument("--active", action="store_true", help="enable the complete family")
    parser.add_argument("--inactive", action="store_true", help="disable the complete family")
    args = parser.parse_args()
    if args.active == args.inactive:
        parser.error("choose exactly one of --active or --inactive")
    set_family_activity(str(args.path), args.material, args.family, args.active)
    state = "active" if args.active else "inactive"
    print(f"Set {args.material} family {args.family} to {state}")


if __name__ == "__main__":
    main()
