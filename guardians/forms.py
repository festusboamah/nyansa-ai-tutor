from django import forms

from schools.models import SchoolMembership

from .models import GuardianLink


class GuardianLinkForm(forms.ModelForm):
    class Meta:
        model = GuardianLink
        fields = ["guardian", "student", "relationship", "is_primary_contact", "authorization_reference"]

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["guardian"].queryset = SchoolMembership.objects.filter(
            school=school, role=SchoolMembership.Role.PARENT, status=SchoolMembership.Status.ACTIVE
        ).select_related("user")
        self.fields["student"].queryset = SchoolMembership.objects.filter(
            school=school, role=SchoolMembership.Role.STUDENT, status=SchoolMembership.Status.ACTIVE
        ).select_related("user")
        self.instance.school = school

