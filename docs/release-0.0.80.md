# Covenant 0.0.80

A network endpoint can now restrict where a caller-supplied `target` can
connect. Set `allowed_targets` next to `plugin`. For example, the following
TLS probe accepts the certificate service on port 443:

```yaml
endpoints:
  certificate:
    plugin: ssl
    allowed_targets: ['tls://example.com:443']
    vars:
      timeout: 5
    import_probes: probes.d/secure-layer.yml
```

An omitted list preserves existing configurations. An empty list disables
caller-selected destinations on the endpoint. A fixed URL or URI still takes
precedence. HTTP checks each redirected destination for dynamic requests.
Credential forwarding remains subject to the separate `credential_targets`
rules. Upgrade all instances serving the endpoint before relying on this option.
