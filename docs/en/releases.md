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
2. Push the commit to `master` and wait for `ci.yml`. Automatic runs select checks
   affected by the changed files. Before tagging, require **Release ready**: if it was
   skipped, run **Actions → ci → Run workflow → master** (or
   `gh workflow run ci.yml --ref master`) and wait for the full run on this exact commit.
3. Run `python scripts/check_release.py --tag v<project.version>`.
4. Push the version tag when authorized. `release.yml` requires successful full master CI
   and its documentation artifact for that exact commit, then publishes the GitHub
   release with the matching changelog and marks it Latest.
5. After that workflow succeeds, `pages.yml` deploys the existing CI documentation
   artifact. In parallel, `pypi.yml` builds **one universal wheel and one sdist** on
   Python 3.12, checks both with Twine and installs each into a clean environment.
6. A separate job uploads the verified files to PyPI through Trusted Publishing; a final
   job installs the exact version from the public index and checks packaged resources.

Releases never rerun the test matrix. The latest `ci.yml` run for the tagged SHA from
a push to `master` or a manual run on `master` must finish successfully, including
**CI ready** and **Release ready**. A selective green run allows a merge but does not
authorize publication. An older green run cannot hide a newer failed, cancelled,
unfinished or selective run. PR runs and runs from other branches cannot authorize
releases. Do the full run before tagging, while `master` still points to the release
commit; any subsequent commit needs its own validation.

Missing or expired documentation artifacts also block the release; rerun the full CI
to rebuild them. Pages publishes the tagged version even if `master` has advanced,
using the documentation artifact from the same full run without rebuilding it or
repeating demo tests. PyPI checks the same full-validation gate on automatic and manual
uploads, without requiring the documentation artifact again.

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

`ci.yml` first selects checks from the Git diff, then calls the reusable Python,
documentation, JavaScript, browser, database, dependency-compatibility and security
workflows. Every run checks release metadata without installing dependencies. Selection
is reported in the run summary.

| Changed files | Selected checks |
| --- | --- |
| Documentation, README, changelog or documentation build scripts | Strict EN/RU documentation and demo build |
| Python sources, examples or demo export script | Python/lint/API checks, databases, compatibility, JavaScript, browsers and docs/demo |
| Shared UI templates or static assets | Python, compatibility, JavaScript, browsers and docs/demo |
| Demo sources | JavaScript, browsers and docs/demo |
| Python tests | Python, databases and compatibility; shared browser fixtures also select browsers |
| Node tests / Playwright specs or config | JavaScript / browser checks respectively |
| `pyproject.toml` or `uv.lock` | All Python consumers and the Python dependency audit |
| `package.json` or `package-lock.json` | Documentation, JavaScript, browsers and the npm audit |
| CI workflows, CI guard scripts/tests or unknown paths | Full validation |

Mixed changes select the union of their checks. PRs compare the head to its merge base
with the target branch; pushes compare the whole pushed range. Deleted files and both
paths of a rename count. An unavailable comparison, including a missing force-push base,
runs all checks. Manual `ci.yml` runs always run everything. Weekly security scans
continue auditing both ecosystems even without dependency changes.

**CI ready** always runs and requires every selected group to succeed. Only groups
explicitly excluded by the selection plan may be skipped; failed selection, failed
metadata, cancellation or an unexpected skip fails the gate. Configure **CI ready**
as the required check on `master`; branch protection is a repository setting.
**Release ready** succeeds only after complete validation; leave it optional for merges.
A version-tag push only runs publication and checks these existing gates for the exact
tagged SHA. Version checks allow Unreleased; release tags require a finalized changelog date.

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

Pages deploys after the `release` workflow succeeds and rechecks full CI for the
released SHA. Ordinary pushes, PRs and manual CI runs alone do not deploy the site.
