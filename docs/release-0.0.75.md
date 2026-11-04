# Covenant 0.0.75

## Before upgrading

**Authenticated dynamic Redis targets.** Declare the origins that should receive
the probe's configured credentials. For example, with the shipped Redis template:

```yaml
vars:
  credential_targets:
    - 'rediss://*.cache.example.org:6380'
```

A missing or empty list probes the requested Redis server anonymously. If that
server requires authentication, the scrape can report a failed upstream.
Rules match the scheme, host and port. An unmatched destination receives neither
the configured Redis login nor a client certificate. To share rules, set
`import_credential_targets` to a YAML list file relative to the main config.
For inline probes or metrics, put these settings in the target's `config`.

Dynamic URLs accept a host, port and numeric database path such as `/0`.
Move URL query options into trusted configuration before upgrading. Use fixed
configuration for Unix sockets and URLs with user information. A configured
fixed URL keeps precedence over the caller's target. See the
[Redis configuration examples](../README.md#credentials-for-dynamic-redis-targets).

**Remote Prometheus.** Native Covenant now listens on `127.0.0.1` when
`general.listen_addr` is omitted or null. Existing explicit addresses retain
precedence over this default. For a remote scraper, configure the private
monitoring address and restrict inbound access to the intended clients.

Both Compose examples now publish port 9118 on host loopback. Containers on the
same Docker network can still scrape `covenant:9118`. For a scraper on another
machine, set the host-side port mapping to the private monitoring address.

Install `covenant==0.0.75` or use `decryptus/covenant:0.0.75`.
