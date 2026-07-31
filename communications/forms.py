from django import forms

from guardians.models import GuardianLink
from schools.models import SchoolMembership

from .models import CommunicationPreference, MessageTemplate


class CommunicationPreferenceForm(forms.ModelForm):
    class Meta:
        model = CommunicationPreference
        fields = ["email_enabled", "sms_enabled", "sms_phone"]


class MessageTemplateForm(forms.ModelForm):
    class Meta:
        model = MessageTemplate
        fields = [
            "code", "name", "channel", "event_type", "subject_template",
            "body_template", "contains_sensitive_data", "is_active",
        ]
        widgets = {"body_template": forms.Textarea(attrs={"rows": 5})}


class SchoolEventForm(forms.Form):
    title = forms.CharField(max_length=120)
    message = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 4}))
    guardians = forms.ModelMultipleChoiceField(queryset=SchoolMembership.objects.none())

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["guardians"].queryset = SchoolMembership.objects.filter(
            school=school, role=SchoolMembership.Role.PARENT, status=SchoolMembership.Status.ACTIVE,
            guardian_links__status=GuardianLink.Status.ACTIVE,
        ).select_related("user").distinct()

