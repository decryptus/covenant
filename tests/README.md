# Collector regression tests

Run from the repository root in a dedicated Python environment:

```sh
python -m pip install six cryptography prometheus-client sonicprobe dwho httpdis jmespath
python -m unittest discover -s tests -v
```

The suite was validated on Python 3.9.25. It uses real Covenant classes,
Prometheus serialization, generated DER certificates, temporary files and the
shipped YAML/Mako templates. Only the HTTP transport is mocked. It does not
require a running NGINX, Redis or RabbitMQ service, or the optional-to-this-suite
`pyjq` filter. This is not a full daemon or deployment test.

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

The production timeout settings and request queue behavior are unchanged.
Python 3.12 requires additional compatibility work in legacy dependencies
(`pyinotify` imports `asyncore`, and `dwho`'s loader imports `imp`); passing these
collector tests alone must not be taken as full Python 3.12 support.
