<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/svg/logo-horizontal-dark.svg">
    <img src="assets/brand/svg/logo-horizontal.svg" alt="Covenant" width="520">
  </picture>
</p>

# Covenant

**Turn HTTP APIs, Redis data, TLS certificates and file checks into Prometheus
metrics using YAML configuration.**

Covenant is a configurable, multi-endpoint Prometheus exporter. It separates data
collection from transformation and metric exposition, so you can adapt a source
without writing a separate exporter for every service.

Prometheus evaluates alert rules; Alertmanager handles notification delivery,
grouping and silences. Covenant does not implement a notification engine.

The optional [CertLord collector](docs/certlord.md) exposes validated certificate
observations, with sample Prometheus rules for expiry, retries and source freshness.
It requires Python 3.8+ and is included from Covenant 0.0.71.

## Why Covenant?

Your internal API already knows how many orders are waiting, how many workers are
active or whether a background task completed. Covenant can extract those values
and expose them to Prometheus.

It is useful for internal services and unusual data sources, particularly when you
need several custom exporters with similar collection logic. Dedicated exporters
remain a good choice when they already cover your service. For complicated business
logic, a small purpose-built exporter may be easier to maintain than a long chain
of configuration filters.

## Quickstart: a JSON API to Prometheus metrics

This repository includes a local example with a small HTTP server and Covenant.
It needs Docker with Compose and does not require Nginx, Redis or an external API.

```sh
git clone https://github.com/decryptus/covenant.git
cd covenant
docker compose -f examples/quickstart/compose.yml up -d
curl --fail http://localhost:9118/metrics/orders
```

The [source JSON](examples/quickstart/data/status.json) contains:

```json
{"orders":{"pending":12},"workers":{"active":3}}
```

The output includes these samples, along with Prometheus HELP and TYPE lines:

```text
orders_source_up 1.0
orders_pending 12.0
orders_workers_active 3.0
```

Edit `examples/quickstart/data/status.json`, then call the endpoint again to see the
new values. Collection happens when the endpoint is scraped.

The example pins `decryptus/covenant:0.0.76` and exposes port 9118 only on the local
host. If the first request arrives before the API is ready, retry it.

```sh
# Inspect logs or stop the example.
docker compose -f examples/quickstart/compose.yml logs covenant
docker compose -f examples/quickstart/compose.yml down
```

## Listener and Prometheus access

HTTPdis 0.6.36 denies cross-origin browser preflights by default. A browser
dashboard can reach Covenant through a same-origin reverse proxy. Prometheus
scrapes and direct API clients require no CORS configuration.

A native Covenant process defaults to `127.0.0.1` when `general.listen_addr`
is omitted or null. An explicit YAML address takes precedence over the default,
and `--listen-addr` overrides YAML. If Prometheus runs on a different machine,
set `general.listen_addr` to the exporter's private monitoring address and
restrict inbound access to the intended scrapers.

Both Compose examples publish `127.0.0.1:9118:9118` on the host. Covenant
listens on `0.0.0.0` **inside the container** so Prometheus on the same Docker
network can scrape `covenant:9118`. Other containers on that network can also
reach the unauthenticated routes. For a remote Prometheus, replace the host
loopback in the port mapping with the host's private monitoring address.

## Service identity and startup

When launched by root, Covenant requires an existing service user and group
(default: `covenant`). The Docker image and Debian package provide both. For a
custom installation, create the account or select existing names with `-u` and
`-g` or `COVENANT_USER` and `COVENANT_GROUP`. Explicit unknown names stop
startup. A non-root launch defaults to its current user and group. Ensure its PID and log directories are writable.

Before starting collectors as the service user, a root launcher switches its
supplementary groups to that account's memberships. Give the service account
access to any files it must probe. In detached mode the launcher waits for the
HTTP listener to enter its serving loop. Startup errors return a nonzero status
in both detached and foreground (`-f`) mode.

## How it works

1. A client requests `/metrics/<endpoint>` or `/probe/<endpoint>`.
2. The endpoint's plugin reads its configured source or sources.
3. Filters extract and transform values and labels.
4. Collectors update a dedicated registry and return Prometheus text.

| Configuration term | Meaning |
| --- | --- |
| Endpoint | A named collection exposed through an HTTP route, such as `orders` |
| Plugin | The source adapter: `http`, `redis`, `ssl` or `filestat` |
| Target | A collection definition with a `name`, source `config` and `collects` |
| `value_tasks` | An ordered list of transformations applied to a metric value |
| Labels | Static or extracted dimensions attached to metrics |
| Template | An imported YAML/Mako file parameterized through endpoint `vars` |

An endpoint defines either metrics or probes, not both. The shipped module files
provide the routes; `/probe/` and `/probes/` are both accepted for probes.

## Define your own API metrics

Here is the endpoint section from the quickstart, reduced to one metric. Place it
under the `endpoints` mapping in your configuration:

```yaml
orders:
  plugin: http
  metrics:
    - name: status
      config:
        url: http://api:8000/status.json
        format: json
        timeout: 2
      collects:
        - orders_pending:
            type: gauge
            documentation: Orders waiting to be processed.
            value_tasks:
              - '@filter': jmespath
                expression: orders.pending
```

See the [complete configuration](examples/quickstart/covenant.yml), including
`general` and module imports. Change the URL and JMESPath expression to match your
API. The HTTP plugin expects HTTP **200** and decodes JSON when `format: json` is
set. In Docker, `localhost` means the Covenant container; use a reachable hostname
or a Compose service name for other services.

Filters can be chained. For example, extract a string value and convert it:

```yaml
value_tasks:
  - '@filter': jmespath
    expression: orders.pending
  - '@filter': builtins
    func: float
```

Other filters cover regular expressions, jq, built-in types, math, time and file
paths. See [the filter implementations](covenant/filters) and the shipped templates
for their accepted arguments.

### Choose metric types deliberately

A gauge represents a current value, such as queue length. Covenant's `counter`
uses `inc`: it adds the supplied value at each collection. Do not feed an API's
already cumulative total into a normal counter, or each scrape will add it again.
The code also provides `const_counter` for setting a source-supplied counter value;
see [metric types](covenant/classes/metrictypes.py).

### Distinguish failure, missing data and zero

- `on_fail` handles a failed source collection.
- `on_noresult` handles an absent result from a transformation.
- By default, affected collectors are removed from exposition. You can configure a
  replacement value when it has a clear meaning.

For example, a source availability gauge can use:

```yaml
orders_source_up:
  type: gauge
  documentation: Whether the source API request succeeded.
  value: 1
  on_fail:
    value: 0
```

For business metrics such as queue length, a missing field is not necessarily zero.
Only add `on_noresult: {value: 0}` if zero is the intended meaning. A successful
HTTP request also does not prove every expected field exists.

## Reuse the shipped templates

| Source | Plugin | Template | Source requirements |
| --- | --- | --- | --- |
| Apache | `http` | [apache.yml](etc/covenant/metrics.d/apache.yml) | Accessible server-status endpoint |
| Nginx | `http` | [nginx.yml](etc/covenant/metrics.d/nginx.yml) | `/nginx_status`; optional `/nginx_version` |
| RabbitMQ | `http` | [rabbitmq.yml](etc/covenant/metrics.d/rabbitmq.yml) | Management HTTP API and appropriate credentials |
| Redis | `redis` | [redis.yml](etc/covenant/metrics.d/redis.yml) | Reachable Redis instance |
| TLS | `ssl` | [secure-layer.yml](etc/covenant/probes.d/secure-layer.yml) | Reachable TLS target |
| File existence | `filestat` | [file.yml](etc/covenant/probes.d/file.yml) | File visible to the Covenant process |

### Nginx

Add this endpoint alongside your existing endpoints:

```yaml
nginx1:
  plugin: http
  vars:
    url: http://nginx:8080
    timeout: 2
    version_enabled: false
  import_metrics: metrics.d/nginx.yml
```

Expose Nginx's status page at `/nginx_status`. `version_enabled: false` disables the
separate `/nginx_version` request, which a standard Nginx installation does not
provide automatically.

```sh
curl --fail http://localhost:9118/metrics/nginx1
```

This template exposes connection counts, connection-state labels, a source `up`
gauge and a scrape-failure counter.

### TLS probe

```yaml
secure-layer1:
  plugin: ssl
  vars:
    timeout: 10
  import_probes: probes.d/secure-layer.yml
```

```sh
curl --get --fail http://localhost:9118/probe/secure-layer1 \
  --data-urlencode 'target=https://example.com'
```

The template includes connection/probe success and certificate validity metrics.

### File existence probe

```yaml
application-file:
  plugin: filestat
  vars:
    state_include_paths:
      - '^/watched/app\.pid$'
  import_probes: probes.d/file.yml
```

```sh
curl --get --fail http://localhost:9118/probe/application-file \
  --data-urlencode 'target=/watched/app.pid'
```

In Docker, mount the required host directory read-only at `/watched`. This tests
file existence; a PID file's presence does not prove its process is running.

When `state_include_paths` or `state_exclude_paths` is set, supply normalized
paths (for example, `/watched/app.pid`). Covenant checks the requested name,
the name after resolving parent directories, and the destination of a symlink.
Every name must pass the inclusion rules and exclusions take precedence.
This also applies with `state_follow: false`, because link metrics include
the destination and its access permissions. An allowed missing file reports
absence. The shipped template reports `file_exists 0` for a denied probe.

To share file rules, opt in per endpoint using the shipped template:

```yaml
application-file:
  plugin: filestat
  import_probes: probes.d/file.yml
  import_state_include_paths: rules/files-allowed.yml
  import_state_exclude_paths: rules/files-denied.yml
  vars:
    state_include_paths: ['^/srv/monapp/ready$']
    state_exclude_paths: ['^/watched/maintenance/']
```

To try this with the repository's Compose example, uncomment `application-file`
in [covenant.yml.example](etc/covenant/covenant.yml.example). Compose mounts
the [allowed paths](etc/covenant/rules/files-allowed.yml) and
[excluded paths](etc/covenant/rules/files-denied.yml) read-only. Each file
contains a YAML list of regular expressions. Mount the directory to probe
at `/watched` so its files are visible to Covenant.

Both imports are optional. Paths are relative to the main configuration.
Covenant combines each imported list with its endpoint's local rules at startup.
An exclusion always wins, even over a local inclusion. Restart after edits.
An unreadable or invalid import prevents startup, as does an imported inclusion
list with no rules after merging. The same endpoint directives apply to inline
probes or metrics, combining with each target's `config.include_paths` and
`config.exclude_paths`.

For a directory alias, allow both spellings of the intended file. For example,
`^/(var/)?run/sshd[.]pid$` supports both `/var/run/sshd.pid` and
`/run/sshd.pid`. Existing rules that cover only the alias need updating.
Use administrator-controlled directories for filtered probes. On systems
without Linux path descriptors and procfs, file inspection uses pathname lookups.

Template paths are resolved relative to the main configuration directory. The
Docker image already includes `modules`, `metrics.d` and `probes.d` under
`/etc/covenant`. Mounting an entire directory there hides those bundled files;
include them in your mount or mount only the main configuration, as in the demo.

## Connect Prometheus

For a fixed endpoint, add a scrape job to your Prometheus configuration:

```yaml
scrape_configs:
  - job_name: covenant-orders
    scrape_interval: 30s
    scrape_timeout: 10s
    metrics_path: /metrics/orders
    static_configs:
      - targets: ['covenant:9118']
```

Here `covenant:9118` must be reachable **from Prometheus**. It works as a service
name when the containers share a Docker network. For Prometheus running directly
on the demo host, use `localhost:9118` instead.

For one dynamic TLS target:

```yaml
scrape_configs:
  - job_name: covenant-tls
    scrape_interval: 60s
    scrape_timeout: 15s
    metrics_path: /probe/secure-layer1
    params:
      target: ['https://example.com']
    static_configs:
      - targets: ['covenant:9118']
```

Enable the corresponding endpoint in Covenant before scraping it. Prometheus's
own `up` metric describes its scrape of Covenant; source availability is reported
by the metrics you configure inside Covenant.

## Run and configure Covenant

### Collection deadlines

Set a finite result wait in the main YAML configuration:

```yaml
general:
  result_timeout: 30
```

`result_timeout` is expressed in seconds and defaults to **30** when omitted,
so existing configurations remain valid. Positive fractional values are accepted;
zero, negative, boolean, null, non-finite and platform-overflow values are rejected
at startup. This applies to both metric and probe requests, including time spent
waiting in the endpoint queue. An expired wait returns **HTTP 504**. Unknown endpoints
return 404. Invalid query parameters and endpoint-type mismatches return 400.
Unexpected failures on metric, probe and server routes return a generic 500.
A plugin that successfully reports upstream failure through a metric can still
return a valid scrape with that metric set to zero. `lock_timeout` separately bounds acquisition of the module lock.

The deadline bounds the client's result wait; it does **not** interrupt a running
plugin, cancel backend I/O, or remove an already queued job. Keep backend timeouts
configured. The endpoint queues remain unbounded; this setting is not queue
backpressure. Late callbacks are ignored, and completed/expired waits retain no
result in a module-level dictionary. Collections that previously took more than
30 seconds now time out unless a larger value is configured. Set the Prometheus
scrape timeout and backend timeouts consistently with this budget.

Collection dispatch, correlation and completion live in `CollectionService`,
which accepts endpoint queues and the existing plugin job factory. It consumes
plain parameters and returns results or domain exceptions, with no HTTP, CLI or
TUI imports. HTTP modules validate requests and map these exceptions to responses.
The `CovenantEPTObject` callback contract, plugin hooks, endpoint registries,
routes, and metric names/labels are preserved. Historical module methods
`_push_epts_sync(endpoint, method, params, args=None)`, `_set_result(obj)` and
`_get_result(uid)` remain available as compatibility facades. HTTP handlers still
call them, so subclass overrides continue to participate. Submission returns the
UID; retrieval preserves the `{'error': ..., 'result': ...}` shape, including
plugin errors, and expiration raises HTTP 504.

`results` is now a synchronized mapping view of completed, unconsumed jobs.
Lookup, membership, iteration, copy, pop and assignment for an active UID are
supported. It is not a concrete `dict`; replacing the attribute or depending on
its exact type is not supported. Expired, consumed and unknown callbacks/writes
are ignored, so they cannot recreate orphaned results. Unlike the old dictionary,
unconsumed results expire too. A finite deadline starts at submission; delaying
`_get_result` does not reset it. One active expiry worker per module cleans up
abandoned calls, is reused across adjacent calls, and exits when idle. New callers
should use the service API; these methods are retained for transition without a
scheduled removal.


Docker is the simplest way to use the tested runtime. To run your own configuration:

```sh
docker run --rm --name covenant \
  -p 127.0.0.1:9118:9118 \
  -v "$PWD/covenant.yml:/etc/covenant/covenant.yml:ro" \
  decryptus/covenant:0.0.76
```

For this bridge-network command, set `general.listen_addr: 0.0.0.0` in the
mounted YAML so the published port can reach the container.

For a Python installation, `pip install covenant` installs the version published
on PyPI, which may differ from GitHub or Docker Hub. Installing from the repository
requires its dependencies and native build tools; the [Dockerfile](Dockerfile)
provides the working build recipe.

```sh
# Foreground, with an explicit configuration.
covenant -f -c /etc/covenant/covenant.yml

# Daemon mode, with writable PID and log locations.
covenant -c /etc/covenant/covenant.yml \
  -p /tmp/covenant.pid --logfile /tmp/covenant.log

# Foreground debug logging.
covenant -f -l debug -c /etc/covenant/covenant.yml
```

The current Docker image uses Python 3.11. Do not assume Python 3.12+ compatibility:
legacy dependencies import `imp` and `asyncore`, removed in Python 3.12.

### Timeouts and access

The network templates expose `vars.timeout`. HTTP and TLS use a source `timeout`.
The Redis template sets `socket_timeout` and `socket_connect_timeout`.
HTTP defaults to 10 seconds for connection and read inactivity when `timeout`
is omitted or null. An explicit positive timeout still takes precedence. This
is not a deadline for the entire download.

HTTP targets accept up to 4 MiB (4,194,304 decoded bytes) per successful
response. Set `config.max_response_bytes` to a positive integer to change the
limit, or set `vars.max_response_bytes` with the shipped Apache, NGINX and
RabbitMQ templates. Raise it before upgrading if an existing response is larger.
An oversized response triggers the target's configured failure metrics. Bodies
from redirects and unsuccessful HTTP statuses are discarded. `general.lock_timeout`
is not an overall collection deadline. Allow enough Prometheus scrape time for
all sources configured in an endpoint.

For a fixed HTTP URL, set `config.trust_env: false` to ignore proxy environment
variables, automatic `.netrc` credentials and the Requests environment CA bundle.
TLS verification stays enabled by default. Set `config.allow_redirects: false`
to stop at the first redirect. With the Apache, NGINX and RabbitMQ templates,
put these options in endpoint `vars`:

```yaml
vars:
  url: 'https://apache.example.org/server-status/?auto'
  trust_env: false
  allow_redirects: false
```

Fixed URLs without credential rules inherit the environment by default.
Dynamic destinations and targets with `credential_targets` always ignore it.
Setting `trust_env: true` for either prevents startup.

Keep collection endpoints on a trusted network. Dynamic `target` parameters let
callers select destinations or paths permitted by the plugin configuration. For
HTTP endpoints with credentials, prefer a fixed configured URL. Do not commit
credentials; see the [credentials example](etc/covenant/credentials.yml.example)
and provide deployment-specific files securely. Imported Mako templates are trusted
configuration, not a sandbox for untrusted input.

### Credentials for dynamic HTTP probes

Add this endpoint under `endpoints` in your Covenant YAML. Create the
`monitoring` section (keys `username` and `password`) in a private
`credentials.yml` next to the main configuration.

```yaml
  internal-health:
    plugin: http
    credentials: credentials.yml?__section=monitoring
    probes:
      - name: health
        config:
          path: /health
          timeout: 3
          credential_targets:
            - 'https://api.example.org'
            - 'https://*.services.example.org'
            - regex: 'node[0-9]+\.monitoring\.example\.org'
              scheme: https
              port: 443
            - cidr: '10.42.0.0/24'
              scheme: https
              port: 8443
        collects:
          - upstream_up:
              type: gauge
              documentation: Whether the upstream returned HTTP 200.
              value: 1
              on_fail:
                value: 0
```

Call `/probe/internal-health?target=https://node42.monitoring.example.org`.
Covenant requests `/health` with the configured credentials. An unmatched host
is still probed anonymously. A rule matches the scheme, effective port and
whole hostname. `*.` matches one DNS label. CIDR rules accept literal IPs
only. Redirect destinations are checked individually. Configured headers
(including custom API keys), Basic auth, cookies and client certificates are
withheld from unmatched destinations. Keep secrets out of request URLs,
parameters and bodies. Scoped requests ignore environment proxies and netrc.

To share rules across HTTP probes or metrics, put `import_credential_targets`
in the same target `config` block. For example:

```yaml
config:
  path: /health
  timeout: 3
  import_credential_targets: rules/monitoring.yml
  credential_targets:                 # Optional extra rules for this target
    - 'https://api.example.org'
```

`rules/monitoring.yml` contains a plain YAML list:

```yaml
- 'https://*.services.example.org'
- regex: 'node[0-9]+\.monitoring\.example\.org'
  scheme: https
  port: 443
```

Relative paths start at the directory containing the main Covenant YAML,
including when the probe itself comes from an imported template. Covenant
loads the rules at startup. Restart it after editing the file. Imported rules
come first, followed by inline rules. A missing file, malformed list or invalid
rule prevents startup. The unrestricted `'*'` must be the only rule across both
lists. Use `[]` for an empty file policy.

**Migration:** a dynamic target with omitted or empty `credential_targets`
now receives no configured credentials. To explicitly trust every HTTP(S)
destination, replace the entire list with `credential_targets: ['*']`. Anyone
able to select a target for that probe can then receive its credentials. A
fixed URL without this setting continues using the existing HTTP transport.

### Credentials for dynamic Redis targets

Redis targets support the same exact origins, single-label wildcards, hostname
regexes, literal IP networks and shared YAML lists as HTTP. Use `redis` or
`rediss` in Redis rules. Both schemes default to port 6379. With the shipped
template, place the settings in endpoint `vars`:

```yaml
endpoints:
  cache-fleet:
    plugin: redis
    credentials: credentials.yml?__section=cache
    import_metrics: metrics.d/redis.yml
    vars:
      timeout: 3
      credential_targets:
        - 'rediss://*.cache.example.org:6380'
```

For example, scrape
`/metrics/cache-fleet?target=rediss://node1.cache.example.org:6380/0`.
Set `vars.import_credential_targets` to a YAML file relative to the main config
to share rules. For inline metric or probe definitions, put both options in the
target's `config` block.

**Migration.** Before upgrading authenticated dynamic Redis endpoints, list
their credential destinations. An omitted or empty list probes anonymously.
An unmatched destination receives neither the configured Redis login nor a
configured TLS client certificate. A sole quoted `'*'` allows every network
destination chosen by the caller to receive the probe's credentials.

Dynamic URLs accept a host, optional port and optional numeric database path.
Move connection options from query strings into trusted configuration; keep
userinfo and Unix socket URLs in fixed configuration. A fixed configured URL
continues to take precedence over the caller's target and uses its configured
credentials. Prefer `rediss://` with verified TLS when sending credentials.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Cannot reach port 9118 | Container logs, port mapping and listen address |
| Endpoint not found | Module imports, endpoint name and `/metrics/` versus `/probe/` route |
| API connection failure in Docker | Use a reachable service hostname rather than container-local `localhost` |
| Metric absent | Source response, filter expression, and `on_fail`/`on_noresult` behavior |
| Nginx version collection fails | Disable `version_enabled` unless `/nginx_version` is configured |
| Files reported absent | Container mount path, permissions and include/exclude expressions |

## License

[GNU General Public License v3](LICENSE).

See [configuration validation](docs/configuration-validation.md) for YAML schema
coverage and compatibility.

## Documentation

- **Users:** installation, configuration, operation and API usage in this README and the user guide.
- **Contributors:** [architecture, tests and development](https://github.com/decryptus/covenant/blob/master/CONTRIBUTING.md).

Complete inventory exporters for Monit-Docker and CertLord are available through
the optional [observation plugins](docs/observations.md). Existing numeric collectors
keep their current configuration and output.
