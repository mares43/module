"""Reconstruct hydro output that was lost to economic curtailment (2026 low-price hours).

Logic, per HES plant and per day:
  * capacity  = 99.5th percentile of hourly output over the full data set
  * a day is a "run-at-capacity" day if, in the hours the plant was running,
    its average output was >= RUN_FULL x capacity. Then river flow was at or
    above capacity, so every stopped hour with low PTF is spilled water.
  * stopped hours (output < STOP x capacity) with PTF < PRICE_THRESHOLD on such
    days are refilled at the plant's average running output of that day.
  * whole-day stops: refill at the average running output of the nearest
    running days within +/- WINDOW days, if that average was >= RUN_FULL x cap.
Pondage plants that merely shift water within the day run below capacity and
are left untouched, so intra-day shifting is not counted as lost energy.
"""
import pandas as pd

PRICE_THRESHOLD = 10.0   # USD/MWh; below this a stop is treated as economic
STOP = 0.05
RUN_FULL = 0.85
WINDOW = 3


def reconstruct(hourly: pd.DataFrame, ptf_usd: pd.Series) -> pd.DataFrame:
    """hourly: index datetime, one column per HES plant (MWh). Returns potential output."""
    out = hourly.copy()
    price = ptf_usd.reindex(hourly.index)
    for plant in hourly.columns:
        s = hourly[plant]
        cap = s.quantile(0.995)
        if cap <= 0.5:
            continue
        running = s >= STOP * cap
        day = s.index.normalize()
        run_avg = s.where(running).groupby(day).mean()
        full_days = run_avg[run_avg >= RUN_FULL * cap]
        all_days = pd.Series(sorted(set(day)))
        for d in all_days:
            if d in full_days.index:
                level = full_days[d]
            elif pd.isna(run_avg.get(d)):
                near = full_days[(full_days.index >= d - pd.Timedelta(days=WINDOW)) &
                                 (full_days.index <= d + pd.Timedelta(days=WINDOW))]
                if near.empty:
                    continue
                level = near.mean()
            else:
                continue
            mask = (day == d) & ~running & (price < PRICE_THRESHOLD)
            out.loc[mask, plant] = level
    return out
