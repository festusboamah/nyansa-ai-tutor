from django.contrib import admin
from .models import (
    AcademicYear, ClassEnrollment, CourseEnrollment, CourseSection, SchoolClass,
    SubjectOffering, TeacherAssignment, Term,
)

admin.site.register([
    AcademicYear, Term, SchoolClass, ClassEnrollment, SubjectOffering, TeacherAssignment,
    CourseSection, CourseEnrollment,
])
