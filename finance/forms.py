from django import forms

from academics.models import SchoolClass, Term

from .models import Adjustment, FeeItem, FeeStructure


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = ["term", "school_class", "name"]

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["term"].queryset = Term.objects.filter(academic_year__school=school)
        self.fields["school_class"].queryset = SchoolClass.objects.filter(school=school)


class FeeItemForm(forms.ModelForm):
    class Meta:
        model = FeeItem
        fields = ["code", "name", "amount", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}


class AdjustmentForm(forms.Form):
    kind = forms.ChoiceField(choices=Adjustment.Kind.choices)
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    reason = forms.CharField(min_length=5, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class MobileMoneyPaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    email = forms.EmailField()
    phone = forms.CharField(max_length=30)

