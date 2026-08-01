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
            "channels": ["mobile_money"],
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

