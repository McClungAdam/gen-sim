"""Fit the run-of-river model to EIA-923 per docs/calibration_protocol.md, then score it.

Nothing here changes which months are excluded: that comes from rules.monthly_table (prior model).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from gensim.assets.hydro_ror import HydroParams, daily_energy, monthly_energy
from gensim.calibration import rules

# (lower, upper) per protocol
BOUNDS = {
    "head_eff_ft": (0.60 * rules.GROSS_HEAD_FT, 0.92 * rules.GROSS_HEAD_FT),
    "q_max_cfs": (1500.0, 2300.0),
    "q_minflow_cfs": (0.0, 100.0),
    "availability": (0.80, 1.00),
}
NAMES = list(BOUNDS)
LONG_RUN = ("2003", "2016")
PUBLISHED_LONG_RUN_MWH = 26150.0


def _params(x, p_cap) -> HydroParams:
    return HydroParams(*[float(v) for v in x], p_cap_mw=p_cap)


def _model_months(flow, p, months):
    m = monthly_energy(flow, p).set_index("month")["model_mwh"]
    return m.reindex(months).to_numpy()


@dataclass
class CalibrationResult:
    params: HydroParams
    table: pd.DataFrame                       # monthly: actual, prior model, fitted model, exclusion, period
    annual: pd.DataFrame                      # per calendar year
    metrics: dict
    water_years: pd.DataFrame                 # modeled generation per water year (Oct-Sep)
    exceedance: dict
    fit_info: dict = field(default_factory=dict)


def fit(flow: pd.DataFrame, table: pd.DataFrame, p_cap: float = rules.PRIOR.p_cap_mw) -> tuple[HydroParams, dict]:
    cal = table[(table["period"] == "calibrate") & ~table["excluded"]]
    months, actual = cal["month"].tolist(), cal["net_generation_mwh"].to_numpy()
    # pre-compute the daily flow slice once
    f = flow[flow["date"].str[:7].isin(set(months))].copy()

    def sse(x):
        pred = _model_months(f, _params(x, p_cap), months)
        return float(np.nansum((pred - actual) ** 2))

    lo = np.array([b[0] for b in BOUNDS.values()]); hi = np.array([b[1] for b in BOUNDS.values()])
    best = None
    starts = product(np.linspace(lo[0], hi[0], 3), np.linspace(lo[1], hi[1], 3), [10.0], [0.95])
    for s in starts:
        r = minimize(sse, np.array(s), method="Powell", bounds=list(zip(lo, hi)),
                     options={"xtol": 1e-4, "ftol": 1e-10, "maxiter": 20000})
        if best is None or r.fun < best.fun:
            best = r
    at_bound = [n for n, v, (l, h) in zip(NAMES, best.x, BOUNDS.values()) if np.isclose(v, l, rtol=1e-3) or np.isclose(v, h, rtol=1e-3)]
    return _params(best.x, p_cap), {"sse": best.fun, "n_months": len(months), "at_bound": at_bound,
                                    "success": bool(best.success)}


def _corr(a, b):
    ok = ~(np.isnan(a) | np.isnan(b))
    return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 2 else float("nan")


def evaluate(flow, table, p: HydroParams, fit_info: dict) -> CalibrationResult:
    t = table.copy()
    t["model_mwh"] = _model_months(flow, p, t["month"].tolist())
    t["error_mwh"] = t["model_mwh"] - t["net_generation_mwh"]
    t["ratio_actual_to_model"] = t["net_generation_mwh"] / t["model_mwh"]

    flags = rules.flagged_years(t)
    t["year"] = t["month"].str[:4]
    a = t.groupby("year").agg(actual_mwh=("net_generation_mwh", "sum"), model_mwh=("model_mwh", "sum"),
                              months=("month", "count"), excluded_months=("excluded", "sum")).reset_index()
    a["error_pct"] = 100 * (a["model_mwh"] - a["actual_mwh"]) / a["actual_mwh"].replace(0, np.nan)
    a["flag"] = a["year"].map(flags).astype(object).fillna("")
    a["period"] = np.where(a["year"].between(rules.CALIBRATE[0][:4], rules.CALIBRATE[1][:4]), "calibrate",
                  np.where(a["year"].between(rules.VALIDATE[0][:4], rules.VALIDATE[1][:4]), "validate", "other"))
    a["within_5pct"] = (a["error_pct"].abs() <= 5.0).astype("boolean")
    a.loc[(a["flag"] != "") | (a["months"] < 12), "within_5pct"] = pd.NA   # not assessed

    metrics = {}
    for per in ("calibrate", "validate"):
        k = t[(t["period"] == per) & ~t["excluded"]]
        ay = a[(a["period"] == per) & (a["flag"] == "") & (a["months"] == 12)]
        metrics[per] = {
            "months_used": int(len(k)),
            "months_excluded": int(((t["period"] == per) & t["excluded"]).sum()),
            "monthly_r": _corr(k["model_mwh"].to_numpy(), k["net_generation_mwh"].to_numpy()),
            "bias_pct": float(100 * (k["model_mwh"].sum() - k["net_generation_mwh"].sum()) / k["net_generation_mwh"].sum()),
            "years_assessed": int(len(ay)),
            "years_within_5pct": int(ay["within_5pct"].astype(bool).sum()),
            "worst_year_error_pct": float(ay["error_pct"].abs().max()) if len(ay) else float("nan"),
        }
    lr = a[a["year"].between(*LONG_RUN)]
    metrics["long_run"] = {
        "years": f"{LONG_RUN[0]}-{LONG_RUN[1]}",
        "model_mean_mwh": float(lr["model_mwh"].mean()), "actual_mean_mwh": float(lr["actual_mwh"].mean()),
        "published_mwh": PUBLISHED_LONG_RUN_MWH,
        "model_vs_published_pct": float(100 * (lr["model_mwh"].mean() / PUBLISHED_LONG_RUN_MWH - 1)),
    }
    metrics["acceptance"] = {
        "annual_within_5pct_all_assessed": all(metrics[p_]["years_within_5pct"] == metrics[p_]["years_assessed"] for p_ in ("calibrate", "validate")),
        "monthly_r_ge_0.9": all(metrics[p_]["monthly_r"] >= 0.9 for p_ in ("calibrate", "validate")),
        "long_run_within_5pct": abs(metrics["long_run"]["model_vs_published_pct"]) <= 5.0,
    }

    wy, exc = water_year_scenarios(flow, p)
    return CalibrationResult(p, t, a, metrics, wy, exc, fit_info)


def water_year_scenarios(flow: pd.DataFrame, p: HydroParams, first: int = 1930, last: int | None = None):
    """Each complete water year (Oct-Sep) of record is one hydrology scenario."""
    d = daily_energy(flow, p)
    dt = pd.to_datetime(d["date"])
    d["wy"] = dt.dt.year + (dt.dt.month >= 10).astype(int)
    g = d.groupby("wy").agg(mwh=("mwh", "sum"), days=("mwh", "count"), q_mean_cfs=("q_cfs", "mean")).reset_index()
    g = g[(g["days"] >= 365) & (g["wy"] >= first)]
    if last:
        g = g[g["wy"] <= last]
    exc = {  # exceedance: P90 = generation exceeded in 90% of years (low case)
        "P10_mwh": float(np.percentile(g["mwh"], 90)),
        "P50_mwh": float(np.percentile(g["mwh"], 50)),
        "P90_mwh": float(np.percentile(g["mwh"], 10)),
        "mean_mwh": float(g["mwh"].mean()),
        "water_years": f"{int(g['wy'].min())}-{int(g['wy'].max())}",
        "n": int(len(g)),
    }
    return g, exc


def run(flow: pd.DataFrame, actual: pd.DataFrame) -> CalibrationResult:
    table = rules.monthly_table(flow, actual)
    p, info = fit(flow, table)
    return evaluate(flow, table, p, info)
