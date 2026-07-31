from django.contrib import admin
from .models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term

admin.site.register([AcademicYear, Term, SchoolClass, ClassEnrollment, SubjectOffering, TeacherAssignment])
