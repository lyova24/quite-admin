# Releases and compatibility policy

The current planned release is **0.2.0**, not yet published. Its changes are recorded in
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

The 2026-10-29 local audit found no known Python vulnerabilities. npm overrides update
js-yaml 4.x, lodash, linkify-it and markdown-it to patched versions. Diplodoc 5.64 still
imports legacy markdown-it CommonJS internals; `scripts/diplodoc.cjs` adapts those module
paths to markdown-it 14's ESM exports on Node 24. The wrapper is confined to docs builds;
it does not change parser behavior or suppress advisory checks. A fresh strict EN/RU
build verifies compatibility. Eight moderate affected npm packages remain in the
documentation toolchain; no high/critical findings remain. Review the audit output and
remove overrides/interop when upstream supports the patched dependency directly.
