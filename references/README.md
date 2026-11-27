# References and Submission Notes

## Primary Data, Standards, and Archives
| Source | Identifier / URL | Used for |
|---|---|---|
| Zenodo Preprint (`v1.0`) | https://doi.org/10.5281/zenodo.24535399 (concept DOI: https://doi.org/10.5281/zenodo.24535398) | Public manuscript preprint |
| Zenodo Software & Data Archive (`v1.3.0`) | https://doi.org/10.5281/zenodo.24507246 (concept DOI: https://doi.org/10.5281/zenodo.24411217) | Frozen journal replication release (`iso20022-carbon-msme`) |
| GitHub Repository | https://github.com/jgp-founder/iso20022-carbon-msme | Source code, `params.json`, `data_dictionary.csv`, and outputs |
| ISO 20022 Message Archive (`pacs.008.001.08`, `pacs.003.001.08`) | https://www.iso20022.org/catalogue-messages/iso-20022-messages-archive | Official XML Schema validation (`schemas/`, root `pacs.008.001.08.xsd`) and field mapping |
| ISO 20022 External Code Sets (`CR1639` `FUEL`, `ELEC`) | https://www.iso20022.org/catalogue-messages/additional-content-messages/external-code-sets | `ExternalPurpose1Code` verification (`ELEC`, `FUEL` registered 2026-08-28) |
| ICSC PRESYO-PH National Overview & Master Workbook | https://presyo.icsc.ngo/national | October 2026 rates for 113 distribution utilities (`data/presyo_oct2026_residential.csv`) and 2018–2026 class checks |
| DOE Price Monitoring of Liquid Fuels (20–26 Oct 2026) | https://doe.gov.ph/retail-pump-prices-metro-manila | 341-location regional diesel & gasoline pump price ranges (`data/doe_fuel_prices_2026-10-20.csv`) |
| DOE Philippine Energy Plan 2023–2050 Vol. III | https://doe.gov.ph/pep | Luzon–Visayas operating (`0.6935`) and combined (`0.7058`) grid emission factors |
| DOE 2023–2032 Distribution Development Plan | https://prod-cms.doe.gov.ph/documents/d/epimb/2023-2032-distribution-development-plan | 2022 captive customer counts across 101 on-grid utilities (`data/ddp_customers_2022.csv`) |
| PCAF Global GHG Accounting & Reporting Standard Part A (3rd ed.) | https://carbonaccountingfinancials.com/standard | Financed-emissions attribution & data quality score hierarchy (Scores 1–5) |

The complete numbered reference list is in the manuscript (`paper/Manuscript_JCLF.docx` in the local workspace).

## Target Journal
- **Journal:** *Journal of Climate Finance* (Elsevier, ISSN `2949-7280`)
- **Author Guidelines:** `references/JCLF_submission_guidelines.pdf` (local copy; git-ignored)
- **Keywords:** `ISO 20022`; `IFRS S2`; `PCAF`; `financed emissions`; `MSMEs`; `Philippines`
- **JEL Codes:** `E42`, `G21`, `M41`, `Q54`, `Q56`

## Local Reference Subfolders (git-ignored)
- `Aleco/`, `Davao Light/`, `Meralco Oct 2026 rates/`, `Veco/` — Published October 2026 utility rate schedules and tariff advisories used in `business_tariffs/table7.py`
- `Fuel/` — DOE regional liquid fuel price monitoring PDFs (20–26 October 2026)
- `PEP 2023-2050 Vol. III_0/` — DOE grid emission factor source volume
- `Utility Grid Master File/` — ICSC 2018–2026 rate master workbook (staged locally to `data/icsc_rates/` by `run_all.py`)

## Submission & Workspace Checklist
- [x] `python run_all.py` passes from a clean environment at the workspace root.
- [x] Every generated `pacs.008.001.08` XML batch validates against the official ISO 20022 XSD (`output/xsd_validation.csv`).
- [x] `v1.3.0` tracked paths match Zenodo (`10.5281/zenodo.24507246`) and `paper/Manuscript_JCLF.docx`.
- [ ] Upload `paper/Manuscript_JCLF.docx`, `paper/Highlights.docx`, `paper/Cover_Letter_JCLF.docx`, `paper/Figure_1.pdf` (or `.eps`/`.png`), and `declarationStatement.docx` at https://submit.elsevier.com/JCLIMF per `references/JCLF_submission_guidelines.pdf`.
