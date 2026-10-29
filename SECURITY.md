# Security reporting

Report suspected vulnerabilities privately to [the maintainer](mailto:lengthylyova@gmail.com).
Include the affected version, a minimal reproduction and the impact. Avoid public issues
containing credentials, private records or an exploit against someone else's application.

The active unreleased line is 0.2.x. This early project does not promise a separate
long-term maintenance branch. Security fixes and any required migration are documented
in CHANGELOG.md and the English/Russian documentation.

Dependency checks run on pushes, pull requests and weekly. Python audits cover the
locked runtime, extras and development groups; npm audits cover documentation tooling.
An unavailable advisory service fails the check instead of reporting a clean audit.
Public-repository pull requests also use GitHub Dependency Review.

Applications remain responsible for identity revalidation, tenant scoping, service rules,
database privileges and reviewing discovered fields. See `docs/en/data-safety.md` and
`docs/en/extensions.md` for transaction and audit boundaries.
