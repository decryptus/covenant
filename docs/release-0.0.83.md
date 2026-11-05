# Covenant 0.0.83

The sample TLS endpoint `secure-layer1` accepts `example.com` on port 443.
When copying the sample, set `allowed_targets` to the hosts and ports you
monitor. If you manage an existing endpoint, edit its YAML and restart
Covenant to apply the same restriction.

The source archive contains the sample under `etc/covenant/`. The Python
wheel installs the same files under `share/covenant/examples/` in the
installation prefix, including the templates and rule files. In the Docker
image, the directory is `/usr/local/share/covenant/examples/`. Copy the
directory before editing it and use your copy as the configuration.
