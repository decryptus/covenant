# Covenant 0.0.72

TLS observations now interpret certificate dates in UTC, accept certificates
with subject alternative names but no common name, and verify the requested
hostname on the connection used for the observation. Modern Python hostname
matching uses `service-identity`. Sockets are closed on handshake and observation
failures. Existing metric names and configuration remain unchanged.

Collection now limits each endpoint queue and each split-call result registry
to 256 entries. Saturated admission returns HTTP 503 without evicting accepted
work. Queued work whose original deadline has expired does not start its plugin.
An ordinary completion callback exception no longer stops the endpoint worker;
the callback is not retried and subsequent work continues.

Caller timeout does not cancel an already running plugin. The capacity bound is
a count limit, not a byte-size guarantee. See
[configuration and overload behavior](configuration-validation.md).

Install `covenant==0.0.72` or use `decryptus/covenant:0.0.72`. The quickstart
Compose example pins this version.
