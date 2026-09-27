# Collector regression tests

Run from the repository root in a dedicated Python environment:

```sh
python -m pip install six cryptography prometheus-client sonicprobe "dwho>=0.3.61" httpdis jmespath
python -m unittest discover -s tests -v
```

The suite was validated on Python 3.9.25. It uses real Covenant classes,
Prometheus serialization, generated DER certificates, temporary files and the
shipped YAML/Mako templates. Only the HTTP transport is mocked. It does not
require a running NGINX, Redis or RabbitMQ service, or the optional-to-this-suite
`pyjq` filter. The original collector scenarios are not a full daemon or deployment test;
the additional runtime coverage is described below.

The tests cover:

- Binary certificate parsing and exception wrapping under Python 3.
- File allowlists and denylists, including non-ASCII filenames.
- Missing final filter results: replace the prior value or remove the metric,
  and recover on the next successful collection.
- Combined label filters: every configured inclusion must match, and any
  matching exclusion removes the label. Configurations that relied on a later
  regex overriding an earlier exclusion will behave differently.
- NGINX success, failure and recovery with the shipped template.
- Passing a configured HTTP timeout to Requests and emitting failure metrics
  when Requests raises `Timeout`.
- Preserving a configured HTTP URL when a query supplies another target.
- Default network timeouts in the shipped templates.
- Dynamic file targets using a temporary registry without modifying the
  endpoint's persistent registry.

The suite also exercises `CollectionService` using real queues and concurrent
callers: successful results, plugin errors, bounded waits, late/duplicate callbacks,
submission failures and invalid timeout settings. The runtime smoke tests start an
actual HTTPdis listener in an isolated subprocess, load relative YAML imports,
start real filestat metric/probe plugins, scrape all shipped route aliases, verify
400/404/500/504 responses, and invoke the DWho SIGTERM stop hooks. Both legacy YAML
without `result_timeout` and an explicit short deadline are covered.

The runtime fixture does not invoke `bin/covenant`, drop privileges, daemonize,
or test PID-file ownership. Existing plugin worker threads are daemon threads;
this verifies HTTP shutdown and stop-hook invocation, not cooperative cancellation
of every backend operation. No external backend or Docker daemon is required.

Local validation for this change: Python 3.12, DWho 0.3.61, HTTPdis 0.6.28,
Sonicprobe 0.3.53; 46 tests passed. The Docker workflow runs the same discovery
against the built Python 3.11 image, including its installed package and dependencies.

DWho 0.3.61 provides the `asyncore` compatibility dependency and an importlib-based
loader for Python 3.12. Passing these collector tests alone must not be taken as
full daemon or deployment validation on that interpreter.

Compatibility facade tests additionally cover original signatures and error/result
shapes, subclass overrides used by the HTTP handlers, result mapping writes,
concurrent split calls, abandoned-call expiry and late callbacks after consumption
or timeout. These facades retain bounded waits; they do not restore indefinite
result retention or concrete-dict identity.
