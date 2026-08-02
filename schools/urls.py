from django.urls import path
from . import views

urlpatterns = [
    path("admin/", views.school_admin_dashboard, name="school_admin_dashboard"),
    path("admin/setup/", views.school_onboarding, name="school_onboarding"),
    path("admin/years/add/", views.create_academic_year, name="create_academic_year"),
    path("admin/terms/add/", views.create_term, name="create_term"),
    path("admin/classes/add/", views.create_school_class, name="create_school_class"),
    path("admin/offerings/add/", views.create_subject_offering, name="create_subject_offering"),
    path("admin/teachers/assign/", views.create_teacher_assignment, name="create_teacher_assignment"),
    path("admin/people/", views.people_directory, name="people_directory"),
    path("admin/people/import-students/", views.bulk_student_import, name="bulk_student_import"),
    path("admin/people/student-template/", views.student_roster_template, name="student_roster_template"),
    path("admin/classes/<int:class_id>/roster/", views.class_roster, name="class_roster"),
    path("admin/classes/<int:class_id>/roster/export/", views.export_class_roster, name="export_class_roster"),
    path("admin/classes/<int:class_id>/roster/<int:enrollment_id>/transfer/", views.transfer_student, name="transfer_student"),
    path("admin/classes/<int:class_id>/promote/", views.promote_class, name="promote_class"),
    path("admin/people/<int:membership_id>/edit/", views.edit_student_record, name="edit_student_record"),
    path("admin/people/invite/", views.invite_member, name="invite_member"),
    path("admin/people/<int:membership_id>/<str:status>/", views.set_membership_status, name="set_membership_status"),
    path("invitations/<str:token>/", views.accept_school_invitation, name="accept_school_invitation"),
]
