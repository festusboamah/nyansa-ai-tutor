# Phase 7: Fees and Mobile Money

## Authoritative ledger

Fee structures belong to one class and term. Draft structures can receive fee items; activation freezes the version for posting. Posting is idempotent on student and fee item, so retrying cannot duplicate a debit.

Ledger balance is calculated from retained records:

`charges + debit adjustments - credit adjustments - successful payments`

Failed, pending, unknown, and reversed payments do not reduce the balance. Reversal changes normalized payment state but retains the original allocations, provider events, and receipt as historical evidence. Charges, adjustments, payments, allocations, provider events, and receipts are not deleted through ordinary workflows.

## Paystack Mobile Money

Nyansa initializes Paystack transactions only on the server with GHS, a unique internal reference, an amount in currency subunits, and the `mobile_money` checkout channel. See the official [Paystack Transaction API](https://paystack.com/docs/api/transaction/) and [payment-channel guide](https://paystack.com/docs/payments/payment-channels/).

The checkout redirect is a customer experience only. It never changes payment status. Paystack recommends server webhooks because browser callbacks can fail or be manipulated; Nyansa follows that guidance and validates the `x-paystack-signature` as HMAC-SHA512 over the exact raw request body before parsing or processing it. See [Paystack webhook verification](https://paystack.com/docs/payments/webhooks/).

Configure:

```env
PAYSTACK_SECRET_KEY=sk_test_or_live_value
```

Set the provider webhook URL to:

```text
https://YOUR_HOST/finance/webhooks/paystack/
```

Never place the secret key in browser code, templates, logs, screenshots, or source control.

## Reconciliation

Each provider event has a provider-scoped unique event ID and a SHA-256 payload digest. An exact replay returns the existing event. Before crediting value, Nyansa requires:

- a valid webhook signature;
- an internal payment matching the provider reference;
- exact amount equality after subunit conversion;
- exact `GHS` currency equality; and
- a valid normalized state transition.

Successful events mark the payment successful, allocate it oldest-due-charge first, create one stable numbered receipt, and queue receipt email notices. Failure leaves the balance unchanged. Reversal restores the balance without erasing history. Amount/currency mismatches and invalid state transitions create administrator-visible reconciliation exceptions. Resolution requires an administrator and a note.

## Guardian and communication workflow

Only an active linked guardian or school administrator can initialize payment for a student. The guardian portal exposes the linked student's balance, payment states, and successful-payment receipts. Balance and receipt messages contain no amount in SMS; sensitive details remain behind authenticated portal access.

## Recovery

- If initialization fails, the payment remains `UNKNOWN`; inspect configuration and start a new uniquely referenced checkout.
- If a valid provider event does not arrive, reconcile using Paystack's server verification tooling before any manual action.
- If a mismatch enters the exception queue, compare the Paystack dashboard reference, amount, currency, and event history. Record the resolution note; never edit the original payment to force agreement.
- Duplicate webhook delivery is safe and does not duplicate allocations or receipts.
