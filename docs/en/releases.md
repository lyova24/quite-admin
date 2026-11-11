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
2. Push the commit to `master` and wait for its automatic full `ci.yml` run, including
   **CI ready** and **Release ready**. Every branch push runs all validation groups,
   both dependency audits, the documentation build and distribution checks.
3. Run `python scripts/check_release.py --tag v<project.version>`.
4. Push the version tag when authorized. `release.yml` requires successful full master CI
   and its documentation and distribution artifacts for that exact commit, then publishes
   the GitHub release with the matching changelog and marks it Latest.
5. After that workflow succeeds, `pages.yml` deploys the existing CI documentation
   artifact. In parallel, `pypi.yml` downloads the verified **one universal wheel and
   one sdist** from the same full CI run, without rebuilding them.
6. A separate job uploads the verified files to PyPI through Trusted Publishing; a final
   job installs the exact version from the public index and checks packaged resources.

Releases reuse CI artifacts without rerunning the test matrix or rebuilding packages.
The latest `ci.yml` run for the tagged SHA from
a push to `master` or a manual run on `master` must finish successfully, including
**CI ready** and **Release ready**. PR checks remain selective for merges; publication
requires the full result from `master`. An older green run cannot hide a newer failed,
cancelled or unfinished run. PR runs and runs from other branches cannot authorize
releases. Wait for the automatic full run before tagging, while `master` still points
to the release commit; any subsequent commit needs its own validation. Manual full CI
remains available for retries and is optional in the normal release flow.

Missing or expired `quite-admin-docs` or `quite-admin-distributions` artifacts block
the release. Retry the existing CI run for the release commit to regenerate them, or
start full CI on `master` while it still points to that SHA. Pages publishes the tagged
version even if `master` has advanced, using the documentation artifact from the same
full run without rebuilding it or repeating demo tests. PyPI checks the same
full-validation gate and distribution artifact on automatic and manual uploads,
without requiring the documentation artifact again.

Documentation-only updates do not require a package version bump, tag or release. Push them
to `master` and wait for full CI: `pages.yml` also accepts a successful `ci` completion
when that exact commit remains the master head. The deployment guard checks its full
diff from the latest published release, including deleted files and both paths of
renames. Only `docs/`, README, repository instructions and the explicitly listed
screenshot and documentation-deployment tooling may differ. Runtime code, the demo,
package metadata, dependencies or other tooling require the normal release flow.
The commit must descend from the published tag; missing history or release metadata
blocks deployment. Pages downloads the documentation artifact from the latest exact-SHA
full master CI after **CI ready** and **Release ready** succeed. It does not rebuild
the site, move the published tag or upload another package to PyPI.

Creating a release in GitHub's interface uses the same existing-CI gate before Pages
and PyPI publication. The package workflow checks out the validated commit by SHA,
checks master CI and its distribution artifact again for automatic and manual uploads,
and verifies that the published version tag still points to that exact commit. It
downloads `quite-admin-distributions` from that CI run and passes the same files as
`pypi-distributions` to the isolated Trusted Publishing job.

GitHub release downloads remain the automatic source-code ZIP/tar.gz archives.
Wheel/sdist files go to PyPI, not GitHub release assets. A dedicated full-CI job builds
one pair, runs strict Twine checks and checks clean installations, packaged resources
and FastAPI/Litestar mounting with `scripts/check_distributions.py`. Python test matrix
jobs do not build packages. Both distributions explicitly use core metadata **2.4**;
checks reject a different metadata version.

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
commit and require its distribution artifact; they do not need the documentation
artifact again. Existing package files are skipped on retry; PyPI versions cannot
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

`security.yml` runs Python `pip-audit` and documentation `npm audit` after every branch
push, on full manual runs and weekly. PRs select audits for the affected dependency
ecosystems. Python checks cover all locked extras/dev groups; npm reports all severities
and fails on high/critical findings. Public PRs that select security checks also use
[GitHub Dependency Review](https://github.com/actions/dependency-review-action).
Network/advisory service errors fail checks. No blanket advisory ignores are configured.
See `SECURITY.md` for private reporting and the early-release maintenance policy.

Documentation tooling pins transitive dependencies through `package-lock.json` and
`package.json` overrides. `scripts/diplodoc.cjs` handles CommonJS/ESM interop on Node 24.
Strict EN/RU builds and fresh security audits validate that environment.

## Required checks and artifacts

`ci.yml` runs the complete Python, documentation, JavaScript, browser, database,
dependency-compatibility, security and distribution workflows on every push to any
branch. Optional manual runs also include all groups. Version-tag pushes use the publication workflows
and do not duplicate CI. Every CI run checks release metadata without installing
dependencies. For pull requests, checks are selected from the Git diff and reported
in the run summary:

| Changed files in a PR | Selected checks |
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

Mixed PR changes select the union of their checks. PRs compare the head to its merge
base with the target branch; deleted files and both paths of a rename count. An
unavailable comparison runs all checks. Branch pushes always use full validation,
regardless of the changed paths. Weekly security scans continue auditing both ecosystems
even without dependency changes.

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
the source checkout; the dedicated distribution job verifies the wheel/sdist pair.
Both **CI ready** and full **Release ready** require its success when selected.
Documentation and distribution artifacts remain separate from GitHub release assets.

WebKit runs on macOS. Playwright's Linux WebKit build currently renders text attachments
inline despite a valid Content-Disposition header
([upstream issue](https://github.com/microsoft/playwright/issues/43763)); macOS lets the
suite assert real CSV and XLSX download events without replacing response headers.

Pages deploys after the `release` workflow succeeds and rechecks full CI for the
released SHA. Successful full master CI can also publish documentation-only changes
under the guard above. PRs, other branches and commits containing unreleased package
changes do not deploy the site through that route.
