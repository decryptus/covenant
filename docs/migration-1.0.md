# Migrating dynamic network targets to 1.0

Covenant 1.0.0rc1 keeps the 0.0.83 destination behavior and warns once at
startup for each HTTP, Redis or TLS endpoint with an enabled dynamic target
and no explicit allow policy. Fixed URLs and URIs take precedence over caller
input. Disabled targets are excluded from the migration warning.

## Declare the allowed destinations

Put the policy on the endpoint alongside `plugin`:

```yaml
endpoints:
  certificate:
    plugin: ssl
    allowed_targets: ['tls://example.com:443']
    import_probes: probes.d/secure-layer.yml
```

For HTTP use `http://` or `https://`, for Redis use `redis://` or `rediss://`.
TLS rules always use `tls://` and the socket destination's effective port.
Set `allowed_targets: []` to reject all caller-selected destinations.

Shared and local lists are combined at startup:

```yaml
endpoints:
  certificates:
    plugin: ssl
    import_allowed_targets: rules/tls-allowed.yml
    allowed_targets: ['tls://status.example.net:443']
    import_disallowed_targets: rules/tls-disallowed.yml
    disallowed_targets: ['tls://legacy.example.net:443']
    import_probes: probes.d/secure-layer.yml
```

Each imported file is a plain YAML list. Paths are relative to the main
configuration directory. Exact origins, single-label wildcards, hostname
regexes and literal IP CIDRs are supported. Exclusions take priority,
including on dynamic HTTP redirects. Restart Covenant after editing a policy.
An empty imported allow list explicitly blocks every dynamic destination.

## Explicitly retain free target selection

If callers should choose any destination, declare `allowed_targets: ['*']`.
This grants network access from Covenant's host. Existing exclusions still
apply. A deny-only policy needs this explicit allow rule before upgrading to
stable 1.0.0, otherwise every dynamic destination will be rejected.

Credential forwarding is controlled separately by `credential_targets`.
An approved credential destination also needs network permission under the
endpoint's `allowed_targets` policy.

## Validate the migration

Restart with the RC and review warnings naming affected endpoints. Check both
an approved destination and a destination outside the allow list. Rejected
collections use the endpoint's configured failure metrics. Keep those metrics
in your checks alongside Prometheus scrape availability.

Stable 1.0.0 is planned for review on 6 December 2026. Its default allow list
will be empty. The RC retains the compatible default while operators declare
their policies. Publication of stable depends on tests and migration feedback.
