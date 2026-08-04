from django import forms
from django.db import models
from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from .models import School, SchoolMembership, StudentProfile
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


class SchoolProfileForm(forms.ModelForm):
    class Meta:
        model = School
        fields = [
            "name", "address", "phone", "email", "timezone", "student_access_mode",
            "offers_kg", "offers_primary", "offers_jhs", "stream_structure", "logo", "official_stamp",
        ]
        labels = {
            "offers_kg": "Kindergarten (KG 1–2)",
            "offers_primary": "Primary (Basic 1–6)",
            "offers_jhs": "Junior High School (JHS 1–3)",
            "stream_structure": "Class streams",
        }
        help_texts = {
            "student_access_mode": "Choose how students will access Nyansa.",
            "offers_kg": "Select every education level operated by this school.",
            "stream_structure": "Choose double stream if each level is divided into A and B classes.",
        }


class StudentRosterUploadForm(forms.Form):
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none())
    roster_file = forms.FileField(help_text="Upload a .csv or .xlsx file for one class.")

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        classes = SchoolClass.objects.filter(school=school)
        if classes.exclude(name="Demo Class").exists():
            classes = classes.exclude(name="Demo Class")
        self.fields["school_class"].queryset = classes

    def clean_roster_file(self):
        roster_file = self.cleaned_data["roster_file"]
        if not roster_file.name.lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Upload a CSV or Excel (.xlsx) file.")
        return roster_file


class StudentRecordForm(forms.Form):
    identifier = forms.CharField(label="Student ID", max_length=50)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    gender = forms.ChoiceField(choices=[("", "Not specified"), *StudentProfile.Gender.choices], required=False)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    guardian_name = forms.CharField(max_length=160, required=False)
    guardian_phone = forms.CharField(max_length=30, required=False)

    def __init__(self, *args, membership, **kwargs):
        self.membership = membership
        profile, _ = StudentProfile.objects.get_or_create(membership=membership)
        kwargs.setdefault("initial", {
            "identifier": membership.identifier,
            "first_name": membership.user.first_name,
            "last_name": membership.user.last_name,
            "gender": profile.gender,
            "date_of_birth": profile.date_of_birth,
            "guardian_name": profile.guardian_name,
            "guardian_phone": profile.guardian_phone,
        })
        super().__init__(*args, **kwargs)

    def clean_identifier(self):
        identifier = self.cleaned_data["identifier"].strip()
        if SchoolMembership.objects.filter(
            school=self.membership.school, identifier=identifier
        ).exclude(pk=self.membership.pk).exists():
            raise forms.ValidationError("This student ID is already used in this school.")
        return identifier

    def save(self):
        membership = self.membership
        membership.identifier = self.cleaned_data["identifier"]
        membership.save(update_fields=["identifier", "updated_at"])
        membership.user.first_name = self.cleaned_data["first_name"].strip()
        membership.user.last_name = self.cleaned_data["last_name"].strip()
        membership.user.save(update_fields=["first_name", "last_name"])
        profile, _ = StudentProfile.objects.get_or_create(membership=membership)
        for field in ("gender", "date_of_birth", "guardian_name", "guardian_phone"):
            setattr(profile, field, self.cleaned_data[field])
        profile.save()
        return membership


class SubjectSetupForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        from courses.models import Subject
        model = Subject
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class ClassEnrollmentForm(forms.ModelForm):
    class Meta:
        model = ClassEnrollment
        fields = ["school_class", "student"]

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)
        self.fields["student"].queryset = SchoolMembership.objects.filter(
            school=school,
            role=SchoolMembership.Role.STUDENT,
            status=SchoolMembership.Status.ACTIVE,
        ).select_related("user")


class AcademicYearForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}
        help_texts = {
            "name": "For example, 2026/2027.",
            "start_date": "The first day of the full school year, before First Term begins.",
            "end_date": "The final day of the full school year, after Third Term ends.",
            "is_current": "Select this only for the academic year the school is using now.",
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if AcademicYear.objects.filter(school=self.school, name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This academic year already exists. Use the existing year instead.")
        return name


class TermForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Term
        fields = ["academic_year", "name", "order", "start_date", "end_date"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}
        help_texts = {"order": "Use 1 for First Term, 2 for Second Term, and 3 for Third Term."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(school=self.school)


class SchoolClassForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ["academic_year", "name", "capacity", "class_teacher"]
        labels = {
            "academic_year": "Academic year",
            "name": "Class name",
            "capacity": "Maximum number of students",
            "class_teacher": "Class teacher (optional)",
        }
        help_texts = {
            "academic_year": "Choose the school year in which this class will operate.",
            "name": "Examples: Basic 1, Basic 6, JHS 1, JHS 2, or JHS 3.",
            "capacity": "Enter the maximum class size, not the number currently enrolled. You may leave it blank.",
            "class_teacher": "Choose the teacher responsible for this class. Subject teachers are assigned later.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. JHS 1"}),
            "capacity": forms.NumberInput(attrs={"placeholder": "e.g. 45", "min": 1}),
        }

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
    apply_all_terms = forms.BooleanField(
        required=False,
        label="Assign across all terms",
        help_text="Assign this teacher to the same class and subject for every configured term in the academic year.",
    )

    class Meta:
        model = TeacherAssignment
        fields = ["offering", "teacher", "is_lead"]
        labels = {
            "offering": "Class, subject and term",
            "teacher": "Teacher",
            "is_lead": "Lead subject teacher",
        }
        help_texts = {
            "offering": "Choose the exact class, subject, and term this teacher will teach.",
            "teacher": "Only active teachers in this school are shown.",
            "is_lead": "The main teacher responsible for this particular class and subject. This is different from the overall class teacher.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        offerings = SubjectOffering.objects.filter(school=self.school)
        if offerings.exclude(school_class__name="Demo Class", term__name="Demo Term").exists():
            offerings = offerings.exclude(
                models.Q(school_class__name="Demo Class") | models.Q(term__name="Demo Term")
            )
        self.fields["offering"].queryset = offerings.select_related("school_class", "subject", "term").order_by(
            "school_class__name", "subject__name", "term__order"
        )
        self.fields["teacher"].queryset = SchoolMembership.objects.filter(school=self.school, role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE)
