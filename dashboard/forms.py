from django import forms
from .models import LessonNote


class LessonNoteForm(forms.ModelForm):
    class Meta:
        model = LessonNote
        fields = [
            "subject", "class_level", "week_ending", "strand_topic",
            "content_standard", "learning_indicator", "performance_indicator",
            "reference", "resources", "num_days",
        ]
        widgets = {
            "week_ending": forms.DateInput(attrs={"type": "date"}),
            "content_standard": forms.Textarea(attrs={"rows": 2}),
            "learning_indicator": forms.Textarea(attrs={"rows": 2}),
            "performance_indicator": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )
