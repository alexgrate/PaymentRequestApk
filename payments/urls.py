from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentRequestListView.as_view(), name="payment-request-list"),
    path("export/xlsx/", views.export_xlsx, name="export-xlsx"),
    path("healthz/", views.healthz, name="healthz"),
    path("<str:pk>/", views.PaymentRequestDetailView.as_view(), name="payment-request-detail"),
]
