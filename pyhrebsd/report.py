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
    fig, ax = plt.subplots(figsize=(7, 5))
    if np.any(valid):
        sc = ax.scatter(x[valid], y[valid], c=z[valid], s=12, cmap=cmap)
        fig.colorbar(sc, ax=ax, label=key)
    ax.set_title(title); ax.set_xlabel("column"); ax.set_ylabel("row"); ax.invert_yaxis()
    fig.tight_layout(); fig.savefig(output, dpi=160); plt.close(fig)

def _hist(rows, output, keys):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    for key in keys:
        values = np.asarray([_float(r, key) for r in rows]); values = values[np.isfinite(values)]
        if values.size: ax.hist(values, bins=40, alpha=.45, label=key)
    ax.set_title("Strain distributions"); ax.set_xlabel("value"); ax.set_ylabel("points"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(output, dpi=160); plt.close(fig)

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
    config_path=output/"run_config.json"
    config=json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    plots=[]
    for key,title in [("rms_shift_error_pixels","ROI RMS shift error"),("znssd_rms","Homography ZNSSD"),("roi_znssd_rms","ROI ZNSSD"),("pc_sensitivity_strain_max","PC sensitivity"),("strain_sample_11","E11"),("strain_sample_22","E22"),("strain_sample_33","E33")]:
        if any(key in r and r.get(key) not in ("",None) for r in rows):
            name=key+".png"; _plot(rows,assets/name,key,title); plots.append((title, "report_assets/"+name))
    hist=assets/"strain_histogram.png"; _hist(rows,hist,["strain_sample_11","strain_sample_22","strain_sample_33"]); plots.append(("Strain histograms","report_assets/strain_histogram.png"))
    profile=assets/"strain_profile_e11.png"; _profile(rows,profile,"strain_sample_11"); plots.append(("E11 row profile","report_assets/strain_profile_e11.png"))
    stats=_stats(rows); (output/"region_statistics.json").write_text(json.dumps(stats,indent=2),encoding="utf-8")
    rejected=[r for r in rows if r.get("status")!="ok"];
    with (output/"rejected_points.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["status","error"]); w.writeheader(); w.writerows(rejected)
    body=["<h1>PyHREBSD analysis report</h1>",f"<p>Points: {len(rows)}; accepted: {len(rows)-len(rejected)}; rejected: {len(rejected)}</p>","<h2>Configuration</h2>","<pre>"+html.escape(json.dumps(config,indent=2,ensure_ascii=False))+"</pre>","<h2>Region statistics</h2>","<pre>"+html.escape(json.dumps(stats,indent=2,ensure_ascii=False))+"</pre>","<h2>Plots</h2>"]
    body += [f'<h3>{html.escape(t)}</h3><img src="{src}" style="max-width:900px"><br>' for t, src in plots]
    body += ['<h2>Rejected points</h2><p><a href="rejected_points.csv">rejected_points.csv</a></p>']
    report=output/"report.html"; report.write_text("<!doctype html><html><body>"+"\n".join(body)+"</body></html>",encoding="utf-8")
    if report_format.lower() in ("pdf","html_pdf","both"):
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_pdf import PdfPages
        import matplotlib.pyplot as plt
        with PdfPages(output/"report.pdf") as pdf:
            for _,src in plots:
                image=plt.imread(output/src); fig,ax=plt.subplots(figsize=(11,7)); ax.imshow(image); ax.axis("off"); pdf.savefig(fig); plt.close(fig)
    return report
