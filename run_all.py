"""Master one-command reproducibility script for Study Paper 1 ('iso20022-carbon-msme').

Reproduces end-to-end (run from any location; all paths are relative to this file):
  1. Synthetic MSME world, ISO 20022 pacs.008.001.08 XML generation & XSD validation,
     Methods A/B/C/C2 scenario grid, Figure 1 (.png/.pdf/.eps), electricity sensitivity,
     30-seed & structural robustness checks, closed-form analytical verification,
     borrower-year & PCAF portfolio attribution checks, purpose-code miscoding, and
     DOE regional fuel-price decomposition (run_analysis.py)
  2. Section 4.6 business-tariff case study across ALECO, VECO, Davao Light, and
     Meralco rate schedules (business_tariffs/table7.py)
  3. Real-rate monthly & commercial/residential checks (data/icsc_rate_checks.py) and
     2022 DOE Distribution Development Plan customer-weighted Method B check
     (data/ddp_weighting.py), executed automatically when the local-only ICSC master
     workbook is staged in data/icsc_rates/
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROOT_XSD = ROOT / "pacs.008.001.08.xsd"
SCHEMA_XSD = ROOT / "schemas" / "pacs.008.001.08.xsd"
ICSC_XLSX = ROOT / "data" / "icsc_rates" / "Rates_per_Costumer_Class_Per_DU_Per_Region.xlsx"
REF_ICSC_XLSX = (
    ROOT / "references" / "Utility Grid Master File" / "Rates per Costumer Class, Per DU, Per Region.xlsx"
)


def main() -> None:
    if not ROOT_XSD.exists() and SCHEMA_XSD.exists():
        shutil.copy2(SCHEMA_XSD, ROOT_XSD)
    if not ICSC_XLSX.exists() and REF_ICSC_XLSX.exists():
        ICSC_XLSX.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REF_ICSC_XLSX, ICSC_XLSX)

    steps: list[tuple[str, Path]] = [
        ("run_analysis.py", ROOT),
        ("business_tariffs/table7.py", ROOT / "business_tariffs"),
    ]
    if ICSC_XLSX.exists():
        steps.extend([
            ("data/icsc_rate_checks.py", ROOT),
            ("data/ddp_weighting.py", ROOT),
        ])
    else:
        print("Note: local ICSC workbook not present in data/icsc_rates/; skipping ICSC rate checks.")

    for rel, workdir in steps:
        print(f"\n>>> Running {rel} ...")
        subprocess.run([sys.executable, str(ROOT / rel)], check=True, cwd=workdir)

    print("\nAll Study Paper 1 checks, tables, XML validations, and figures verified!")


if __name__ == "__main__":
    main()
