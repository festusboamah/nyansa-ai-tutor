"""Domain events other apps (e.g. `communications`) can subscribe to, so
gradebook never has to import a notification app to describe what happened.
"""
import django.dispatch

# Fired when a grade entry transitions to PUBLISHED, needing administrator review.
# kwargs: entry (GradeEntry), actor (SchoolMembership who published it)
grade_entry_published = django.dispatch.Signal()

# Fired when an administrator approves or returns a grade entry.
# kwargs: entry (GradeEntry, already saved with the decision), note (str)
grade_review_decided = django.dispatch.Signal()
