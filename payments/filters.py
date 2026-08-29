"""Filters for the payment request list.

Dropdown options are read from the live table rather than hard-coded, so new
statuses or payment types appear on their own without a code change.
"""

import django_filters
from django import forms
from django.db.models import Q
from django.db.utils import Error as DatabaseError

from .models import PaymentRequest


def _distinct_choices(column):
    """Distinct values for `column`, as form choices.

    The stored value is kept as the option value; the label is humanised, so a
    dropdown reads "Externally marked paid" rather than EXTERNALLY_MARKED_PAID.

    Returns an empty list if the database is unreachable so the page can still
    render (and show the connection error) instead of raising during form
    construction.
    """
    def choices():
        try:
            values = (
                PaymentRequest.objects.order_by(column)
                .values_list(column, flat=True)
                .distinct()
            )
            return [(v, PaymentRequest._humanise(v)) for v in values if v]
        except DatabaseError:
            return []

    return choices


class PaymentRequestFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Reference, name, account number, description..."}
        ),
    )

    status = django_filters.ChoiceFilter(
        choices=_distinct_choices("status"), empty_label="All statuses"
    )
    request_type = django_filters.ChoiceFilter(
        choices=_distinct_choices("request_type"), empty_label="All types"
    )
    payment_type = django_filters.ChoiceFilter(
        choices=_distinct_choices("payment_type"), empty_label="All payment types"
    )
    request_currency = django_filters.ChoiceFilter(
        choices=_distinct_choices("request_currency"), empty_label="All currencies"
    )

    created_from = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte",
        label="Created from",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    created_to = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte",
        label="Created to",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    amount_min = django_filters.NumberFilter(
        field_name="request_amount", lookup_expr="gte", label="Amount from"
    )
    amount_max = django_filters.NumberFilter(
        field_name="request_amount", lookup_expr="lte", label="Amount to"
    )

    requester_account_number = django_filters.CharFilter(
        lookup_expr="icontains", label="Requester account"
    )
    payer_account_number = django_filters.CharFilter(
        lookup_expr="icontains", label="Payer account"
    )

    class Meta:
        model = PaymentRequest
        fields = []

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(payment_reference__icontains=value)
            | Q(settlement_reference__icontains=value)
            | Q(cross_bank_token__icontains=value)
            | Q(requester_account_name__icontains=value)
            | Q(requester_account_number__icontains=value)
            | Q(payer_account_name__icontains=value)
            | Q(payer_account_number__icontains=value)
            | Q(payer_display_identifier__icontains=value)
            | Q(description__icontains=value)
            | Q(id__icontains=value)
        )
