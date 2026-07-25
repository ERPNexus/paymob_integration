# Phase 07 — Amount Verification (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** An authentic callback whose amount differs from the frozen snapshot is held for a
human. Nothing posts.

**Depends on:** 06. **Blocks:** 08.

## Scope

- `processor.py` — between "is it a success?" and "post it": compare
  `transaction.amount_cents` against `attempt.expected_amount_cents` with
  `amounts.amounts_match`.
- Mismatch → audit entry (`Amount Mismatch`, `needs_action=1`, both amounts recorded) and
  `attempt.needs_human_attention = 1`. **The lifecycle state is not regressed** (ADR-0003).

## Must be true

- [ ] Under-payment and over-payment are both mismatches.
- [ ] Currency mismatch is a mismatch too, not just the number.
- [ ] Comparison is integer-to-integer. No float appears anywhere in the path.
- [ ] The flag is orthogonal: a mismatched success stays `Paid` and carries
      `needs_human_attention`, exactly as `states.md` describes.
- [ ] Integration test: mismatch → one audit entry, **zero** Payment Entries, invoice still
      unpaid. Assert by counting.
- [ ] `docs/reference/states.md` `needs_human_attention` entry linked from the code path.
