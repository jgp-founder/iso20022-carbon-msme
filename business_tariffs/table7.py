"""Reproduce Table 7 (Section 4.6): business tariffs at ALECO, VECO, Davao Light and Meralco, October 2026.
Davao Light: published totals per class (data/davaolight_rates_oct2026.csv).
VECO: average monthly rates per class (data/veco_average_monthly_rate_oct2026.csv).
ALECO: published total rates per class (ALECO, 2026a; archived rates page).
Meralco: bills computed from the Summary Schedule of Rates, October 2026 billing
(Meralco, 2026b) by meralco_bill.py; VAT included, local franchise tax excluded."""
import numpy as np, pandas as pd
from meralco_bill import bill

H = 730
rows = []
aleco = {"Residential Mainland": 11.8297, "Low Voltage Mainland": 10.8494, "High Voltage": 9.2756}
for k, v in aleco.items():
    rows.append(dict(utility="ALECO", cls=k, eff_min=v, eff_max=v,
                     err_min=100 * (v / aleco["Residential Mainland"] - 1),
                     err_max=100 * (v / aleco["Residential Mainland"] - 1)))
veco = pd.read_csv("../data/veco_average_monthly_rate_oct2026.csv").set_index("customer_class")
v_res = veco.loc["Residential", "rate_php_per_kwh_oct2026"]
for k in ("Residential", "General Service", "General Power", "Bulk Power"):
    v = veco.loc[k, "rate_php_per_kwh_oct2026"]
    rows.append(dict(utility="VECO", cls=f"{k} ({veco.loc[k, 'consumption_kwh']} kWh)", eff_min=v, eff_max=v,
                     err_min=100 * (v / v_res - 1), err_max=100 * (v / v_res - 1)))
dl = pd.read_csv("../data/davaolight_rates_oct2026.csv").set_index("customer_class")
d_res = dl.loc["Residential", "total_php_per_kwh_oct2026"]
for k in ("Residential", "Secondary Retail 2.1", "Secondary Retail 3.1", "Primary Retail 4.1"):
    v = dl.loc[k, "total_php_per_kwh_oct2026"]
    rows.append(dict(utility="Davao Light", cls=k, eff_min=v, eff_max=v,
                     err_min=100 * (v / d_res - 1), err_max=100 * (v / d_res - 1)))
r_res = bill("RES", 200)[0] / 200
print(f"Meralco residential, 200 kWh: {r_res:.4f} PHP/kWh (announced 15.0615; the gap is likely the local franchise tax, which is excluded)")
for kwh in (200, 500):
    e = bill("GSA", kwh)[0] / kwh
    rows.append(dict(utility="Meralco", cls=f"GS-A {kwh} kWh", eff_min=e, eff_max=e,
                     err_min=100 * (e / r_res - 1), err_max=100 * (e / r_res - 1), dem_min=0, dem_max=0))
for cls, kws, name in (("GSB", (10, 20, 35), "GS-B"), ("GP_MED_SEC", (50, 100, 180), "GP Medium secondary")):
    eff, dem = [], []
    for kw in kws:
        for lf in (0.2, 0.35, 0.5):
            k = kw * H * lf
            t, d, _ = bill(cls, k, kw)
            eff.append(t / k); dem.append(d / t)
    eff, dem = np.array(eff), np.array(dem)
    rows.append(dict(utility="Meralco", cls=name, eff_min=eff.min(), eff_max=eff.max(),
                     err_min=100 * (eff.min() / r_res - 1), err_max=100 * (eff.max() / r_res - 1),
                     dem_min=100 * dem.min(), dem_max=100 * dem.max()))
    # average error over a dense grid of demand and load factor
    lo, hi = {"GSB": (5, 40), "GP_MED_SEC": (40, 200)}[cls]
    g = np.array([bill(cls, kw * H * lf, kw)[0] / (kw * H * lf)
                  for kw in np.linspace(lo, hi, 40) for lf in np.linspace(0.2, 0.5, 61)])
    print(f"{name}: mean |error| vs residential rate {100*np.mean(np.abs(g/r_res-1)):.1f}%; "
          f"vs class median rate {100*np.mean(np.abs(g/np.median(g)-1)):.1f}%")
df = pd.DataFrame(rows).round(2)
print(df.to_string(index=False))
df.to_csv("table7_business_tariffs.csv", index=False)
