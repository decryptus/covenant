# Covenant 0.0.77

## HTTP collector options

Fixed HTTP targets inherit proxy settings, automatic `.netrc` credentials and
the Requests environment CA bundle by default when no credential rules are set.
Use `trust_env: false` to ignore these settings for a target. TLS certificate
verification remains enabled by default. Dynamic targets and targets with
credential rules always ignore the environment and reject `trust_env: true`.

The Apache, NGINX and RabbitMQ templates accept both options in endpoint
`vars`. To contact a fixed server directly and stop at a redirect:

```yaml
vars:
  url: 'https://apache.example.org/server-status/?auto'
  trust_env: false
  allow_redirects: false
```

For inline HTTP probes or metrics, put these options in the target's `config`.
If you rely on a proxy or a CA bundle supplied through the environment, keep
environment inheritance enabled for that fixed target.

## Configuration examples and dependency

The sample configuration includes an optional `application-file` endpoint
with shared allowed and excluded path files. The repository's Compose example
mounts those files read-only. See the [file probe guide](../README.md#file-existence-probe).

Covenant now requires HTTPdis 0.6.35 or later for bounded HTTP request parsing.
Update any dependency pin below that version before upgrading.

Install `covenant==0.0.77` or use `decryptus/covenant:0.0.77`.
