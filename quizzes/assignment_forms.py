from django import forms
from .models import Assignment, AssignmentSubmission


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["subject", "title", "instructions", "grading_rubric", "deadline"]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 4}),
            "grading_rubric": forms.Textarea(attrs={"rows": 3}),
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