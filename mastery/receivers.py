"""Busts class_subject_mastery's cache at the two moments its result can
change: a grade entry being published or reviewed. See services.py's
MASTERY_CACHE_TTL_SECONDS comment for why quiz-answer grading and roster
changes aren't handled here too.
"""
from django.core.cache import cache
from django.dispatch import receiver

from gradebook.signals import grade_entry_published, grade_review_decided

from .services import mastery_cache_key


def _bust(entry):
    offering = entry.assessment.offering
    cache.delete(mastery_cache_key(offering.school_class_id, offering.subject_id, offering.term_id))


@receiver(grade_entry_published)
def bust_mastery_cache_on_publish(sender, entry, **kwargs):
    _bust(entry)


@receiver(grade_review_decided)
def bust_mastery_cache_on_review_decision(sender, entry, **kwargs):
    _bust(entry)
