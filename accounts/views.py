from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from .forms import StudentSignUpForm


def home_view(request):
    return render(request, "home.html")


def signup_view(request):
    if request.method == "POST":
        form = StudentSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully! Welcome to Nyansa.")
            return redirect("home")
    else:
        form = StudentSignUpForm()
    return render(request, "accounts/signup.html", {"form": form})