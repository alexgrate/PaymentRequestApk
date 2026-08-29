"""Compare an exported CSV against an older report of the same table.

    python scripts/compare_reports.py <old-report.csv> <new-export.csv>

Matches rows on ID and reports three things: rows only in one file, rows only
in the other, and field-level differences for rows present in both. Amounts and
timestamps are normalised first, so "1,000.00" and "1000.0000" compare equal.
"""

import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Old analyst report column -> exported column.
COLUMN_MAP = {
    "ID": "id",
    "Requester Acct No": "requester_account_number",
    "Requester Name": "requester_account_name",
    "Payer Acct No": "payer_account_number",
    "Payer Name": "payer_account_name",
    "Amount": "request_amount",
    "Currency": "request_currency",
    "Description": "description",
    "Status": "status",
    "Request Type": "request_type",
    "Payment Type": "payment_type",
    "Cancellation Reason": "cancellation_reason",
    "Decline Reason": "decline_reason",
    "Created At": "created_at",
    "Updated At": "updated_at",
    "Requester Cust ID": "requester_customer_id",
    "Payer Cust ID": "payer_customer_id",
}

# Fields worth comparing. Descriptions are excluded: the old tool replaced
# emoji with "?", so they differ for reasons that say nothing about the data.
COMPARE = [
    "status", "request_type", "payment_type", "request_amount",
    "request_currency", "requester_account_number", "requester_account_name",
    "payer_account_number", "payer_account_name", "created_at",
]


def normalise(field, value):
    value = (value or "").strip()
    if not value:
        return ""
    if field == "request_amount":
        try:
            return str(Decimal(value.replace(",", "")).normalize())
        except InvalidOperation:
            return value
    if field in {"created_at", "updated_at"}:
        # Old report is minute-precision; the export has seconds.
        return value.replace("T", " ")[:16]
    return value


def load(path):
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = {}
    for row in csv.DictReader(raw.splitlines()):
        row = {COLUMN_MAP.get(k, k): v for k, v in row.items() if k}
        key = (row.get("id") or "").strip()
        if key:
            rows[key] = row
    return rows


def main(old_path, new_path):
    old, new = load(old_path), load(new_path)
    old_ids, new_ids = set(old), set(new)

    print(f"old report : {len(old):4d} rows  {Path(old_path).name}")
    print(f"new export : {len(new):4d} rows  {Path(new_path).name}")
    print(f"in both    : {len(old_ids & new_ids):4d}")

    only_new = new_ids - old_ids
    only_old = old_ids - new_ids

    print(f"\nOnly in the new export: {len(only_new)}")
    for rid in sorted(only_new, key=lambda r: new[r].get("created_at", "")):
        row = new[rid]
        print(f"   {row.get('created_at','')[:16]}  {row.get('status',''):22s} "
              f"{row.get('request_amount',''):>16s}  {row.get('requester_account_name','')}")
    if only_new:
        print("   (expected - these were created after the old report was run)")

    print(f"\nOnly in the old report: {len(only_old)}")
    for rid in sorted(only_old):
        print(f"   {rid}  {old[rid].get('status','')}")
    if only_old:
        print("   (NOT expected - rows should never disappear from a read-only view)")

    print(f"\nField differences among the {len(old_ids & new_ids)} shared rows:")
    diffs = 0
    for rid in sorted(old_ids & new_ids, key=lambda r: new[r].get("created_at", "")):
        for field in COMPARE:
            a = normalise(field, old[rid].get(field))
            b = normalise(field, new[rid].get(field))
            if a != b:
                diffs += 1
                print(f"   {rid[:8]}  {field:26s} old={a or '(blank)':<28s} new={b or '(blank)'}")
    if not diffs:
        print("   none - every shared row matches on every compared field")
    else:
        print(f"\n   {diffs} difference(s). Check `updated_at`: if the row changed after")
        print("   the old report was generated, a different status is correct.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
