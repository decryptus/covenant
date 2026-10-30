# Complete Monit-Docker and CertLord observations

The optional `monit_observation` and `certlord_observation` plugins export complete
allowlisted JSON inventories for Atraxis through Prometheus. They read `/v1/status`
and `/api/certificates/observations`, respectively. Existing `http` and `certlord`
plugins, configurations and metric output keep their existing behavior.

```yaml
endpoints:
  containers:
    plugin: monit_observation
    metrics:
      - name: monit
        config:
          url: https://monit.example.org/v1/status
          username: covenant-reader
          password_file: secrets/monit-read.password
          timeout: 10
        collects: []
  certificates:
    plugin: certlord_observation
    metrics:
      - name: certlord
        config:
          url: https://certlord.example.org/api/certificates/observations
          username: covenant-reader
          password_file: secrets/certlord-read.password
          timeout: 10
        collects: []
```

Set `general.result_timeout` above twice the source timeout. Use exactly one metric
target with no custom `collects` or dynamic destination. Credentials and optional
`ca_file` resolve relative to the configuration directory. Token-file authentication
is also supported; do not combine it with username/password authentication. Remote
sources require HTTPS and explicit read credentials. Literal loopback IPs permit
HTTP for local tests. TLS is verified; redirects, environment proxies and ambient
netrc credentials are not used. Each read has a finite network/time/size budget.

One response becomes a fresh registry with `covenant_monit_observation_*` or
`covenant_certlord_observation_*` families: typed field values, schema/count/content
digest manifest, collection time, HTTP duration and `up`. Source read/serialization
failure emits only the corresponding `up=0`, without cached fields. `up=1` means a
complete allowlisted response was exported; the consuming native parser still
validates source readiness, schema, identity and freshness. It is not a health claim.

The schema preserves every field consumed by Atraxis's native inventory adapters:
Monit source metadata/action counters, containers and filesystems; CertLord domains,
UUIDs, versions, fingerprints, dates, lifecycle/retry fields and full stored TLS
evidence. Missing values stay null. Large integers retain exact decimal values.
Unknown source keys, PEM material and action/audit details are not exported.

For Prometheus use `honor_timestamps: false`, preserve every observation family and
its labels, and keep one upstream source per target. Protect the exporter and its
inventory labels. The complete contract is for reconstruction, not a replacement
for the existing conventional numeric CertLord metrics used by alert rules.
See Atraxis's [Monit guide](https://github.com/decryptus/atraxis/blob/main/docs/prometheus-monit.md)
and [CertLord guide](https://github.com/decryptus/atraxis/blob/main/docs/prometheus-certlord.md)
for consumer configuration.

Limits are 4 MiB per source response and generated exposition, 10,000 typed field
rows, 10,000 list members and 4,096 characters per string. Overflow rejects the
whole snapshot. Text timestamps and digests create new label generations: size
retention/cardinality for your inventory and scrape rate before deployment. The
consumer uses instant queries to exclude old generations from reconstruction;
Prometheus storage still retains them. Clocks must be synchronized within the
consumer's configured clock-skew budget. Python 3.8+ is required for these plugins.
