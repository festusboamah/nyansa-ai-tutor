from django.contrib import admin

from .models import BillingProviderEvent, LicenseInvoice, LicensePayment, LicensePlan, SchoolLicense

admin.site.register(LicensePlan)
admin.site.register(SchoolLicense)
admin.site.register(LicenseInvoice)
admin.site.register(LicensePayment)
admin.site.register(BillingProviderEvent)
