from django import forms
from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from .models import School, SchoolMembership
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
            "offers_kg", "offers_primary", "offers_jhs", "logo", "official_stamp",
        ]
        labels = {
            "offers_kg": "Kindergarten (KG 1–2)",
            "offers_primary": "Primary (Basic 1–6)",
            "offers_jhs": "Junior High School (JHS 1–3)",
        }
        help_texts = {
            "student_access_mode": "Choose how students will access Nyansa.",
            "offers_kg": "Select every education level operated by this school.",
        }


class StudentRosterUploadForm(forms.Form):
    school_class = forms.ModelChoiceField(queryset=SchoolClass.objects.none())
    roster_file = forms.FileField(help_text="Upload a .csv or .xlsx file for one class.")

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)

    def clean_roster_file(self):
        roster_file = self.cleaned_data["roster_file"]
        if not roster_file.name.lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Upload a CSV or Excel (.xlsx) file.")
        return roster_file


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
    class Meta:
        model = TeacherAssignment
        fields = ["offering", "teacher", "is_lead"]
        labels = {
            "offering": "Class, subject and term",
            "teacher": "Teacher",
            "is_lead": "Lead teacher for this subject",
        }
        help_texts = {
            "offering": "Choose the exact class, subject, and term this teacher will teach.",
            "teacher": "Only active teachers in this school are shown.",
            "is_lead": "Select this for the main teacher responsible when two or more teachers share the subject. For one teacher, you may select it.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["offering"].queryset = SubjectOffering.objects.filter(
            school=self.school
        ).select_related("school_class", "subject", "term").order_by(
            "school_class__name", "subject__name", "term__order"
        )
        self.fields["teacher"].queryset = SchoolMembership.objects.filter(school=self.school, role=SchoolMembership.Role.TEACHER, status=SchoolMembership.Status.ACTIVE)
