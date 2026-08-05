# Contributing

## Environment and setup

Use Frappe v16 and ERPNext v16 from the `version-16` branch with Python `>=3.14,<3.15`, MariaDB
10.11, and Redis 7. From a Bench root:

```bash
bench init --skip-redis-config-generation --frappe-branch version-16 /tmp/paymob-alpha-bench
cd /tmp/paymob-alpha-bench
bench get-app --branch version-16 https://github.com/frappe/erpnext
ln -s /home/frappe/frappe-bench-16/apps/paymob_integration apps/paymob_integration
bench new-site --db-root-password root --admin-password admin --db-host 127.0.0.1 --db-port 3306 alpha.test
bench --site alpha.test install-app erpnext
bench --site alpha.test install-app paymob_integration
bench --site alpha.test migrate
```

```bash
cd apps/paymob_integration
pre-commit install
pre-commit run --all-files
bench --site alpha.test run-tests --app paymob_integration
```

Tests must use fake-only credentials and mocks. Never make live Paymob calls or commit test data to
a shared site. Integration tests must not call `frappe.db.commit()` and must use
`NoCommitIntegrationTestCase`.

## Payment safety and documentation

Payment changes require a review against `rules/payments.md` and `rules/implementation-gate.md`.
Verify signed callbacks, integer-cent/currency matching, duplicate protection, permissions,
allocation, refund locking, timeout/error handling, and unchanged ledgers on failure. Update the
relevant user/developer/reference documentation and tests in the same change.

## Commits and pull requests

Use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, or `chore:`). A pull request should
state the problem, summarize the implementation, include test evidence, migration notes when
relevant, linked issues, and screenshots for Desk or website changes.
