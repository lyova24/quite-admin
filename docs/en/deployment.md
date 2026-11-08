# Deploy your admin

Use this guide after [connecting your application](quickstart.md). Your application
continues to own its database, accounts, business rules and migrations.

## Configure accounts and sessions

Connect [your application's authentication backend](authentication.md) and define who
may view, create, change and delete records. `PasswordAuth.single_user()` is useful
for a local trial; it does not integrate your application's accounts automatically.

Set `secret_key` from your secret store to a persistent random value of at least
32 bytes. Use the same value for all workers that share sessions. Serve the application
over HTTPS and keep `secure_cookies=True`; `False` in the standalone example is for local HTTP.
See [sessions and request protection](authentication.md#sessions).

## Review models and write rules

Automatic discovery exposes the adapter's models. Review the selected collections,
visible fields, editable fields and allowed operations before granting access.
[Collection and field settings](configuration.md) apply on the server as well as in the UI.

Choose the data-access mode that preserves your application rules:

| Mode | What runs when records change |
| --- | --- |
| Native ORM adapter | ORM persistence, Python defaults and the ORM's supported hooks |
| SQL reflection | Database constraints, defaults and triggers |
| Application-service adapter | Your service's validation, authorization and write operations |

SQL reflection does not run Python ORM hooks or service-layer rules. Use
[application services](custom-adapters.md#application-services) when writes must pass
through your existing business logic. Check the [compatibility matrix and limits](data-safety.md)
for your adapter and database.

## Persist admin service data

Business records remain in your application's database. Activity history uses separate
[admin service storage](storage.md), which defaults to `.quite-admin/state.sqlite3`.
Put SQLite storage on a persistent writable volume, or configure the documented
PostgreSQL/MySQL storage for your deployment. Replicas that must share admin state need
the same storage; separate container-local files do not share it.

Choose the history recording level and retention period for your requirements.
History defaults to committed changes and 90-day retention. Review
[failure and durability semantics](storage.md#failure-and-durability-semantics) and include
both business data and admin service data in your backup process.

## Preserve application startup and shutdown

Create the mount before the host starts. `mount_fastapi()` and `mount_litestar()`
preserve the host lifespan and close admin service resources on shutdown.
Your host still initializes and closes its own engines, ORM clients and pools.

Keep migrations in your deployment process. After a migration, refresh SQL reflection
metadata when needed. [Integrations](integration.md) cover lifecycle, mount paths and
reverse-proxy prefixes. Configure [read deadlines and concurrency](configuration.md#shared-read-limits)
if the admin shares a database pool with application traffic.

## Check the deployed application

Verify sign-in, permissions, a representative write through your business rules,
activity history and the mount URL behind your proxy. Connect
[application logging](logging.md) to investigate failures.

Use [public API guarantees](api-stability.md) and the
[dependency compatibility guide](dependency-compatibility.md) when planning upgrades.
Release and migration notes are in the [changelog](https://github.com/lyova24/quite-admin/blob/master/CHANGELOG.md).
