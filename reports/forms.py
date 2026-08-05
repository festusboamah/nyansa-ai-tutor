from django import forms

from .models import ReportPolicy, TermReport


class ReportPolicyForm(forms.ModelForm):
    class Meta:
        model = ReportPolicy
        fields = ["show_position", "pass_mark", "promotion_average"]


class ReportDetailsForm(forms.ModelForm):
    class Meta:
        model = TermReport
        fields = ["conduct", "teacher_remark", "administrator_remark", "promotion_outcome"]
        widgets = {
            "teacher_remark": forms.Textarea(attrs={"rows": 3}),
            "administrator_remark": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, is_admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        if is_admin:
            self.fields.pop("conduct")
            self.fields.pop("teacher_remark")
        else:
            self.fields.pop("administrator_remark")
            self.fields.pop("promotion_outcome")


class ReportDecisionForm(forms.Form):
    action = forms.ChoiceField(choices=[])
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, actions, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["action"].choices = actions
        self.fields["note"].help_text = "Required when sending back or reopening a published report."
