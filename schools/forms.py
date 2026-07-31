from django import forms
from academics.models import AcademicYear, SchoolClass, SubjectOffering, TeacherAssignment, Term
from .models import SchoolMembership
from .models import SchoolInvitation


class SchoolInvitationForm(forms.ModelForm):
    class Meta:
        model = SchoolInvitation
        fields = ["email", "role"]

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class SchoolScopedFormMixin:
    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        if hasattr(self.instance, "school_id"):
            self.instance.school = school


class AcademicYearForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}


class TermForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Term
        fields = ["academic_year", "name", "order", "start_date", "end_date"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(school=self.school)


class SchoolClassForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["academic_year", "name", "capacity", "class_teacher"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(school=self.school)
        self.fields["class_teacher"].queryset = SchoolMembership.objects.filter(school=self.school, role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE)


class SubjectOfferingForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = SubjectOffering
        fields = ["school_class", "subject", "term"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = SchoolClass.objects.filter(school=self.school)
        self.fields["subject"].queryset = self.fields["subject"].queryset.filter(school=self.school)
        self.fields["term"].queryset = Term.objects.filter(academic_year__school=self.school)


class TeacherAssignmentForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = TeacherAssignment
        fields = ["offering", "teacher", "is_lead"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["offering"].queryset = SubjectOffering.objects.filter(school=self.school)
        self.fields["teacher"].queryset = SchoolMembership.objects.filter(school=self.school, role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE)
