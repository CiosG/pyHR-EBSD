"""Re-reference a completed homography run without re-correlating patterns."""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
from .analysis import Material
from .h5oina import H5OINAReader
from .homography import deformation_from_homography

def _matrix(row, prefix):
    return np.array([[float(row[f"{prefix}_{i}{j}"]) for j in range(1,4)] for i in range(1,4)])

def rereference_homography(input_dir, new_reference_index, output_dir):
    input_dir=Path(input_dir); output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=False)
    config=json.loads((input_dir/"run_config.json").read_text(encoding="utf-8"))
    with (input_dir/"scan_results.csv").open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
    if not rows or "H_11" not in rows[0]: raise ValueError("re-referencing requires a homography scan_results.csv")
    target=next((r for r in rows if int(r["scan_index"])==int(new_reference_index)),None)
    if target is None: raise ValueError("new reference index is not present in the completed run")
    input_file=Path(config["input_file"]); pattern_type=config.get("pattern_type","processed")
    pc_source=config.get("h5_pc_source","ebsd")
    if input_file.suffix.lower() != ".h5oina": raise ValueError("automatic deformation re-reference currently supports H5OINA runs")
    material_db=config.get("material_database") or str(Path(__file__).with_name("materials.h5"))
    material=Material.from_hdf5(material_db,config.get("material_name","silicon"))
    with H5OINAReader(input_file,pattern_type=pattern_type,pc_source=pc_source) as reader:
        side=min(reader.height,reader.width); orientation_cache={}
        h_ref=_matrix(target,"H")
        new=[]
        for row in rows:
            idx=int(row["scan_index"]); h_old=_matrix(row,"H")
            h_new=h_old @ np.linalg.inv(h_ref)
            g=orientation_cache.setdefault(idx,reader.orientation(idx))
            ref_pc=tuple(float(target[f"pattern_center_{a}"]) for a in ("x","y","z"))
            scan_pc=tuple(float(row[f"pattern_center_{a}"]) for a in ("x","y","z"))
            fmat,strain,stress,g=deformation_from_homography(
                h_new,ref_pc,scan_pc,g,np.deg2rad(float(config["sample_tilt_degrees"])),
                np.deg2rad(float(config["camera_elevation_degrees"])),material,side,
                config.get("phosphor_to_sample"),config.get("mechanical_constraint","traction_free"))
            out=dict(row); out["reference_index"]=int(new_reference_index)
            out.update({f"H_{i+1}{j+1}":float(h_new[i,j]) for i in range(3) for j in range(3)})
            for prefix,m in (("F",fmat),("strain",strain),("stress_gpa",stress),
                             ("strain_sample",g.T@strain@g),("stress_sample_gpa",g.T@stress@g),
                             ("deviatoric_strain_sample",g.T@strain@g-np.eye(3)*np.trace(strain)/3)):
                out.update({f"{prefix}_{i+1}{j+1}":float(m[i,j]) for i in range(3) for j in range(3)})
            new.append(out)
    with (output_dir/"scan_results.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(new[0])); w.writeheader(); w.writerows(new)
    config["reference_index"]=int(new_reference_index); config["rereferenced_from"] = str(input_dir)
    (output_dir/"run_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    return output_dir


def rereference_strain(input_dir, new_reference_index, output_dir):
    """Subtract a stored reference strain from every point without refitting."""
    input_dir=Path(input_dir); output_dir=Path(output_dir)
    if output_dir.exists(): raise FileExistsError(output_dir)
    output_dir.mkdir(parents=True)
    with (input_dir/"scan_results.csv").open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    if not rows: raise ValueError("scan_results.csv is empty")
    target=next((r for r in rows if int(r["scan_index"])==int(new_reference_index)),None)
    if target is None: raise ValueError("new reference index is not present")
    def matrix(row,prefix):
        return np.array([[float(row[f"{prefix}_{i}{j}"]) for j in range(1,4)] for i in range(1,4)])
    ref=matrix(target,"strain_sample")
    out=[]
    for row in rows:
        item=dict(row); strain=matrix(row,"strain_sample")-ref
        dev=strain-np.eye(3)*np.trace(strain)/3
        item["reference_index"]=int(new_reference_index)
        item["strain_rereferenced"]=True
        for prefix,m in (("strain_sample",strain),("deviatoric_strain_sample",dev)):
            item.update({f"{prefix}_{i+1}{j+1}":float(m[i,j]) for i in range(3) for j in range(3)})
        for i in range(1,4):
            key=f"rotation_sample_{i}_mrad"
            if key in item and target.get(key,"") not in ("",None):
                item[key]=float(item[key])-float(target[key])
        out.append(item)
    with (output_dir/"scan_results.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    config={}
    if (input_dir/"run_config.json").exists():
        config=json.loads((input_dir/"run_config.json").read_text(encoding="utf-8"))
    config["reference_index"]=int(new_reference_index); config["strain_rereferenced_from"]=str(input_dir)
    config["strain_rereference_note"]="Stored relative sample strains were subtracted; stresses are retained from the original run."
    (output_dir/"run_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    return output_dir
