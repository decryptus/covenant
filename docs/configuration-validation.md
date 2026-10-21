# Configuration validation

The loader validates the main document and endpoint definitions before framework
initialization. Endpoint plugins are nonempty strings; vars are mappings; metrics
and probes are lists. Mako imports are validated after rendering, before merging.
Plugin-specific metric/probe objects remain opaque to the common schema. Relative
paths, inline variable precedence, result-timeout conversion and bounds, and the
requirement to select metrics or probes remain in the existing loader/services.
Missing endpoints retain their existing error order after timeout validation.

XYS (Sonicprobe >= 0.3.57) validates parsed Python data; it does not replace the
YAML loader, resolve imports, initialize services or grant permissions. Schemas
are compiled once. These schemas use no modifiers and do not silently convert
values. The existing numeric normalization and semantic checks still apply.

Known application fields are validated explicitly. Extension settings remain
available where the existing contract permits them; this is not universal typo
detection for plugin configuration. Malformed section/component shapes now fail
with a configuration error instead of incidental attribute/update exceptions.
New validation errors do not include configuration values or credential contents.

`tests/test_configuration_schema.py` covers valid/invalid shapes and compatibility
at the loader boundary. Run the collection guard before the unittest suite:

```sh
python .github/scripts/check-test-collection.py --runner unittest tests
python -m unittest discover -s tests -v
```

These tests use synthetic data and mocked adapters or loopback services. They do
not establish provider availability or production acceptance.

# Collection overload and expiration

Each endpoint accepts at most 256 queued collection requests, in addition to
the collection currently executing. Admission never waits for space: when the
queue is full, metrics and probes return HTTP 503. There is no automatic retry.
This replaces the previous unbounded queue behavior.

Each split submission/retrieval instance also retains at most 256 outstanding
calls across its endpoints, including completed results not yet retrieved. A
full result store refuses new submissions with the same HTTP 503 response,
even when the endpoint queue is empty. Retrieving, deleting or expiring a result
releases its slot. The existing result deadline remains active; this limit does
not evict a valid result to admit another caller.

Requests submitted through the collection service carry the existing
`general.result_timeout` deadline. A worker discards an expired request before
starting its plugin call. The caller still receives HTTP 504 on expiration;
late results cannot replace the result of another request. Legacy directly
constructed plugin jobs without a deadline retain their execution behavior,
but share the same queue capacity.

The deadline does not interrupt a plugin call already running. If a plugin is
blocked, expired queued requests occupy bounded slots until the worker resumes;
new requests can continue to receive HTTP 503. Configure backend timeouts and
investigate the blocked dependency. The request-count bound is not a byte-size
limit or a guarantee of bounded backend execution time.

An exception in a custom completion callback is logged without retrying that
callback and does not stop the endpoint worker. Later queued requests continue
to be processed. If the failed callback did not deliver the result, its caller
still reaches the original result deadline.
