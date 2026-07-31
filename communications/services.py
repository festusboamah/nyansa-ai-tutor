import hashlib
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from guardians.models import GuardianLink
from schools.models import SchoolMembership

from .gateways import gateway_for
from .models import CommunicationPreference, DeliveryAttempt, MessageIntent, MessageTemplate


DEFAULT_TEMPLATES = (
    ("report-email", "Published report email", "EMAIL", "REPORT", "{{school_name}}: report available", "A new term report for {{student_name}} is available in your secure Nyansa guardian portal."),
    ("report-sms", "Published report SMS", "SMS", "REPORT", "", "{{school_name}} has published a new report. Sign in to your secure Nyansa guardian portal."),
    ("attendance-email", "Attendance email", "EMAIL", "ATTENDANCE", "{{school_name}} attendance notice", "An attendance update for {{student_name}} is available in your secure Nyansa guardian portal."),
    ("attendance-sms", "Attendance SMS", "SMS", "ATTENDANCE", "", "{{school_name}} has posted an attendance update. Sign in to your secure Nyansa guardian portal."),
    ("school-event-email", "School event email", "EMAIL", "SCHOOL_EVENT", "{{school_name}}: {{event_title}}", "{{event_message}}"),
    ("balance-email", "Balance email", "EMAIL", "BALANCE", "{{school_name}} account notice", "A fee-account update for {{student_name}} is available in your secure portal."),
)


def ensure_default_templates(school):
    templates = {}
    for code, name, channel, event_type, subject, body in DEFAULT_TEMPLATES:
        template, _ = MessageTemplate.objects.get_or_create(
            school=school, code=code,
            defaults={
                "name": name, "channel": channel, "event_type": event_type,
                "subject_template": subject, "body_template": body,
            },
        )
        templates[code] = template
    return templates


def _render(value, context):
    rendered = value
    for key, replacement in context.items():
        rendered = rendered.replace("{{" + key + "}}", str(replacement))
    if "{{" in rendered or "}}" in rendered:
        raise ValidationError("The message template contains an unresolved placeholder.")
    return rendered


@transaction.atomic
def enqueue_message(*, template, recipient, business_reference, context, student=None):
    if not recipient.is_active or recipient.role != SchoolMembership.Role.PARENT:
        raise ValidationError("Messages can be queued only for active guardians.")
    if recipient.school_id != template.school_id or (student and student.school_id != template.school_id):
        raise ValidationError("Message records must belong to one school.")
    if student and not GuardianLink.objects.filter(
        school=template.school, guardian=recipient, student=student, status=GuardianLink.Status.ACTIVE
    ).exists():
        raise ValidationError("Guardian is not authorized for this student.")
    preference, _ = CommunicationPreference.objects.get_or_create(recipient=recipient)
    if template.channel == MessageTemplate.Channel.EMAIL:
        if not preference.email_enabled or not recipient.user.email:
            return None
        destination = recipient.user.email
    else:
        if not preference.sms_enabled or not preference.sms_phone:
            return None
        if template.contains_sensitive_data:
            raise ValidationError("Sensitive details cannot be sent by SMS.")
        destination = preference.sms_phone
    raw_key = f"{template.school_id}:{template.code}:{recipient.id}:{business_reference}"
    key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    defaults = {
        "recipient": recipient, "student": student, "template": template,
        "channel": template.channel, "event_type": template.event_type,
        "business_reference": business_reference, "destination": destination,
        "rendered_subject": _render(template.subject_template, context),
        "rendered_body": _render(template.body_template, context),
        "next_attempt_at": timezone.now(),
    }
    intent, created = MessageIntent.objects.get_or_create(
        school=template.school, idempotency_key=key, defaults=defaults
    )
    return intent


def enqueue_guardian_event(*, student, event_type, business_reference, context):
    templates = ensure_default_templates(student.school)
    intents = []
    links = GuardianLink.objects.filter(
        school=student.school, student=student, status=GuardianLink.Status.ACTIVE,
        guardian__status=SchoolMembership.Status.ACTIVE,
    ).select_related("guardian__user")
    prefix = {
        MessageTemplate.EventType.REPORT: "report",
        MessageTemplate.EventType.ATTENDANCE: "attendance",
        MessageTemplate.EventType.SCHOOL_EVENT: "school-event",
        MessageTemplate.EventType.BALANCE: "balance",
    }.get(event_type)
    if not prefix:
        raise ValidationError("Unsupported guardian event type.")
    full_context = {"school_name": student.school.name, "student_name": student.user.get_full_name() or student.user.username, **context}
    for link in links:
        for suffix in ("email", "sms"):
            template = templates.get(f"{prefix}-{suffix}")
            if template and template.is_active:
                intent = enqueue_message(
                    template=template, recipient=link.guardian, student=student,
                    business_reference=business_reference, context=full_context,
                )
                if intent:
                    intents.append(intent)
    return intents


@transaction.atomic
def process_queued_messages(*, limit=50, now=None):
    now = now or timezone.now()
    ids = list(MessageIntent.objects.filter(
        Q(status=MessageIntent.Status.QUEUED) | Q(status=MessageIntent.Status.FAILED),
        next_attempt_at__lte=now, attempt_count__lt=3,
    ).order_by("created_at").values_list("id", flat=True)[:limit])
    processed = []
    for intent_id in ids:
        intent = MessageIntent.objects.select_for_update().get(pk=intent_id)
        intent.status = MessageIntent.Status.PROCESSING
        intent.attempt_count += 1
        intent.save(update_fields=["status", "attempt_count", "updated_at"])
        gateway = gateway_for(intent.channel)
        try:
            provider_id = gateway.send(
                destination=intent.destination, subject=intent.rendered_subject, body=intent.rendered_body
            )
        except Exception as error:
            message = str(error)[:500]
            intent.status = MessageIntent.Status.FAILED
            intent.last_error = message
            intent.next_attempt_at = now + timedelta(minutes=2 ** intent.attempt_count)
            intent.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
            DeliveryAttempt.objects.create(
                intent=intent, attempt_number=intent.attempt_count, succeeded=False,
                provider=gateway.name, error=message,
            )
        else:
            intent.status = MessageIntent.Status.SENT
            intent.provider_message_id = provider_id
            intent.last_error = ""
            intent.sent_at = now
            intent.next_attempt_at = None
            intent.save(update_fields=[
                "status", "provider_message_id", "last_error", "sent_at", "next_attempt_at", "updated_at"
            ])
            DeliveryAttempt.objects.create(
                intent=intent, attempt_number=intent.attempt_count, succeeded=True,
                provider=gateway.name, provider_message_id=provider_id,
            )
        processed.append(intent)
    return processed
