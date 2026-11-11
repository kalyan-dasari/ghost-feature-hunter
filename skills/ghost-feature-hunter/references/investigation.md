# Investigation guide

## Define the journey

Break the feature into observable checkpoints from user action through the final outcome. For checkout, that might include cart calculation, request submission, payment outcome, order persistence, inventory, notification, and rendered confirmation. Pick only checkpoints whose expected behavior has an authoritative source.

For each checkpoint capture:

- A stable ID and plain-language name.
- The expected result and its source.
- The adapter that can observe it.
- The exact assertion and required inputs.
- Required user role/account, test data, and environment.
- Preconditions, cleanup expectations, and risk of side effects.

## Inspect before execution

Read `ghost-hunter.json` and the selected journey. Check that the configured `environment` is truthful, `base_url` is intentional, and allowed hosts are scoped. Check whether an adapter's optional package and runtime exist. Missing prerequisites mean UNKNOWN, not failure.

Use discovery to find likely Flask routes, tests, templates, and model declarations. Discovery parses files without executing them and is advisory. Follow references into code manually and do not treat a route's existence as proof that the feature works.

## Isolate state

Use a disposable local database and synthetic accounts. Avoid real payment instruments, outbound notification credentials, and production data. A test journey that might create or change state must be approved through the project's write setting and CLI flag. Plan resets using application-owned fixtures outside Ghost Feature Hunter; the engine will not delete or mutate databases to clean up.
