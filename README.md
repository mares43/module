# Elestas 2027 Baseload Desk

Tool for sizing and pricing the 2027 forward electricity sale (ikili anlaşma) for the portfolio that leaves YEKDEM: all HES and the unlicensed GES capacity whose 10-year support ends.

## Pipeline

```bash
pip install -r requirements.txt
python scripts/extract_data.py path/to/Elestas_Saatlik_Uretimler_2025-2026.xlsx   # -> data/*.csv
python scripts/build_app_data.py                                                  # -> app/data.js
python model/analysis.py                                                          # scenario tables
```

Then open `app/index.html` in a browser. It is a static page and needs no server.

The workbook, the CSVs, `app/data.js` and `REPORT.md` are git-ignored on purpose. They contain meter data and pricing targets, and this repository is public.

## Model

- `model/curtailment.py` adds back the hydro output spilled while plants were stopped in near-zero PTF hours. A stopped hour is refilled only on days the plant otherwise ran at ≥ 85% of capacity, so intra-day pondage shifting is not counted.
- `model/scenarios.py` maps 2025/2026 hourly generation and PTF onto 2027 dates. It also holds the GES YEKDEM exit schedule: 5 MW all year, +10 MW from February, +5.5 MW from August.
- `model/contract.py` contains the hourly merchant dispatch and the settlement of a baseload contract against PTF:
  - HES stops when PTF is below its stop price.
  - Post-YEKDEM unlicensed GES is paid min(PTF, cap), following Cumhurbaşkanı Kararı 11415.
- `model/analysis.py` builds the five weighted scenarios (normal, wet repeat, dry, and two cross cases) and compares candidate deals.
- `app/index.html` runs the same model in the browser, with editable volumes, prices, scenario weights, GES rules and plant inclusion.
