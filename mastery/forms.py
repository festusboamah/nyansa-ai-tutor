from django import forms

from .models import Strand, Topic


class StrandForm(forms.ModelForm):
    class Meta:
        model = Strand
        fields = ["subject", "name", "order"]

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            self.fields["subject"].queryset = self.fields["subject"].queryset.filter(school=school)


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ["strand", "name", "order"]

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            self.fields["strand"].queryset = self.fields["strand"].queryset.filter(school=school)
