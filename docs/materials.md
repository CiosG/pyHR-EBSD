# Elastic-material database

PyHREBSD stores single-crystal stiffness tensors in `pyhrebsd/materials.h5`.
Each `/materials/<key>/stiffness_voigt_gpa` dataset is a symmetric 6 by 6
matrix in GPa, using Voigt order `11,22,33,23,13,12`. The complete matrices
allow the stress calculation to support cubic, hexagonal, tetragonal,
trigonal, orthorhombic, and monoclinic materials without reducing them to
three elastic constants.

The root datasets `/voigt_axis_labels` and `/component_labels` describe every
matrix position. `/component_labels` has the same 6 by 6 shape and contains
`C11` through `C66`; for example, matrix cells `[0,0]`, `[0,1]`, `[3,3]`, and
`[5,5]` are respectively `C11`, `C12`, `C44`, and `C66`. The same row and
column labels are also stored as attributes on every stiffness dataset.

Select a material in `run_pyhrebsd.py` with:

```python
"material_database": "pyhrebsd/materials.h5",
"material_name": "silicon",
```

The key or the human-readable material name may be used. List keys with
`Material.list_hdf5("pyhrebsd/materials.h5")`.

## Provenance and verification

The distributed database deliberately excludes 101 rows from the supplied
`Materials.txt` whose individual provenance could not be verified online. It
contains 33 source materials matched unambiguously to NIST, six additional
NIST elements, and five phase-specific experimental semiconductor records:
wurtzite GaN, wurtzite AlN, 3C-SiC, 4H-SiC, and 6H-SiC. There is no copy of the
omitted matrices under a legacy group.

Preferred elemental values that could be matched unambiguously were checked
against Tables 7.1 and 7.2 of:

H. M. Ledbetter and S. D. Kim, *Monocrystal Elastic Constants and Derived
Properties of the Cubic and the Hexagonal Elements*, Handbook of Elastic
Properties of Solids, Liquids, and Gases, Vol. II (2001),
doi:10.1016/B978-012445760-7/50033-2. The publication is available from
[NIST](https://www.nist.gov/publications/monocrystal-elastic-constants-and-deprived-properties-cubic-and-hexagonal-elements).

All records have status `verified_reference`. Measurement uncertainties are
stored in `stiffness_uncertainty_gpa` beside the stiffness matrix when they are
reported by the source.

Complete bibliographic records are stored under `/references/<reference_id>`.
Each material contains `reference_id` and `reference_path` attributes pointing
to the applicable record. The title, DOI, and URL are repeated on the material
group so a single group remains self-describing when exported.

Every record stores `verification_status`, `reference_title`, `reference_url`,
`reference_doi`, and `temperature_k` attributes. `temperature_k` is NaN where
the cited compilation or legacy row does not identify a single measurement
temperature. Elastic constants vary with temperature, phase, purity, magnetic
state, and whether a measurement is adiabatic or isothermal, so these metadata
are part of the material definition.

A flat, reviewable inventory of every current record is provided in
[`materials_audit.csv`](materials_audit.csv).

Rebuild the database after changing the source table with:

```powershell
python tools/build_materials_h5.py ..\Materials.txt pyhrebsd\materials.h5
```

## Slip systems

The FCC records listed below contain a `/slip_systems` group with the standard
perfect-dislocation family `a/2<110>{111}`: 12 edge systems and 6 unique screw
directions. The Burgers vectors are stored as fractional cubic unit-cell
coordinates (`[1, -1, 0] / 2`), while line directions and edge plane normals
are normalized vectors. A screw system has a zero plane-normal vector because
its slip plane is not unique from the measured curvature alone.

The assigned FCC keys are `aluminium`, `calcium`, `copper`, `gold`, `iridium`,
`iron_fcc`, `lead`, `nickel`, `platinum`, `rhodium`, `silver`, `strontium`,
and `thorium`. Diamond-cubic materials and 3C-SiC are intentionally not
silently classified as metallic FCC; they need their own phase-specific family.

To reapply the assignment to a copied database:

```powershell
python tools/add_fcc_slip_systems.py path\to\materials.h5
```

The BCC records additionally contain the conventional candidate families
`{110}<111>`, `{112}<111>`, and `{123}<111>` (12, 12, and 24 systems). These
are candidate geometries, not a declaration that all systems are active. The
database does not contain critical resolved shear stresses, so activity must
be selected from the phase, loading state, or a constrained/sparse GND fit.

Every slip-system group has an `active` boolean dataset, initially set to
`True`. Systems with `active=False` must be excluded by consumers. For example,
to disable rows 0 and 3 of nickel:

```powershell
python tools/set_slip_system_activity.py nickel 0 3 --inactive
```

The activity flag is deliberately separate from the crystallographic family:
turning a system off records an analysis choice without deleting its geometry.

Families can be switched as a whole using `family_active`. For example, to
disable every `{112}<111>` BCC system for vanadium:

```powershell
python tools/set_slip_family_activity.py vanadium "{112}<111>" --inactive
```

The analysis mask combines the per-system `active` flags with `family_active`,
so a disabled family cannot contribute any of its systems.

The semiconductor records also contain `/dislocations`. This group stores
edge, screw, mixed, and (for 3C-SiC) Shockley-partial candidates with their
Burgers-vector notation, line-character description, linked slip family,
activity flag, confidence, and literature reference. Mixed and curved lines
are intentionally textual rather than assigned an arbitrary Cartesian line
vector. The GND solver still needs a phase-specific conversion into numerical
line vectors before using these entries in an optimization.

The semiconductor phases use `/slip_families` because their hexagonal systems
are stored explicitly in Miller--Bravais notation. Their `name`,
`plane_indices`, `direction_indices`, `burgers_vector`, `reference`, and
`active` datasets preserve the literature notation without silently applying a
cubic coordinate conversion.
