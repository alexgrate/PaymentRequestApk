"""Views for browsing and exporting payment requests.

Everything here reads. The router in payments/routers.py raises on any write
attempt, and the `robot` database account holds GRANT SELECT only.
"""

import csv
import json
import logging
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.utils import Error as DatabaseError
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.generic import DetailView
from django_filters.views import FilterView

from .filters import PaymentRequestFilter
from .models import PaymentRequest

audit = logging.getLogger("payments.audit")

SETTLED_STATUSES = ["COMPLETED", "PAID"]

LIST_COLUMNS = [
    ("created_at", "Created"),
    ("payment_reference", "Reference"),
    ("requester_account_name", "Requester"),
    ("payer_account_name", "Payer"),
    ("request_amount", "Amount"),
    ("request_currency", "Ccy"),
    ("status", "Status"),
    ("request_type", "Type"),
]

EXPORT_COLUMNS = [
    "id", "created_at", "updated_at",
    "payment_reference", "settlement_reference", "cross_bank_token",
    "status", "request_type", "payment_type",
    "request_amount", "request_currency", "description",
    "requester_account_number", "requester_account_name",
    "requester_email", "requester_phone", "requester_customer_id",
    "payer_account_number", "payer_account_name", "payer_display_identifier",
    "payer_email", "payer_phone", "payer_customer_id",
    "cancellation_reason", "decline_reason",
    "created_by_user", "modified_by_user",
    "confirmation_deadline", "reversal_reference",
]

PII_COLUMNS = {
    "requester_email", "requester_phone", "requester_customer_id",
    "payer_email", "payer_phone", "payer_customer_id",
}


def handle_db_errors(view):
    """Render the connectivity page instead of a 500 when the CBA is down."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except DatabaseError as exc:
            return render(
                request,
                "payments/db_error.html",
                {"error": exc, "host": settings.DATABASES["cba"]["HOST"]},
                status=503,
            )

    return wrapper

DETAIL_GROUPS = [
    ("Request", ["id", "payment_reference", "request_type", "payment_type", "description"]),
    ("Requester", ["requester_account_name", "requester_account_number",
                   "requester_email", "requester_phone", "requester_customer_id"]),
    ("Payer", ["payer_account_name", "payer_account_number", "payer_display_identifier",
               "payer_email", "payer_phone", "payer_customer_id"]),
    ("References", ["cross_bank_token", "settlement_reference", "reversal_reference"]),
    ("Outcome", ["status", "cancellation_reason", "decline_reason"]),
    ("Timeline", ["created_at", "updated_at", "created_by_user", "modified_by_user",
                  "confirmation_deadline", "next_confirmation_reminder_at",
                  "next_poll_at", "next_reversal_at"]),
    ("System", ["version", "poll_attempts", "reversal_attempts",
                "confirmation_reminder_count", "metadata", "payment_details"]),
]

HEADER_FIELDS = {"request_amount", "request_currency"}


class DatabaseErrorMixin:
    """Render a readable page when the core banking database is unreachable.

    Without this a dropped VPN or closed tunnel produces a raw 500, which
    reads like an application bug rather than a connectivity problem.
    """

    def get(self, request, *args, **kwargs):
        try:
            response = super().get(request, *args, **kwargs)
            if hasattr(response, "render"):
                response.render()
            return response
        except DatabaseError as exc:
            return render(
                request,
                "payments/db_error.html",
                {"error": exc, "host": settings.DATABASES["cba"]["HOST"]},
                status=503,
            )


class PaymentRequestListView(LoginRequiredMixin, DatabaseErrorMixin, FilterView):
    model = PaymentRequest
    filterset_class = PaymentRequestFilter
    template_name = "payments/list.html"
    context_object_name = "payment_requests"
    paginate_by = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["list_columns"] = LIST_COLUMNS
        context["summary"] = self.filterset.qs.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="PENDING")),
            settled=Count("id", filter=Q(status__in=SETTLED_STATUSES)),
            total_value=Sum("request_amount"),
        )
        context["total_value_compact"] = compact_number(context["summary"]["total_value"])
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_query"] = params.urlencode()
        context["applied_filter_count"] = sum(1 for value in params.values() if value)
        return context


class PaymentRequestDetailView(LoginRequiredMixin, DatabaseErrorMixin, DetailView):
    model = PaymentRequest
    template_name = "payments/detail.html"
    context_object_name = "payment_request"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        labels = {f.name: f.verbose_name for f in obj._meta.fields}

        humanised = {"request_type", "payment_type"}

        groups = []
        for title, names in DETAIL_GROUPS:
            rows = []
            for name in names:
                value = getattr(obj, name)
                if name in humanised:
                    value = PaymentRequest._humanise(value) or None
                elif isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2, ensure_ascii=False)
                rows.append((labels[name].capitalize(), value, name))
            groups.append((title, rows))
        context["groups"] = groups
        return context


def _cell(value, column):
    """Render one value for export."""
    if not settings.EXPORT_INCLUDE_PII and column in PII_COLUMNS and value:
        return "***"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return value


def _filtered_queryset(request):
    filterset = PaymentRequestFilter(request.GET, queryset=PaymentRequest.objects.all())
    return filterset.qs


def _filename(extension):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"payment-requests-{stamp}.{extension}"


class _Echo:
    """File-like object that returns what it is given, for streaming CSV."""

    def write(self, value):
        return value


@login_required
@handle_db_errors
def export_csv(request):
    """Stream the current filter selection as CSV.

    Streamed rather than buffered so the response stays flat in memory as the
    table grows.
    """
    queryset = _filtered_queryset(request).values_list(*EXPORT_COLUMNS)
    queryset.exists()
    writer = csv.writer(_Echo())

    def rows():
        # UTF-8 BOM. Without it Excel opens the file as Windows-1252 and any
        # non-ASCII character in a description (emoji, accented names) renders
        # as mojibake. Other tools ignore the BOM.
        yield "\ufeff"
        yield writer.writerow(EXPORT_COLUMNS)
        for row in queryset.iterator(chunk_size=500):
            yield writer.writerow([_cell(v, c) for v, c in zip(row, EXPORT_COLUMNS)])

    _audit_export(request, "csv", queryset.count())
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{_filename("csv")}"'
    return response


@login_required
@handle_db_errors
def export_xlsx(request):
    """Export the current filter selection as an Excel workbook."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Payment Requests")

    header = []
    for name in EXPORT_COLUMNS:
        cell = WriteOnlyCell(sheet, value=name)
        cell.font = Font(bold=True)
        header.append(cell)
    sheet.append(header)

    rows = _filtered_queryset(request).values_list(*EXPORT_COLUMNS)
    _audit_export(request, "xlsx", rows.count())
    for row in rows.iterator(chunk_size=500):
        sheet.append([_excel_cell(v, c) for v, c in zip(row, EXPORT_COLUMNS)])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{_filename("xlsx")}"'
    workbook.save(response)
    return response


def compact_number(value):
    """1284 -> 1,284 | 1284000 -> 1.3M. For stat tiles, not table columns."""
    if value is None:
        return "0"
    number = float(value)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(number) >= limit:
            trimmed = f"{number / limit:.1f}".removesuffix(".0")
            return f"{trimmed}{suffix}"
    return f"{number:,.0f}"


def _audit_export(request, fmt, row_count):
    """Record who exported what.

    The exported columns include customer emails, phone numbers and account
    numbers, so downloads must be attributable after the fact.
    """
    filters = request.GET.urlencode() or "(none)"
    audit.info(
        "EXPORT format=%s user=%s ip=%s rows=%d pii=%s filters=%s",
        fmt,
        request.user.get_username(),
        request.META.get("REMOTE_ADDR", "?"),
        row_count,
        "included" if settings.EXPORT_INCLUDE_PII else "masked",
        filters,
    )


def _excel_cell(value, column):
    value = _cell(value, column)
    if hasattr(value, "quantize"):
        return float(value)
    return value
