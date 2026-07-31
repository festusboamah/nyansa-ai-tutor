from django.core.exceptions import ValidationError
from django.db import models


class MessageTemplate(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"

    class EventType(models.TextChoices):
        REPORT = "REPORT", "Published report"
        ATTENDANCE = "ATTENDANCE", "Attendance"
        SCHOOL_EVENT = "SCHOOL_EVENT", "School event"
        BALANCE = "BALANCE", "Fee balance"
        GENERAL = "GENERAL", "General notice"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="message_templates")
    code = models.SlugField(max_length=60)
    name = models.CharField(max_length=120)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    subject_template = models.CharField(max_length=200, blank=True)
    body_template = models.TextField()
    contains_sensitive_data = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "code"], name="unique_school_message_template")]

    def clean(self):
        if self.channel == self.Channel.EMAIL and not self.subject_template.strip():
            raise ValidationError({"subject_template": "Email templates require a subject."})
        if self.channel == self.Channel.SMS and self.contains_sensitive_data:
            raise ValidationError("SMS templates cannot contain sensitive academic or financial details.")


class CommunicationPreference(models.Model):
    recipient = models.OneToOneField(
        "schools.SchoolMembership", on_delete=models.CASCADE, related_name="communication_preference"
    )
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    sms_phone = models.CharField(max_length=30, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.recipient_id and self.recipient.role != "PARENT":
            raise ValidationError("Communication preferences belong to guardian memberships.")
        if self.sms_enabled and not self.sms_phone.strip():
            raise ValidationError({"sms_phone": "A phone number is required when SMS is enabled."})


class MessageIntent(models.Model):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        PROCESSING = "PROCESSING", "Processing"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="message_intents")
    recipient = models.ForeignKey(
        "schools.SchoolMembership", on_delete=models.PROTECT, related_name="message_intents"
    )
    student = models.ForeignKey(
        "schools.SchoolMembership", null=True, blank=True, on_delete=models.PROTECT,
        related_name="student_message_intents",
    )
    template = models.ForeignKey(MessageTemplate, on_delete=models.PROTECT, related_name="message_intents")
    channel = models.CharField(max_length=10, choices=MessageTemplate.Channel.choices)
    event_type = models.CharField(max_length=20, choices=MessageTemplate.EventType.choices)
    business_reference = models.CharField(max_length=160)
    idempotency_key = models.CharField(max_length=64)
    destination = models.CharField(max_length=254)
    rendered_subject = models.CharField(max_length=200, blank=True)
    rendered_body = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=160, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["school", "idempotency_key"], name="unique_school_message_event")
        ]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="message_delivery_queue_idx")]

    def clean(self):
        if self.recipient_id and self.recipient.school_id != self.school_id:
            raise ValidationError("Message recipient must belong to the message school.")
        if self.student_id and self.student.school_id != self.school_id:
            raise ValidationError("Message student must belong to the message school.")
        if self.template_id and self.template.school_id != self.school_id:
            raise ValidationError("Message template must belong to the message school.")
        if self.template_id and self.channel != self.template.channel:
            raise ValidationError("Message channel must match its template.")


class DeliveryAttempt(models.Model):
    intent = models.ForeignKey(MessageIntent, on_delete=models.PROTECT, related_name="delivery_attempts")
    attempt_number = models.PositiveSmallIntegerField()
    succeeded = models.BooleanField(default=False)
    provider = models.CharField(max_length=40)
    provider_message_id = models.CharField(max_length=160, blank=True)
    error = models.CharField(max_length=500, blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]
        constraints = [models.UniqueConstraint(fields=["intent", "attempt_number"], name="unique_message_attempt")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Delivery history is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Delivery history is immutable.")
