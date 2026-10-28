# quite-admin

- Support Python 3.11–3.15, FastAPI and Litestar. Keep the core ORM-independent; access data through adapters.
- Preserve authentication, authorization, CSRF, field restrictions and CSP. Never log passwords, tokens or record values.
- Document user-facing changes in both Diplodoc languages: `docs/en` is primary, `docs/ru` is the translation. Update both navigation files when adding pages.
- Verify changed behavior with integration tests. Do not suppress dependency warnings.
- Python checks: `uv run pytest -q`, `uv run ruff check src tests examples`, `uv run ruff format --check src tests examples`, `uv build`.
- Run `npm run docs:build` after documentation changes.

## Versioning

- Use PEP 440-compatible `MAJOR.MINOR.PATCH` versions.
- `PATCH`: backward-compatible bug fixes, security fixes and runtime dependency fixes.
- `MINOR`: new features, options and adapters that preserve existing default behavior.
- `MAJOR`: incompatible public API or behavior changes, feature removal, or dropping Python / framework / ORM support. Before `1.0`, bump `MINOR` for these changes; moving to `1.0` requires a separate decision about API stability.
- Reset `MINOR` and `PATCH` when bumping `MAJOR`; reset `PATCH` when bumping `MINOR`.
- Documentation-only changes, tests, behavior-preserving refactoring and development tooling updates do not require a library version bump. A dependency upgrade alone does not imply `MAJOR`: assess the library's compatibility.
- Plan the version relative to the latest released version, choosing the highest applicable bump. Bump once per batch of unreleased changes; retain the planned `0.1.0` until the first release.
- The source of truth is `project.version` in `pyproject.toml`. Update `src/quite_admin/__init__.py::__version__` in sync and regenerate `uv.lock` with `uv lock`; check version references in the UI and documentation.
- `package.json` and `package-lock.json` belong to documentation tooling and need not match the Python package version. Update lockfiles through their package managers.
- Document breaking changes and migration steps in EN/RU. Create release tags and publish only when explicitly requested by the user.
