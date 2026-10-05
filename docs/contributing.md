# Contributor documentation

This guide is for people changing or maintaining covenant. For installation, configuration and everyday use, start with the [user documentation](https://github.com/decryptus/covenant/blob/master/README.md).

## Tests

See [tests/README.md](https://github.com/decryptus/covenant/blob/master/tests/README.md) for local test setup and coverage.

The container checks include a jq expression, the collected unittest suite covering collectors, templates, runtime integration
and CertLord observations, the installed package version and CLI startup. They do not replace a full
integration test against your real services.

## Documentation rules

Keep user instructions and contributor material separate. The repository [engineering requirements](https://github.com/decryptus/covenant/blob/master/AGENTS.md) define the review and validation rules. Preserve user-facing compatibility, security and recovery guidance when moving internal explanations.
