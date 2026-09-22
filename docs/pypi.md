# PyPI publishing

The existing `dockerhub.yml` release workflow also builds source distributions
and wheels, checks them with Twine, verifies names, versions and installed
scripts, and uploads the validated artifacts to PyPI after the Docker release
job succeeds. Builds run on pull requests without publishing or OIDC credentials.
Automatic tags use GITHUB_TOKEN, so PyPI publication happens in the same workflow
rather than depending on a second tag-triggered workflow.

## One-time PyPI setup

Add a GitHub Trusted Publisher under Publishing for each project below:

| PyPI project | GitHub owner | Repository | Workflow filename | Environment |
| --- | --- | --- | --- | --- |
| `covenant` | `decryptus` | `covenant` | `dockerhub.yml` | `pypi` |

Use the project's Publishing settings if it already exists; otherwise configure
a pending publisher. You must have permission to manage that PyPI project.
The workflow uses the GitHub environment `pypi`; any required approvals on that
environment must be granted before publishing. No PYPI_API_TOKEN is required.

See [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Releases and retries

Update the version files consistently and merge into master. For a new version,
the existing release selection creates the tag after validation and the PyPI job
publishes the exact distributions from that run. Ordinary commits on an already
tagged version do not publish. Adding this workflow does not republish old tags
or increment the version.

If PyPI setup or upload fails after Docker publication, correct the setup and
re-run the failed PyPI job in the same Actions run. Artifacts are retained for
seven days. Existing distribution filenames are skipped to allow partial-upload
retries; they cannot be replaced. Changed package contents require a new version.
Do not rerun an older workflow expecting it to gain this publishing configuration.
