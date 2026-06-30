from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404

from .models import (
    Vendor, PurchaseOrder, MeasurementBookLog,
    WorkCompletionCertificate, Invoice, ComplianceSubmission, Role,
)
from .forms import (
    VendorOnboardForm, PurchaseOrderForm, MeasurementBookLogForm,
    WCCForm, InvoiceForm, ComplianceSubmissionForm,
)


def _role(user):
    return getattr(getattr(user, "profile", None), "role", None)


def role_required(*roles):
    def check(user):
        return user.is_authenticated and (user.is_superuser or _role(user) in roles)
    return user_passes_test(check, login_url="/login/")


@login_required
def dashboard(request):
    role = _role(request.user)
    context = {"role": role}
    if role == Role.VENDOR:
        vendor = request.user.profile.vendor
        context["pos"] = PurchaseOrder.objects.filter(vendor=vendor) if vendor else []
    else:
        context["vendors"] = Vendor.objects.all()[:10]
        context["pos"] = PurchaseOrder.objects.all()[:10]
    return render(request, "core/dashboard.html", context)


# --- Step 1: Procurement triggers the LOI ---
@role_required(Role.ADMIN)
def onboard_vendor(request):
    if request.method == "POST":
        form = VendorOnboardForm(request.POST, request.FILES)
        if form.is_valid():
            vendor = form.save(commit=False)
            vendor.created_by = request.user
            vendor.save()
            messages.success(request, f"Vendor '{vendor.name}' onboarded. is_approved=False until PO acceptance.")
            return redirect("dashboard")
    else:
        form = VendorOnboardForm()
    return render(request, "core/onboard_vendor.html", {"form": form})


# --- Step 2: PMO generates base PO ---
@role_required(Role.PMO)
def create_po(request):
    if request.method == "POST":
        form = PurchaseOrderForm(request.POST, request.FILES)
        if form.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            messages.success(request, f"PO {po.po_number} created (DRAFT).")
            return redirect("dashboard")
    else:
        form = PurchaseOrderForm()
    return render(request, "core/create_po.html", {"form": form})


# --- Step 3: Vendor accepts PO ---
@role_required(Role.VENDOR)
def accept_po(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id, vendor=request.user.profile.vendor)
    if request.method == "POST":
        po.accept()
        messages.success(request, f"PO {po.po_number} accepted. Contract is now active.")
        return redirect("dashboard")
    return render(request, "core/accept_po.html", {"po": po})


# --- Step 4: Measurement Book entry upload ---
@role_required(Role.SITE_ENGINEER, Role.ADMIN)
def log_progress(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    if request.method == "POST":
        form = MeasurementBookLogForm(request.POST, request.FILES)
        if form.is_valid():
            log = form.save(commit=False)
            log.purchase_order = po
            log.logged_by = request.user
            log.save()
            messages.success(request, "Measurement book entry logged.")
            return redirect("dashboard")
    else:
        form = MeasurementBookLogForm()
    return render(request, "core/log_progress.html", {"form": form, "po": po})


# --- Step 5: WCC verification matrix + sequential sign-offs ---
@role_required(Role.SITE_ENGINEER, Role.QUALITY, Role.VERTICAL_LEAD, Role.ADMIN)
def wcc_verification(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    role = _role(request.user)

    if request.method == "POST" and "create_wcc" in request.POST:
        form = WCCForm(request.POST, purchase_order=po)
        if form.is_valid():
            try:
                wcc = form.save(commit=False)
                wcc.purchase_order = po
                wcc.save()
                messages.success(request, "WCC entry created.")
            except ValidationError as e:
                messages.error(request, "; ".join(e.messages))
            return redirect("wcc_verification", po_id=po.id)
    else:
        form = WCCForm(purchase_order=po)

    if request.method == "POST" and "sign" in request.POST:
        wcc = get_object_or_404(WorkCompletionCertificate, id=request.POST["wcc_id"], purchase_order=po)
        try:
            if request.POST["sign"] == "engineer" and role in (Role.SITE_ENGINEER, Role.ADMIN):
                wcc.sign_engineer(request.user)
            elif request.POST["sign"] == "quality" and role in (Role.QUALITY, Role.ADMIN):
                wcc.sign_quality(request.user)
            elif request.POST["sign"] == "vertical_lead" and role in (Role.VERTICAL_LEAD, Role.ADMIN):
                wcc.sign_vertical_lead(request.user)
            else:
                messages.error(request, "You are not authorized for this sign-off step.")
            messages.success(request, "Sign-off recorded.")
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
        return redirect("wcc_verification", po_id=po.id)

    certificates = po.certificates.select_related("measurement_book_log").all()
    return render(request, "core/wcc_verification.html", {
        "po": po, "form": form, "certificates": certificates, "role": role,
    })


# --- Step 6: Vendor invoice generation (locked until full WCC sign-off) ---
@role_required(Role.VENDOR)
def generate_invoice(request, wcc_id):
    wcc = get_object_or_404(WorkCompletionCertificate, id=wcc_id, purchase_order__vendor=request.user.profile.vendor)
    if not wcc.is_fully_certified:
        messages.error(request, "Invoice locked: WCC requires all three sign-offs (engineer, quality, vertical lead).")
        return redirect("dashboard")

    if request.method == "POST":
        form = InvoiceForm(request.POST, certificate=wcc)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.certificate = wcc
            invoice.created_by = request.user
            invoice.status = Invoice.Status.SUBMITTED
            try:
                invoice.save()
                messages.success(request, f"Invoice {invoice.invoice_number} created. Upload compliance docs next.")
                return redirect("compliance_upload", invoice_id=invoice.id)
            except ValidationError as e:
                messages.error(request, "; ".join(e.messages))
    else:
        form = InvoiceForm(certificate=wcc)
    return render(request, "core/generate_invoice.html", {"form": form, "wcc": wcc})


# --- Step 7: HR compliance dropzone (blocks final PMO submission until present) ---
@role_required(Role.VENDOR)
def compliance_upload(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id, certificate__purchase_order__vendor=request.user.profile.vendor)
    if request.method == "POST":
        form = ComplianceSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.invoice = invoice
            doc.save()
            invoice.status = Invoice.Status.PMO_REVIEW
            invoice.save(update_fields=["status"])
            messages.success(request, "Compliance document uploaded. Invoice sent for PMO review.")
            return redirect("dashboard")
    else:
        form = ComplianceSubmissionForm()
    return render(request, "core/compliance_upload.html", {"form": form, "invoice": invoice})


# --- Step 8: PMO final dossier clearance & disbursement trigger ---
@role_required(Role.PMO)
def payment_clearance(request):
    pending = Invoice.objects.filter(status=Invoice.Status.PMO_REVIEW).select_related("certificate")
    if request.method == "POST":
        invoice = get_object_or_404(Invoice, id=request.POST["invoice_id"], status=Invoice.Status.PMO_REVIEW)
        invoice.clear_for_payment()
        messages.success(
            request,
            f"{invoice.invoice_number} cleared for payment. "
            f"Retention of {invoice.retention_amount} logged to ledger."
        )
        return redirect("payment_clearance")
    return render(request, "core/payment_clearance.html", {"pending": pending})
