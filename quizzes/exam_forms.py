from django import forms

from academics.models import SubjectOffering
from .models import Answer


class ExamOfferingsForm(forms.Form):
    offerings = forms.ModelMultipleChoiceField(
        queryset=SubjectOffering.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text=(
            "Every active student enrolled in the selected class/subject offering(s) is "
            "eligible. Leave every box unchecked for a subject-wide quiz (or, for an "
            "exam, every active student in the school - publishing still requires at "
            "least one class to be chosen)."
        ),
    )

    def __init__(self, *args, teacher_membership=None, subject=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = SubjectOffering.objects.none()
        if teacher_membership is not None and subject is not None:
            queryset = SubjectOffering.objects.filter(
                subject=subject,
                teacher_assignments__teacher=teacher_membership,
            ).select_related("school_class", "term").distinct()
        self.fields["offerings"].queryset = queryset


EssayGradingFormSet = forms.modelformset_factory(
    Answer,
    fields=["points_awarded", "teacher_feedback"],
    extra=0,
    widgets={"teacher_feedback": forms.Textarea(attrs={"rows": 3})},
)
