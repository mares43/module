"""Scenario analysis for the 2027 forward sale. Prints the tables used in REPORT.md.

Run: python model/analysis.py
"""
import numpy as np
import pandas as pd

from contract import MONTH, Settings, evaluate, merchant_generation
from scenarios import build

MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def scenario_set(dry_factor=0.75, h2_2026_factor=0.82):
    """h2_2026_factor: Jul-Dec 2026 PTF is missing, so the 2026 price curve reuses
    2025 H2 scaled by this factor (Q3 2026 came in ~18% lower in USD y/y)."""
    hydro, prices, _ = build()
    prices = dict(prices)
    prices["2026"] = prices["2026"].copy()
    prices["2026"][MONTH >= 6] *= h2_2026_factor
    dry = {}
    for k in ("hes", "ges", "res", "bes"):
        a, b = hydro["2025"][k], hydro["2026"][k]
        sa = pd.Series(a).groupby(MONTH).transform("sum").to_numpy()
        sb = pd.Series(b).groupby(MONTH).transform("sum").to_numpy()
        dry[k] = np.where(sa <= sb, a, b) * (dry_factor if k == "hes" else 1.0)
    return [  # name, weight, hydrology, ptf, price factor
        ("Normal year", 0.45, hydro["2025"], prices["2025"], 1.00),
        ("Wet repeat (2026)", 0.25, hydro["2026"], prices["2026"], 1.00),
        ("Dry year", 0.15, dry, prices["2025"], 1.15),
        ("Low PTF, normal water", 0.10, hydro["2025"], prices["2026"], 1.00),
        ("Normal PTF, wet water", 0.05, hydro["2026"], prices["2025"], 1.00),
    ]


def run(contract_mw, price_by_month, scen, s_kwargs=None):
    """price_by_month: 12 prices; contract_mw: 12 MW. Contract revenue priced per month."""
    out = []
    for name, w, hyd, ptf, k in scen:
        s = Settings(price_multiplier=k, **(s_kwargs or {}))
        r = evaluate(0, 0, hyd, ptf, s)
        p = ptf * k
        q = np.asarray(contract_mw)[MONTH]
        px = np.asarray(price_by_month)[MONTH]
        gen = sum(merchant_generation(hyd, p, s).values())
        hedge = (q * (px - p)).sum()
        short = np.maximum(q - gen, 0)
        out.append(dict(scenario=name, weight=w, gen_gwh=r["generation_mwh"] / 1e3,
                        capture=r["capture_price"], merchant_musd=r["total_revenue"] / 1e6,
                        hedged_musd=(r["total_revenue"] + hedge) / 1e6,
                        buyback_mwh=short.sum(), buyback_kusd=(short * p).sum() / 1e3))
    return pd.DataFrame(out)


def run_book(book, scen, s_kwargs=None):
    """book: list of (name, months (0-based), MW, USD/MWh) baseload contracts."""
    q = np.zeros(12)
    for _, months, mw, _ in book:
        q[list(months)] += mw
    out = []
    for name, w, hyd, ptf, k in scen:
        s = Settings(price_multiplier=k, **(s_kwargs or {}))
        p = ptf * k
        r = evaluate(0, 0, hyd, ptf, s)
        gen = sum(merchant_generation(hyd, p, s).values())
        hedge = sum((mw * (px - p[np.isin(MONTH, list(months))])).sum() for _, months, mw, px in book)
        short = np.maximum(q[MONTH] - gen, 0)
        out.append(dict(scenario=name, weight=w, gen_gwh=r["generation_mwh"] / 1e3,
                        capture=r["capture_price"], merchant_musd=r["total_revenue"] / 1e6,
                        hedge_musd=hedge / 1e6, hedged_musd=(r["total_revenue"] + hedge) / 1e6,
                        buyback_mwh=short.sum(), buyback_kusd=(short * p).sum() / 1e3))
    return pd.DataFrame(out)


def load_book(path=None, sold_only=True):
    """Signed trades live in data/book.json (git-ignored): [{name, from, to, mw, px, sold}]."""
    import json
    from pathlib import Path
    path = Path(path or Path(__file__).resolve().parent.parent / "data/book.json")
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    return [(r["name"], range(r["from"], r["to"] + 1), r["mw"], r["px"])
            for r in rows if r.get("sold", True) or not sold_only]


def main():
    pd.set_option("display.width", 200)
    scen = scenario_set()
    w = np.array([x[1] for x in scen])

    print("== Monthly view: expected merchant MW, range, fair baseload PTF (USD) ==")
    rows = []
    for m in range(12):
        idx = MONTH == m
        g = [sum(merchant_generation(h, p * k, Settings(price_multiplier=k)).values())[idx].mean()
             for _, _, h, p, k in scen]
        b = [(p * k)[idx].mean() for _, _, h, p, k in scen]
        rows.append(dict(month=MON[m], gen_exp=np.dot(w, g), gen_min=min(g), gen_max=max(g),
                         fair=np.dot(w, b), ptf_min=min(b), ptf_max=max(b)))
    monthly = pd.DataFrame(rows).round(1)
    print(monthly.to_string(index=False))

    fair_year = np.dot(w, [np.mean(p * k) for _, _, _, p, k in scen])
    spring = [2, 3, 4]
    fair_spring = np.dot(w, [np.mean((p * k)[np.isin(MONTH, spring)]) for _, _, _, p, k in scen])
    print(f"\nFair flat 2027 baseload: {fair_year:.1f} USD/MWh · fair Mar-May block: {fair_spring:.1f}")

    print("\n== Deal book (data/book.json) vs no deals, M USD ==")
    for label, book in (("No deals", []), ("Sold book", load_book()), ("Sold + proposals", load_book(sold_only=False))):
        df = run_book(book, scen)
        print(f"{label:18s} expected {np.dot(df.weight, df.hedged_musd):.2f}  worst {df.hedged_musd.min():.2f}"
              f"  best {df.hedged_musd.max():.2f}  buy-back {np.dot(df.weight, df.buyback_mwh) / 1e3:.1f} GWh")

    print("\n== GES without toplayici: unlicensed (min(PTF, 53$)) vs licensed (85% of PTF) ==")
    for label, kw in [("Unlicensed, cap 53", dict(ges_aggregator=False, ges_price_cap=53.0, ges_price_share=1.0)),
                      ("Licensed, 85% PTF", dict(ges_aggregator=False, ges_price_cap=None, ges_price_share=0.85))]:
        vals = []
        for name, wt, h, p, k in scen:
            s = Settings(price_multiplier=k, **kw)
            g = merchant_generation(h, p * k, s)["GES"]
            gp = p * k * s.ges_price_share
            if s.ges_price_cap is not None:
                gp = np.minimum(gp, s.ges_price_cap)
            vals.append(((g * gp).sum() / 1e6, (g * gp).sum() / g.sum()))
        print(label, [(round(a, 2), round(b, 1)) for a, b in vals],
              "expected M$", round(np.dot(w, [v[0] for v in vals]), 2))


if __name__ == "__main__":
    main()
