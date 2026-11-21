"""
Scenario analysis: can ISO 20022 payment metadata improve transaction-based
carbon estimates?

Pipeline
1. Build a synthetic "true world" of payer payments (electricity, fuel) with
   known physical quantities and emissions.
2. Write them as ISO 20022 pacs.008 messages (XML). Each message carries only
   what a payment message would carry: amount, currency, optionally a purpose
   code (Purp/Cd) and a creditor identifier (Cdtr/Id).
3. Parse the XML back and estimate emissions three ways, using ONLY the
   message contents plus public averages:
     A  spend-only, category-blind  : amount x one average kg CO2/PHP factor
     B  purpose code known          : amount / category average price x EF
     C  purpose code + creditor ID  : electricity uses the creditor's own tariff
4. Compare estimates with the true emissions across scenarios
   p (share of messages with a purpose code) and
   q (share of coded electricity messages whose creditor ID resolves).

The estimators never see the true tariff, fuel type or quantity, so the
comparison is not circular: error comes from information the message lacks.

Usage:  python run_analysis.py            (reads params.json, writes ./output)
"""

import json
import os
import numpy as np
import pandas as pd
from lxml import etree
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
# Official ISO 20022 schema, downloaded from the ISO 20022 message archive
# (Payments Clearing and Settlement V09, pacs.008.001.08). Not redistributed:
# place the file next to this script to enable validation.
XSD_PATH = os.path.join(HERE, "pacs.008.001.08.xsd")


def load_schema():
    if os.path.exists(XSD_PATH):
        return etree.XMLSchema(etree.parse(XSD_PATH))
    print("NOTE: pacs.008.001.08.xsd not found; XSD validation skipped.")
    return None


def validate(schema, path, log):
    """Validate one XML document against the official XSD and record the result."""
    if schema is None:
        return
    ok = schema.validate(etree.parse(path))
    log.append({"file": os.path.basename(path), "valid": ok,
                "errors": "; ".join(str(e) for e in schema.error_log)[:500]})
    if not ok:
        raise ValueError(f"XSD validation failed for {path}: {schema.error_log}")


# --------------------------------------------------------------------------
# 1. Synthetic true world
# --------------------------------------------------------------------------
def du_table(P):
    """Distribution utilities used for electricity payers: (ids, tariffs).
    tariff_source = "list": the on-grid utilities in the PRESYO-PH October 2026
    residential rate list (minus any codes in exclude_codes).
    tariff_source = "synthetic": n utilities spread evenly between two bounds."""
    e = P["electricity"]
    if e.get("tariff_source", "synthetic") == "list":
        t = pd.read_csv(os.path.join(HERE, e["tariff_list_file"]))
        t = t[t["grid_class"] == "On-grid"]
        t = t[~t["code"].isin(e.get("exclude_codes", []))]
        return list(t["code"]), t["rate"].to_numpy(dtype=float)
    tariffs = np.linspace(e["tariff_min_php_per_kwh"], e["tariff_max_php_per_kwh"],
                          e["n_distribution_utilities"])
    return [f"DU{str(i + 1).zfill(3)}" for i in range(len(tariffs))], tariffs


def estimator_tariff(P):
    """Public average tariff used by methods A and B: the unweighted mean of
    the utility list, or the midpoint of the two bounds in the synthetic design."""
    e = P["electricity"]
    if e.get("tariff_source", "synthetic") == "list":
        return float(np.mean(du_table(P)[1]))
    return (e["tariff_min_php_per_kwh"] + e["tariff_max_php_per_kwh"]) / 2

def build_world(P, rng):
    n = P["n_messages"]
    e = P["electricity"]
    f = P["fuel"]
    ef_grid = P["grid_emission_factor_kgco2_per_kwh"]["value"]

    n_elec = int(round(n * P["category_mix"]["electricity"]))
    n_fuel = n - n_elec

    # Distribution utilities: real on-grid list (default) or synthetic spread
    du_ids, du_tariffs = du_table(P)

    du_idx = rng.integers(0, len(du_tariffs), n_elec)
    kwh = rng.lognormal(np.log(e["median_kwh_per_payment"]),
                        e["kwh_lognormal_sigma"], n_elec)
    w = e.get("within_du_tariff_variation", 0.0)
    tariff = du_tariffs[du_idx] * rng.uniform(1 - w, 1 + w, n_elec)
    elec = pd.DataFrame({
        "category": "electricity",
        "creditor_id": [du_ids[i] for i in du_idx],
        "quantity": kwh,
        "unit_price": tariff,
        "amount_php": np.round(kwh * tariff, 2),
        "true_kgco2": kwh * ef_grid,
        "fuel_type": "",
    })

    is_diesel = rng.random(n_fuel) < f["share_diesel"]
    price = np.where(
        is_diesel,
        rng.uniform(f["diesel_price_min_php_per_l"], f["diesel_price_max_php_per_l"], n_fuel),
        rng.uniform(f["gasoline_price_min_php_per_l"], f["gasoline_price_max_php_per_l"], n_fuel),
    )
    litres = rng.lognormal(np.log(f["median_litres_per_payment"]),
                           f["litres_lognormal_sigma"], n_fuel)
    ef = np.where(is_diesel, f["ef_diesel_kgco2_per_l"], f["ef_gasoline_kgco2_per_l"])
    fuel = pd.DataFrame({
        "category": "fuel",
        "creditor_id": [f"STN{str(i).zfill(5)}" for i in rng.integers(1, 5000, n_fuel)],
        "quantity": litres,
        "unit_price": price,
        "amount_php": np.round(litres * price, 2),
        "true_kgco2": litres * ef,
        "fuel_type": np.where(is_diesel, "diesel", "gasoline"),
    })

    world = pd.concat([elec, fuel], ignore_index=True)
    world = world.sample(frac=1.0, random_state=int(rng.integers(0, 2**31))).reset_index(drop=True)
    world["msg_id"] = [f"SYN-{i:06d}" for i in range(len(world))]
    registry = dict(zip(du_ids, du_tariffs))
    return world, registry


# --------------------------------------------------------------------------
# 2. Write / read pacs.008 XML
# --------------------------------------------------------------------------
def write_pacs008(world, has_purp, has_cdtr_id, codes, path):
    """Write one pacs.008 document holding all transactions.
    Party names are placeholders: no personal data exist in this study."""
    doc = etree.Element(f"{{{NS}}}Document", nsmap={None: NS})
    root = etree.SubElement(doc, f"{{{NS}}}FIToFICstmrCdtTrf")
    grp = etree.SubElement(root, f"{{{NS}}}GrpHdr")
    _sub(grp, "MsgId", "SYNTHETIC-BATCH-0001")
    _sub(grp, "CreDtTm", "2026-11-19T00:00:00+08:00")
    _sub(grp, "NbOfTxs", str(len(world)))
    sttl = etree.SubElement(grp, f"{{{NS}}}SttlmInf")
    _sub(sttl, "SttlmMtd", "CLRG")

    for i, r in world.iterrows():
        tx = etree.SubElement(root, f"{{{NS}}}CdtTrfTxInf")
        pid = etree.SubElement(tx, f"{{{NS}}}PmtId")
        _sub(pid, "EndToEndId", r.msg_id)
        amt = _sub(tx, "IntrBkSttlmAmt", f"{r.amount_php:.2f}")
        amt.set("Ccy", "PHP")
        _sub(tx, "ChrgBr", "SLEV")
        dbtr = etree.SubElement(tx, f"{{{NS}}}Dbtr")
        _sub(dbtr, "Nm", "SYNTHETIC PAYER")
        for agent in ("DbtrAgt", "CdtrAgt"):
            a = etree.SubElement(tx, f"{{{NS}}}{agent}")
            fi = etree.SubElement(a, f"{{{NS}}}FinInstnId")
            _sub(fi, "BICFI", "SYNTPHMMXXX")
        cdtr = etree.SubElement(tx, f"{{{NS}}}Cdtr")
        _sub(cdtr, "Nm", "SYNTHETIC CREDITOR")
        if has_cdtr_id[i]:
            idn = etree.SubElement(cdtr, f"{{{NS}}}Id")
            org = etree.SubElement(idn, f"{{{NS}}}OrgId")
            oth = etree.SubElement(org, f"{{{NS}}}Othr")
            _sub(oth, "Id", r.creditor_id)
        if has_purp[i]:
            purp = etree.SubElement(tx, f"{{{NS}}}Purp")
            _sub(purp, "Cd", codes[r.category])

    etree.ElementTree(doc).write(path, xml_declaration=True,
                                 encoding="UTF-8", pretty_print=True)


def _sub(parent, tag, text):
    el = etree.SubElement(parent, f"{{{NS}}}{tag}")
    el.text = text
    return el


def parse_pacs008(path):
    """Extract only what a payment message carries."""
    ns = {"p": NS}
    tree = etree.parse(path)
    rows = []
    for tx in tree.iterfind(".//p:CdtTrfTxInf", ns):
        rows.append({
            "msg_id": tx.findtext("p:PmtId/p:EndToEndId", namespaces=ns),
            "amount_php": float(tx.findtext("p:IntrBkSttlmAmt", namespaces=ns)),
            "purpose_code": tx.findtext("p:Purp/p:Cd", default="", namespaces=ns),
            "creditor_id": tx.findtext("p:Cdtr/p:Id/p:OrgId/p:Othr/p:Id",
                                       default="", namespaces=ns),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 3. Estimators (use only message fields + public averages)
# --------------------------------------------------------------------------
def public_averages(P):
    e, f = P["electricity"], P["fuel"]
    ef_grid = P["grid_emission_factor_kgco2_per_kwh"]["value"]
    t_mid = estimator_tariff(P)
    d_mid = (f["diesel_price_min_php_per_l"] + f["diesel_price_max_php_per_l"]) / 2
    g_mid = (f["gasoline_price_min_php_per_l"] + f["gasoline_price_max_php_per_l"]) / 2
    sd = f["share_diesel"]
    # Category spend factors (kg CO2 per PHP) from public midpoints
    k_elec = ef_grid / t_mid
    k_fuel = sd * (f["ef_diesel_kgco2_per_l"] / d_mid) + (1 - sd) * (f["ef_gasoline_kgco2_per_l"] / g_mid)
    # Category-blind factor: spend-weighted blend using the assumed mix and
    # typical payment sizes (median quantity x midpoint price)
    mix = P["category_mix"]
    s_elec = mix["electricity"] * e["median_kwh_per_payment"] * t_mid
    s_fuel = mix["fuel"] * f["median_litres_per_payment"] * (sd * d_mid + (1 - sd) * g_mid)
    k_blind = (k_elec * s_elec + k_fuel * s_fuel) / (s_elec + s_fuel)
    return {"k_elec": k_elec, "k_fuel": k_fuel, "k_blind": k_blind,
            "t_mid": t_mid, "ef_grid": ef_grid}


def estimate(msgs, avg, registry, codes, use_creditor):
    """Method B (use_creditor=False) or C (True). Uncoded messages fall back to A."""
    est = msgs["amount_php"] * avg["k_blind"]                     # A fallback
    is_elec = msgs["purpose_code"] == codes["electricity"]
    is_fuel = msgs["purpose_code"] == codes["fuel"]
    est = np.where(is_elec, msgs["amount_php"] * avg["k_elec"], est)  # B
    est = np.where(is_fuel, msgs["amount_php"] * avg["k_fuel"], est)  # B
    if use_creditor:                                                # C
        tariff = msgs["creditor_id"].map(registry)
        has_t = is_elec & tariff.notna()
        est = np.where(has_t, msgs["amount_php"] / tariff * avg["ef_grid"], est)
    return np.asarray(est, dtype=float)


def estimate_creditor_only(msgs, avg, registry, codes):
    """Method C without the purpose-code condition: any payment whose creditor
    ID resolves to a utility in the registry is converted with that utility's
    tariff; all other payments are treated as in method B."""
    est = estimate(msgs, avg, registry, codes, use_creditor=False)
    tariff = msgs["creditor_id"].map(registry)
    has_t = tariff.notna().to_numpy()
    return np.where(has_t, msgs["amount_php"].to_numpy() / tariff.to_numpy() * avg["ef_grid"], est)


# --------------------------------------------------------------------------
# 4. Scenario loop
# --------------------------------------------------------------------------
def metrics(true, est):
    total_err = (est.sum() - true.sum()) / true.sum() * 100
    mape = np.mean(np.abs(est - true) / true) * 100
    return total_err, mape


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(HERE, "params.json")) as fh:
        P = json.load(fh)
    rng = np.random.default_rng(P["seed"])
    world, registry = build_world(P, rng)
    codes = P["iso_codes"]
    avg = public_averages(P)
    n = len(world)

    # Fixed random draws so scenarios are nested (same messages gain metadata)
    u_purp = rng.random(n)
    u_cdtr = rng.random(n)

    results = []
    sample_written = False
    schema = load_schema()
    val_log = []
    for p in P["scenarios"]["purpose_code_share_p"]:
        for q in P["scenarios"]["creditor_id_resolvable_share_q"]:
            has_purp = u_purp < p
            has_cdtr = (u_cdtr < q) & (world["category"] == "electricity").to_numpy()
            xml_path = os.path.join(OUT, "_tmp_pacs008.xml")
            write_pacs008(world, has_purp, has_cdtr, codes, xml_path)
            validate(schema, xml_path, val_log)
            if val_log:
                val_log[-1].update({"file": f"scenario p={p} q={q}"})
            msgs = parse_pacs008(xml_path)
            assert (msgs["msg_id"].values == world["msg_id"].values).all()

            est_A = msgs["amount_php"].to_numpy() * avg["k_blind"]
            est_B = estimate(msgs, avg, registry, codes, use_creditor=False)
            est_C = estimate(msgs, avg, registry, codes, use_creditor=True)
            est_Cr = estimate_creditor_only(msgs, avg, registry, codes)
            for cat in ["all", "electricity", "fuel"]:
                m = np.ones(n, bool) if cat == "all" else (world["category"] == cat).to_numpy()
                t = world["true_kgco2"].to_numpy()[m]
                for name, est in [("A_spend_only", est_A), ("B_purpose_code", est_B),
                                  ("C_code_plus_creditor", est_C),
                                  ("C2_creditor_only", est_Cr)]:
                    te, mape = metrics(t, est[m])
                    results.append({"p": p, "q": q, "category": cat, "method": name,
                                    "total_error_pct": round(te, 3),
                                    "mape_pct": round(mape, 3),
                                    "true_tco2": round(t.sum() / 1000, 3),
                                    "est_tco2": round(est[m].sum() / 1000, 3)})
            if p == 0.5 and q == 0.5 and not sample_written:
                # keep a small human-readable sample
                write_pacs008(world.head(5), has_purp[:5], has_cdtr[:5], codes,
                              os.path.join(OUT, "sample_pacs008.xml"))
                validate(schema, os.path.join(OUT, "sample_pacs008.xml"), val_log)
                sample_written = True
    os.remove(os.path.join(OUT, "_tmp_pacs008.xml"))
    if schema is not None:
        pd.DataFrame(val_log).to_csv(os.path.join(OUT, "xsd_validation.csv"), index=False)
        print(f"XSD validation: {sum(r['valid'] for r in val_log)} of {len(val_log)} "
              f"documents valid against pacs.008.001.08.xsd "
              f"({len(world)} transactions per scenario document).")

    res = pd.DataFrame(results)
    res.to_csv(os.path.join(OUT, "scenario_results.csv"), index=False)
    world.to_csv(os.path.join(OUT, "synthetic_world.csv"), index=False)
    pd.DataFrame([avg]).to_csv(os.path.join(OUT, "public_average_factors.csv"), index=False)

    plot(res)
    sensitivity(P)
    print_summary(res, avg)
    robustness(P)
    analytical_check(P)
    borrower_year(P)


def plot(res):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    styles = {0.0: ":", 0.5: "--", 1.0: "-"}
    for ax, cat in zip(axes, ["electricity", "fuel"]):
        d = res[(res.category == cat)]
        a = d[(d.method == "A_spend_only") & (d.q == 0.0)]
        ax.plot(a.p, a.mape_pct, color="#888888", marker="o", label="A: spend-only")
        b = d[(d.method == "B_purpose_code") & (d.q == 0.0)]
        ax.plot(b.p, b.mape_pct, color="#1f77b4", marker="o", label="B: + purpose code")
        if cat == "electricity":
            for q in [0.5, 1.0]:
                c = d[(d.method == "C_code_plus_creditor") & (d.q == q)]
                ax.plot(c.p, c.mape_pct, color="#2ca02c", ls=styles[q], marker="o",
                        label=f"C: + creditor ID (q={q:.0%})")
        ax.set_title(cat.capitalize())
        ax.set_xlabel("Share of messages with a purpose code (p)")
        ax.set_xticks([0, .25, .5, .75, 1])
        ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
        ax.grid(alpha=.3)
    axes[0].set_ylabel("MAPE per payment (%)")
    axes[0].legend(fontsize=8, frameon=False)
    axes[1].legend(fontsize=8, frameon=False)
    fig.suptitle("Estimation error vs metadata coverage (synthetic pacs.008 messages; 101 on-grid utility rates, Oct 2026)", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_error_vs_coverage.png"), dpi=200)
    plt.close(fig)


def sensitivity(P):
    """One-at-a-time sensitivity of method B electricity MAPE at p=1, q=0
    and method C at p=1, q=1, to the grid factor, the utility list and the
    consumption spread."""
    rows = []
    variants = [("base", {}),
                ("grid EF = combined margin 0.7058", {"ef": P["grid_emission_factor_kgco2_per_kwh"]["sensitivity_alt"]}),
                ("exclude LASURECO (lowest on-grid rate)", {"excl": ["LASURECO"]}),
                ("synthetic: 20 utilities between ALECO and Meralco", {"synth": True}),
                ("kWh sigma 0.8", {"sig": 0.8})]
    for label, v in variants:
        Q = json.loads(json.dumps(P))
        if "excl" in v:
            Q["electricity"]["exclude_codes"] = v["excl"]
        if "synth" in v:
            Q["electricity"]["tariff_source"] = "synthetic"
        if "sig" in v:
            Q["electricity"]["kwh_lognormal_sigma"] = v["sig"]
        rng = np.random.default_rng(Q["seed"])
        world, registry = build_world(Q, rng)
        if "ef" in v:
            world.loc[world.category == "electricity", "true_kgco2"] *= v["ef"] / P["grid_emission_factor_kgco2_per_kwh"]["value"]
        avg = public_averages(Q)
        m = world.category == "electricity"
        amt = world.loc[m, "amount_php"].to_numpy()
        true = world.loc[m, "true_kgco2"].to_numpy()
        estB = amt * avg["k_elec"]
        estC = amt / world.loc[m, "creditor_id"].map(registry).to_numpy() * avg["ef_grid"]
        rows.append({"variant": label,
                     "B_mape_pct": round(metrics(true, estB)[1], 2),
                     "C_mape_pct": round(metrics(true, estC)[1], 2),
                     "B_total_error_pct": round(metrics(true, estB)[0], 2),
                     "C_total_error_pct": round(metrics(true, estC)[0], 2)})
    sens = pd.DataFrame(rows)
    sens.to_csv(os.path.join(OUT, "sensitivity_electricity.csv"), index=False)
    print("\nElectricity sensitivity (p = q = 100%):\n",
          sens.set_index("variant").round(1).to_string())


def full_coverage(world, avg, registry):
    """Estimates at p = 100%, q = 100% computed directly from the world.
    Equivalent to the XML route in main() at full coverage (every message
    carries its purpose code and, for electricity, its creditor ID)."""
    amt = world["amount_php"].to_numpy()
    is_elec = (world["category"] == "electricity").to_numpy()
    est_A = amt * avg["k_blind"]
    est_B = np.where(is_elec, amt * avg["k_elec"], amt * avg["k_fuel"])
    tariff = world["creditor_id"].map(registry).to_numpy(dtype=float)
    est_C = np.where(is_elec, amt / np.where(is_elec, tariff, 1.0) * avg["ef_grid"], est_B)
    true = world["true_kgco2"].to_numpy()
    out = {}
    for cat, m in [("all", np.ones(len(world), bool)), ("electricity", is_elec),
                   ("fuel", ~is_elec)]:
        for name, est in [("A", est_A), ("B", est_B), ("C", est_C)]:
            te, mape = metrics(true[m], est[m])
            out[f"{cat}_{name}_mape"] = mape
            out[f"{cat}_{name}_total"] = te
    return out


def robustness(P):
    """Robustness checks at full coverage (p = 100%, q = 100%).
    1. Random seed: 30 seeds, all other inputs at base values.
    2. True category mix varied while the spend-only estimator keeps the
       base-mix factor (tests whether method A's offset in the portfolio total holds).
    3. Within-utility tariff variation w (drives method C's remaining error).
    4. True diesel share varied while estimators keep the base 50/50 blend."""
    base_avg = public_averages(P)
    rows = []

    def run(label, Q, seed, avg=None):
        rng = np.random.default_rng(seed)
        world, registry = build_world(Q, rng)
        r = full_coverage(world, avg if avg is not None else public_averages(Q), registry)
        r.update({"check": label, "seed": seed})
        rows.append(r)

    for s in range(1, 31):
        run("seed", P, P["seed"] + s)
    for mix in (0.4, 0.6, 0.8):
        Q = json.loads(json.dumps(P))
        Q["category_mix"] = {"electricity": mix, "fuel": round(1 - mix, 2)}
        run(f"category mix electricity={mix:.0%} (estimator assumes 60%)", Q, P["seed"], base_avg)
    for w in (0.0, 0.05, 0.10):
        Q = json.loads(json.dumps(P))
        Q["electricity"]["within_du_tariff_variation"] = w
        run(f"within-utility variation w={w:.0%}", Q, P["seed"])
    for sd in (0.3, 0.5, 0.7):
        Q = json.loads(json.dumps(P))
        Q["fuel"]["share_diesel"] = sd
        run(f"diesel share={sd:.0%} (estimator assumes 50%)", Q, P["seed"], base_avg)

    df = pd.DataFrame(rows)
    cols = ["check", "seed"] + [c for c in df.columns if c not in ("check", "seed")]
    df = df[cols]
    df.round(3).to_csv(os.path.join(OUT, "robustness_runs.csv"), index=False)

    seeds = df[df.check == "seed"].drop(columns=["check", "seed"])
    summ = pd.DataFrame({"mean": seeds.mean(), "min": seeds.min(), "max": seeds.max(),
                         "sd": seeds.std(ddof=1)}).round(2)
    summ.to_csv(os.path.join(OUT, "robustness_seed_summary.csv"))
    key = ["all_A_mape", "all_B_mape", "all_C_mape", "electricity_C_mape",
           "fuel_B_mape", "all_A_total", "electricity_A_total", "fuel_A_total"]
    print("\nRobustness across 30 seeds (p = q = 100%):\n", summ.loc[key].to_string())
    print("\nOther robustness checks (p = q = 100%):\n",
          df[df.check != "seed"].set_index("check")[key].round(1).to_string())



# --------------------------------------------------------------------------
# 6. Analytical expected errors (no random numbers)
# --------------------------------------------------------------------------
def _uniform_grid(lo, hi, n=20001):
    """Midpoints of n equal slices of [lo, hi]: averaging f over them
    approximates the expectation of f under a uniform distribution."""
    if hi == lo:
        return np.array([lo], dtype=float)
    edges = np.linspace(lo, hi, n + 1)
    return (edges[:-1] + edges[1:]) / 2


def analytical(P, avg=None):
    """Expected per-payment MAPE (%) at full coverage, computed from the
    assumptions alone. Because estimate / true depends only on prices
    (Section 4.4), each error is an average over the price distributions:
      electricity, payer tariff T = T_u (1 + e), T_u one of the evenly spread
      utility rates, e ~ U(-w, w):
        A: |k_blind * T / EF_grid - 1|    B: |T / T_mid - 1|    C: |e|  (= w/2)
      fuel, price P ~ U(lo, hi) for diesel (share s) or gasoline:
        A: |k_blind * P / EF_type - 1|    B and C: |k_fuel * P / EF_type - 1|
    Expected MAPE at partial coverage is linear in p (and q):
        MAPE(p) = (1 - p) MAPE_A + p MAPE_B (or C)."""
    avg = avg or public_averages(P)
    e, f = P["electricity"], P["fuel"]
    ef = avg["ef_grid"]
    du = du_table(P)[1]
    w = e.get("within_du_tariff_variation", 0.0)
    eps = _uniform_grid(-w, w)
    T = (du[:, None] * (1 + eps[None, :])).ravel()
    elec = {"A": np.mean(np.abs(avg["k_blind"] * T / ef - 1)),
            "B": np.mean(np.abs(T / avg["t_mid"] - 1)),
            "C": np.mean(np.abs(eps))}
    sd = f["share_diesel"]
    Pd = _uniform_grid(f["diesel_price_min_php_per_l"], f["diesel_price_max_php_per_l"])
    Pg = _uniform_grid(f["gasoline_price_min_php_per_l"], f["gasoline_price_max_php_per_l"])
    efd, efg = f["ef_diesel_kgco2_per_l"], f["ef_gasoline_kgco2_per_l"]

    def fuel_err(k):
        return (sd * np.mean(np.abs(k * Pd / efd - 1))
                + (1 - sd) * np.mean(np.abs(k * Pg / efg - 1)))

    fuel = {"A": fuel_err(avg["k_blind"]), "B": fuel_err(avg["k_fuel"])}
    fuel["C"] = fuel["B"]
    me = P["category_mix"]["electricity"]
    out = {}
    for m in ("A", "B", "C"):
        out[f"electricity_{m}_mape"] = 100 * elec[m]
        out[f"fuel_{m}_mape"] = 100 * fuel[m]
        out[f"all_{m}_mape"] = 100 * (me * elec[m] + (1 - me) * fuel[m])
    return out


def analytical_check(P):
    """Compare the analytical expectations with the simulation at full
    coverage (base seed and 30 further seeds) and along the p grid."""
    rows = []
    sims = []
    for s in range(0, 31):
        rng = np.random.default_rng(P["seed"] + s)
        world, registry = build_world(P, rng)
        sims.append(full_coverage(world, public_averages(P), registry))
    an = analytical(P)
    for key in an:
        vals = np.array([r[key] for r in sims])
        rows.append({"metric": key, "analytical": round(an[key], 2),
                     "simulated_base_seed": round(vals[0], 2),
                     "simulated_31_seed_mean": round(vals.mean(), 2),
                     "difference_base_minus_analytical": round(vals[0] - an[key], 2)})
    # Partial coverage: expected MAPE is linear in p (q = 100% for method C)
    for p in P["scenarios"]["purpose_code_share_p"]:
        for m in ("B", "C"):
            for cat in ("electricity", "fuel", "all"):
                v = (1 - p) * an[f"{cat}_A_mape"] + p * an[f"{cat}_{m}_mape"]
                rows.append({"metric": f"{cat}_{m}_mape at p={p:.0%}",
                             "analytical": round(v, 2)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "analytical_vs_simulated.csv"), index=False)
    full = df.dropna(subset=["simulated_base_seed"])
    print("\nAnalytical expected MAPE vs simulation (p = q = 100%):\n",
          full.set_index("metric").to_string())
    print("Largest |simulated - analytical| at base seed: "
          f"{full['difference_base_minus_analytical'].abs().max():.2f} percentage points")


def borrower_year(P, n_borrowers=5000, months=12):
    """Electricity error per borrower-year (the unit PCAF attributes), p = q = 100%.
    Each borrower pays one utility for 12 months. Two cases for the +/-w
    within-utility variation: redrawn every month (transient, e.g. monthly
    adjustments) or fixed per borrower (persistent, e.g. customer class)."""
    e = P["electricity"]
    rng = np.random.default_rng(P["seed"] + 7)
    du_ids, du_t = du_table(P)
    avg = public_averages(P)
    w = e.get("within_du_tariff_variation", 0.0)
    u = rng.integers(0, len(du_t), n_borrowers)
    kwh = rng.lognormal(np.log(e["median_kwh_per_payment"]), e["kwh_lognormal_sigma"],
                        (n_borrowers, months))
    dev_transient = rng.uniform(1 - w, 1 + w, (n_borrowers, months))
    dev_persistent = np.repeat(rng.uniform(1 - w, 1 + w, (n_borrowers, 1)), months, 1)
    rows = []
    for label, dev in [("transient (redrawn monthly)", dev_transient),
                       ("persistent (fixed per borrower)", dev_persistent)]:
        published = du_t[u][:, None]
        amt = kwh * published * dev
        true_m = kwh * avg["ef_grid"]
        est = {"B_purpose_code": amt * avg["k_elec"],
               "C_code_plus_creditor": amt / published * avg["ef_grid"]}
        for m, x in est.items():
            pay = np.mean(np.abs(x - true_m) / true_m) * 100
            yr = np.mean(np.abs(x.sum(1) - true_m.sum(1)) / true_m.sum(1)) * 100
            rows.append({"within_utility_variation": label, "method": m,
                         "mape_per_payment_pct": round(pay, 2),
                         "mape_per_borrower_year_pct": round(yr, 2)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "borrower_year.csv"), index=False)
    print(f"\nElectricity error per payment vs per borrower-year ({n_borrowers} borrowers x {months} months, p = q = 100%):\n",
          df.set_index(["within_utility_variation", "method"]).to_string())


def print_summary(res, avg):
    print("Public average factors (kg CO2 per PHP):",
          {k: round(v, 5) for k, v in avg.items()})
    piv = res.pivot_table(
        index=["category", "method", "q"], columns="p", values="mape_pct")
    print("\nMAPE (%) by p:\n", piv.round(1).to_string())
    tot = res[(res.category == "all") & (res.q == 1.0)].pivot_table(
        index="method", columns="p", values="total_error_pct")
    print("\nTotal-emissions error (%) by p, q=1, all categories:\n", tot.round(2).to_string())


if __name__ == "__main__":
    main()
