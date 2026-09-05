from django import forms
import json
from .models import LessonNote, SchemeOfLearning, StudentNote


class LessonNoteForm(forms.ModelForm):
    class Meta:
        model = LessonNote
        fields = [
            "subject", "class_level", "class_size", "duration", "week_ending", "strand_topic",
            "sub_strand", "content_standard", "learning_indicator", "performance_indicator",
            "core_competencies", "reference", "resources", "num_days",
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


class LessonNoteRevisionForm(LessonNoteForm):
    generated_content = forms.JSONField(
        widget=forms.Textarea(attrs={"rows": 18}),
        help_text="Edit the structured daily plan as valid JSON.",
    )
    revision_reason = forms.CharField(
        min_length=5,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Explain what changed in this version.",
    )

    class Meta(LessonNoteForm.Meta):
        fields = LessonNoteForm.Meta.fields + ["generated_content"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            try:
                self.initial["generated_content"] = json.loads(self.instance.generated_content)
            except (json.JSONDecodeError, TypeError):
                self.initial["generated_content"] = self.instance.generated_content


class LessonCommentForm(forms.Form):
    message = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class SchemeOfLearningForm(forms.ModelForm):
    starting_topics = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional: list any topics you already know you want covered, to guide the AI.",
    )

    class Meta:
        model = SchemeOfLearning
        fields = ["subject", "class_level", "term", "num_weeks"]

    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )


class StudentNoteForm(forms.ModelForm):
    class Meta:
        model = StudentNote
        fields = ["subject", "class_level", "topic"]

    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )
