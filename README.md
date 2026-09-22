# Covenant

**Turn HTTP APIs, Redis data, TLS certificates and file checks into Prometheus
metrics using YAML configuration.**

Covenant is a configurable, multi-endpoint Prometheus exporter. It separates data
collection from transformation and metric exposition, so you can adapt a source
without writing a separate exporter for every service.

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

The example pins `decryptus/covenant:0.0.67` and exposes port 9118 only on the local
host. If the first request arrives before the API is ready, retry it.

```sh
# Inspect logs or stop the example.
docker compose -f examples/quickstart/compose.yml logs covenant
docker compose -f examples/quickstart/compose.yml down
```

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

Docker is the simplest way to use the tested runtime. To run your own configuration:

```sh
docker run --rm --name covenant \
  -p 127.0.0.1:9118:9118 \
  -v "$PWD/covenant.yml:/etc/covenant/covenant.yml:ro" \
  decryptus/covenant:0.0.67
```

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

The network templates expose `vars.timeout`. HTTP and TLS use a source `timeout`;
the Redis template sets `socket_timeout` and `socket_connect_timeout`. A custom
HTTP definition should set `config.timeout` explicitly. `general.lock_timeout`
is not an overall collection deadline. Allow enough Prometheus scrape time for
all sources configured in an endpoint.

Keep collection endpoints on a trusted network. Dynamic `target` parameters let
callers select destinations or paths permitted by the plugin configuration. For
HTTP endpoints with credentials, prefer a fixed configured URL. Do not commit
credentials; see the [credentials example](etc/covenant/credentials.yml.example)
and provide deployment-specific files securely. Imported Mako templates are trusted
configuration, not a sandbox for untrusted input.

## Tests and Docker releases

See [tests/README.md](tests/README.md) for local test setup and coverage.

The [Docker Hub workflow](.github/workflows/dockerhub.yml) builds and tests on
`master` and pull requests. After successful tests on `master`, a new stable
version in `VERSION` and `RELEASE` automatically creates its missing `vX.Y.Z`
tag and publishes the tested Linux amd64 image as:

- `decryptus/covenant:X.Y.Z`
- `decryptus/covenant:vX.Y.Z`

Publication requires the GitHub repository secret `DOCKERHUB_TOKEN`. The workflow
does not update `latest` or overwrite existing Git tags. Ordinary commits on an
already tagged version skip publication. Manual version-tag pushes remain supported.
See [Docker Hub setup and release instructions](docs/dockerhub.md).

The container checks include a jq expression, the 24 collector/template regression
tests, the installed package version and CLI startup. They do not replace a full
integration test against your real services.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Cannot reach port 9118 | Container logs, port mapping and listen address |
| Endpoint not found | Module imports, endpoint name and `/metrics/` versus `/probe/` route |
| API connection failure in Docker | Use a reachable service hostname rather than container-local `localhost` |
| Metric absent | Source response, filter expression, and `on_fail`/`on_noresult` behavior |
| Nginx version collection fails | Disable `version_enabled` unless `/nginx_version` is configured |
| Files reported absent | Container mount path, permissions and include/exclude expressions |
| Image not published | Tag/version checks and Docker Hub credentials in the Actions log |

## License

[GNU General Public License v3](LICENSE).

## Publishing to PyPI

See [PyPI publishing](docs/pypi.md) for Trusted Publisher setup and automated releases.
