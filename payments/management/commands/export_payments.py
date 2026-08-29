"""Write the payment request export to a file, server-side.

Removes the browser round-trip when verifying on the server: the file is
produced where the database is reachable, so it can be compared immediately.

    python manage.py export_payments check.csv
    python scripts/verify_against_db.py check.csv

Uses exactly the same columns and value formatting as the web download, so what
this writes is what the download contains.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from payments.models import PaymentRequest
from payments.views import EXPORT_COLUMNS, _cell


class Command(BaseCommand):
    help = "Write the payment_requests export to a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("path", help="output file, e.g. check.csv")
        parser.add_argument(
            "--status", help="optional status filter, e.g. PENDING", default=None
        )

    def handle(self, *args, **options):
        queryset = PaymentRequest.objects.all()
        if options["status"]:
            queryset = queryset.filter(status=options["status"])

        path = Path(options["path"]).expanduser().resolve()
        rows = 0
        # utf-8-sig matches the web download, so Excel reads it the same way.
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(EXPORT_COLUMNS)
            for row in queryset.values_list(*EXPORT_COLUMNS).iterator(chunk_size=500):
                writer.writerow([_cell(v, c) for v, c in zip(row, EXPORT_COLUMNS)])
                rows += 1

        self.stdout.write(self.style.SUCCESS(f"Wrote {rows} rows to {path}"))
