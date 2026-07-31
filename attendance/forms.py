from django import forms

from academics.models import Term

from .models import AttendanceRecord, SchoolCalendarPolicy, SchoolClosure


WEEKDAY_CHOICES = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
    (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class CalendarPolicyForm(forms.ModelForm):
    instructional_weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = SchoolCalendarPolicy
        fields = ["instructional_weekdays"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["instructional_weekdays"] = [str(value) for value in self.instance.weekday_set]

    def clean_instructional_weekdays(self):
        return ",".join(sorted(self.cleaned_data["instructional_weekdays"], key=int))


class SchoolClosureForm(forms.ModelForm):
    class Meta:
        model = SchoolClosure
        fields = ["term", "name", "closure_type", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["term"].queryset = Term.objects.filter(academic_year__school=school)
        self.instance.school = school


class AttendanceCorrectionForm(forms.Form):
    status = forms.ChoiceField(choices=AttendanceRecord.Status.choices)
    reason = forms.CharField(
        min_length=5,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
