# Fund Performance & Attribution Report Generator

A Python-based portfolio reporting prototype demonstrating financial return analytics, risk measurement, data-quality controls, sector attribution, exception tracking, Excel reporting, and audit logging.

## Business objective

Investment reporting teams need repeatable calculations, validated inputs, explainable performance differences, and an auditable record of report generation. This project demonstrates those controls in a reproducible reporting workflow.

## Features

- Data validation for required fields, invalid dates, nonpositive prices, and duplicate ticker/date records.
- Daily and monthly compounded return calculations.
- Annualized return, volatility, maximum drawdown, and Sharpe ratio.
- Allocation, selection, and interaction effects for sector attribution.
- Attribution reconciliation against active return.
- Excel workbook with executive summary, performance, data-quality, remediation, and attribution worksheets.
- Append-only JSON Lines audit history.
- Automated tests for workbook structure, calculations, and attribution controls.

## Technology

Python, pandas, NumPy, openpyxl, pytest, Excel.

## Run locally

1. Install Python 3.11 or later.
2. Install dependencies:

   `python -m pip install -r requirements.txt`

3. Place the historical stock-price dataset at:

   `data/raw/all_stocks_5yr.csv`

4. Generate a report:

   `python -m src.complete_report`

5. Run automated tests:

   `python -m pytest -q`

## Outputs

- `outputs/` — generated Excel reports.
- `logs/audit_history.jsonl` — report-run audit history.

## Data integrity and limitations

The historical price file contains stock prices, not verified mutual-fund holdings. Its equal-weighted stock-universe return is a research proxy, not an actual fund return.

The sector attribution input in `data/raw/illustrative_attribution_inputs.csv` is illustrative sample data. It demonstrates allocation, selection, interaction, and reconciliation calculations; it is not actual client or fund data.

A production deployment would require approved fund holdings, period-matched benchmark weights and returns, appropriate corporate-action treatment, documented calculation policies, and a persistent remediation workflow.

## Testing

The automated suite verifies the generated workbook, key report metrics, audit-log existence, return outputs, attribution reconciliation, and weight validation.

## Project status

Core reporting prototype implemented. Production use requires verified investment data and additional operational controls.
