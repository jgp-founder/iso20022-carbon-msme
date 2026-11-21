# ISO 20022 metadata and transaction-based carbon estimates — scenario analysis

[![DOI](https://zenodo.org/badge/1465087918.svg)](https://doi.org/10.5281/zenodo.24411217)

Code and synthetic data for the working paper *Can ISO 20022 Payment Metadata Improve Transaction-Based Carbon Estimates? A Field Mapping and Scenario Analysis for Philippine Retail Payment Rails*.

## Files
- `params.json` — every input, with its source or marked ASSUMPTION
- `run_analysis.py` — builds the synthetic world, writes and parses pacs.008 XML, runs the scenarios
- `data_dictionary.csv` — RQ1 field-to-GHG-category mapping
- `data/presyo_oct2026_residential.csv` — October 2026 residential rates of 113 distribution utilities (101 on-grid used), transcribed from ICSC PRESYO-PH National Overview (archived https://web.archive.org/web/20261120151637/https://presyo.icsc.ngo/national)
- `output/scenario_results.csv` — error by method, category, p and q
- `output/sensitivity_electricity.csv` — one-at-a-time sensitivity
- `output/xsd_validation.csv` — result of validating every generated pacs.008 document against the official schema
- `output/robustness_runs.csv` — full-coverage results for 30 extra seeds, alternative category mixes, within-utility variation and diesel shares
- `output/robustness_seed_summary.csv` — mean, min, max and SD across the 30 seeds
- `output/analytical_vs_simulated.csv` — expected MAPE computed from the assumptions alone (no random draws), compared with the simulation at full coverage, plus the expected MAPE along the coverage grid (MAPE is linear in p)
- `output/fig_error_vs_coverage.png` — main figure
- `business_tariffs/` — Section 4.6 case study: `meralco_bill.py` (bill model from Meralco's October 2026 Summary Schedule of Rates) and `table7.py`, which reproduces Table 7 (ALECO, VECO and Davao Light class rates, and Meralco business classes; VECO and Davao Light values are transcribed in `data/` because their pages could not be archived) into `table7_business_tariffs.csv`. Run it from inside that folder: `cd business_tariffs` then `python table7.py`.
- `output/sample_pacs008.xml` — five example messages
- `output/synthetic_world.csv` — the 10,000 synthetic payments with true quantities and emissions

## Run
Tested with Python 3.15 on Windows; package versions are pinned in `requirements.txt`.
```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # Windows (macOS/Linux: .venv/bin/python)
.venv/Scripts/python run_analysis.py
```
Place your own copy of `pacs.008.001.08.xsd` (ISO 20022 message archive, Payments Clearing and Settlement V09) in this folder first; it is not redistributed here. Runs in about 20 seconds. The seed is fixed, so results are reproducible.

On Windows, keep the folder path short (for example `D:\iso20022-carbon`). If the full path to `.venv` is too long, lxml and pillow fail with "DLL load failed ... The filename or extension is too long".

## Design
Methods compared (estimators see only message fields plus public averages, never the true tariff, fuel type or quantity):
- **A** spend-only, category-blind: amount × one blended kg CO2/PHP factor
- **B** purpose code known: amount × category factor (DOE grid factor ÷ unweighted mean of the utility rates, ₱13.28/kWh; fuel CO2 factor ÷ midpoint pump price)
- **C** purpose code + creditor ID: electricity amount ÷ that utility's published tariff × grid factor

Scenarios: p = share of messages with a purpose code (0–100%); q = share of coded electricity messages whose creditor ID resolves to a known utility (0, 50, 100%).

## Headline results (base case)
All prices are for October 2026: residential rates of the 101 on-grid distribution utilities in ICSC PRESYO-PH (₱5.33–19.36/kWh, mean ₱13.28; each utility equally likely); Metro Manila fuel ranges for the week beginning 20 October 2026 (diesel ₱88.30–98.80/L, gasoline ₱74.90–101.10/L).

| MAPE per payment (%) | A | B (p=100%) | C (p=100%, q=100%) |
|---|---|---|---|
| Electricity | 17.3 | 12.3 | 2.5 |
| Fuel | 63.7 | 6.9 | 6.9 |
| All | 35.9 | 10.1 | 4.2 |

Method A misstates category totals (electricity −15.0%, fuel +63.0% at p = 100%); these errors offset in the combined portfolio (+0.6%) under the assumed mix. Methods B and C are within 0.1% of each category's true total at full coverage.

## Main caveats
- Synthetic payments. Utility rates are real but unweighted (no customer counts) and residential only. Results depend on the assumptions in `params.json`; `output/analytical_vs_simulated.csv` shows which assumption drives each error.
- Setting `tariff_source` to `synthetic` in `params.json` reproduces the earlier design (20 utilities between ALECO and Meralco).
- C's remaining 2.5% electricity error comes entirely from the assumed ±5% variation within each utility.
- `FUEL` (Fuel/Gas) was registered in ExternalPurpose1Code on 28 Aug 2026 (CR1639). Domestic schemes still need to adopt it; until then, fuel payments cannot be tagged and stay at method A's error.
- CO2 only for fuel; CH4 and N2O excluded. Fuel densities are assumed.


## Schema validation (optional but recommended)
Download the official `pacs.008.001.08.xsd` from the ISO 20022 message archive
(https://www.iso20022.org/catalogue-messages/iso-20022-messages-archive?page=6 → Payments Clearing and Settlement V09 → pacs.008.001.08 → XSD)
and place it in the same folder as `run_analysis.py`. The script then validates every generated document and stops if any is invalid.
The schema is not included in this repository because it is ISO material; download it from the source.

## Message types

The simulation uses pacs.008.001.08 (credit transfer). The data dictionary also maps the direct-debit message pacs.003.001.08 (FIToFICustomerDirectDebitV08, Payments Clearing and Settlement V10 in the ISO 20022 message archive), which has the same purpose, creditor, ultimate creditor and remittance elements plus two direct-debit-only elements (creditor scheme identification and mandate related information). Neither schema file is redistributed here.

## How to cite
If you use this code, data or outputs, please cite:

Pardiñas, J. G. (2026). *iso20022-carbon-msme: Code and data for 'Can ISO 20022 Payment Metadata Improve Borrower-Level Carbon Estimates? A Field Mapping and Scenario Analysis of MSME Payments on Philippine Retail Payment Rails'* (Version 1.0.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.24411218

The DOI above is for version 1.0.0, the version used in the working paper. To cite all versions, use https://doi.org/10.5281/zenodo.24411217.

GitHub's "Cite this repository" button gives the same citation in APA and BibTeX (from `CITATION.cff`).

## Licence
The code and the author's own data and outputs are released under the MIT licence (see `LICENSE`); any copy or substantial portion must keep the copyright notice. Tariff figures in `data/` are transcribed from third-party public sources (ICSC PRESYO-PH, Meralco, VECO, Davao Light, ALECO) and remain subject to their owners' terms; their sources are listed in `params.json`, the `data/*_SOURCE.txt` files and the comments in `business_tariffs/`.
