from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # Step 1
    path("admin-panel/onboard-vendor/", views.onboard_vendor, name="onboard_vendor"),
    # Step 2
    path("pmo/create-po/", views.create_po, name="create_po"),
    # Step 3
    path("vendor/accept-po/<int:po_id>/", views.accept_po, name="accept_po"),
    # Step 4
    path("site/log-progress/<int:po_id>/", views.log_progress, name="log_progress"),
    # Step 5
    path("site/wcc-verification/<int:po_id>/", views.wcc_verification, name="wcc_verification"),
    # Step 6
    path("vendor/generate-invoice/<int:wcc_id>/", views.generate_invoice, name="generate_invoice"),
    # Step 7
    path("vendor/compliance-upload/<int:invoice_id>/", views.compliance_upload, name="compliance_upload"),
    # Step 8
    path("pmo/payment-clearance/", views.payment_clearance, name="payment_clearance"),
]
