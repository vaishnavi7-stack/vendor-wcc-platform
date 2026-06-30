# Vendor WCC Platform (Django)

Implements the full 8-step vendor pipeline: LOI onboarding -> PO -> vendor
acceptance -> measurement book logging -> WCC sign-off matrix -> invoicing
-> compliance docs -> PMO payment clearance with retention.

## Setup
```
pip install django pillow
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Assigning roles
After creating users (via /admin/), give each one a `UserProfile` with a
role: ADMIN, PMO, SITE_ENGINEER, QUALITY, VERTICAL_LEAD, or VENDOR (and link
a Vendor record for VENDOR role users). This is done via /admin/core/userprofile/.

## URLs
- /admin-panel/onboard-vendor/   (Step 1, ADMIN)
- /pmo/create-po/                (Step 2, PMO)
- /vendor/accept-po/<po_id>/     (Step 3, VENDOR)
- /site/log-progress/<po_id>/    (Step 4, SITE_ENGINEER/ADMIN)
- /site/wcc-verification/<po_id>/ (Step 5, ENGINEER -> QUALITY -> VERTICAL_LEAD)
- /vendor/generate-invoice/<wcc_id>/ (Step 6, VENDOR, locked until full WCC sign-off)
- /vendor/compliance-upload/<invoice_id>/ (Step 7, VENDOR)
- /pmo/payment-clearance/        (Step 8, PMO, applies 10% retention)

## Guardrails enforced in models.py
- `WorkCompletionCertificate.passed_qty <= executed_qty`
- Sign-off order: engineer -> quality -> vertical_lead (each raises
  ValidationError if attempted out of order)
- `Invoice.billed_qty <= certificate.passed_qty`
- Invoice cannot be created unless WCC has all three sign-offs
