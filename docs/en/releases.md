# Releases and compatibility policy

Release history and migration instructions live in the repository [CHANGELOG](https://github.com/lyova24/quite-admin/blob/master/CHANGELOG.md). A version update alone does not create a tag or release.

## Version rules

- PATCH: compatible bug/security fixes and runtime dependency fixes.
- MINOR: compatible new features; before 1.0, also documented incompatible changes.
- MAJOR after 1.0: required API changes, feature removals or dropped runtime support.

Use the highest required bump once for a batch. Update `pyproject.toml`, public
`__version__`, `uv.lock`, README, UI and documentation references together. Before
the first published release, compare with the previous recorded version.
Every task uses its own Conventional Commit. Commit messages do not automatically
publish a package. Required adapter-contract changes also increment `ADAPTER_API_VERSION`.

The library follows explicit [public API guarantees](api-stability.md). Incompatible
changes before 1.0 require MINOR and EN/RU migration notes; after 1.0 they require MAJOR.
Deprecated APIs remain through at least one subsequent compatible MINOR release, with
the replacement and removal version announced. Python/framework/ORM support follows
the documented tested matrix; dependency ranges are not proof of every combination.

## Release flow

1. Finalize the version, changelog date and migration notes.
2. Push the commit to `master` and wait for `ci.yml` to finish successfully. It runs
   tests, lint, the API compatibility guard, documentation and dependency audits.
3. Run `python scripts/check_release.py --tag v<project.version>`.
4. Push the version tag when authorized. `release.yml` requires successful master CI
   and its documentation artifact for that exact commit, then publishes the GitHub
   release with the matching changelog and marks it Latest.
5. After that workflow succeeds, `pages.yml` deploys the existing CI documentation
   artifact. In parallel, `pypi.yml` builds **one universal wheel and one sdist** on
   Python 3.12, checks both with Twine and installs each into a clean environment.
6. A separate job uploads the verified files to PyPI through Trusted Publishing; a final
   job installs the exact version from the public index and checks packaged resources.

Releases never rerun the test matrix. Missing, unfinished, failed, cancelled or skipped
CI blocks publication immediately; finish or rerun the master CI, then rerun the release.
The latest master-push run for the tagged SHA must succeed, including **CI ready**;
an older green run cannot hide a newer unsuccessful run. PR and manual CI runs do not
authorize releases. Missing or expired documentation artifacts also block the release;
rerun the master CI to rebuild them. Pages publishes the tagged version even if `master`
has advanced, without rebuilding the docs or repeating demo tests.

Creating a release in GitHub's interface uses the same existing-CI gate before Pages
and PyPI publication. The package workflow checks out the validated commit by SHA,
checks master CI again for automatic and manual uploads, and verifies that the published
version tag still points to that exact commit.

GitHub release downloads remain the automatic source-code ZIP/tar.gz archives.
Wheel/sdist files go to PyPI, not GitHub release assets. Python test matrix jobs do not
build packages. Both distributions explicitly use core metadata **2.4**; checks reject
a different metadata version.

## One-time PyPI setup

Sign in to PyPI and add a pending publisher at
[account publishing settings](https://pypi.org/manage/account/publishing/) for the first
upload, or configure a publisher on the existing project's Publishing page:

| Field | Value |
|---|---|
| PyPI project | `quite-admin` |
| GitHub owner | `lyova24` |
| Repository | `quite-admin` |
| Workflow filename | `pypi.yml` |
| GitHub environment | `pypi` |

The upload job uses the GitHub environment `pypi`. Only that job has `id-token: write`;
no checkout or project code runs in it. PyPI exchanges the GitHub OIDC identity for a
short-lived upload credential; no long-lived PyPI token belongs in GitHub secrets or
the repository. Optional environment reviewers can restrict who authorizes publication.
See [PyPI's official setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

The PyPI workflow is top-level rather than reusable, so the publisher always matches
`pypi.yml`. It accepts only successful release runs from this repository and verifies
the tag still points to the validated source commit and the GitHub release is published.
For a retry, run **publish to PyPI** manually from `master`, entering the existing tag,
`v<project.version>`. Manual runs use the same latest-master-CI gate for the source
commit. They do not need the documentation artifact again. Existing package files are
skipped on retry; PyPI versions cannot
be overwritten. Never move a published tag to change an uploaded package.

## Install with a package manager

```bash
pip install 'quite-admin[sqlalchemy,fastapi]'
uv add 'quite-admin[sqlalchemy,litestar]'
```

The core also installs as `pip install quite-admin` without ORM dependencies.
Other extras are `sqlmodel`, `tortoise`, `peewee`, `gino-legacy`, `pydantic`, `fastapi`, `litestar`
and `all`. GINO 1.x requires a separate environment from modern SQLAlchemy adapters.
Installation from an unpacked source archive remains available.

## Dependency security

`security.yml` runs Python `pip-audit` and documentation `npm audit` on master pushes, PRs,
manual runs and weekly. Python checks cover all locked extras/dev groups; npm reports
all severities and fails on high/critical findings. Public PRs also use
[GitHub Dependency Review](https://github.com/actions/dependency-review-action).
Network/advisory service errors fail checks. No blanket advisory ignores are configured.
See `SECURITY.md` for private reporting and the early-release maintenance policy.

Documentation tooling pins transitive dependencies through `package-lock.json` and
`package.json` overrides. `scripts/diplodoc.cjs` handles CommonJS/ESM interop on Node 24.
Strict EN/RU builds and fresh security audits validate that environment.

## Required checks and artifacts

`ci.yml` calls the reusable tests, database, dependency-compatibility and security
workflows. The **CI ready** job fails when any group fails, is cancelled or is skipped.
Configure this check as required on `master`; branch protection is a repository setting.
CI runs on pushes to `master`, PRs and manual requests; a version-tag push only runs
the publication workflow. The release checks the existing CI result for the tagged SHA
before publishing a source-only GitHub release and triggering Pages/PyPI. Version checks allow
Unreleased; release tags require a finalized changelog date.

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
