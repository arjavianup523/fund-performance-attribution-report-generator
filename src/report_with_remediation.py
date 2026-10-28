from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.remediation import (
    DEFAULT_DB,
    create_issue,
    list_issues,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def refresh_remediation_sheet(
    workbook_path: str | Path,
    db_path: str | Path = DEFAULT_DB,
) -> int:
    """Seed new data-quality issues and replace the workbook tracker with live records."""
    workbook_path = Path(workbook_path)

    if not workbook_path.exists():
        raise FileNotFoundError(workbook_path)

    # Seed only new exceptions. Existing issue records and their assignments
    # remain in SQLite and are not reset on subsequent report runs.
    try:
        exceptions = pd.read_excel(workbook_path, sheet_name="Data Quality")
    except ValueError:
        exceptions = pd.DataFrame()

    existing_keys = {
        issue["issue_key"] for issue in list_issues(db_path=db_path)
    }

    for _, row in exceptions.iterrows():
        record = {
            str(key): (
                None if pd.isna(value) else str(value)
            )
            for key, value in row.to_dict().items()
        }

        # Ignore empty rows in the source worksheet.
        record = {
            key: value for key, value in record.items()
            if value not in (None, "")
        }
        if not record:
            continue

        serialized = json.dumps(
            record, sort_keys=True, ensure_ascii=False
        )
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
        issue_key = f"DQ-{digest}"

        if issue_key in existing_keys:
            continue

        first_value = next(iter(record.values()))
        title = f"Data quality exception: {str(first_value)[:120]}"

        create_issue(
            issue_key=issue_key,
            title=title,
            description=serialized,
            severity="MEDIUM",
            actor="report-generator",
            db_path=db_path,
        )
        existing_keys.add(issue_key)

    issues = list_issues(db_path=db_path)
    tracker = pd.DataFrame(issues)

    if tracker.empty:
        tracker = pd.DataFrame(
            columns=[
                "issue_id", "issue_key", "title", "description",
                "severity", "status", "owner", "resolution",
                "created_at", "updated_at",
            ]
        )

    # Replace only the tracker worksheet; preserve every other report sheet.
    with pd.ExcelWriter(
        workbook_path,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace",
    ) as writer:
        tracker.to_excel(
            writer,
            sheet_name="Remediation Tracker",
            index=False,
        )

    return len(tracker)


def main() -> None:
    from src.complete_report import main as generate_report

    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    before = {
        path.resolve()
        for path in output_dir.glob("fund_performance_report_*.xlsx")
    }

    generate_report()

    candidates = [
        path for path in output_dir.glob("fund_performance_report_*.xlsx")
        if path.resolve() not in before
    ]
    if not candidates:
        candidates = list(output_dir.glob("fund_performance_report_*.xlsx"))

    if not candidates:
        raise FileNotFoundError(
            "The report generator did not produce a report workbook."
        )

    workbook = max(candidates, key=lambda path: path.stat().st_mtime)
    count = refresh_remediation_sheet(workbook)

    print(f"\nIntegrated report: {workbook}")
    print(f"Persistent remediation records: {count}")
    print(f"Remediation database: {DEFAULT_DB}")


if __name__ == "__main__":
    main()
