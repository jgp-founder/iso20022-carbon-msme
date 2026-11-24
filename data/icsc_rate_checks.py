"""Real-rate checks from the ICSC master file of rates per customer class (2018-2026).

Input (local only, not redistributed; download from ICSC PRESYO-PH):
  data/icsc_rates/Rates_per_Costumer_Class_Per_DU_Per_Region.xlsx
Outputs:
  output/icsc_methodB_by_month_2026.csv   Method B expected electricity error, Jan-Oct 2026
  output/icsc_commercial_vs_residential_oct2026.csv   commercial/residential rate ratio per on-grid utility
Method B's expected error uses the same analytical formula as run_analysis.py: every on-grid
utility equally likely, each customer's rate uniform within +/-5% of the utility rate, and
Method B dividing the payment by the cross-utility mean rate.
"""
import csv, datetime as dt, pathlib
import numpy as np
import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "icsc_rates" / "Rates_per_Costumer_Class_Per_DU_Per_Region.xlsx"
OUT = ROOT / "output"
WITHIN = 0.05


def load(ws):
    """Return {(DU, grid): {(year, month): rate}} for one tab; non-numeric cells (NDA) are skipped."""
    out, hdr = {}, None
    for r in ws.iter_rows(values_only=True):
        if r[0] == "DU Name":
            hdr = r
            continue
        if hdr and r[0] and r[1] in ("ONGRID", "OFFGRID"):
            d = {(h.year, h.month): v for h, v in zip(hdr[5:], r[5:])
                 if isinstance(h, dt.datetime) and isinstance(v, (int, float))}
            out.setdefault((r[0].strip(), r[1]), d)
    return out


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    res, com = load(wb.worksheets[0]), load(wb.worksheets[1])
    on = [k for k in res if k[1] == "ONGRID"]
    u = np.linspace(-WITHIN, WITHIN, 2001)
    OUT.mkdir(exist_ok=True)
    with open(OUT / "icsc_methodB_by_month_2026.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "n_ongrid_utilities", "min_rate", "max_rate", "mean_rate", "methodB_expected_error_pct"])
        for m in range(1, 13):
            v = np.array([res[k][(2026, m)] for k in on if (2026, m) in res[k]])
            if len(v) == 0:
                continue
            err = np.mean(np.abs(v[:, None] * (1 + u[None, :]) / v.mean() - 1)) * 100
            w.writerow([f"2026-{m:02d}", len(v), v.min(), v.max(), round(v.mean(), 4), round(err, 2)])
    rows = [(k[0], res[k][(2026, 10)], com[k][(2026, 10)]) for k in on
            if (2026, 10) in res[k] and (2026, 10) in com.get(k, {})]
    with open(OUT / "icsc_commercial_vs_residential_oct2026.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["utility", "residential", "commercial", "ratio_commercial_to_residential"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], round(r[2] / r[1], 4)])
    rr = np.array([r[2] / r[1] for r in rows])
    print(f"Oct 2026: {len(rr)} on-grid utilities with both rates; commercial < residential at {(rr < 1).sum()}; "
          f"median ratio {np.median(rr):.3f}; p10-p90 {np.percentile(rr, 10):.3f}-{np.percentile(rr, 90):.3f}")


if __name__ == "__main__":
    main()
