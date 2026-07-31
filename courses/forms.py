from django import forms
from .models import Subject, Material


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class MaterialForm(forms.ModelForm):
    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is None:
            self.fields["subject"].queryset = Subject.objects.none()
        else:
            self.fields["subject"].queryset = Subject.objects.filter(school=school)

    class Meta:
        model = Material
        fields = ["subject", "title", "material_type", "file", "video_url", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
