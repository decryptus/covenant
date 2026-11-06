# Covenant 1.0.0rc1

This release candidate adds startup migration warnings for HTTP, Redis and TLS
endpoints that implicitly permit caller-selected destinations. Each affected
endpoint emits one warning naming the endpoint and the available settings.
A fixed destination or an explicit allow policy needs no migration warning.

The RC keeps the existing destination behavior. Stable 1.0.0 will use an
empty default allow list. Review the [migration guide](migration-1.0.md) and
declare endpoint policies before upgrading to stable. Review of the stable
release is planned for 6 December 2026, subject to tests and migration feedback.

Install explicitly with `pip install covenant==1.0.0rc1` or use
`decryptus/covenant:1.0.0rc1`. The existing shared allow and deny imports
and exclusion precedence are supported.
