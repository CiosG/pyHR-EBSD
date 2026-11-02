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

BCC_MATERIAL_KEYS = frozenset({
    "chromium", "iron_bcc", "lithium", "molybdenum", "niobium",
    "potassium", "rubidium", "sodium", "tungsten", "vanadium",
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
    systems.create_dataset("active", data=np.ones(18, dtype=np.bool_))
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


def bcc_system_records() -> dict[str, np.ndarray]:
    """Return the 48 conventional BCC slip systems.

    The families are ``{110}<111>`` (12), ``{112}<111>`` (12), and
    ``{123}<111>`` (24).  ``line_direction`` stores the crystallographic slip
    direction, not a claim that every dislocation is screw; the actual line
    character and activity must be selected by the GND model or experiment.
    """
    directions = ((1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1))

    def unique_planes(values: tuple[int, int, int]) -> list[tuple[int, int, int]]:
        result: set[tuple[int, int, int]] = set()
        from itertools import permutations, product
        for permutation in set(permutations(values)):
            for signs in product((-1, 1), repeat=3):
                vector = tuple(a * b for a, b in zip(permutation, signs))
                first = next(value for value in vector if value)
                if first < 0:
                    vector = tuple(-value for value in vector)
                result.add(vector)
        return sorted(result)

    families = (("110", (1, 1, 0)), ("112", (1, 1, 2)),
                ("123", (1, 2, 3)))
    names: list[str] = []
    kinds: list[str] = []
    burgers: list[np.ndarray] = []
    lines: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    family_names: list[str] = []
    for family, values in families:
        for plane in unique_planes(values):
            normal = np.asarray(plane, dtype=float)
            normal /= np.linalg.norm(normal)
            for direction in directions:
                d = np.asarray(direction, dtype=float)
                if abs(np.dot(plane, direction)) > 0:
                    continue
                names.append(
                    f"({plane[0]}{plane[1]}{plane[2]})"
                    f"[{direction[0]}{direction[1]}{direction[2]}] {family}"
                )
                kinds.append("slip")
                burgers.append(d / 2.0)
                lines.append(d / np.linalg.norm(d))
                normals.append(normal)
                family_names.append(f"{{{family}}}<111>")
    result = {
        "names": np.asarray(names, dtype=object),
        "kind": np.asarray(kinds, dtype=object),
        "family": np.asarray(family_names, dtype=object),
        "burgers_fractional": np.asarray(burgers, dtype=float),
        "line_direction": np.asarray(lines, dtype=float),
        "plane_normal": np.asarray(normals, dtype=float),
    }
    counts = {family: family_names.count(f"{{{family}}}<111>") for family, _ in families}
    if counts != {"110": 12, "112": 12, "123": 24}:
        raise AssertionError(f"unexpected BCC family counts: {counts}")
    return result


def write_bcc_systems(group: h5py.Group) -> None:
    """Create or replace the conventional BCC slip-system group."""
    if "slip_systems" in group:
        del group["slip_systems"]
    records = bcc_system_records()
    systems = group.create_group("slip_systems")
    string_type = h5py.string_dtype("utf-8")
    systems.create_dataset("name", data=np.asarray(records["names"], dtype=string_type))
    for key in ("kind", "family"):
        systems.create_dataset(key, data=np.asarray(records[key], dtype=string_type))
    for key in ("burgers_fractional", "line_direction", "plane_normal"):
        systems.create_dataset(key, data=records[key])
    systems.create_dataset("active", data=np.ones(48, dtype=np.bool_))
    systems.attrs["family"] = "BCC {110}<111> + {112}<111> + {123}<111>"
    systems.attrs["system_count"] = 48
    systems.attrs["family_counts"] = "{110}<111>:12; {112}<111>:12; {123}<111>:24"
    systems.attrs["coordinate_convention"] = (
        "cubic crystal axes; burgers_fractional is in unit-cell fractions; "
        "line_direction is the crystallographic slip direction"
    )
    systems.attrs["burgers_unit"] = "fractional cubic unit-cell coordinates"
    systems.attrs["activity_note"] = (
        "All systems are candidates. Activity is not inferred from elastic constants; "
        "use a phase/stress criterion or a sparse GND fit to select active systems."
    )
    systems.attrs["source"] = (
        "Conventional BCC slip families generated from Miller indices; "
        "no material-specific CRSS values are implied"
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
        for key in sorted(BCC_MATERIAL_KEYS):
            if key not in materials:
                continue
            write_bcc_systems(materials[key])
            materials[key].attrs["slip_system_family"] = "bcc_110_112_123_111"
            updated.append(key)
        file.attrs["schema_version"] = "1.1"
        file.attrs["slip_systems_schema"] = (
            "material/slip_systems datasets; see each group coordinate_convention"
        )
    return updated


def set_system_activity(path: str, material: str, indices: list[int], active: bool) -> None:
    """Set the active flag for selected slip-system rows in one material."""
    with h5py.File(path, "r+") as file:
        systems = file["materials"][material]["slip_systems"]
        flags = systems["active"][:]
        if any(index < 0 or index >= len(flags) for index in indices):
            raise IndexError(f"slip-system index outside 0..{len(flags) - 1}")
        flags[indices] = active
        systems["active"][:] = flags


def active_system_mask(group: h5py.Group) -> np.ndarray:
    """Return the boolean activity mask, defaulting old databases to all true."""
    systems = group["slip_systems"]
    if "active" not in systems:
        return np.ones(systems["name"].shape[0], dtype=np.bool_)
    flags = np.asarray(systems["active"], dtype=np.bool_)
    if flags.ndim != 1 or flags.shape[0] != systems["name"].shape[0]:
        raise ValueError("slip-system active mask has the wrong length")
    return flags

