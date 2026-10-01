"""Build 2027 hourly scenarios (generation x price) from 2025/2026 history."""
from pathlib import Path

import numpy as np
import pandas as pd

from curtailment import reconstruct

ROOT = Path(__file__).resolve().parent.parent
YEAR = 2027
HOURS = pd.date_range(f"{YEAR}-01-01", f"{YEAR}-12-31 23:00", freq="h")

# Solar capacity outside YEKDEM in 2027 (MW, of 30 MW installed unlicensed GES)
GES_INSTALLED_MW = 30.0
GES_EXIT_SCHEDULE = [  # (first month of 2027 the step applies, MW leaving YEKDEM)
    (1, 5.0),    # already out during 2026
    (2, 10.0),   # out from start of February 2027
    (8, 5.5),    # out from August 2027
]


def ges_merchant_mw_by_month(schedule=GES_EXIT_SCHEDULE):
    return np.array([sum(mw for m0, mw in schedule if m0 <= m) for m in range(1, 13)])


def load_history():
    p = pd.read_csv(ROOT / "data/production_hourly.csv", parse_dates=["datetime"])
    f = pd.read_csv(ROOT / "data/ptf_hourly.csv", parse_dates=["datetime"]).set_index("datetime")
    wide = p.pivot_table(index="datetime", columns="plant", values="mwh").fillna(0.0)
    techs = p.drop_duplicates("plant").set_index("plant").tech
    hes_cols = techs[techs == "HES"].index
    hes_pot = reconstruct(wide[hes_cols], f.ptf_usd)
    return wide, hes_pot, techs, f


def _map_to_2027(series: pd.Series, year: int, fallback: pd.Series | None = None) -> np.ndarray:
    """Pick the value at the same month/day/hour in `year`; use fallback where missing."""
    src = HOURS.map(lambda t: t.replace(year=year))
    vals = series.reindex(src).to_numpy(dtype=float)
    if fallback is not None:
        fb = fallback.reindex(HOURS.map(lambda t: t.replace(year=2025))).to_numpy(dtype=float)
        vals = np.where(np.isnan(vals), fb, vals)
    return vals


def build():
    wide, hes_pot, techs, f = load_history()
    hes = hes_pot.sum(axis=1)
    hes_act = wide[hes_pot.columns].sum(axis=1)
    ges = wide["GES (45 lisanssız)"]
    res = wide["Orhanlı RES"]
    bes = wide["Beylikova BES"]

    hydro = {
        "2025": dict(hes=_map_to_2027(hes, 2025), ges=_map_to_2027(ges, 2025)),
        "2026": dict(hes=_map_to_2027(hes, 2026, hes), ges=_map_to_2027(ges, 2026, ges)),
    }
    for k in hydro:
        y = int(k)
        hydro[k]["res"] = _map_to_2027(res, y, res)
        hydro[k]["bes"] = _map_to_2027(bes, y, bes)
    prices = {
        "2025": _map_to_2027(f.ptf_usd, 2025),
        "2026": _map_to_2027(f.ptf_usd, 2026, f.ptf_usd),  # Jul-Dec filled with 2025
    }
    meta = dict(
        hes_actual_2025=float(hes_act[hes_act.index.year == 2025].sum()),
        hes_actual_2026=float(hes_act[hes_act.index.year == 2026].sum()),
        hes_potential_2025=float(hes[hes.index.year == 2025].sum()),
        hes_potential_2026=float(hes[hes.index.year == 2026].sum()),
    )
    return hydro, prices, meta
