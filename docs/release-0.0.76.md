# Covenant 0.0.76

## Upgrading filtered file probes

Covenant now checks the requested path, its resolved parent and any symlink
destination against the configured file rules. Use normalized paths.
For example, if SSH writes its PID under `/run` and your probe requests
`/var/run/sshd.pid`, use `^/(var/)?run/sshd[.]pid$` to allow both spellings.
The shipped file probe reports `file_exists 0` for a denied path.

## Sharing rules between endpoints

Declare either or both imports beside `import_probes` on each participating
endpoint. This example also adds one path just for the application probe.

```yaml
endpoints:
  application-file:
    plugin: filestat
    import_probes: probes.d/file.yml
    import_state_include_paths: rules/files-allowed.yml
    import_state_exclude_paths: rules/files-denied.yml
    vars:
      state_include_paths: ['^/srv/monapp/ready$']
```

Each file contains a YAML list of regular expressions. Covenant resolves the
filenames relative to the main configuration and combines the imported and
local rules at startup. Exclusions take precedence. Restart Covenant after
editing the lists. See the [file probe guide](../README.md#file-existence-probe)
for examples and startup validation.

Install `covenant==0.0.76` or use the image `decryptus/covenant:0.0.76`.
