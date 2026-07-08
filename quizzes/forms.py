from django import forms
from .models import Quiz, Question, Choice


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["subject", "title", "description", "time_limit_minutes", "max_attempts", "deadline"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["text", "question_type", "order"]
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

    def __init__(self, *args, **kwargs):
        from courses.models import Subject
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.all()