# Docker Hub publishing

The Docker Hub workflow builds and tests Linux amd64 images on pull requests and
pushes to master. After successful tests on master, it creates the missing `vX.Y.Z`
tag from VERSION and publishes the tested image as `decryptus/covenant:X.Y.Z` and
`decryptus/covenant:vX.Y.Z`. Manually pushed version tags remain supported.
Pull requests only build and test. Ordinary master commits whose version was
already tagged on an ancestor skip publication. `latest` is deliberately not moved.
Use an explicit version in docker-compose.yml when deploying a release.

## One-time setup

1. Ensure the Docker Hub repository `decryptus/covenant` exists.
2. Create a Docker Hub personal access token with read/write access for that image.
3. In this GitHub repository, Settings > Secrets and variables > Actions, add a
   repository secret named `DOCKERHUB_TOKEN` containing the token. Never commit it.
   The workflow authenticates as `decryptus`.

## Release

Update VERSION, RELEASE, setup.yml, bin/covenant and CHANGELOG consistently, then
merge into master. No manual tag command or additional GitHub token is required.
The image job builds and tests with read-only repository access. The separate
publication job downloads that exact tested image and has `contents: write` to
create a lightweight tag on the tested commit. Repository rules must allow this
tag creation; the workflow does not bypass tag protections.

Only stable X.Y.Z versions are accepted. VERSION and RELEASE must agree, and the
installed package version is tested against VERSION. Manual tags must match too.
An existing tag is never moved. A tag on an unrelated commit causes a failure.
An existing tag on the current commit permits retrying the publication; a tag on
an ancestor skips it, preserving the previous image for ordinary master changes.

Tag creation and Docker Hub publication happen in the same workflow: a tag made
using GITHUB_TOKEN does not trigger another push workflow. Release jobs are
serialized to prevent competing tag creations. Docker credentials and the tested
image are checked before a missing tag is created.

If an upload fails, fix the problem and re-run the failed publication job in
Actions. The tested image artifact is retained for seven days. After expiry,
re-run all jobs of that original run to rebuild and publish the original commit.
Dependency versions are not fully locked, so a rebuild may differ from the first.

On first activation, the workflow will release the current version if its tag is
missing, including when the triggering commit only installs this automation.
The workflow must exist in the tagged commit for manually pushed tags to run it.

The image installs this repository's source, not the PyPI release. Python 3.11 is
used because legacy dependencies still import imp and asyncore, removed in 3.12.
pyjq is updated to 2.6.0 for the newer Python build environment. The workflow checks
a jq expression, the collector tests, the installed version and CLI startup before
pushing. Dependencies other than pyjq are not locked; builds are not bit-reproducible.
A full running-service/integration test is not included.

References: https://docs.docker.com/build/ci/github-actions/
and https://github.com/docker/login-action (use a token, not your account password).
