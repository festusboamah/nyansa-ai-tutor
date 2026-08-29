from django import forms
from .models import Quiz, Question, Choice


class QuizForm(forms.ModelForm):
    # Declared explicitly (rather than left to ModelForm auto-derivation) so an
    # omitted/empty submission - the common case for a plain, non-exam quiz -
    # cleans to the model's real default instead of "" or None. See clean().
    results_release_mode = forms.ChoiceField(
        choices=Quiz.ResultsReleaseMode.choices, required=False,
        initial=Quiz.ResultsReleaseMode.INSTANT,
        help_text="Exams only: Instant shows the score as soon as it's ready; Scheduled releases it "
                   "automatically at a set time; Manual waits for you to publish it.",
    )
    require_webcam_snapshots = forms.BooleanField(
        required=False,
        help_text="Exams only: periodically capture a webcam snapshot during the exam for you to review afterward.",
    )
    snapshot_interval_seconds = forms.IntegerField(
        required=False, min_value=10, initial=90,
        help_text="How often to capture a webcam snapshot, in seconds (only used if webcam snapshots are required above).",
    )

    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject

        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )

    class Meta:
        model = Quiz
        fields = [
            "subject", "title", "description", "assessment_type",
            "time_limit_minutes", "max_attempts", "deadline",
            "starts_at", "essay_weight_percent",
            "results_release_mode", "results_release_at",
            "require_webcam_snapshots", "snapshot_interval_seconds",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "results_release_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
        help_texts = {
            "starts_at": "Exams only: when students may begin. Leave blank for a plain quiz.",
            "essay_weight_percent": "Exams with essay questions: essay's share of the combined score (0-100).",
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("results_release_mode"):
            cleaned_data["results_release_mode"] = Quiz.ResultsReleaseMode.INSTANT
        if not cleaned_data.get("snapshot_interval_seconds"):
            cleaned_data["snapshot_interval_seconds"] = 90

        quiz = Quiz(
            essay_weight_percent=cleaned_data.get("essay_weight_percent"),
            results_release_mode=cleaned_data.get("results_release_mode"),
            results_release_at=cleaned_data.get("results_release_at"),
            starts_at=cleaned_data.get("starts_at"),
            deadline=cleaned_data.get("deadline"),
        )
        try:
            quiz.clean()
        except forms.ValidationError as exc:
            raise forms.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return cleaned_data


class QuestionForm(forms.ModelForm):
    def __init__(self, *args, quiz=None, **kwargs):
        super().__init__(*args, **kwargs)
        if quiz is None or quiz.assessment_type != Quiz.AssessmentType.EXAM:
            self.fields["question_type"].choices = [
                choice for choice in self.fields["question_type"].choices
                if choice[0] != Question.QuestionType.ESSAY
            ]

    class Meta:
        model = Question
        fields = ["text", "question_type", "points", "order"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 2}),
        }


class ChoiceForm(forms.Form):
    text = forms.CharField(max_length=255, required=False)
    is_correct = forms.BooleanField(required=False)


ChoiceFormSet = forms.formset_factory(ChoiceForm, extra=4)


class AIQuizGenerationForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=None)
    title = forms.CharField(max_length=200)
    topic = forms.CharField(
        max_length=300,
        help_text="What should this quiz cover? e.g. 'Basic algebra: solving for x'"
    )
    num_questions = forms.IntegerField(min_value=1, max_value=15, initial=5)
    difficulty = forms.ChoiceField(choices=[
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ])

    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )


class BankQuestionGenerationForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=None)
    mastery_topic = forms.ModelChoiceField(queryset=None, required=False, label="Mastery topic (optional tag)")
    topic_description = forms.CharField(
        max_length=300,
        help_text="What should these questions cover? e.g. 'Basic algebra: solving for x'"
    )
    num_questions = forms.IntegerField(min_value=1, max_value=15, initial=5)
    difficulty = forms.ChoiceField(choices=[
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ])

    def __init__(self, *args, school=None, **kwargs):
        from courses.models import Subject
        from mastery.models import Topic
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = (
            Subject.objects.filter(school=school) if school else Subject.objects.none()
        )
        self.fields["mastery_topic"].queryset = (
            Topic.objects.filter(strand__subject__school=school).select_related("strand")
            if school else Topic.objects.none()
        )
