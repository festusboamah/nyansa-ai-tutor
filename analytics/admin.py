from django.contrib import admin

from .models import EarlyWarningPolicy, Intervention, NarrativeSnapshot, RiskSignal


admin.site.register(EarlyWarningPolicy)
admin.site.register(RiskSignal)
admin.site.register(Intervention)
admin.site.register(NarrativeSnapshot)
