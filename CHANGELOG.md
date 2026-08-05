# Changelog

## 0.1.0-alpha

### Supported payment flow

- Hosted Paymob checkout for incoming ERPNext Payment Requests.
- Signed processed callbacks with immediate-capture-only behavior.

### Reconciliation

- Duplicate callback protection and inquiry-based recovery for missing callbacks.
- Integer-cent amount and currency mismatch auditing before ledger posting.

### Refunds

- Full and partial refunds with locked, one-shot requests and signed callback ledger updates.

### Security controls

- Password-field credentials, HMAC verification, permission checks, allocated Payment Entries, and
  no raw card handling.

### Documentation

- Added setup, contributor, security, and sandbox smoke-test guidance.

### Known alpha limitations

- No authorization/capture, void, stored-card/tokenization, subscription, BNPL, POS, or webshop
  gateway-controller support. Alpha upgrades may require migration review.
