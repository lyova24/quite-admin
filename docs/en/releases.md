# Releases and compatibility policy

Release **0.4.0** was finalized on **2026-11-01**. Subsequent work targets a higher version.
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

The 0.4.x line follows explicit [public API guarantees](api-stability.md). Incompatible
changes before 1.0 require MINOR and EN/RU migration notes; after 1.0 they require MAJOR.
Deprecated APIs remain through at least one subsequent compatible MINOR release, with
the replacement and removal version announced. Python/framework/ORM support follows
the documented tested matrix; dependency ranges are not proof of every combination.

## Release flow

1. Finalize the versioned changelog section with a release date and migration notes.
2. Run tests, lint, the API compatibility guard, documentation and dependency audits.
3. Run `python scripts/check_release.py`; the tag must equal `v<project.version>`.
4. When authorized, push the tag. The workflow validates versions and runs the complete
   CPython 3.11–3.15, database, browser, compatibility and security gate.
5. It creates or updates the GitHub release with the matching changelog section.
6. It **publishes the release automatically and marks it Latest**, including an existing
   draft. No separate publication click is required. No library distributions are built
   and nothing is published to PyPI.

Releases contain only GitHub's automatic **Source code (zip)** and **Source code (tar.gz)**
archives of the tagged commit. No wheel, package sdist or extra release assets are
built/uploaded. These source archives do not use Python distribution metadata or Twine;
removing the unnecessary Twine step avoids its rejection of metadata version 2.5.
Download and unpack an archive, then install the source with the desired extras:

```bash
pip install '/path/to/quite-admin-0.4.0[sqlalchemy,fastapi]'
```

The Python build backend remains available for installation from source. Installing
an editable checkout or dependencies in test environments is separate from producing
release artifacts. No API tokens or passwords belong in the repository.

## Dependency security

`security.yml` runs Python `pip-audit` and documentation `npm audit` on pushes, PRs,
manual runs and weekly. Python checks cover all locked extras/dev groups; npm reports
all severities and fails on high/critical findings. Public PRs also use
[GitHub Dependency Review](https://github.com/actions/dependency-review-action).
Network/advisory service errors fail checks. No blanket advisory ignores are configured.
See `SECURITY.md` for private reporting and the early-release maintenance policy.

The 2026-11-01 CI/CD changes included in **0.4.0** update Diplodoc and pin patched
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
publishing a source-only GitHub release. Ordinary version checks allow Unreleased;
release tags require a finalized changelog date.

CI exercises Chromium, Firefox and WebKit against a disposable fictional database.
It checks filters and related-ID lookup, debounced search, CSV/XLSX downloads,
inline toggles and stale writes, themed calendars, narrow layouts and the no-script
fallback. Failed browser jobs retain screenshots and traces. Python matrix jobs test
the source checkout without distribution builds or wheel/sdist checks. Documentation
artifacts remain separate from release assets.

WebKit runs on macOS. Playwright's Linux WebKit build currently renders text attachments
inline despite a valid Content-Disposition header
([upstream issue](https://github.com/microsoft/playwright/issues/43763)); macOS lets the
suite assert real CSV and XLSX download events without replacing response headers.

Pages deploys after a successful `ci` push run for the current `master` SHA. Failed,
stale and pull-request runs cannot trigger publication. A manual run also requires a successful complete CI run
for the current `master` commit.
