# Covenant 0.0.73

## Before upgrading authenticated dynamic HTTP probes

If your HTTP probe accepts a caller-supplied target and uses Basic auth, custom
headers or a client certificate, configure its allowed destinations before you
upgrade. With an absent or empty list, Covenant probes dynamic targets
anonymously. Services that require authentication may then report a failed probe.

Inside the target's existing `config` block, add an exact origin or import a shared
YAML list. Inline rules and imported rules can be combined.

```yaml
config:
  import_credential_targets: rules/monitoring.yml
  credential_targets:
    - 'https://api.example.org'
```

Paths are relative to the main configuration. Put rules such as
`- 'https://*.services.example.org'` in the shared file and restart Covenant
after changes. A missing or invalid file prevents startup.

Covenant checks each redirect against the policy. A single quoted `'*'` as the
entire rule list permits every HTTP(S) destination, so a caller can direct this
probe's credentials to a server they control. Fixed URLs with no credential
policy keep their previous behavior. These rules apply only to the HTTP plugin.

See the [configuration examples](../README.md#credentials-for-dynamic-http-probes)
for hostname regexes and IP networks. Install `covenant==0.0.73` or use the
Docker image `decryptus/covenant:0.0.73`.
