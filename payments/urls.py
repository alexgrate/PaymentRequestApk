from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentRequestListView.as_view(), name="payment-request-list"),
    path("export/csv/", views.export_csv, name="export-csv"),
    path("export/xlsx/", views.export_xlsx, name="export-xlsx"),
    path("<str:pk>/", views.PaymentRequestDetailView.as_view(), name="payment-request-detail"),
]
