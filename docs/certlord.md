# Collecting CertLord observations

Covenant collects and exposes metrics. Prometheus evaluates alert rules;
Alertmanager handles grouping, deduplication, silences, routing and notifications.
Covenant does not send notifications and does not implement an alert engine.

CertLord already has a Prometheus endpoint: direct Prometheus scraping is also
valid. Use this optional collector when Covenant is your configured collection
boundary. It reads only `/api/certificates/metrics`; it never contacts Vault,
Redis, issuance or deployment endpoints.

This optional plugin requires Python 3.8 or newer; validation uses Python 3.11/3.12.
Older interpreters do not register this plugin; existing plugins remain unchanged.

## Configuration

Merge `examples/certlord/endpoint.yml` into your existing Covenant YAML. Use one
metrics target per endpoint. Set `general.result_timeout: 30`. Configure the fixed
CertLord HTTPS URL, a private token file with CertLord **read** permission, and
optionally a CA file. Paths are relative to the main Covenant configuration.
Keep the token file readable only by the service account; replace it atomically
for rotation. It is reread on each collection. No credential is embedded in the
example. Certificates and hostnames are verified; redirects, environment proxies,
netrc credentials and request-supplied targets are not accepted. HTTP is accepted
only for literal loopback IPs; missing tokens there work only with CertLord's
explicit local authentication policy.

Scrape Covenant at `/metrics/certificates`. Keep Covenant private and protect its
HTTP interface using your normal authenticated ingress. UUIDs and lifecycle
metadata are operational information. Configure Prometheus-to-Covenant ingress
credentials separately from the Covenant-to-CertLord read token.

The source emits `covenant_certlord_source_up` plus validated CertLord gauges.
Every response is a new snapshot: failures emit source_up=0 with no cached
certificate gauges. An empty inventory is successful with zero observed records.
Malformed, inconsistent or oversized inventories fail the collection. Unknown
metric families are ignored; known families, identities, labels and completeness
are checked against the RC1 contract. No raw response body or exception is logged.
The response is limited to 4 MiB. Requests have finite connect/read timeouts and
a monotonic budget checked between chunks. DNS resolution and OS I/O are not a
hard real-time deadline; Covenant's caller timeout does not cancel backend work.

## Rules and notifications

Copy the Prometheus example and rules together, then adapt addresses and job
names. The example thresholds are operator choices, not CertLord defaults.
The rules distinguish collection freshness, expiration, ACME retries and missing
material. Source failure or stale/future-dated snapshots suppress certificate
alerts and raise an observation alert instead. A retry gauge is not a lifetime
failure counter and does not identify an exact failure reason. Expiry describes
stored material, not the certificate currently served by every destination.

Configure receivers in your existing Alertmanager; this example installs no
receiver and sends no message. Use Alertmanager `send_resolved` where supported
if resolved notifications are wanted. An empty inventory does not prove that a
particular expected certificate exists; maintain an explicit expected inventory
if absence of individual UUIDs must alert. Removing one configured scrape target
while others remain requires independent target inventory monitoring.

Validate rules with `promtool check rules certlord.rules.yml` and the included
rule tests. Real delivery to your notification provider requires a separate,
authorized staging check. No live deployment or notification is triggered here.
