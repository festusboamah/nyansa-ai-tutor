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
    class Meta:
        model = Material
        fields = ["subject", "title", "material_type", "file", "video_url", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }