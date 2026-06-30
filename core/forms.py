from django import forms
from .models import (
    Vendor, PurchaseOrder, MeasurementBookLog,
    WorkCompletionCertificate, Invoice, ComplianceSubmission,
)


class VendorOnboardForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "contact_email", "contact_phone", "gst_number", "loi_reference", "loi_document"]


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["vendor", "total_value", "total_qty_ordered", "unit_of_measure", "technical_annexure"]


class MeasurementBookLogForm(forms.ModelForm):
    class Meta:
        model = MeasurementBookLog
        fields = ["executed_qty", "description", "mb_image"]


class WCCForm(forms.ModelForm):
    class Meta:
        model = WorkCompletionCertificate
        fields = ["measurement_book_log", "executed_qty", "passed_qty", "remarks"]

    def __init__(self, *args, purchase_order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if purchase_order is not None:
            self.fields["measurement_book_log"].queryset = purchase_order.mb_logs.all()


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["billed_qty", "billed_amount"]

    def __init__(self, *args, certificate=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.certificate = certificate

    def clean_billed_qty(self):
        billed_qty = self.cleaned_data["billed_qty"]
        if self.certificate and billed_qty > self.certificate.passed_qty:
            raise forms.ValidationError(
                f"Billed quantity cannot exceed certified passed quantity ({self.certificate.passed_qty})."
            )
        return billed_qty


class ComplianceSubmissionForm(forms.ModelForm):
    class Meta:
        model = ComplianceSubmission
        fields = ["document", "document_label", "worker_count_declared"]
