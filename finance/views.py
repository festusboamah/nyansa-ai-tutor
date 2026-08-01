from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from communications.services import enqueue_message, ensure_default_templates
from guardians.models import GuardianLink
from guardians.services import guardian_can_access
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import AdjustmentForm, FeeItemForm, FeeStructureForm, MobileMoneyPaymentForm
from .models import FeeStructure, Payment, Receipt, ReconciliationException
from .pdf import render_receipt_pdf
from .services import (
    activate_fee_structure, can_pay_for, initiate_mobile_money, ledger_summary,
    post_structure_charges, process_paystack_webhook, record_adjustment, resolve_exception,
)


def _admin(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied


@login_required
def finance_dashboard(request):
    _admin(request)
    return render(request, "finance/dashboard.html", {
        "structures": FeeStructure.objects.filter(school=request.school).select_related("term", "school_class"),
        "exceptions": ReconciliationException.objects.filter(school=request.school, status="OPEN").select_related("payment"),
        "payments": Payment.objects.filter(school=request.school).select_related("student__user")[:50],
    })


@login_required
def fee_structure_create(request):
    _admin(request)
    form = FeeStructureForm(request.POST or None, school=request.school)
    if request.method == "POST" and form.is_valid():
        structure = form.save(commit=False)
        structure.school = request.school
        structure.created_by = request.school_membership
        structure.full_clean()
        structure.save()
        messages.success(request, "Fee structure created.")
        return redirect("fee_structure_detail", structure_id=structure.pk)
    return render(request, "finance/structure_form.html", {"form": form})


@login_required
def fee_structure_detail(request, structure_id):
    _admin(request)
    structure = get_object_or_404(FeeStructure, pk=structure_id, school=request.school)
    item_form = FeeItemForm(request.POST or None)
    if request.method == "POST" and request.POST.get("action") == "add_item" and item_form.is_valid():
        if structure.status != FeeStructure.Status.DRAFT:
            item_form.add_error(None, "Items can be added only while the structure is a draft.")
        else:
            item = item_form.save(commit=False)
            item.structure = structure
            item.full_clean()
            item.save()
            messages.success(request, "Fee item added.")
            return redirect("fee_structure_detail", structure_id=structure.pk)
    elif request.method == "POST" and request.POST.get("action") in {"activate", "post"}:
        try:
            if request.POST["action"] == "activate":
                activate_fee_structure(structure=structure, actor=request.school_membership)
                messages.success(request, "Fee structure activated.")
            else:
                charges = post_structure_charges(structure=structure, actor=request.school_membership)
                messages.success(request, f"Posted {len(charges)} student charge(s).")
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))
        return redirect("fee_structure_detail", structure_id=structure.pk)
    return render(request, "finance/structure_detail.html", {"structure": structure, "item_form": item_form})


@login_required
def student_ledger(request, student_id):
    student = get_object_or_404(
        SchoolMembership.objects.select_related("user", "school"), pk=student_id,
        school=request.school, role=SchoolMembership.Role.STUDENT,
    )
    if request.school_membership.role == SchoolMembership.Role.SCHOOL_ADMIN:
        allowed = True
    else:
        allowed = request.school_membership.role == SchoolMembership.Role.PARENT and guardian_can_access(request.school_membership, student)
    if not allowed:
        raise PermissionDenied
    form = AdjustmentForm(request.POST or None) if request.school_membership.role == SchoolMembership.Role.SCHOOL_ADMIN else None
    if request.method == "POST" and form and form.is_valid():
        try:
            record_adjustment(student=student, actor=request.school_membership, **form.cleaned_data)
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Ledger adjustment recorded.")
            return redirect("student_ledger", student_id=student.pk)
    return render(request, "finance/ledger.html", {"student": student, "ledger": ledger_summary(student), "form": form})


@login_required
def start_payment(request, student_id):
    student = get_object_or_404(SchoolMembership, pk=student_id, school=request.school, role="STUDENT")
    if not can_pay_for(request.school_membership, student):
        raise PermissionDenied
    form = MobileMoneyPaymentForm(request.POST or None, initial={"email": request.user.email})
    if request.method == "POST" and form.is_valid():
        try:
            payment = initiate_mobile_money(
                student=student, actor=request.school_membership,
                callback_url=request.build_absolute_uri(reverse("payment_callback")),
                **form.cleaned_data,
            )
        except Exception as error:
            form.add_error(None, f"Payment could not be initialized: {error}")
        else:
            return redirect(payment.authorization_url)
    return render(request, "finance/start_payment.html", {"student": student, "form": form})


@login_required
def payment_callback(request):
    reference = request.GET.get("reference", "")
    payment = Payment.objects.filter(reference=reference, school=request.school).first()
    return render(request, "finance/payment_callback.html", {"payment": payment})


@csrf_exempt
def paystack_webhook(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    try:
        process_paystack_webhook(
            raw_body=request.body, signature=request.headers.get("x-paystack-signature", "")
        )
    except PermissionDenied:
        return JsonResponse({"detail": "Invalid signature"}, status=401)
    except (ValidationError, ValueError):
        return JsonResponse({"detail": "Invalid event"}, status=400)
    return JsonResponse({"status": "accepted"})


@login_required
def receipt_pdf(request, receipt_id):
    receipt = get_object_or_404(Receipt.objects.select_related("payment__student"), pk=receipt_id, school=request.school)
    if request.school_membership.role != SchoolMembership.Role.SCHOOL_ADMIN and not guardian_can_access(
        request.school_membership, receipt.payment.student
    ):
        raise PermissionDenied
    response = HttpResponse(render_receipt_pdf(receipt), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt-{receipt.number}.pdf"'
    return response


@login_required
def send_balance_reminder(request, student_id):
    _admin(request)
    if request.method != "POST":
        raise PermissionDenied
    student = get_object_or_404(SchoolMembership, pk=student_id, school=request.school, role="STUDENT")
    template = ensure_default_templates(request.school)["balance-email"]
    queued = 0
    for link in GuardianLink.objects.filter(school=request.school, student=student, status="ACTIVE").select_related("guardian__user"):
        intent = enqueue_message(
            template=template, recipient=link.guardian, student=student,
            business_reference=f"balance-reminder:{student.id}:{request.POST.get('reminder_key', '')}",
            context={"school_name": request.school.name, "student_name": student.user.get_full_name() or student.user.username},
        )
        queued += bool(intent)
    messages.success(request, f"Queued {queued} balance reminder(s).")
    return redirect("student_ledger", student_id=student.pk)


@login_required
def resolve_exception_view(request, exception_id):
    _admin(request)
    if request.method != "POST":
        raise PermissionDenied
    exception = get_object_or_404(ReconciliationException, pk=exception_id, school=request.school)
    try:
        resolve_exception(
            exception=exception, actor=request.school_membership,
            note=request.POST.get("resolution_note", ""),
        )
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Reconciliation exception resolved.")
    return redirect("finance_dashboard")
