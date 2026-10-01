"""Evaluate a 2027 baseload sale (bilateral agreement) against the merchant portfolio."""
from dataclasses import dataclass, field

import numpy as np

from scenarios import GES_INSTALLED_MW, HOURS, ges_merchant_mw_by_month

MONTH = HOURS.month.to_numpy() - 1


@dataclass
class Settings:
    hydro_marginal_cost: float = 3.0       # USD/MWh: HES stops when PTF is below this
    price_multiplier: float = 1.0          # scales the scenario PTF curve
    ges_exit_mw: np.ndarray = field(default_factory=ges_merchant_mw_by_month)
    ges_price_share: float = 1.0           # share of PTF paid for post-YEKDEM unlicensed GES
    ges_price_cap: float | None = 53.0     # USD/MWh: 90% x YEKDEM solar TL price (CB Karari 11415), None = no cap
    ges_aggregator: bool = True            # sold via toplayici portfolio: PTF - fee, no cap
    aggregator_fee: float = 0.0            # USD/MWh kept by the aggregator
    include_bes: bool = False
    include_res: bool = False


def ges_unit_price(ptf: np.ndarray, s: Settings) -> np.ndarray:
    """USD/MWh received for post-YEKDEM unlicensed GES output."""
    if s.ges_aggregator:
        return ptf - s.aggregator_fee
    price = ptf * s.ges_price_share
    if s.ges_price_cap is not None:
        price = np.minimum(price, s.ges_price_cap)
    return price


def merchant_generation(hydro: dict, ptf: np.ndarray, s: Settings) -> dict:
    """Hourly MWh of the plants that are outside YEKDEM in 2027, after economic dispatch."""
    hes = np.where(ptf >= s.hydro_marginal_cost, hydro["hes"], 0.0)
    ges = hydro["ges"] * s.ges_exit_mw[MONTH] / GES_INSTALLED_MW
    gen = {"HES": hes, "GES": ges}
    if s.include_bes:
        gen["BES"] = hydro["bes"]
    if s.include_res:
        gen["RES"] = hydro["res"]
    return gen


def evaluate(contract_mw, price: float, hydro: dict, ptf_raw: np.ndarray, s: Settings) -> dict:
    """contract_mw: scalar or 12 monthly MW values of a baseload (7x24) sale at `price` USD/MWh."""
    ptf = ptf_raw * s.price_multiplier
    gen = merchant_generation(hydro, ptf, s)
    q = np.broadcast_to(np.asarray(contract_mw, dtype=float), (12,))[MONTH]

    ges_price = ges_unit_price(ptf, s)
    spot_value = {k: v * (ges_price if k == "GES" else ptf) for k, v in gen.items()}
    g = sum(gen.values())
    merchant_rev = sum(x.sum() for x in spot_value.values())
    hes_cost = gen["HES"].sum() * s.hydro_marginal_cost

    # Contract settles financially against PTF: we receive price, pay PTF on q.
    hedge_pnl = (q * (price - ptf)).sum()
    shortfall = np.maximum(q - g, 0.0)
    surplus = np.maximum(g - q, 0.0)
    total = merchant_rev + hedge_pnl - hes_cost
    return dict(
        generation_mwh=g.sum(),
        generation_by_tech={k: v.sum() for k, v in gen.items()},
        contract_mwh=q.sum(),
        merchant_revenue=merchant_rev - hes_cost,
        capture_price=merchant_rev / g.sum() if g.sum() else 0.0,
        baseload_ptf=(q * ptf).sum() / q.sum() if q.sum() else ptf.mean(),
        hedge_pnl=hedge_pnl,
        total_revenue=total,
        realized_price=total / g.sum() if g.sum() else 0.0,
        shortfall_mwh=shortfall.sum(),
        shortfall_cost=(shortfall * ptf).sum(),
        shortfall_hours=int((shortfall > 0).sum()),
        surplus_mwh=surplus.sum(),
        surplus_revenue=(surplus * ptf).sum(),
        hedge_ratio=q.sum() / g.sum() if g.sum() else 0.0,
    )
