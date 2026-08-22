from django import forms
from .models import Assignment, AssignmentSubmission, RubricCriterion


class AssignmentForm(forms.ModelForm):
    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject

        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )

    class Meta:
        model = Assignment
        fields = ["subject", "title", "instructions", "deadline"]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 4}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ["file"]


class GradeAssignmentForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ["final_score", "teacher_feedback"]
        widgets = {
            "teacher_feedback": forms.Textarea(attrs={"rows": 4}),
        }


RubricCriterionFormSet = forms.inlineformset_factory(
    Assignment,
    RubricCriterion,
    fields=["name", "description", "max_points", "order"],
    widgets={"description": forms.Textarea(attrs={"rows": 2})},
    extra=3,
    can_delete=True,
)
