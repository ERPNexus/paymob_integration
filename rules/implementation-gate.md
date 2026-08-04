# Implementation Gate — must-not-get-wrong list

Output of Session 9 (2026-07-25). This is the review checklist for every piece of
generated code that touches money. Each item names the attack or failure it prevents.

Use it two ways:

1. As the constraints section of the implementation plan.
2. As the checklist to review generated code against, item by item.

---

## 1. The single write path

- **Exactly one function creates Payment Entries.** The webhook handler, the reconciliation
  poller, and any manual action all route through it. No second path, ever.
- Reason: every extra path needs its own amount check, its own duplicate guard, and its own
  status logic — and the second path is the one nobody tests.
- Review question: *how many places in this codebase call `Payment Entry` insert?* The answer
  must be one.

## 2. Verify before anything else

- HMAC-SHA512 verification runs **first** in the webhook handler — before loading the Payment
  Request, before reading the amount, before any database access.
- Compare with `hmac.compare_digest`, never `==` (timing attack).
- On failure: return an error code, log it, do nothing else.
- Prevents: a forged callback that claims an unpaid order was paid.

## 3. A valid signature is not permission to post

Three separate questions, all required before a ledger write:

1. Is the message authentic? (HMAC)
2. Does it say the payment succeeded? (`success`, transaction state)
3. Does the amount match what we expected? (integer cents comparison)

A valid HMAC only proves the message came from Paymob. It says nothing about whether the
business facts are acceptable.

## 4. Money is integer cents

- Store `custom_grand_total_cents` (integer) on the Payment Request at intention time.
- Compare `amount_cents` from Paymob against that integer directly.
- Never `float(amount) * 100`, never `==` between floats.
- Prevents: silent one-piastre truncation on some transactions.

## 5. Amount mismatch never posts automatically

- Authentic callback, but amount differs from expected → create an audit record, post nothing,
  require human review (ADR-0003).
- Prevents: automatically accepting an underpayment as full settlement.

## 6. Incoming duplicates — deduplicate

- Unique database constraint on the Paymob transaction ID.
- A repeated webhook returns HTTP 200 and changes nothing.
- Prevents: replay attacks **and** Paymob's normal retries — same code, both problems.

## 7. Duplicate payment for one Payment Request

- Different transaction IDs, same Payment Request, both genuine (customer double-paid).
- Item 6 does **not** catch this. Add a separate check: does a submitted Payment Entry already
  exist for this Payment Request?
- If yes: audit record, no second posting, **and flag for human refund** — the customer really
  was charged twice.

## 8. Outgoing duplicates — lock, do not deduplicate

- Refund requests must take a server-side lock **before** the API call
  (row lock on the Payment Request, or an in-progress record).
- The refund has no ID until the call happens, so deduplication cannot work here.
- Disabling a button in the browser is not a defense. Neither is trusting Paymob to reject it.

## 9. The API response is not the truth

- Never create a Payment Entry from an HTTP 200 returned by Paymob.
- The ledger write happens on the **verified webhook**, or from the reconciliation poller.
- Reason: "request failed" and "response lost" look identical to the caller. If you trust the
  response, a lost response means the customer was charged and ERPNext has no record.

## 10. Retry reads, never retry writes

- Transaction Inquiry is safe to retry — it changes nothing.
- Refunds must never retry automatically. Paymob's endpoint takes no
  idempotency key, so a retry is a genuinely new money movement.
- Re-issuing a refund is a human decision.

## 11. Errors never change payment state

- A 401, a timeout, or a 502 from Paymob means "try again later". It never means "declare this
  payment dead".
- Auth token expired → refresh the token, retry, keep the payment pending.
- Intention expired **and** inquiry finds no transaction → `expired` (final).
- These are two different things and must not share a code path.

## 12. Failed payments touch nothing

- A declined card updates the Payment Request status only.
- No Payment Entry. No GL row. The Sales Invoice stays unpaid and is not cancelled.
- The customer must still be able to start a **new** attempt — new special reference, new
  intention, new Paymob order, new client secret.

## 13. Every whitelisted method is a public endpoint

- `@frappe.whitelist()` means any logged-in user can call it, whatever the UI shows.
- Every money-moving method checks permission on the document first.
- Every parameter arriving from the browser is attacker-controlled. Amounts are read from
  verified Paymob data or from the ERPNext database — never from the request body.
- `allow_guest=True` on anything that moves money is an automatic reject.

## 14. Status is derived, never written by hand

- Do not `db_set` the Payment Request status. ERPNext derives it from submitted Payment Entries
  and their allocations.
- A hand-written "Paid" makes the document lie about the ledger below it.

## 15. Every Payment Entry is allocated

- The `references` table must point at the specific Sales Invoice.
- An unallocated entry leaves the invoice Unpaid/Overdue while the money floats as an
  unapplied credit.

## 16. Non-blocking network calls

- Every outbound request sets a `timeout`.
- Every outbound request handles connection errors explicitly.
- Prevents: one slow gateway freezing the site's workers.
