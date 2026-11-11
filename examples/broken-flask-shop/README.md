# Broken Flask Shop

This app is an intentionally vulnerable, deliberately incorrect benchmark. Run it only on loopback with synthetic data. Do not expose it to a network or use real account, payment, or notification credentials.

## Defects in this fixture

| ID | Injected defect | Independent checkpoint |
|---|---|---|
| cart-double-tax | Cart total applies tax twice | `cart-total` |
| draft-not-persisted | API claims a draft was saved without storing it | `draft-persistence` |
| duplicate-order | Repeated idempotency key creates another order | `duplicate-order` |
| quantity-validation | Negative quantity is accepted | `quantity-validation` |
| payment-failure | Failed payment is marked paid | `payment-failure` |
| missing-authentication | Order list does not require authentication | `authentication-required` |
| order-ownership | Order lookup ignores ownership | `order-ownership` |
| state-transition | Unsupported order state is accepted | `state-transition` |
| required-fields | Checkout accepts missing required contact/address fields | `required-fields` |
| notification-missing | Checkout never records a notification | `notification-delivery` |
| empty-cart | Empty cart can be checked out | `empty-cart` |
| inventory-reduction | Inventory decreases by one, regardless of quantity | `inventory-reduction` |
| partial-transaction | Order remains after simulated stock failure | `partial-transaction` |
| error-handling | Malformed checkout returns success and internal debug text | `error-handling` |
| stale-frontend-state | UI ignores the returned order ID | `stale-order-state` |

The scoring labels are in `benchmark-manifest.json`. Ghost Feature Hunter does not read that file. It executes the explicit journey in `journeys/checkout.json`; benchmark tests consult the manifest only afterward to compare actual statuses with the known injected defects.

## Install and run

From the repository root:

```console
python -m pip install -e ".[demo,database,browser,dev]"
python -m playwright install chromium
```

Configure a disposable local database and run the Flask server from this directory:

```powershell
$env:GHOST_SHOP_DB = Join-Path $PWD "instance\benchmark.sqlite3"
$env:GHOST_SHOP_DATABASE_URL = "sqlite:///" + $env:GHOST_SHOP_DB.Replace("\", "/")
python app.py
```

The app binds to `127.0.0.1` by default. In `ghost-hunter.json`, set `allow_writes` to `true` only for this isolated demo. Then, from the repository root, run:

```console
ghost-hunter discover --project-root examples/broken-flask-shop
ghost-hunter audit checkout --project-root examples/broken-flask-shop --allow-writes --force
```

The journey includes an HTTP write check and a browser click, so both config and CLI approval are required. Its expected FAIL findings demonstrate the broken behaviors; UNKNOWN means an optional dependency, browser runtime, database URL, or local service was not available. Reports are written to this example's `ghost-reports/` directory.

Tests use isolated temporary databases. The local run command above creates a persistent demo database in `instance/`; remove it manually when you no longer need it.
