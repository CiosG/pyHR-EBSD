"""Crystallographic slip-system families used by PyHREBSD.

The FCC family is stored without assuming a material lattice parameter.  The
Burgers vectors are therefore fractional cubic unit-cell coordinates; a
consumer converts them to metres by multiplying by the material's lattice
parameter.  This keeps the material database independent of a particular
temperature or lattice-parameter source.
"""

from __future__ import annotations

from typing import Any

import h5py
import numpy as np


# These records are cubic FCC phases, not merely materials whose crystal
# system is reported as cubic.  Diamond-cubic Si/Ge/C and 3C-SiC are excluded:
# their slip geometry needs a separate phase family and should not be silently
# treated as metallic FCC.
FCC_MATERIAL_KEYS = frozenset({
    "aluminium", "calcium", "copper", "gold", "iridium", "iron_fcc",
    "lead", "nickel", "platinum", "rhodium", "silver", "strontium",
    "thorium",
})


def fcc_system_records() -> dict[str, np.ndarray]:
    """Return the 18 standard FCC ``a/2<110>{111}`` systems.

    The result contains arrays ``names``, ``kind``, ``burgers_fractional``,
    ``line_direction`` and ``plane_normal``.  Edge planes are normalized and
    screw planes are represented by zeros because a screw dislocation belongs
    to two equivalent {111} planes and has no unique plane assignment here.
    """
    planes = ((1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1))
    directions: set[tuple[int, int, int]] = set()
    for zero in range(3):
        others = [i for i in range(3) if i != zero]
        for sign in (-1, 1):
            vector = np.zeros(3, dtype=int)
            vector[others[0]], vector[others[1]] = 1, sign
            directions.add(tuple(int(value) for value in vector))
    directions = sorted(directions)

    names: list[str] = []
    kinds: list[str] = []
    burgers: list[np.ndarray] = []
    lines: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    for plane in planes:
        normal = np.asarray(plane, dtype=float)
        normal /= np.linalg.norm(normal)
        for direction in directions:
            d = np.asarray(direction, dtype=float)
            if np.dot(plane, direction) != 0:
                continue
            line = np.cross(normal, d)
            line /= np.linalg.norm(line)
            names.append(
                f"({plane[0]}{plane[1]}{plane[2]})"
                f"[{direction[0]}{direction[1]}{direction[2]}] edge"
            )
            kinds.append("edge")
            burgers.append(d / 2.0)
            lines.append(line)
            normals.append(normal)

    for direction in directions:
        d = np.asarray(direction, dtype=float)
        d /= np.linalg.norm(d)
        names.append(f"<{direction[0]}{direction[1]}{direction[2]}> screw")
        kinds.append("screw")
        burgers.append(np.asarray(direction, dtype=float) / 2.0)
        lines.append(d)
        normals.append(np.zeros(3, dtype=float))

    result = {
        "names": np.asarray(names, dtype=object),
        "kind": np.asarray(kinds, dtype=object),
        "burgers_fractional": np.asarray(burgers, dtype=float),
        "line_direction": np.asarray(lines, dtype=float),
        "plane_normal": np.asarray(normals, dtype=float),
    }
    if len(names) != 18 or sum(kind == "edge" for kind in kinds) != 12:
        raise AssertionError("FCC family must contain 12 edge and 6 screw systems")
    return result


def write_fcc_systems(group: h5py.Group) -> None:
    """Create or replace the ``slip_systems`` group in one material record."""
    if "slip_systems" in group:
        del group["slip_systems"]
    records = fcc_system_records()
    systems = group.create_group("slip_systems")
    string_type = h5py.string_dtype("utf-8")
    systems.create_dataset("name", data=np.asarray(records["names"], dtype=string_type))
    systems.create_dataset("kind", data=np.asarray(records["kind"], dtype=string_type))
    systems.create_dataset("burgers_fractional", data=records["burgers_fractional"])
    systems.create_dataset("line_direction", data=records["line_direction"])
    systems.create_dataset("plane_normal", data=records["plane_normal"])
    systems.attrs["family"] = "a/2<110>{111}"
    systems.attrs["system_count"] = 18
    systems.attrs["edge_system_count"] = 12
    systems.attrs["screw_system_count"] = 6
    systems.attrs["coordinate_convention"] = (
        "cubic crystal axes; burgers_fractional is in unit-cell fractions; "
        "line_direction and plane_normal are normalized Cartesian vectors"
    )
    systems.attrs["burgers_unit"] = "fractional cubic unit-cell coordinates"
    systems.attrs["screw_plane_convention"] = (
        "plane_normal is [0,0,0] because a screw direction belongs to two {111} planes"
    )
    systems.attrs["source"] = (
        "Standard FCC perfect-dislocation family generated from Miller indices; "
        "no material-specific CRSS or line-energy values are implied"
    )


def add_fcc_systems_to_file(path: str) -> list[str]:
    """Assign the FCC family to all selected FCC material records in an HDF5 file."""
    updated: list[str] = []
    with h5py.File(path, "r+") as file:
        materials = file["materials"]
        for key in sorted(FCC_MATERIAL_KEYS):
            if key not in materials:
                continue
            write_fcc_systems(materials[key])
            materials[key].attrs["slip_system_family"] = "fcc_a_over_2_110_111"
            updated.append(key)
        file.attrs["schema_version"] = "1.1"
        file.attrs["slip_systems_schema"] = (
            "material/slip_systems datasets; see each group coordinate_convention"
        )
    return updated

