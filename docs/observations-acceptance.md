# Complete observation collector acceptance

The closed stdlib wire codec is mirrored in Atraxis; its integration suite checks
byte equality so schema/encoding drift cannot silently pass. Encoding projects only
known native fields. Numeric gauges preserve type tags, exact large integers use
bounded decimal text, and strings use bounded labels. Container/certificate and
nested array order, explicit nulls and empty arrays survive. A schema version,
row count and canonical SHA-256 digest protect completeness; the digest does not
replace authenticated transport or validate native business semantics.

`tests/test_observations.py` covers actual Prometheus serialization round trips,
allowlist privacy, malformed/duplicate JSON keys, nonfinite values, row/size limits,
missing/duplicate/corrupted fields, fixed destinations and failure/recovery for both
new plugins. `tests/observations_runtime.py` runs YAML loading, both registered
plugins, actual endpoint workers and HTTPdis against authenticated synthetic HTTP
sources in an isolated subprocess. Existing CertLord transport/runtime tests remain
in the same suite, including credential rotation and redirect refusal.

Run the collection guard before both roots, then execute them:

```sh
python .github/scripts/check-test-collection.py --runner unittest tests .github/tests
python -m unittest discover -s tests -v
python -m unittest discover -s .github/tests -v
```

The Docker workflow executes `tests` against the installed package in the built
image. Atraxis additionally qualifies native projection equality through two real
Prometheus instances. These are synthetic acceptance tests, not production capacity,
remote TLS, source deployment or certificate issuance acceptance. No deployment or
publication is implied by a passing run.
