"""Static HTML/PDF reports for completed PyHREBSD runs."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

import numpy as np

def _rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def _float(row, key):
    try:
        value = float(row.get(key, ""))
        return value if np.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan

def _plot(rows, output, key, title, cmap="viridis"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = np.asarray([_float(r, "column") for r in rows])
    y = np.asarray([_float(r, "row") for r in rows])
    z = np.asarray([_float(r, key) for r in rows])
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    fig, ax = plt.subplots(figsize=(8, 6))
    if np.any(valid):
        width = int(np.nanmax(x[valid])) + 1
        height = int(np.nanmax(y[valid])) + 1
        image = np.full((height, width), np.nan, dtype=float)
        image[y[valid].astype(int), x[valid].astype(int)] = z[valid]
        shown = ax.imshow(image, origin="upper", interpolation="nearest", cmap=cmap)
        fig.colorbar(shown, ax=ax, label=key)
    ax.set_title(title); ax.set_xlabel("column"); ax.set_ylabel("row")
    ax.set_aspect("equal")
    fig.tight_layout(); fig.savefig(output, dpi=180); plt.close(fig)

def _hist(rows, output, keys):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    series=[]
    for key in keys:
        values=np.asarray([_float(r,key) for r in rows])
        values=values[np.isfinite(values)]
        if values.size: series.append((key,values))
    fig,ax=plt.subplots(figsize=(9,5.5))
    all_values=np.concatenate([v for _,v in series]) if series else np.asarray([])
    if all_values.size:
        low,high=np.percentile(all_values,[1.0,99.0])
        if not np.isfinite(low) or not np.isfinite(high) or low==high:
            low,high=float(np.min(all_values)),float(np.max(all_values))
        if low==high: high=low+1e-12
        for key,values in series:
            ax.hist(values,bins=120,range=(low,high),alpha=.45,label=key)
        ax.set_xlim(low,high)
        ax.set_title("Distributions (1st?99th percentile)")
    else:
        ax.set_title("Distributions")
    ax.set_xlabel("value"); ax.set_ylabel("points"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(output,dpi=180); plt.close(fig)

def _profile(rows, output, key):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups={}
    for r in rows:
        try: groups.setdefault(int(r["row"]), []).append(_float(r,key))
        except (KeyError,ValueError): pass
    y=sorted(groups); vals=[np.nanmean([v for v in groups[k] if np.isfinite(v)]) for k in y]
    fig,ax=plt.subplots(figsize=(8,4)); ax.plot(y,vals,".-"); ax.set_xlabel("row"); ax.set_ylabel(key); ax.set_title(f"Row profile: {key}"); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(output,dpi=160); plt.close(fig)

def _stats(rows):
    out=[]
    groups={"all":rows, "accepted":[r for r in rows if r.get("status")=="ok"], "rejected":[r for r in rows if r.get("status")!="ok"]}
    grain_ids={r.get("grain_id","") for r in rows if r.get("grain_id","") not in ("",None)}
    for gid in grain_ids: groups[f"grain_{gid}"]=[r for r in rows if r.get("grain_id")==gid]
    keys=["strain_sample_11","strain_sample_22","strain_sample_33","rotation_sample_1_mrad","rotation_sample_2_mrad","rotation_sample_3_mrad"]
    for name, subset in groups.items():
        item={"region":name,"points":len(subset)}
        for key in keys:
            a=np.asarray([_float(r,key) for r in subset]); a=a[np.isfinite(a)]
            if a.size: item[key]={"mean":float(np.mean(a)),"std":float(np.std(a)),"min":float(np.min(a)),"max":float(np.max(a))}
        out.append(item)
    return out

def generate_report(output_dir: str | Path, report_format: str = "html") -> Path:
    """Generate an HTML report and, when requested, a companion PDF."""
    output=Path(output_dir); csv_path=output/"scan_results.csv"
    if not csv_path.exists(): raise FileNotFoundError(csv_path)
    rows=_rows(csv_path); assets=output/"report_assets"; assets.mkdir(exist_ok=True)
    accepted_rows=[r for r in rows if r.get("status")=="ok"]
    plot_rows=accepted_rows if accepted_rows else rows
    config_path=output/"run_config.json"
    config=json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    plots=[]
    plot_specs=[
        ("rms_shift_error_pixels", "ROI RMS shift error"),
        ("znssd_rms", "Homography ZNSSD"),
        ("roi_znssd_rms", "ROI ZNSSD"),
        ("pc_sensitivity_strain_max", "PC sensitivity"),
        ("strain_sample_11", "E11"), ("strain_sample_12", "E12"),
        ("strain_sample_13", "E13"), ("strain_sample_22", "E22"),
        ("strain_sample_23", "E23"), ("strain_sample_33", "E33"),
        ("rotation_sample_1_mrad", "Rotation w1 (mrad)"),
        ("rotation_sample_2_mrad", "Rotation w2 (mrad)"),
        ("rotation_sample_3_mrad", "Rotation w3 (mrad)"),
    ]
    for key,title in plot_specs:
        if any(key in r and r.get(key) not in ("",None) for r in plot_rows):
            name=key+".png"; _plot(plot_rows,assets/name,key,title); plots.append((title, "report_assets/"+name))
    strain_keys=["strain_sample_11","strain_sample_12","strain_sample_13",
                 "strain_sample_22","strain_sample_23","strain_sample_33"]
    hist=assets/"strain_histogram.png"; _hist(plot_rows,hist,strain_keys); plots.append(("Strain histograms","report_assets/strain_histogram.png"))
    rotation_keys=["rotation_sample_1_mrad","rotation_sample_2_mrad","rotation_sample_3_mrad"]
    rhist=assets/"rotation_histogram.png"; _hist(plot_rows,rhist,rotation_keys); plots.append(("Rotation histograms","report_assets/rotation_histogram.png"))
    for key,title in [("strain_sample_11","E11 row profile"),
                      ("strain_sample_22","E22 row profile"),
                      ("strain_sample_33","E33 row profile"),
                      ("rotation_sample_1_mrad","w1 row profile"),
                      ("rotation_sample_2_mrad","w2 row profile"),
                      ("rotation_sample_3_mrad","w3 row profile")]:
        name=key+"_profile.png"; _profile(plot_rows,assets/name,key); plots.append((title,"report_assets/"+name))
    # Reuse the validated tensor-panel plotting style used by the previous
    # full-scan figures: quality mask, sample-axis rotation, shared scales,
    # and symmetric-log strain colors around zero.
    try:
        from plot_tensor_maps import KINDS, draw, load_result, shared_limit
        panel = load_result(csv_path, 90.0, mask_bad_fit=True)
        rotation_limit = shared_limit([panel["rotations"]], 99.5)
        strain_limit = shared_limit([panel["tensors"][kind] for kind in KINDS], 99.5)
        for kind in KINDS:
            panel_path = assets / f"{kind}_strain_rotations_symlog.png"
            draw(panel, kind, strain_limit, rotation_limit, panel_path, 99.5,
                 step_um=float(config.get("map_step_um", 1.0)),
                 strain_linthresh=0.5)
            plots.append((f"{kind.title()} strain and lattice rotation (legacy panel style)",
                          f"report_assets/{panel_path.name}"))
    except Exception as exc:
        # The standard per-component plots below remain available if the
        # optional panel helper cannot be imported in a minimal installation.
        config["panel_plot_warning"] = str(exc)

    stats=_stats(rows); (output/"region_statistics.json").write_text(json.dumps(stats,indent=2),encoding="utf-8")
    rejected=[r for r in rows if r.get("status")!="ok"];
    with (output/"rejected_points.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["status","error"]); w.writeheader(); w.writerows(rejected)
    body=["<h1>PyHREBSD analysis report</h1>",f"<p>Points: {len(rows)}; accepted: {len(rows)-len(rejected)}; rejected: {len(rejected)}</p>","<h2>Configuration</h2>","<pre>"+html.escape(json.dumps(config,indent=2,ensure_ascii=False))+"</pre>","<h2>Region statistics</h2>","<pre>"+html.escape(json.dumps(stats,indent=2,ensure_ascii=False))+"</pre>","<h2>Plots</h2>"]
    body += [f'<h3>{html.escape(t)}</h3><img src="{src}" style="width:100%;max-width:1600px;height:auto"><br>' for t, src in plots]
    body += ['<h2>Rejected points</h2><p><a href="rejected_points.csv">rejected_points.csv</a></p>']
    report=output/"report.html"; report.write_text("<!doctype html><html><body>"+"\n".join(body)+"</body></html>",encoding="utf-8")
    if report_format.lower() in ("pdf","html_pdf","both"):
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_pdf import PdfPages
        import matplotlib.pyplot as plt
        with PdfPages(output/"report.pdf") as pdf:
            for _,src in plots:
                image=plt.imread(output/src)
                height, width = image.shape[:2]
                fig_width = 11.0
                fig_height = max(4.0, fig_width * height / width)
                fig, ax = plt.subplots(figsize=(fig_width, fig_height))
                ax.imshow(image); ax.axis("off")
                fig.subplots_adjust(0, 0, 1, 1)
                pdf.savefig(fig); plt.close(fig)
    return report
