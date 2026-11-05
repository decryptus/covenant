# Covenant 0.0.78

## Collection and access logs

Collector errors identify the configured target and the exception type, with
the upstream HTTP status when available. Covenant omits source values and raw
exception text from these log messages.

Covenant now requires HTTPdis 0.6.38 or later. An incoming request such as
`/probe/web?target=...` appears in the access log as `GET /probe/web HTTP/1.1`
with status and size. The probe still receives the requested target. Review
log parsers that used the query string. Reverse proxies record separate logs
according to their own configuration.

## Upgrading HTTPdis

Check any dependency pin for HTTPdis. Deployments with custom handlers that
read the Basic password from HTTPdis should migrate to a configured service
credential. Browser clients that use cross-origin preflight requests need an
explicit permitted origin on their route. See the HTTPdis
[Basic authentication](https://github.com/decryptus/httpdis/blob/v0.6.37/docs/release-0.6.37.md)
and [CORS](https://github.com/decryptus/httpdis/blob/v0.6.36/docs/release-0.6.36.md) migration notes.

Install `covenant==0.0.78` or use `decryptus/covenant:0.0.78`.
