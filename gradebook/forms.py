from django import forms

from .models import Assessment, AssessmentCategory, GradeScheme


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["category", "title", "max_score", "due_at", "status"]
        widgets = {"due_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, offering, **kwargs):
        self.offering = offering
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = AssessmentCategory.objects.filter(
            scheme__school=offering.school,
            scheme__academic_year=offering.term.academic_year,
            scheme__status=GradeScheme.Status.ACTIVE,
        ).select_related("scheme")
        self.instance.school = offering.school
        self.instance.offering = offering
