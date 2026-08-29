"""Build a local stand-in for the core banking table.

Only ever touches a local SQLite file. The command refuses to run against
MySQL, so it cannot reach the real database even by accident.

    USE_SAMPLE_DB=True .venv/bin/python manage.py seed_sample_db
"""

import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from payments.models import PaymentRequest

# Weighted to match the live distribution as of 2026-08-28.
STATUSES = (
    ["PENDING"] * 51 + ["CANCELLED"] * 16 + ["COMPLETED"] * 10
    + ["EXTERNALLY_MARKED_PAID"] * 8 + ["DECLINED"] * 6 + ["PAID"] * 3 + ["FAILED"] * 2
)

FIRST_NAMES = ["Adebayo", "Chiamaka", "Ifeanyi", "Ngozi", "Olumide", "Fatima",
               "Emeka", "Aisha", "Tunde", "Zainab", "Segun", "Amaka"]
LAST_NAMES = ["Okafor", "Adeyemi", "Balogun", "Eze", "Ibrahim", "Nwosu",
              "Oyelaran", "Danjuma", "Achebe", "Bello"]


def _name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


class Command(BaseCommand):
    help = "Populate a local SQLite stand-in for payment_requests with fake rows."

    def add_arguments(self, parser):
        parser.add_argument("--rows", type=int, default=120)
        parser.add_argument("--seed", type=int, default=20260828)

    def handle(self, *args, **options):
        connection = connections["cba"]
        engine = settings.DATABASES["cba"]["ENGINE"]
        if "sqlite3" not in engine:
            raise CommandError(
                f"Refusing to run: the `cba` connection is {engine}, not SQLite.\n"
                "This command only ever writes to a local sample file. "
                "Set USE_SAMPLE_DB=True to point `cba` at sample.sqlite3 first."
            )

        rng = random.Random(options["seed"])
        table = PaymentRequest._meta.db_table

        with connection.schema_editor() as editor:
            existing = connection.introspection.table_names()
            if table in existing:
                editor.delete_model(PaymentRequest)
            editor.create_model(PaymentRequest)

        start = datetime(2026, 6, 16, 5, 29, 7)
        span = int((datetime.now() - start).total_seconds())

        rows = []
        for _ in range(options["rows"]):
            created = start + timedelta(seconds=rng.randint(0, span))
            request_type = rng.choice(["PAY_FOR_ME"] * 54 + ["PAYMENT_REQUEST"] * 42)
            # payment_type is only populated for PAY_FOR_ME in the live data.
            payment_type = (
                rng.choice(["BANK_TRANSFER"] * 49 + ["BILL_PAYMENT"] * 5)
                if request_type == "PAY_FOR_ME" else None
            )
            status = rng.choice(STATUSES)
            requester, payer = _name(rng), _name(rng)
            rows.append(PaymentRequest(
                id=str(uuid.uuid4()),
                requester_account_number=str(rng.randint(1000000000, 9999999999)),
                requester_account_name=requester,
                requester_email=f"{requester.split()[0].lower()}@example.test",
                requester_phone=f"080{rng.randint(10000000, 99999999)}",
                requester_customer_id=f"CUS{rng.randint(100000, 999999)}",
                payer_account_number=str(rng.randint(1000000000, 9999999999)),
                payer_account_name=payer,
                payer_display_identifier=payer,
                payer_email=f"{payer.split()[0].lower()}@example.test",
                payer_phone=f"070{rng.randint(10000000, 99999999)}",
                payer_customer_id=f"CUS{rng.randint(100000, 999999)}",
                request_amount=Decimal(rng.randrange(50000, 250000000)) / 100,
                request_currency="NGN",
                description=rng.choice([
                    "School fees", "Rent contribution", "Equipment purchase",
                    "Invoice settlement", "Transport refund", None,
                ]),
                status=status,
                request_type=request_type,
                payment_type=payment_type,
                payment_reference=f"PR{rng.randint(10**11, 10**12 - 1)}",
                cross_bank_token=str(uuid.uuid4()) if rng.random() < 0.4 else None,
                settlement_reference=(
                    f"STL{rng.randint(10**11, 10**12 - 1)}"
                    if status in {"COMPLETED", "PAID"} else None
                ),
                cancellation_reason="Cancelled by requester" if status == "CANCELLED" else None,
                decline_reason="Insufficient funds" if status == "DECLINED" else None,
                metadata={"channel": rng.choice(["mobile", "web", "ussd"])},
                payment_details=None,
                created_at=created,
                updated_at=created + timedelta(minutes=rng.randint(0, 4000)),
                created_by_user=requester,
                modified_by_user=None,
                version=rng.randint(0, 5),
                poll_attempts=rng.randint(0, 3),
                next_poll_at=None,
                reversal_reference=None,
                reversal_attempts=0,
                next_reversal_at=None,
                confirmation_reminder_count=rng.randint(0, 2),
                confirmation_deadline=created + timedelta(days=2),
                next_confirmation_reminder_at=None,
            ))

        # `using` targets the sample file explicitly; the router's write guard
        # protects the real connection, which this command has already refused
        # to touch.
        PaymentRequest.objects.using("cba").bulk_create(rows, batch_size=200)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(rows)} sample rows into {settings.DATABASES['cba']['NAME']}"
        ))
