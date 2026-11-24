"""Method B's expected electricity error when the 101 on-grid utilities are weighted by customers.

Inputs: October 2026 residential rates from the ICSC master file (data/icsc_rates/, local only, read
through data/icsc_rate_checks.py) and customer counts from data/ddp_customers_2022.csv (DOE 2023-2032
Distribution Development Plan, 2022 actuals).
Output: output/weighted_methodB.csv
Same analytical formula as run_analysis.py: within-utility rate uniform within +/-5%; Method B divides the
payment by a reference mean rate (unweighted, or customer-weighted). Error per payment = R(1+u)/ref - 1.
"""
import csv, pathlib, importlib.util
import numpy as np
import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ic", ROOT / "data" / "icsc_rate_checks.py")
ic = importlib.util.module_from_spec(spec); spec.loader.exec_module(ic)


def main():
    res = ic.load(openpyxl.load_workbook(ic.SRC, read_only=True, data_only=True).worksheets[0])
    rows = list(csv.DictReader(open(ROOT / "data" / "ddp_customers_2022.csv")))
    R = np.array([res[(r["icsc_code"], "ONGRID")][(2026, 10)] for r in rows], float)
    u = np.linspace(-ic.WITHIN, ic.WITHIN, 2001)
    weights = {"equal": np.ones(len(R)),
               "total customers": np.array([float(r["captive_customers_total_2022"]) for r in rows]),
               "residential customers": np.array([float(r["residential_2022"]) for r in rows]),
               "commercial customers": np.array([float(r["commercial_2022"]) for r in rows])}
    um = R.mean()
    out = []
    for name, w in weights.items():
        wm = (w * R).sum() / w.sum()
        for refname, ref in (("unweighted mean", um), ("weighted mean", wm)):
            e = R[:, None] * (1 + u[None, :]) / ref - 1
            mape = (w * np.abs(e).mean(axis=1)).sum() / w.sum() * 100
            bias = (w * e.mean(axis=1)).sum() / w.sum() * 100
            out.append([name, refname, round(ref, 4), round(mape, 2), round(bias, 2)])
    (ROOT / "output").mkdir(exist_ok=True)
    with open(ROOT / "output" / "weighted_methodB.csv", "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["weighting", "reference_rate", "reference_rate_php_per_kwh", "methodB_mape_pct", "methodB_mean_signed_error_pct"])
        wr.writerows(out)
    for row in out:
        print(row)


if __name__ == "__main__":
    main()
