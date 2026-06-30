import uuid
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


# ---------------------------------------------------------------------------
# Roles: we use Django's built-in auth + a lightweight profile for
# Vendor / Site Engineer / Quality / Vertical Lead / PMO / Admin.
# ---------------------------------------------------------------------------

class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin / Procurement"
    PMO = "PMO", "PMO (Head Office)"
    SITE_ENGINEER = "SITE_ENGINEER", "Site Engineer"
    QUALITY = "QUALITY", "Quality"
    VERTICAL_LEAD = "VERTICAL_LEAD", "Vertical Lead"
    VENDOR = "VENDOR", "Vendor"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices)
    vendor = models.ForeignKey("Vendor", null=True, blank=True, on_delete=models.SET_NULL,
                                help_text="Set only when role=VENDOR")

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# ---------------------------------------------------------------------------
# Phase 1: Onboarding & Contract Initialization
# ---------------------------------------------------------------------------

class Vendor(models.Model):
    """Step 1: Procurement creates the vendor + LOI metadata."""
    name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    loi_reference = models.CharField(max_length=100, help_text="Letter of Intent reference number")
    loi_document = models.FileField(upload_to="loi/", blank=True, null=True)
    is_approved = models.BooleanField(default=False, help_text="Flips True when vendor accepts PO (Step 3)")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, related_name="vendors_onboarded")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    """Step 2: PMO generates the base PO. Step 3: vendor acceptance flips status active."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft - awaiting vendor acceptance"
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"

    po_number = models.CharField(max_length=50, unique=True, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="purchase_orders")
    total_value = models.DecimalField(max_digits=14, decimal_places=2)
    total_qty_ordered = models.DecimalField(max_digits=12, decimal_places=2)
    unit_of_measure = models.CharField(max_length=20, default="unit")
    technical_annexure = models.FileField(upload_to="po_annexures/", blank=True, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, related_name="pos_created")
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = f"PO-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def accept(self):
        """Step 3: Vendor digital acceptance."""
        self.status = self.Status.ACTIVE
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at"])
        self.vendor.is_approved = True
        self.vendor.save(update_fields=["is_approved"])

    @property
    def qty_passed_so_far(self):
        return self.certificates.aggregate(total=models.Sum("passed_qty"))["total"] or 0

    @property
    def qty_remaining(self):
        return self.total_qty_ordered - self.qty_passed_so_far

    def __str__(self):
        return self.po_number


# ---------------------------------------------------------------------------
# Phase 2: Site Progress Logging
# ---------------------------------------------------------------------------

class MeasurementBookLog(models.Model):
    """Step 4: raw field-executed numbers + scanned MB page."""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="mb_logs")
    executed_qty = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    mb_image = models.ImageField(upload_to="measurement_books/")
    transcribed_text = models.TextField(blank=True, help_text="Reserved for future HTR/OCR pipeline output")
    logged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    logged_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"MB log #{self.pk} - {self.purchase_order.po_number} ({self.executed_qty})"


# ---------------------------------------------------------------------------
# Phase 3: Milestone Certification & Invoice Loop
# ---------------------------------------------------------------------------

class WorkCompletionCertificate(models.Model):
    """
    Step 5: The Joint Walkthrough & WCC Generation.

    Guardrail: passed_qty <= executed_qty (enforced in clean()).
    State machine: engineer -> quality -> vertical_lead, strictly in order.
    """
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="certificates")
    measurement_book_log = models.ForeignKey(MeasurementBookLog, on_delete=models.PROTECT, related_name="certificates")
    executed_qty = models.DecimalField(max_digits=12, decimal_places=2)
    passed_qty = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.TextField(blank=True)

    is_signed_by_engineer = models.BooleanField(default=False)
    engineer_signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                            on_delete=models.SET_NULL, related_name="wcc_engineer_signs")
    engineer_signed_at = models.DateTimeField(null=True, blank=True)

    is_signed_by_quality = models.BooleanField(default=False)
    quality_signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                           on_delete=models.SET_NULL, related_name="wcc_quality_signs")
    quality_signed_at = models.DateTimeField(null=True, blank=True)

    is_signed_by_vertical_lead = models.BooleanField(default=False)
    vertical_lead_signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                                 on_delete=models.SET_NULL, related_name="wcc_vlead_signs")
    vertical_lead_signed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.passed_qty is not None and self.executed_qty is not None:
            if self.passed_qty > self.executed_qty:
                raise ValidationError("passed_qty cannot exceed executed_qty.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    # --- state machine transitions, each enforcing strict ordering ---
    def sign_engineer(self, user):
        self.is_signed_by_engineer = True
        self.engineer_signed_by = user
        self.engineer_signed_at = timezone.now()
        self.save()

    def sign_quality(self, user):
        if not self.is_signed_by_engineer:
            raise ValidationError("Engineer sign-off required before Quality sign-off.")
        self.is_signed_by_quality = True
        self.quality_signed_by = user
        self.quality_signed_at = timezone.now()
        self.save()

    def sign_vertical_lead(self, user):
        if not self.is_signed_by_quality:
            raise ValidationError("Quality sign-off required before Vertical Lead sign-off.")
        self.is_signed_by_vertical_lead = True
        self.vertical_lead_signed_by = user
        self.vertical_lead_signed_at = timezone.now()
        self.save()

    @property
    def is_fully_certified(self):
        return self.is_signed_by_engineer and self.is_signed_by_quality and self.is_signed_by_vertical_lead

    def __str__(self):
        return f"WCC #{self.pk} - {self.purchase_order.po_number}"


class Invoice(models.Model):
    """Step 6: unlocked only once the linked WCC is fully certified."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted - awaiting compliance docs"
        PMO_REVIEW = "PMO_REVIEW", "Pending PMO Clearance"
        CLEARED = "STATUS_CLEARED_FOR_PAYMENT", "Cleared for Payment"
        REJECTED = "REJECTED", "Rejected"

    certificate = models.OneToOneField(WorkCompletionCertificate, on_delete=models.CASCADE, related_name="invoice")
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    billed_qty = models.DecimalField(max_digits=12, decimal_places=2)
    billed_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    retention_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    cleared_at = models.DateTimeField(null=True, blank=True)

    RETENTION_RATE = 0.10  # 10% retention, per spec

    def clean(self):
        if not self.certificate_id:
            return
        if not self.certificate.is_fully_certified:
            raise ValidationError("Invoice cannot be created until the WCC has all three sign-offs.")
        if self.billed_qty is not None and self.billed_qty > self.certificate.passed_qty:
            raise ValidationError("Billed quantity cannot exceed the certified passed_qty.")

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
        self.clean()
        super().save(*args, **kwargs)

    def clear_for_payment(self):
        """Step 8: PMO approves payout; calculates retention deduction."""
        self.retention_amount = round(float(self.billed_amount) * self.RETENTION_RATE, 2)
        self.status = self.Status.CLEARED
        self.cleared_at = timezone.now()
        self.save()
        RetentionLedgerEntry.objects.create(invoice=self, amount=self.retention_amount)

    def __str__(self):
        return self.invoice_number


class ComplianceSubmission(models.Model):
    """Step 7: HR compliance proofs required before invoice can move past SUBMITTED."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="compliance_docs")
    document = models.FileField(upload_to="compliance/")
    document_label = models.CharField(max_length=100, help_text="e.g. GST proof, PF challan, ESI challan")
    worker_count_declared = models.PositiveIntegerField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_label} for {self.invoice.invoice_number}"


class RetentionLedgerEntry(models.Model):
    """Step 8: 10% retention deduction logged as a separate ledger asset account."""
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="retention_entry")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    released = models.BooleanField(default=False)
    released_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Retention {self.amount} for {self.invoice.invoice_number}"
