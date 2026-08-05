# Paymob Integration 0.1.0-alpha

> **Alpha warning:** this is the first public alpha. Payment behavior and upgrade paths may change
> before a stable release. Test on a disposable site and keep verified backups before upgrades.

Paymob Integration adds hosted Paymob checkout for incoming ERPNext Payment Requests. It verifies
signed callbacks, reconciles missing callbacks, protects against duplicate delivery, creates
allocated Payment Entries, and supports full and partial refunds.

## Supported and unsupported functionality

Supported: hosted checkout, signed processed callbacks, reconciliation inquiries, duplicate
protection, allocated Payment Entries, and full/partial refunds. Payments are immediate-capture only.

Not supported: deferred authorization/capture, void workflows, stored cards or tokenization,
subscriptions, BNPL, POS/webshop gateway-controller integration, and raw card handling. Card PAN and
CVV never enter this app.

## Compatibility

- Frappe v16 and ERPNext v16 (`version-16` branch)
- Python `>=3.14,<3.15`
- MariaDB 10.11 and Redis 7 are the tested infrastructure baseline

## Installation

```bash
bench get-app <repository-url> --branch version-16
bench --site <site-name> install-app paymob_integration
bench --site <site-name> migrate
```

## Configuration

Open **Paymob Settings** and configure the Password fields for Secret Key, API Key, and HMAC
Secret. Configure the public key, country, currency, mode, payment account, and matching numeric
Integration ID. Country, currency, and mode must match across each credential and integration row.
Use sandbox credentials and Test mode first; never copy live credentials into a test site.

Set Paymob's processed-callback URL to:

```text
/api/method/paymob_integration.webhooks.processed_callback
```

Use the processed callback, not the browser response callback, as payment authority. Configure
immediate capture only. See the [user guide](docs/user-guide/README.md) for the complete setup.

## Payment behavior

The app creates a hosted checkout for a submitted incoming Payment Request. A valid signed success
callback with matching integer-cent amount and currency is reconciled to one allocated Payment
Entry. Declines leave the invoice and ledger unchanged. Duplicate callbacks are acknowledged without
duplicate posting. Missing callbacks can be recovered by reconciliation inquiry. Amount or currency
mismatches are audited and held for review without posting. Refunds are one-shot outbound requests;
verified refund callbacks create the corresponding ledger reversal, and full/partial refund state is
tracked. Refunds are never retried automatically.

## Production prerequisites

Use HTTPS and a publicly reachable callback URL. Provide MariaDB, Redis, workers, scheduler,
ERPNext, backups, configured email, correct live credentials, and monitoring. A sandbox smoke test
does not prove live-mode readiness; review [the smoke-test checklist](docs/developer-guide/sandbox-smoke-test.md).

## Documentation

- [User guide](docs/user-guide/README.md)
- [Developer guide](docs/developer-guide/README.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Alpha limitations and upgrade risk

This release has no compatibility promise for future alpha migrations or payment-state changes.
Keep backups, test upgrades on a disposable clone, and review the changelog before updating.

## Roadmap

- **`payments` app integration** — register Paymob as a `Payment Gateway Controller` so ERPNext's
  webshop "Pay Now", POS, and any other app already speaking that interface get a working checkout
  for free, instead of every storefront hand-rolling its own Sales Order → Payment Request wiring.
  This remains unsupported in 0.1.0-alpha and needs a design decision because the `payments` app
  models one gateway account per site while this app's Credential Set table is multi-country/multi-currency.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the supported environment, checks, payment-safety review,
and pull-request expectations.

## License

MIT. See [license.txt](license.txt).
