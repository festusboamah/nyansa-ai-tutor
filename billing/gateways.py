"""
Structurally mirrors finance/gateways.py::PaystackGateway - deliberately not
imported from there. `finance` is a frozen app slated for extraction to
Suku360 (see AGENTS.md); billing is permanent Nyansa revenue logic that must
never be extracted, so it can't depend on code that will eventually move to
a different system. Both classes call the same Paystack account (a single
platform-wide PAYSTACK_SECRET_KEY), just through independent code paths.
"""
import json
from urllib import request as urllib_request

from django.conf import settings


class PaystackGateway:
    name = "PAYSTACK"
    initialize_url = "https://api.paystack.co/transaction/initialize"

    def initialize(self, *, reference, amount, email, callback_url):
        secret = settings.PAYSTACK_SECRET_KEY
        if not secret:
            raise RuntimeError("PAYSTACK_SECRET_KEY is not configured.")
        payload = json.dumps({
            "reference": reference,
            "amount": str(int(amount * 100)),
            "email": email,
            "currency": "GHS",
            "callback_url": callback_url,
        }).encode("utf-8")
        req = urllib_request.Request(
            self.initialize_url, data=payload, method="POST",
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
        )
        with urllib_request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("status") or not result.get("data", {}).get("authorization_url"):
            raise RuntimeError("Paystack did not initialize the payment.")
        return result["data"]
