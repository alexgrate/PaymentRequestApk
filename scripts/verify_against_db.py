"""Independently verify an export against the core banking database.

This deliberately does NOT use Django. It opens its own PyMySQL connection and
issues plain SQL, so it shares no code with the application - the model, the
router, the filters and the export all sit outside this path. If the numbers
agree, they agree for real.

    python scripts/verify_against_db.py                    # what the database says
    python scripts/verify_against_db.py <export.csv>       # compare an export against it

Read-only: every statement is a SELECT, and the `robot` account holds
GRANT SELECT only.
"""

import csv
import os
import sys
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TABLE = "payment_requests"


def load_env():
    """Minimal .env reader - avoids importing anything the app uses."""
    values = {}
    env = BASE_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def connect():
    import pymysql

    env = load_env()
    host = os.getenv("CBA_DB_HOST", env.get("CBA_DB_HOST", ""))
    if not host:
        sys.exit("No CBA_DB_HOST. Run this on the server, or set up a tunnel.")
    return pymysql.connect(
        host=host,
        port=int(os.getenv("CBA_DB_PORT", env.get("CBA_DB_PORT", "3306"))),
        user=os.getenv("CBA_DB_USER", env.get("CBA_DB_USER", "")),
        password=os.getenv("CBA_DB_PASSWORD", env.get("CBA_DB_PASSWORD", "")),
        database=os.getenv("CBA_DB_NAME", env.get("CBA_DB_NAME", "")),
        charset="utf8mb4",
        connect_timeout=10,
    )


def db_snapshot(cursor):
    """Everything the comparison needs, straight from SQL."""
    snapshot = {}

    cursor.execute(f"SELECT COUNT(*), SUM(request_amount) FROM `{TABLE}`")
    count, total = cursor.fetchone()
    snapshot["count"] = count
    snapshot["total"] = Decimal(total or 0)

    cursor.execute(f"SELECT MIN(created_at), MAX(created_at) FROM `{TABLE}`")
    snapshot["first"], snapshot["last"] = cursor.fetchone()

    for column in ("status", "request_type"):
        cursor.execute(
            f"SELECT `{column}`, COUNT(*) FROM `{TABLE}` GROUP BY `{column}` ORDER BY 2 DESC"
        )
        snapshot[column] = dict(cursor.fetchall())

    cursor.execute(
        f"SELECT id, status, request_amount, created_at FROM `{TABLE}`"
    )
    snapshot["rows"] = {
        str(rid): {
            "status": status,
            "amount": Decimal(amount),
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S") if created else "",
        }
        for rid, status, amount, created in cursor.fetchall()
    }
    return snapshot


def read_export(path):
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = {}
    for row in csv.DictReader(raw.splitlines()):
        rid = (row.get("id") or "").strip()
        if not rid:
            continue
        rows[rid] = {
            "status": (row.get("status") or "").strip(),
            "amount": Decimal((row.get("request_amount") or "0").replace(",", "")),
            "created_at": (row.get("created_at") or "").strip()[:19],
        }
    return rows


def show(snapshot):
    print("Straight from the database")
    print(f"  rows          : {snapshot['count']}")
    print(f"  total value   : {snapshot['total']:,.2f}")
    print(f"  earliest      : {snapshot['first']}")
    print(f"  latest        : {snapshot['last']}")
    print("  by status     :")
    for status, n in snapshot["status"].items():
        print(f"      {status:<26s} {n}")
    print("  by type       :")
    for kind, n in snapshot["request_type"].items():
        print(f"      {kind:<26s} {n}")
    print("\nCompare these against the dashboard tiles.")


def compare(snapshot, export, name):
    db_rows = snapshot["rows"]
    db_ids, csv_ids = set(db_rows), set(export)
    problems = 0

    print(f"\nComparing {name} against the database")
    print(f"  database  : {len(db_ids)} rows")
    print(f"  export    : {len(csv_ids)} rows")

    missing = db_ids - csv_ids
    extra = csv_ids - db_ids
    if missing:
        problems += len(missing)
        print(f"\n  IN DATABASE BUT NOT IN THE EXPORT: {len(missing)}")
        for rid in sorted(missing)[:20]:
            print(f"      {rid}  {db_rows[rid]['status']}")
        print("      (an unfiltered export must contain every row)")
    if extra:
        problems += len(extra)
        print(f"\n  IN THE EXPORT BUT NOT IN THE DATABASE: {len(extra)}")
        for rid in sorted(extra)[:20]:
            print(f"      {rid}")
        print("      (the export must never invent rows)")

    mismatches = 0
    for rid in sorted(db_ids & csv_ids):
        for field in ("status", "amount", "created_at"):
            a, b = db_rows[rid][field], export[rid][field]
            if a != b:
                mismatches += 1
                if mismatches <= 20:
                    print(f"      {rid[:8]}  {field:11s} db={a}  export={b}")
    if mismatches:
        problems += mismatches
        print(f"\n  FIELD MISMATCHES: {mismatches}")

    csv_total = sum(r["amount"] for r in export.values())
    print(f"\n  total value   database={snapshot['total']:,.2f}  export={csv_total:,.2f}",
          "  MATCH" if csv_total == snapshot["total"] else "  DIFFERENT")

    print("\n" + ("  EXPORT MATCHES THE DATABASE EXACTLY" if problems == 0
                  else f"  {problems} discrepancy/discrepancies - see above"))
    return problems


def main():
    export_path = sys.argv[1] if len(sys.argv) > 1 else None
    connection = connect()
    try:
        with connection.cursor() as cursor:
            snapshot = db_snapshot(cursor)
    finally:
        connection.close()

    show(snapshot)
    if export_path:
        sys.exit(1 if compare(snapshot, read_export(export_path), Path(export_path).name) else 0)


if __name__ == "__main__":
    main()
