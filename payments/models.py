"""Read-only mapping onto the existing `payment_requests` table.

`managed = False` means Django never creates, alters or drops this table -
it already exists in the core banking database and is owned by that system.
Field definitions mirror the live schema; if a column is added upstream,
re-run `inspectdb` and update this model.
"""

from django.db import models


class PaymentRequest(models.Model):
    id = models.CharField(primary_key=True, max_length=36)

    requester_account_number = models.CharField(max_length=50)
    requester_account_name = models.CharField(max_length=255)
    requester_email = models.CharField(max_length=255, blank=True, null=True)
    requester_phone = models.CharField(max_length=30, blank=True, null=True)
    requester_customer_id = models.CharField(max_length=100, blank=True, null=True)

    payer_account_number = models.CharField(max_length=50, blank=True, null=True)
    payer_account_name = models.CharField(max_length=255, blank=True, null=True)
    payer_display_identifier = models.CharField(max_length=255, blank=True, null=True)
    payer_email = models.CharField(max_length=255, blank=True, null=True)
    payer_phone = models.CharField(max_length=30, blank=True, null=True)
    payer_customer_id = models.CharField(max_length=100, blank=True, null=True)

    request_amount = models.DecimalField(max_digits=19, decimal_places=4)
    request_currency = models.CharField(max_length=3)
    description = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=50)
    request_type = models.CharField(max_length=20)
    payment_type = models.CharField(max_length=50, blank=True, null=True)

    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    cross_bank_token = models.CharField(unique=True, max_length=36, blank=True, null=True)
    settlement_reference = models.CharField(unique=True, max_length=150, blank=True, null=True)

    cancellation_reason = models.CharField(max_length=500, blank=True, null=True)
    decline_reason = models.CharField(max_length=500, blank=True, null=True)

    metadata = models.JSONField()
    payment_details = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    created_by_user = models.CharField(max_length=255, blank=True, null=True)
    modified_by_user = models.CharField(max_length=255, blank=True, null=True)

    version = models.BigIntegerField()
    poll_attempts = models.IntegerField()
    next_poll_at = models.DateTimeField(blank=True, null=True)

    reversal_reference = models.CharField(max_length=64, blank=True, null=True)
    reversal_attempts = models.IntegerField()
    next_reversal_at = models.DateTimeField(blank=True, null=True)

    confirmation_reminder_count = models.IntegerField()
    confirmation_deadline = models.DateTimeField(blank=True, null=True)
    next_confirmation_reminder_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "payment_requests"
        ordering = ["-created_at"]
        verbose_name = "payment request"
        verbose_name_plural = "payment requests"

    @staticmethod
    def _humanise(value):
        """EXTERNALLY_MARKED_PAID -> Externally marked paid."""
        if not value:
            return ""
        return value.replace("_", " ").capitalize()

    @property
    def status_label(self):
        return self._humanise(self.status)

    @property
    def request_type_label(self):
        return self._humanise(self.request_type)

    @property
    def payment_type_label(self):
        return self._humanise(self.payment_type)

    def __str__(self):
        return f"{self.payment_reference or self.id} - {self.request_amount} {self.request_currency}"
