from django import forms
from django.contrib.auth.forms import UserCreationForm
from schools.models import School
from schools.services import register_school_with_admin
from .models import User


class StudentSignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STUDENT
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class SchoolAdminSignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    school_name = forms.CharField(max_length=200, label="School name")
    education_system = forms.ChoiceField(
        choices=School.EducationSystem.choices,
        widget=forms.RadioSelect,
        label="What kind of institution is this?",
        help_text="This sets the curriculum and grading standard your school will use.",
    )

    class Meta:
        model = User
        fields = ["username", "email", "school_name", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            register_school_with_admin(
                name=self.cleaned_data["school_name"],
                user=user,
                education_system=self.cleaned_data["education_system"],
            )
        return user