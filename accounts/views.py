from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .forms import StudentSignUpForm
from schools.models import SchoolMembership
from schools.services import has_school_role


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

@login_required
def profile_view(request):
    user = request.user
    account_age_days = (timezone.now() - user.date_joined).days

    context = {
        "account_age_days": account_age_days,
        "login_count": user.login_count,
        "date_joined": user.date_joined,
    }

    if has_school_role(request, SchoolMembership.Role.STUDENT):
        from quizzes.models import Submission, Badge
        submissions = Submission.objects.filter(
            student=user, quiz__subject__school=request.school
        )
        scores = [s.score for s in submissions if s.score is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        badges = Badge.objects.filter(
            student=user, submission__quiz__subject__school=request.school
        ).select_related("submission__quiz")

        context.update({
            "quizzes_completed": submissions.count(),
            "average_score": avg_score,
            "badges": badges,
        })

    return render(request, "accounts/profile.html", context)
