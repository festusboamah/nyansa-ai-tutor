from django.urls import path
from . import views

urlpatterns = [
    path("admin/", views.school_admin_dashboard, name="school_admin_dashboard"),
    path("admin/years/add/", views.create_academic_year, name="create_academic_year"),
    path("admin/terms/add/", views.create_term, name="create_term"),
    path("admin/classes/add/", views.create_school_class, name="create_school_class"),
    path("admin/offerings/add/", views.create_subject_offering, name="create_subject_offering"),
    path("admin/teachers/assign/", views.create_teacher_assignment, name="create_teacher_assignment"),
]
