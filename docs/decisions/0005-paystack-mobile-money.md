# ADR 0005: Paystack for the first Mobile Money adapter

## Status

Accepted for Phase 7.

## Decision

Use Paystack as the first payment gateway behind a small server-side adapter. Initialize GHS checkout with the `mobile_money` channel and unique Nyansa reference. Treat authenticated webhook events—not redirects—as payment evidence.

## Rationale

Paystack documents Ghana Mobile Money support, server-side transaction initialization, unique references, currency subunits, and HMAC-SHA512 webhook signatures. Its hosted checkout limits payment-data exposure in Nyansa while the adapter boundary permits a future provider replacement.

## Consequences

- Schools need an approved Paystack account and secret key.
- Webhook endpoints require public HTTPS configuration.
- Final value posting depends on exact signature, reference, amount, and currency checks.
- Provider-specific payloads remain at the adapter/service boundary; the ledger uses provider-neutral payment states.
