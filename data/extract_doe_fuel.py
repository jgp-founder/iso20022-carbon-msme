"""Extract weekly retail pump price ranges from DOE 'Price Monitoring of Liquid
Fuels' reports (week of 20-26 October 2026) into doe_fuel_prices_2026-10-20.csv.

Input: the DOE PDFs converted to text with `pdftotext -layout`, placed in
data/doe_fuel/ (the PDFs themselves are not redistributed here; see
doe_fuel_SOURCE.txt). For each city or municipality block, the 'OVERALL RANGE'
(lowest - highest price across brands) of each product is recorded, and so is
the range recomputed from the brand columns themselves. The two differ where the
report's OVERALL RANGE column leaves out a brand column or is shifted by one row;
run_analysis.py uses the range recomputed from the brand columns.

Usage: python data/extract_doe_fuel.py
"""
import csv
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "doe_fuel")
OUT = os.path.join(HERE, "doe_fuel_prices_2026-10-20.csv")

# file prefix (as named in doe_fuel_SOURCE.txt) -> DOE monitoring area
AREAS = {
    "NCR": "NCR",
    "NORTH_LUZON": "North Luzon",
    "REGION_IV-A": "South Luzon",
    "REGION_IV-B": "South Luzon",
    "REGION_V": "South Luzon",
    "VISAYAS": "Visayas",
    "MINDANAO": "Mindanao",
}
PROD = re.compile(r"\b(RON 100|RON 97|RON 95|RON 91|DIESEL PLUS|DIESEL|KEROSENE)\b")
PAIR = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*-\s*(\d{1,3}(?:\.\d+)?)")
NUM = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d+)?(?![\d.])")
SUB = re.compile(r"(REGION\s+[IVX]+(?:-[AB])?|Cordillera Administrative Region|REGIONS 6-8[^)]*)", re.I)


def flag(product, lo, hi):
    """Outliers are kept in the file and flagged; whether they are used is set
    in params.json (fuel.exclude_flagged)."""
    if product == "DIESEL" and lo < 70:
        return "outlier: diesel below PHP 70/L (all other monitored diesel ranges start at PHP 81.80/L or more)"
    if product.startswith("RON") and hi > 125:
        return "outlier: gasoline above PHP 125/L (all other monitored gasoline ranges end at PHP 119.90/L or less)"
    return ""


def main():
    rows = []
    for path in sorted(glob.glob(os.path.join(SRC, "*.txt"))):
        name = os.path.basename(path)
        area = next(v for k, v in AREAS.items() if name.startswith(k + "_"))
        sub, city, block, seen = "", "", 0, set()
        for line in open(path, encoding="utf-8"):
            m = SUB.search(line)
            if m:
                sub = m.group(1).strip()
            p = PROD.search(line)
            if not p:
                continue
            # a new city block starts at RON 100 or when a product repeats
            if p.group(1) == "RON 100" or p.group(1) in seen:
                block += 1
                city, seen = "", set()
            seen.add(p.group(1))
            label = re.sub(r"\s+", " ", line[:p.start()]).strip()
            if label and not re.search(r"\d", label):
                city = (city + " " + label).strip() if city and label not in city else (city or label)
            pairs = list(PAIR.finditer(line))
            if not pairs:
                continue
            last = pairs[-1]
            r_lo, r_hi = float(last.group(1)), float(last.group(2))
            # brand columns: every price between the product name and the
            # OVERALL RANGE column
            cells = [float(x) for x in NUM.findall(line[p.end():last.start()])]
            cells = [c for c in cells if c > 0]
            if not cells:
                if r_hi > 0:
                    print(f"check: overall range but no brand cells: {name} | {line.strip()[:120]}")
                continue
            lo, hi = min(cells), max(cells)
            rows.append({"area": area, "report": name[:-4], "subregion": sub,
                         "block": block, "location": city, "product": p.group(1),
                         "price_min_php_per_l": lo, "price_max_php_per_l": hi,
                         "doe_overall_range_min": r_lo, "doe_overall_range_max": r_hi,
                         "overall_range_differs": abs(lo - r_lo) > 0.005 or abs(hi - r_hi) > 0.005,
                         "flag": flag(p.group(1), lo, hi)})
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
