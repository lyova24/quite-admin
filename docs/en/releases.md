# Releases and compatibility policy

Release **0.3.0** was finalized on **2026-11-01**. Subsequent work targets a higher version.
Its changes are recorded in
the repository `CHANGELOG.md`. A version update alone does not create a tag or release.

## Version rules

- PATCH: compatible bug/security fixes and runtime dependency fixes.
- MINOR: compatible new features; before 1.0, also documented incompatible changes.
- MAJOR after 1.0: required API changes, feature removals or dropped runtime support.

Use the highest required bump once for a batch. Update `pyproject.toml`, public
`__version__`, `uv.lock`, README, UI and documentation references together. Before
the first published release, compare with the previous recorded version.
Every task uses its own Conventional Commit. Commit messages do not automatically
publish a package. Required adapter-contract changes also increment `ADAPTER_API_VERSION`.

Before 1.0, stability is provisional. Breaking field defaults, template changes and API
changes must include migration notes in both languages and CHANGELOG.md. After 1.0,
deprecated public APIs should remain through at least one compatible minor release,
with the removal announced for the next major. Python/framework/ORM support follows
the documented tested matrix; dependency ranges are not proof of every combination.

## Release flow

1. Finalize the versioned changelog section with a release date and migration notes.
2. Run the documented tests, lint, build, documentation and dependency audits.
3. Run `python scripts/check_release.py`; a future tag must equal `v<project.version>`.
4. When explicitly authorized, create/push that tag. The release workflow tests CPython
   3.11–3.15, validates all version references, builds distributions and checks metadata.
5. It creates a **draft GitHub release** using exactly the matching changelog section.
6. A maintainer reviews and publishes the draft. This event rebuilds/validates the tag
   and publishes to PyPI using the separate `pypi` environment and Trusted Publishing.

Configure the PyPI trusted publisher for this repository's `release.yml` workflow and
the GitHub `pypi` environment before publishing. Add required environment reviewers if
the project needs a final manual gate. Build jobs have no OIDC write permission; only
the publishing job receives it and executes no checkout/build code.
This setup follows [PyPI's publishing instructions](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
No API tokens or passwords belong in the repository.

## Dependency security

`security.yml` runs Python `pip-audit` and documentation `npm audit` on pushes, PRs,
manual runs and weekly. Python checks cover all locked extras/dev groups; npm reports
all severities and fails on high/critical findings. Public PRs also use
[GitHub Dependency Review](https://github.com/actions/dependency-review-action).
Network/advisory service errors fail checks. No blanket advisory ignores are configured.
See `SECURITY.md` for private reporting and the early-release maintenance policy.

The 2026-11-01 CI/CD follow-up for **0.3.1** updates Diplodoc and pins patched
transitive packages (including decode-uri-component, fast-xml-parser, glob, minimatch
and KaTeX). The refreshed npm audit reports **zero vulnerabilities**; advisory data can
change, so every run audits again. `scripts/diplodoc.cjs` adapts older CommonJS consumers
to the patched ESM exports of markdown-it and decode-uri-component on Node 24.
It changes module interop only; it does not suppress audits or alter parser behavior.
Strict EN/RU builds verify compatibility. Remove overrides when upstream can use the
patched versions directly.

## Required checks and artifacts

`ci.yml` calls the reusable tests, database, dependency-compatibility and security
workflows. The **CI ready** job fails when any group fails, is cancelled or is skipped.
Configure this check as required on `master`; branch protection is a repository setting.
The release workflow invokes the same complete gate for the tagged commit before
building a draft or publishing to PyPI. Ordinary version checks allow Unreleased;
release tags require a finalized changelog date.

CI exercises Chromium, Firefox and WebKit against a disposable fictional database.
It checks filters and related-ID lookup, debounced search, CSV/XLSX downloads,
inline toggles and stale writes, themed calendars, narrow layouts and the no-script
fallback. Failed browser jobs retain screenshots and traces. Wheel and sdist are each
installed into a clean environment outside the checkout; imports, packaged assets,
FastAPI/Litestar login, filtering and CSV export must work from that installation.

WebKit runs on macOS. Playwright's Linux WebKit build currently renders text attachments
inline despite a valid Content-Disposition header
([upstream issue](https://github.com/microsoft/playwright/issues/43763)); macOS lets the
suite assert real CSV and XLSX download events without replacing response headers.

Pages deploys after a successful `ci` push run for the current `master` SHA. Failed,
stale and pull-request runs cannot trigger publication. A manual run is restricted
to the current `master` commit.
