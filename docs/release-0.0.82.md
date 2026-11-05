# Covenant 0.0.82

HTTP, Redis and TLS endpoints can combine `allowed_targets` with
`import_allowed_targets`, `disallowed_targets` and `import_disallowed_targets`.
Set the fields on each endpoint that uses the policy. Both imports take a
path to a plain YAML list and accept the same origin, wildcard, regex and
CIDR rules as the inline lists. Mount the rule files alongside the main
configuration when running Covenant in Docker.

Matching an exclusion blocks a caller-supplied destination, including a
dynamic HTTP redirect. An explicit empty allow list with no imported
entries blocks all dynamic destinations. With only a deny list, all other
destinations are eligible. Hostname rules rely on DNS; literal CIDR rules
do not resolve names. Fixed configured destinations keep their existing
behavior and credential forwarding uses its own policy.

Upgrade every instance serving the endpoint before enabling the new fields.
