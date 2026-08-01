from django.contrib import admin

from .models import Adjustment, Charge, FeeItem, FeeStructure, Payment, PaymentAllocation, ProviderEvent, Receipt, ReconciliationException


admin.site.register(FeeStructure)
admin.site.register(FeeItem)
admin.site.register(Charge)
admin.site.register(Adjustment)
admin.site.register(Payment)
admin.site.register(PaymentAllocation)
admin.site.register(Receipt)
admin.site.register(ProviderEvent)
admin.site.register(ReconciliationException)
