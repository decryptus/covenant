# Covenant development rules

- Keep business/application services independent of HTTP requests/responses,
  CLI parsing, ncurses/TUI and visual presentation. Interfaces call services;
  services never invoke an interface to execute business operations.
- Pass explicit plain inputs and return values or domain exceptions. Compose
  existing DWho, HTTPdis and Sonicprobe adapters at the application boundary.
- Preserve public plugin hooks, job/callback contracts, existing routes, YAML
  configurations and Prometheus output when refactoring. Document intentional
  behavior changes and compatibility limitations; do not silently rely on new
  breaking shared-library behavior.
- Keep fixed schemas, mappings and patterns in named uppercase constants. Match
  the surrounding coding style; do not create unnecessary framework abstractions.
- Every result wait must have a finite validated timeout. Clean completion state
  on success, error and timeout; late callbacks must not retain orphaned results.
  A caller deadline must not be represented as cancellation of backend work.
- Validate service behavior without an interface, and meaningful consumer paths
  through actual configuration loading, plugins and HTTPdis. Keep runtime-global
  registry and signal tests in isolated subprocesses.

## Test discovery and execution

- Verify the actual runner and every discovery root before adding or changing
  tests. A green command does not prove that all test declarations were loaded.
  Do not put standalone pytest functions into a suite run only by unittest.
- Run `.github/scripts/check-test-collection.py` with Python, the same
  interpreter/environment as the tests, and the declared runner. Pass separately
  discovered directories together when they are nested. The guard compares
  declarations in `test*.py` files with actual collection; it does not run tests.
- Reject empty suites, import/collection errors, duplicate definitions and
  declarations omitted by the runner. Keep test helpers out of the `test*`
  namespace. Explain intentional skips and separate integration prerequisites;
  never hide failures with `continue-on-error` or `|| true`.
- Run the normal test command after the guard. Report collected/executed/skipped
  counts and investigate unexpected changes; collection alone is not a passing
  test run. Parameterization may produce several cases per declaration.
- Check test paths, naming patterns, selection filters and CI commands together.
  A new test directory or non-Python test harness needs an explicit CI entry;
  this guard only covers the directories and Python naming pattern passed to it.
- Verify installed-package tests outside the source checkout where applicable.
  Architecture scans must resolve the package under test and reject empty scans.
- Preserve supported interpreter matrices. Changing runners requires an explicit
  decision and collection parity; this Python 3.8+ CI helper does not replace
  legacy-interpreter execution or integration/system acceptance tests.

Current project runner: `unittest` for `tests`. CI helper tests use
`unittest` in `.github/tests`.

## Separate user and contributor documentation

- Maintain two distinct entry points and tables of contents: user documentation
  for installation, configuration, operation, public APIs and troubleshooting;
  contributor documentation for architecture, internals, tests, benchmarks,
  release engineering and development plans.
- Keep README and package descriptions focused on users. Link to the contributor
  guide instead of embedding maintainer procedures. Library API examples belong
  in the user guide when they are needed to integrate the library.
- Keep registry publishing, CI setup, repository secrets and maintainer account
  configuration out of user guides, website manuals and package descriptions.
  Never include credential values or private infrastructure evidence in either guide.
- Put implementation reviews and acceptance records under the contributor
  navigation. Preserve user-facing compatibility limits, migration instructions,
  security requirements and failure semantics in the user documentation.
- Apply this separation to generated documentation and FR/EN website content.
  Update source content and generators together; do not patch only generated HTML.
- Before delivery, inspect both entry points, check links and build documentation
  with warnings treated as errors where supported. Review README/package text and
  the deployed manual for accidental maintainer content. Preserve private-project
  visibility and existing review/publication approval requirements.
