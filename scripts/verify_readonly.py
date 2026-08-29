"""Prove the read-only guarantees without needing a database connection.

Run:  .venv/bin/python manage.py shell < scripts/verify_readonly.py
"""

from django.apps import apps

from payments.models import PaymentRequest
from payments.routers import CbaRouter, ReadOnlyDatabaseError

router = CbaRouter()
ok = True


def check(label, condition):
    global ok
    ok = ok and condition
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")


print("Read-only guarantees")

check("PaymentRequest is unmanaged (Django never alters the table)",
      PaymentRequest._meta.managed is False)

check("PaymentRequest maps to the existing `payment_requests` table",
      PaymentRequest._meta.db_table == "payment_requests")

check("Reads of PaymentRequest are routed to the `cba` connection",
      router.db_for_read(PaymentRequest) == "cba")

try:
    router.db_for_write(PaymentRequest)
    check("Writes to PaymentRequest raise", False)
except ReadOnlyDatabaseError:
    check("Writes to PaymentRequest raise ReadOnlyDatabaseError", True)

check("No migration may run against the `cba` database",
      router.allow_migrate("cba", "payments") is False
      and router.allow_migrate("cba", "auth") is False
      and router.allow_migrate("cba", "sessions") is False)

check("Django's own apps still migrate on `default`",
      router.allow_migrate("default", "auth") is None)

for app in apps.get_app_configs():
    if app.label == "payments":
        continue
    for model in app.get_models():
        if router.db_for_write(model) is not None:
            check(f"{model.__name__} must not route to cba", False)

print("\nAll guarantees hold." if ok else "\nSOMETHING FAILED - do not deploy.")
