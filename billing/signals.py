"""
Domain events for trial lifecycle changes. billing doesn't import
communications directly - communications/receivers.py subscribes to these,
same pattern as gradebook.signals/dashboard.signals.
"""
import django.dispatch

trial_ending_soon = django.dispatch.Signal()  # kwargs: license
trial_expired = django.dispatch.Signal()  # kwargs: license
