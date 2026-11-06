# Covenant 1.0 release plan

The 6 November review leaves one partial finding: implicit dynamic network
targets. The RC preserves compatibility and adds endpoint-level warnings.
The remaining review fixes were delivered through 0.0.83.

Before stable publication:

- Change the endpoint policy default to an empty list and initialize it for
  every HTTP, Redis and TLS endpoint, including endpoints with no rule keys.
- Verify omitted policies and deny-only policies reject before network I/O.
- Verify explicit local/imported allow lists, wildcard opt-in, exclusion
  precedence, fixed destinations and credential separation through config load.
- Review migration feedback and perform the release checks on 6 December 2026.
- Publish stable only after these checks and update the demo after qualification.

The live demo uses a fixed HTTP destination. Its 0.0.83 deployment was verified
with a fresh Prometheus sample and retained history. Evaluate the RC with
explicit installation commands before scheduling any live upgrade.
