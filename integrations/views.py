import hashlib
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import SchoolClass, Term
from analytics.models import RiskSignal
from courses.models import Subject
from gradebook.evidence import approved_evidence_for_school
from mastery.services import class_subject_mastery
from schools.models import SchoolMembership
from schools.services import has_school_role

from .auth import authenticate_request
from .models import IntegrationCredential


@login_required
def credential_settings_view(request):
    if not has_school_role(request, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied

    credential = IntegrationCredential.objects.filter(school=request.school).first()

    if request.method == "POST" and request.POST.get("action") == "generate":
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if credential:
            credential.token_hash = token_hash
            credential.created_by = request.school_membership
            credential.is_active = True
            credential.save(update_fields=["token_hash", "created_by", "is_active"])
        else:
            credential = IntegrationCredential.objects.create(
                school=request.school, token_hash=token_hash, created_by=request.school_membership,
            )
        messages.success(
            request,
            f"New API token generated: {token} — copy it now, it will not be shown again.",
        )
        return redirect("integration_credential_settings")

    return render(request, "integrations/credential_settings.html", {"credential": credential})


def _require_auth(request):
    school = authenticate_request(request)
    if school is None:
        return None, JsonResponse({"detail": "Invalid or missing API token."}, status=401)
    return school, None


def _require_term(request, school):
    term_id = request.GET.get("term")
    if not term_id:
        return None, JsonResponse({"detail": "A 'term' query parameter is required."}, status=400)
    term = Term.objects.filter(pk=term_id, academic_year__school=school).first()
    if term is None:
        return None, JsonResponse({"detail": "Unknown term for this school."}, status=400)
    return term, None


def evidence_view(request):
    school, error = _require_auth(request)
    if error:
        return error
    term, error = _require_term(request, school)
    if error:
        return error

    entries = approved_evidence_for_school(school, term)
    return JsonResponse({
        "school": school.slug,
        "term": {"id": term.id, "academic_year": term.academic_year.name, "name": term.name},
        "evidence": [
            {
                "student_id": entry.student_id,
                "student_username": entry.student.user.username,
                "assessment_id": entry.assessment_id,
                "assessment_title": entry.assessment.title,
                "max_score": entry.assessment.max_score,
                "topic_id": entry.assessment.topic_id,
                "topic_name": entry.assessment.topic.name if entry.assessment.topic else None,
                "subject_id": entry.assessment.offering.subject_id,
                "subject_name": entry.assessment.offering.subject.name,
                "score": entry.score,
                "percentage": entry.percentage,
                "recorded_at": entry.created_at,
            }
            for entry in entries
        ],
    })


def mastery_summary_view(request):
    school, error = _require_auth(request)
    if error:
        return error
    term, error = _require_term(request, school)
    if error:
        return error

    school_class = get_object_or_404(SchoolClass, pk=request.GET.get("class_id"), school=school)
    subject = get_object_or_404(Subject, pk=request.GET.get("subject_id"), school=school)

    summary = class_subject_mastery(school_class, subject, term)
    return JsonResponse({
        "school": school.slug,
        "school_class": {"id": school_class.id, "name": school_class.name},
        "subject": {"id": subject.id, "name": subject.name},
        "period": summary["period"],
        "strands": [
            {
                "strand": {"id": row["strand"].id, "name": row["strand"].name},
                "topics": [
                    {
                        "topic": {"id": topic_row["topic"].id, "name": topic_row["topic"].name},
                        "mastery_percentage": topic_row["mastery_percentage"],
                        "status": topic_row["status"],
                        "evidence_count": topic_row["evidence_count"],
                        "student_count": topic_row["student_count"],
                    }
                    for topic_row in row["topics"]
                ],
            }
            for row in summary["strands"]
        ],
    })


def risk_signals_view(request):
    school, error = _require_auth(request)
    if error:
        return error
    term, error = _require_term(request, school)
    if error:
        return error

    signals = RiskSignal.objects.filter(
        school=school, term=term, status__in=[RiskSignal.Status.OPEN, RiskSignal.Status.ACKNOWLEDGED],
    ).select_related("student__user", "policy", "school_class")

    return JsonResponse({
        "school": school.slug,
        "term": {"id": term.id, "academic_year": term.academic_year.name, "name": term.name},
        "signals": [
            {
                "student_id": signal.student_id,
                "student_username": signal.student.user.username,
                "school_class_id": signal.school_class_id,
                "school_class_name": signal.school_class.name,
                "policy_name": signal.policy.name,
                "metric": signal.policy.metric,
                "observed_value": signal.observed_value,
                "status": signal.status,
                "generated_at": signal.generated_at,
            }
            for signal in signals
        ],
    })
