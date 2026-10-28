from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "raw" / "all_stocks_5yr.csv"
OUT = ROOT / "outputs"
LOGS = ROOT / "logs"

def run_report():
    OUT.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)

    df = pd.read_csv(INPUT)
    required = {"date","open","high","low","close","volume","Name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["source_row"] = np.arange(2, len(df) + 2)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    df["Name"] = df["Name"].astype("string").str.strip().str.upper()
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    exceptions = []
    def flag(mask, rule, severity, detail):
        for _, row in df.loc[mask].iterrows():
            exceptions.append({
                "source_row": int(row["source_row"]),
                "ticker": str(row["Name"]),
                "date": str(row["date"]),
                "severity": severity,
                "rule": rule,
                "detail": detail
            })

    flag(df["date"].isna(), "INVALID_DATE", "CRITICAL", "Missing or invalid date")
    flag(df["Name"].isna() | df["Name"].eq(""), "INVALID_TICKER", "CRITICAL", "Missing ticker")
    flag(df["close"].isna(), "INVALID_CLOSE", "CRITICAL", "Missing or nonnumeric closing price")
    flag(df["close"].notna() & (df["close"] <= 0), "NONPOSITIVE_CLOSE", "CRITICAL", "Closing price must be positive")

    ohlc = df[["open","high","low","close"]].notna().all(axis=1)
    bad_range = ohlc & (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )
    flag(bad_range, "INVALID_OHLC_RANGE", "HIGH", "OHLC values contradict high/low range")

    duplicate = df.duplicated(["Name","date"], keep="first") & df["Name"].notna() & df["date"].notna()
    flag(duplicate, "DUPLICATE_TICKER_DATE", "HIGH", "Duplicate ticker/date; later record excluded")

    valid = df[
        df["date"].notna() & df["Name"].notna() & df["Name"].ne("") &
        df["close"].notna() & (df["close"] > 0) & ~duplicate & ~bad_range
    ].copy()
    valid = valid.sort_values(["Name","date"]).reset_index(drop=True)
    if valid.empty:
        raise ValueError("No valid price records remain.")

    valid["daily_return"] = valid.groupby("Name")["close"].pct_change()
    daily = valid.dropna(subset=["daily_return"]).copy()
    if daily.empty:
        raise ValueError("Not enough dated prices to calculate returns.")

    # Equal-weighted average of available stock returns; this is a proxy,
    # not a verified mutual fund or investable portfolio.
    series = (
        daily.groupby("date", as_index=False)["daily_return"]
        .mean().rename(columns={"daily_return":"portfolio_return"})
        .sort_values("date").reset_index(drop=True)
    )
    series["growth_of_1"] = (1 + series["portfolio_return"]).cumprod()
    series["drawdown"] = series["growth_of_1"] / series["growth_of_1"].cummax() - 1
    series["month"] = series["date"].dt.to_period("M").astype(str)

    monthly = series.groupby("month", as_index=False).agg(
        portfolio_return=("portfolio_return", lambda x: (1 + x).prod() - 1),
        trading_days=("portfolio_return","count"),
        start_date=("date","min"),
        end_date=("date","max")
    )

    r = series["portfolio_return"]
    total = (1 + r).prod() - 1
    vol = r.std(ddof=1) * np.sqrt(252) if len(r) > 1 else np.nan
    annualized = (1 + total) ** (252 / len(r)) - 1 if len(r) and total > -1 else np.nan
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(252) if len(r) > 1 and r.std(ddof=1) > 0 else np.nan

    summary = pd.DataFrame([
        ["Report status", "COMPLETED WITH EXCEPTIONS" if exceptions else "COMPLETED"],
        ["Data scope", "Equal-weighted stock-return proxy; not a mutual fund"],
        ["Valid price rows", len(valid)],
        ["Unique tickers", valid["Name"].nunique()],
        ["Start date", valid["date"].min()],
        ["End date", valid["date"].max()],
        ["Return observations", len(r)],
        ["Total compounded return", total],
        ["Annualized return (252-day approximation)", annualized],
        ["Annualized volatility", vol],
        ["Maximum drawdown", series["drawdown"].min()],
        ["Sharpe ratio (risk-free rate assumed zero)", sharpe],
        ["Benchmark", "Not provided; no benchmark comparison performed"],
        ["Data quality exceptions", len(exceptions)]
    ], columns=["metric","value"])

    exception_df = pd.DataFrame(exceptions, columns=[
        "source_row","ticker","date","severity","rule","detail"
    ])
    if exception_df.empty:
        exception_df = pd.DataFrame([{
            "source_row": "", "ticker": "", "date": "",
            "severity": "INFO", "rule": "NO_EXCEPTIONS",
            "detail": "No data-quality exceptions detected"
        }])

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = OUT / f"fund_performance_report_{run_id}.xlsx"
    with pd.ExcelWriter(report, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Executive Summary", index=False)
        monthly.to_excel(writer, sheet_name="Monthly Performance", index=False)
        series.to_excel(writer, sheet_name="Daily Returns", index=False)
        exception_df.to_excel(writer, sheet_name="Data Quality", index=False)
        valid.head(1000).to_excel(writer, sheet_name="Validated Sample", index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cells in sheet.columns:
                width = min(max(len(str(c.value or "")) for c in cells) + 2, 42)
                sheet.column_dimensions[cells[0].column_letter].width = max(12, width)

    audit = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(INPUT),
        "report": str(report),
        "valid_rows": len(valid),
        "tickers": int(valid["Name"].nunique()),
        "exceptions": len(exceptions),
        "status": "COMPLETED WITH EXCEPTIONS" if exceptions else "COMPLETED"
    }
    with (LOGS / "audit_history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit, default=str) + "\n")

    print("\nREPORT CREATED:", report)
    print("AUDIT LOG:", LOGS / "audit_history.jsonl")
    print("\n", summary.to_string(index=False))
    print("\nExceptions recorded:", len(exceptions))

if __name__ == "__main__":
    run_report()
