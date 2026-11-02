"""Enable or disable selected slip-system rows in a materials HDF5 file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pyhrebsd.slip_systems import set_system_activity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("material", help="material key, e.g. nickel")
    parser.add_argument("indices", nargs="+", type=int, help="zero-based system rows")
    parser.add_argument("--path", type=Path, default=Path(__file__).resolve().parents[1] / "pyhrebsd" / "materials.h5")
    parser.add_argument("--active", action="store_true", help="enable the selected systems")
    parser.add_argument("--inactive", action="store_true", help="disable the selected systems")
    args = parser.parse_args()
    if args.active == args.inactive:
        parser.error("choose exactly one of --active or --inactive")
    set_system_activity(str(args.path), args.material, args.indices, args.active)
    state = "active" if args.active else "inactive"
    print(f"Set {args.material} systems {args.indices} to {state}")


if __name__ == "__main__":
    main()
