# Covenant 0.0.74

## Before upgrading

- If a successful HTTP response exceeds 4 MiB after decompression, set
  `config.max_response_bytes` to a larger positive byte count for that target.
  The shipped Apache, NGINX and RabbitMQ templates accept the same setting under
  `vars`. Oversized responses trigger the target's configured failure metrics.
- HTTP targets with an omitted or null `timeout` now use 10 seconds for
  connection and read inactivity. Set an explicit positive timeout for slower
  sources. A download that keeps delivering bytes can run longer than this.
- When starting as root on a custom installation, ensure the configured service
  user and group exist. Both default to `covenant`. Check that this account
  can access the files needed by your probes, including bind-mounted files in
  Docker. The Debian package and Docker image provide the service account.

## Scrapes and startup

Unexpected errors in the metrics, probes and server handlers now return a
generic HTTP 500. Invalid query parameters return 400. A successful scrape can
still report an upstream failure via its configured metrics. HTTP error bodies
are discarded without recording their contents in the plugin log.

Root launches initialize the service account's supplementary groups before
switching identity. The detached launcher waits until the HTTP serving loop
starts. A startup failure such as an occupied port returns a nonzero status.

Install `covenant==0.0.74` or use `decryptus/covenant:0.0.74`. When upgrading
from 0.0.72 or earlier, also review the
[dynamic HTTP credential migration](release-0.0.73.md).
