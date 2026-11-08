# quite-admin

- Support Python 3.11–3.15, FastAPI and Litestar. Keep the core ORM-independent; access data through adapters.
- Preserve authentication, authorization, CSRF, field restrictions and CSP. Never log passwords, tokens or record values.
- Document user-facing changes in both languages using the documentation rules below.
- Verify changed behavior with integration tests. Do not suppress dependency warnings.
- Python checks: `uv run pytest -q`, `uv run ruff check src tests examples scripts`, `uv run ruff format --check src tests examples scripts`.

## Documentation

### Structure and page placement

- Keep `docs/en` as the primary source and `docs/ru` as its complete translation. Both languages must have the same page paths and TOC order; translate navigation labels as well as content.
- Preserve Overview followed by these top-level sections in this order. Add feature documentation inside the appropriate existing section; changing the hierarchy belongs to a dedicated documentation-reorganization task.

| EN / RU section | Content and existing entry points |
| --- | --- |
| Getting started / Начало работы | First runnable application (`first-app.md`), existing-app setup (`quickstart.md`), browser demo and interface tour. |
| Integrations / Интеграции | Framework mounting, native ORM adapters and SQL reflection (`integration.md`, `gino.md`). |
| User guide / Руководство пользователя | Collections and fields, filters/search, relationships, exports and database schema. |
| Customization / Настройка и расширение | Appearance, styles, pages/templates, field controls, hooks/actions/services and custom data adapters. |
| Deployment / Развёртывание | Deployment setup, authentication/permissions, persistent storage/history and logging. |
| Reference / Справочник | Database and dependency compatibility, public API guarantees, architecture and contracts. |
| Contributing / Разработка библиотеки | Repository development, checks, release tooling and publishing policy. |

- Extend the relevant existing guide first. Create a page only for a distinct task that needs its own guide; add its EN/RU files and both `toc.yaml` entries together in the same section and order. Every page must be reachable from navigation.
- Keep existing page filenames, public URLs and linked heading anchors stable. Do not move, rename or delete pages as a side effect of adding a feature. Intentional URL changes need compatibility redirects and updates to inbound links in both languages.
- Keep the three entry paths on `index.md`: try the browser demo, run `first-app.md`, or connect an existing app through `quickstart.md`. Keep those pages and README focused on first use; place advanced configuration, compatibility matrices and contributor tooling in their guides instead of expanding onboarding with every feature.

### Content, links and assets

- Describe a user task, its prerequisites, a minimal working example and the expected result. Match actual public APIs, defaults and tested adapter/database support; explain material limitations where the user encounters them. Link to one canonical guide instead of duplicating detailed instructions across pages.
- Keep runnable examples synchronized with their EN/RU instructions and verify changed example behavior with integration tests. Use fictional local data; distinguish local HTTP settings from deployment settings and browser-only demonstrations from the real Python application.
- Use relative `.md` links inside Diplodoc so local builds and both languages work. In README, use full HTTPS URLs for documentation (`https://lyova24.github.io/quite-admin/en/<page>.html` or the RU equivalent), repository files and images; repository-relative file links break on PyPI.
- Use shared static screenshots under `docs/assets/screenshots/`. Promotional videos and animated previews are currently excluded; do not reintroduce them unless requested. Do not link to local paths, temporary files or generated `build/` output from published content.

### Verification

- Run `npm run docs:build` after documentation changes. Its strict build and `scripts/check-docs.mjs` must pass, including EN/RU page coverage, matching navigation order, internal links and README portability to PyPI. Fix the sources rather than weakening these checks.
- When navigation or onboarding changes, inspect the rendered EN/RU pages and follow the entry links. Ensure existing public paths remain available and new pages/assets are included in the generated site.
- Documentation-only updates do not require a library version bump or publication; follow the versioning policy below.

## Versioning

- Use PEP 440-compatible `MAJOR.MINOR.PATCH` versions.
- `PATCH`: backward-compatible bug fixes, security fixes and runtime dependency fixes.
- `MINOR`: new features, options and adapters that preserve existing default behavior.
- `MAJOR`: incompatible public API or behavior changes, feature removal, or dropping Python / framework / ORM support. Before `1.0`, bump `MINOR` for these changes; moving to `1.0` requires a separate decision about API stability.
- Reset `MINOR` and `PATCH` when bumping `MAJOR`; reset `PATCH` when bumping `MINOR`.
- Documentation-only changes, tests, behavior-preserving refactoring and development tooling updates do not require a library version bump. A dependency upgrade alone does not imply `MAJOR`: assess the library's compatibility.
- Plan the version relative to the latest released version, choosing the highest applicable bump. If there is no release, use the previous recorded version. Bump once per batch of changes; the latest finalized release is `0.8.1` (2026-11-06); subsequent changes must target a higher version using the rules above. Keep the version visible in README and record changes in CHANGELOG.md.
- The source of truth is `project.version` in `pyproject.toml`. Update `src/quite_admin/__init__.py::__version__` in sync and regenerate `uv.lock` with `uv lock`; check version references in the UI and documentation.
- Every version-changing commit must update `pyproject.toml`, README, `__version__` and `uv.lock` together. Never change only the displayed README version; verify that all library version references agree before committing.
- `package.json` and `package-lock.json` belong to documentation tooling and need not match the Python package version. Update lockfiles through their package managers.
- Document breaking changes and migration steps in EN/RU. Create release tags and publish only when explicitly requested by the user.
- Preserve the public API baseline in `api/*-0.4.json`; run `python scripts/check_api.py --profile modern`. Keep required adapter methods separate from optional capabilities and preserve template API 1. See `docs/en/api-stability.md` for deprecation and migration rules.
- Run `python scripts/check_release.py` before a version/release commit; finalize the changelog date before tagging. Tagged releases use `.github/workflows/release.yml`; version updates alone never publish.
- GitHub releases retain only automatic source archives. A version-tag push requires the latest master-push `ci.yml` run for the exact tagged SHA to have succeeded, including `CI ready`; releases never rerun the test matrix. After the release workflow succeeds, `pages.yml` publishes that run's `quite-admin-docs` artifact. Keep Pages on `workflow_run` so deployment uses the default branch permitted by the `github-pages` environment, while the artifact matches the release SHA. Missing/unfinished/unsuccessful CI or an unavailable documentation artifact blocks the release. The separate `pypi.yml` workflow rechecks the same CI gate for automatic and manual uploads, builds one wheel/sdist pair, validates metadata 2.4 and clean installations, and publishes to PyPI through the `pypi` environment and Trusted Publishing. Never build packages in each Python matrix entry or store a PyPI API token in the repository.
