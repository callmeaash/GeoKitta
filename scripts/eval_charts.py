"""Report charts from data/evaluation/quadtree.json (needs matplotlib): python scripts/eval_charts.py OUT_DIR."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
rows = json.loads((ROOT / "data" / "evaluation" / "quadtree.json").read_text("utf-8"))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "evaluation"
out.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "Times New Roman", "font.size": 12})

n = [r["parcels"] for r in rows]
labels = [f"{x:,}" for x in n]
STYLE = {"linear_quadtree": dict(color="black", marker="o", label="Linear quadtree"),
         "brute_force": dict(color="0.55", marker="s", linestyle="--", label="Brute-force loop")}


def panel(ax, kind, metric, title, ylabel, log=False):
    for method, st in STYLE.items():
        ax.plot(n, [r[kind][method][metric] for r in rows], linewidth=2, markersize=6, **st)
    ax.set_xscale("log")
    if log:
        ax.set_yscale("log")
    ax.set_xticks(n, labels)
    ax.minorticks_off()
    ax.set_xlabel("Parcels in the data set")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(True, color="0.88")
    ax.legend(frameon=False)


for kind, name, what in (("point", "eval-click.png", "click (point) lookup"),
                         ("box", "eval-box.png", "300 m selection box")):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    panel(axes[0], kind, "search_ms_median", f"Time per {what}", "Median time (ms)")
    panel(axes[1], kind, "rows_or_boxes_checked", "Index rows / boxes checked", "Count (log scale)", log=True)
    fig.tight_layout()
    fig.savefig(out / name, dpi=200)
    print("wrote", out / name)
