from django.contrib import admin
from .models import (
    UserProfile, Vendor, PurchaseOrder, MeasurementBookLog,
    WorkCompletionCertificate, Invoice, ComplianceSubmission, RetentionLedgerEntry,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "vendor")
    list_filter = ("role",)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "loi_reference", "is_approved", "created_at")
    list_filter = ("is_approved",)
    search_fields = ("name", "gst_number")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("po_number", "vendor", "status", "total_value", "total_qty_ordered", "created_at")
    list_filter = ("status",)
    search_fields = ("po_number", "vendor__name")


@admin.register(MeasurementBookLog)
class MeasurementBookLogAdmin(admin.ModelAdmin):
    list_display = ("id", "purchase_order", "executed_qty", "logged_by", "logged_at")


@admin.register(WorkCompletionCertificate)
class WCCAdmin(admin.ModelAdmin):
    list_display = ("id", "purchase_order", "executed_qty", "passed_qty",
                     "is_signed_by_engineer", "is_signed_by_quality", "is_signed_by_vertical_lead")
    list_filter = ("is_signed_by_engineer", "is_signed_by_quality", "is_signed_by_vertical_lead")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "certificate", "billed_qty", "billed_amount", "status", "retention_amount")
    list_filter = ("status",)


@admin.register(ComplianceSubmission)
class ComplianceSubmissionAdmin(admin.ModelAdmin):
    list_display = ("document_label", "invoice", "is_verified", "uploaded_at")
    list_filter = ("is_verified",)


@admin.register(RetentionLedgerEntry)
class RetentionLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "released", "created_at")
