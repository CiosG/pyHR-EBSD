"""Assign standard FCC and BCC slip systems to phases in materials.h5."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyhrebsd.slip_systems import add_fcc_systems_to_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", type=Path,
        default=Path(__file__).resolve().parents[1] / "pyhrebsd" / "materials.h5",
        help="materials.h5 to update (default: the package database)",
    )
    args = parser.parse_args()
    updated = add_fcc_systems_to_file(str(args.path))
    print(f"Updated {len(updated)} FCC/BCC phases in {args.path}")
    print("  " + ", ".join(updated))


if __name__ == "__main__":
    main()
