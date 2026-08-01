from django import forms

from schools.models import SchoolMembership

from .models import EarlyWarningPolicy


class WarningPolicyForm(forms.ModelForm):
    class Meta:
        model = EarlyWarningPolicy
        fields = ["name", "metric", "threshold", "is_active"]


class InterventionForm(forms.Form):
    owner = forms.ModelChoiceField(queryset=SchoolMembership.objects.none())
    plan = forms.CharField(min_length=10, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = SchoolMembership.objects.filter(
            school=school,
            role__in=[SchoolMembership.Role.TEACHER, SchoolMembership.Role.SCHOOL_ADMIN],
            status=SchoolMembership.Status.ACTIVE,
        ).select_related("user")

