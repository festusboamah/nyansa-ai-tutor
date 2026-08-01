from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import SchoolClass, SubjectOffering, Term
from schools.models import SchoolMembership
from schools.services import has_school_role

from .forms import InterventionForm, WarningPolicyForm
from .models import EarlyWarningPolicy, NarrativeSnapshot, RiskSignal
from .services import (
    approve_narrative, can_view_class, class_metrics, complete_intervention, create_intervention,
    create_narrative, generate_risk_signals, offering_metrics, school_metrics,
)


def analytics_staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not has_school_role(request, SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN):
            messages.error(request, "Analytics is available only to school staff.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapped


def _selected_term(request):
    terms = Term.objects.filter(academic_year__school=request.school).select_related("academic_year")
    term_id = request.GET.get("term") or request.POST.get("term")
    return get_object_or_404(terms, pk=term_id) if term_id else terms.order_by("-academic_year__start_date", "-order").first()


@analytics_staff_required
def dashboard(request):
    term = _selected_term(request)
    terms = Term.objects.filter(academic_year__school=request.school).select_related("academic_year")
    if not term:
        return render(request, "analytics/dashboard.html", {"terms": terms})
    if request.school_membership.role == SchoolMembership.Role.SCHOOL_ADMIN:
        metrics = school_metrics(request.school, term)
        classes = request.school.classes.filter(academic_year=term.academic_year)
        if request.method == "POST" and request.POST.get("action") == "narrative":
            create_narrative(
                school=request.school, term=term, actor=request.school_membership,
                scope=NarrativeSnapshot.Scope.SCHOOL, metrics=metrics,
            )
            messages.success(request, "Grounded narrative draft created for administrator review.")
            return redirect(f"{request.path}?term={term.pk}")
        context = {"school_metrics": metrics, "classes": classes}
    else:
        offerings = SubjectOffering.objects.filter(
            term=term, teacher_assignments__teacher=request.school_membership
        ).select_related("school_class", "subject", "term").distinct()
        classes = SchoolClass.objects.filter(
            Q(class_teacher=request.school_membership)
            | Q(subject_offerings__term=term, subject_offerings__teacher_assignments__teacher=request.school_membership),
            school=request.school, academic_year=term.academic_year,
        ).distinct()
        context = {"offerings": [{"offering": item, "metrics": offering_metrics(item)} for item in offerings], "classes": classes}
    context.update({
        "term": term, "terms": terms,
        "signals": RiskSignal.objects.filter(
            school=request.school, term=term, status__in=[RiskSignal.Status.OPEN, RiskSignal.Status.ACKNOWLEDGED]
        ).select_related("student__user", "policy", "school_class")[:50],
        "narratives": NarrativeSnapshot.objects.filter(school=request.school, term=term).select_related("generated_by__user")[:20],
    })
    return render(request, "analytics/dashboard.html", context)


@analytics_staff_required
def class_detail(request, class_id, term_id):
    school_class = get_object_or_404(SchoolClass, pk=class_id, school=request.school)
    term = get_object_or_404(Term, pk=term_id, academic_year=school_class.academic_year)
    if not can_view_class(request.school_membership, school_class, term):
        raise PermissionDenied
    if request.method == "POST" and request.POST.get("action") == "signals":
        signals = generate_risk_signals(
            school_class=school_class, term=term, actor=request.school_membership
        )
        messages.success(request, f"Evaluated warning policies; {len(signals)} signal(s) are active.")
        return redirect("analytics_class", class_id=class_id, term_id=term_id)
    metrics = class_metrics(school_class, term)
    return render(request, "analytics/class_detail.html", {
        "school_class": school_class, "term": term, "metrics": metrics,
        "offerings": SubjectOffering.objects.filter(school_class=school_class, term=term).select_related("subject"),
        "signals": RiskSignal.objects.filter(school_class=school_class, term=term).select_related("student__user", "policy"),
    })


@analytics_staff_required
def offering_detail(request, offering_id):
    offering = get_object_or_404(
        SubjectOffering.objects.select_related("school_class", "term", "subject"),
        pk=offering_id, school=request.school,
    )
    if not can_view_class(request.school_membership, offering.school_class, offering.term):
        raise PermissionDenied
    if request.school_membership.role == SchoolMembership.Role.TEACHER and not (
        offering.teacher_assignments.filter(teacher=request.school_membership).exists()
        or offering.school_class.class_teacher_id == request.school_membership.id
    ):
        raise PermissionDenied
    return render(request, "analytics/offering_detail.html", {
        "offering": offering, "metrics": offering_metrics(offering),
    })


@login_required
def policies(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    form = WarningPolicyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        policy = form.save(commit=False)
        policy.school, policy.created_by = request.school, request.school_membership
        policy.full_clean()
        policy.save()
        messages.success(request, "Early-warning policy saved.")
        return redirect("analytics_policies")
    return render(request, "analytics/policies.html", {
        "form": form, "policies": EarlyWarningPolicy.objects.filter(school=request.school),
    })


@analytics_staff_required
def signal_detail(request, signal_id):
    signal = get_object_or_404(
        RiskSignal.objects.select_related("student__user", "policy", "school_class", "term"),
        pk=signal_id, school=request.school,
    )
    if not can_view_class(request.school_membership, signal.school_class, signal.term):
        raise PermissionDenied
    form = InterventionForm(request.POST or None, school=request.school)
    if request.method == "POST" and request.POST.get("complete_id"):
        intervention = get_object_or_404(signal.interventions, pk=request.POST["complete_id"])
        try:
            complete_intervention(
                intervention=intervention, actor=request.school_membership,
                outcome=request.POST.get("outcome", ""),
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Intervention completed and outcome recorded.")
        return redirect("analytics_signal", signal_id=signal.pk)
    if request.method == "POST" and form.is_valid():
        try:
            create_intervention(
                signal=signal, actor=request.school_membership,
                owner=form.cleaned_data["owner"], plan=form.cleaned_data["plan"],
            )
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Intervention plan recorded.")
            return redirect("analytics_signal", signal_id=signal.pk)
    return render(request, "analytics/signal_detail.html", {"signal": signal, "form": form})


@login_required
def approve_narrative_view(request, narrative_id):
    if request.method != "POST" or not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied
    narrative = get_object_or_404(NarrativeSnapshot, pk=narrative_id, school=request.school)
    approve_narrative(narrative=narrative, actor=request.school_membership)
    messages.success(request, "Narrative approved for sharing.")
    return redirect(f"{reverse('analytics_dashboard')}?term={narrative.term_id}")
