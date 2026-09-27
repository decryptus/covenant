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
