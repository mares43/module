"""Write app/data.js: 2027 hourly scenario arrays consumed by app/index.html."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "model"))
from scenarios import build, load_history  # noqa: E402


def r(a, d=3):
    return [round(float(x), d) for x in a]


def main():
    hydro, prices, meta = build()
    wide, hes_pot, _, f = load_history()
    act = wide[hes_pot.columns].sum(axis=1)
    pot = hes_pot.sum(axis=1)
    monthly = pd.DataFrame({"actual": act, "potential": pot})
    monthly = monthly.groupby([monthly.index.year, monthly.index.month]).sum().round(0)
    ptf_m = f.ptf_usd.groupby([f.index.year, f.index.month]).mean().round(1)
    data = {
        "ptf": {k: r(v, 2) for k, v in prices.items()},
        "hydro": {k: {t: r(v) for t, v in d.items()} for k, d in hydro.items()},
        "history": {
            "hes_monthly": [{"y": int(y), "m": int(m), "actual": float(row.actual), "potential": float(row.potential)}
                            for (y, m), row in monthly.iterrows()],
            "ptf_monthly": [{"y": int(y), "m": int(m), "usd": float(v)} for (y, m), v in ptf_m.items()],
            "zero_price_hours": {str(y): int(((f.ptf_try <= 1) & (f.index.year == y)).sum()) for y in (2025, 2026)},
        },
        "meta": meta,
    }
    rec = ROOT / "data/recommendation.html"  # private, git-ignored
    if rec.exists():
        data["recommendation"] = {
            "html": rec.read_text(),
        }
    book = ROOT / "data/book.json"  # private, git-ignored: signed trades + proposals
    if book.exists():
        data["book"] = json.loads(book.read_text())
    out = ROOT / "app/data.js"
    out.write_text("window.ELESTAS_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(out, round(out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
