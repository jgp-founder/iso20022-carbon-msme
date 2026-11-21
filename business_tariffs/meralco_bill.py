"""Meralco October 2026 bill model from the Summary Schedule of Rates (VAT-exclusive
rates; VAT added per the schedule's VAT table; local franchise tax excluded)."""
VAT = {"gen": .0833, "trans": .1199, "anc": .0909, "other": .12}
COMMON_KWH_NOVAT = {  # not subject to VAT
    "system_loss": .9301, "lifeline_subsidy": .0100, "sc_subsidy": .0001,
    "rpt": .0067, "rpt_adj": .0015, "uc_me_spug": .3296, "uc_me_redci": .0101,
    "uc_ec": .0025, "uc_sd": .0428, "fit_all": .3359}
REGRESET = -.0023  # regulatory reset fees adjustment (treated as 'other', VATable)

RES_DIST = [(200, .9803), (300, 1.2908), (400, 1.5837), (1e12, 2.0941)]  # same blocks GS-A above 200

def dist_rate_res(kwh):
    # Meralco applies the rate of the block the total consumption falls in
    for top, r in RES_DIST:
        if kwh <= top:
            return r

def bill(cls, kwh, kw=0.0):
    """Return (total PHP incl. VAT, energy-proportional part, demand part, fixed part)."""
    gen = 10.2005 * kwh
    if cls in ("RES", "GSA"):
        trans, anc = .5422 * kwh, .602 * kwh
        dist = dist_rate_res(kwh) * kwh
        supply = .4979 * kwh + 16.38
        meter = .3350 * kwh + 5.00
        awat = (-.4278 - .5861) * kwh
        dem_trans = dem_anc = dem_dist = 0.0
        fixed = 16.38 + 5.00
    elif cls == "GSB":
        trans, anc = 162.86 * kw, 180.78 * kw
        dist = .1339 * kwh + 232.20 * kw
        supply, meter = 363.73, 354.78
        awat = (-.2778 - .3879) * kwh
        fixed = 363.73 + 354.78
    elif cls == "GP_MED_SEC":
        trans, anc = 177.19 * kw, 196.69 * kw
        dist = .1339 * kwh + 232.20 * kw
        supply, meter = 827.54, 831.72
        awat = (-.1239 - .1740) * kwh
        fixed = 827.54 + 831.72
    other = dist + supply + meter + awat + REGRESET * kwh
    novat = sum(COMMON_KWH_NOVAT.values()) * kwh
    total = (gen * (1 + VAT["gen"]) + trans * (1 + VAT["trans"]) + anc * (1 + VAT["anc"])
             + other * (1 + VAT["other"]) + novat)
    if cls in ("GSB", "GP_MED_SEC"):
        demand = (162.86 if cls == "GSB" else 177.19) * kw * (1 + VAT["trans"]) \
               + (180.78 if cls == "GSB" else 196.69) * kw * (1 + VAT["anc"]) \
               + 232.20 * kw * (1 + VAT["other"])
    else:
        demand = 0.0
    fixed_v = fixed * (1 + VAT["other"])
    return total, demand, fixed_v

if __name__ == "__main__":
    t, _, _ = bill("RES", 200)
    print("Residential 200 kWh: total %.2f  -> %.4f PHP/kWh (Meralco announced 15.0615 overall)" % (t, t / 200))
