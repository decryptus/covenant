# Docker Hub publishing

The Docker Hub workflow builds and tests Linux amd64 images on pull requests and
pushes to master. Pushing a new release tag `vX.Y.Z` also publishes the tested image
as `decryptus/covenant:X.Y.Z` and `decryptus/covenant:vX.Y.Z`.
No image is published from branches or pull requests. `latest` is deliberately not
moved: publishing a maintenance release must not downgrade existing deployments.
Use an explicit version in docker-compose.yml when deploying a release.

## One-time setup

1. Ensure the Docker Hub repository `decryptus/covenant` exists.
2. Create a Docker Hub personal access token with read/write access for that image.
3. In this GitHub repository, Settings > Secrets and variables > Actions, add a
   repository secret named `DOCKERHUB_TOKEN` containing the token. Never commit it.
   The workflow authenticates as `decryptus`.

## Release

Update VERSION, RELEASE, setup.yml, bin/covenant and CHANGELOG consistently, merge
into master and wait for the Docker Hub build/test job to pass. Then push the tag:

```sh
git tag -a v0.0.67 -m 'version: 0.0.67'
git push origin v0.0.67
```

The example assumes the release commit is checked out and declares version 0.0.67.
Only stable vX.Y.Z tags are accepted. Tag VERSION/RELEASE mismatches fail before
building. The installed package version is checked against VERSION before upload.
The workflow must exist in the tagged commit: v0.0.66 predates it and is not
published retroactively. Do not move existing release tags. If authentication or
an upload fails, fix the secret and re-run the failed job in Actions.

The image installs this repository's source, not the PyPI release. Python 3.11 is
used because legacy dependencies still import imp and asyncore, removed in 3.12.
pyjq is updated to 2.6.0 for the newer Python build environment. The workflow checks
a jq expression, the collector tests, the installed version and CLI startup before
pushing. Dependencies other than pyjq are not locked; builds are not bit-reproducible.
A full running-service/integration test is not included.

References: https://docs.docker.com/build/ci/github-actions/
and https://github.com/docker/login-action (use a token, not your account password).
