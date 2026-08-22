"""Domain events other apps (e.g. `communications`) can subscribe to, so
dashboard never has to import a notification app to describe what happened.
"""
import django.dispatch

# Fired when a lesson note needs reviewer (admin) attention - submitted for
# review, or the author commented while it's pending.
# kwargs: note (LessonNote), message (str)
lesson_note_needs_review = django.dispatch.Signal()

# Fired when a lesson note's author needs to know about a status change or a
# reviewer comment.
# kwargs: note (LessonNote), message (str)
lesson_note_author_notified = django.dispatch.Signal()
