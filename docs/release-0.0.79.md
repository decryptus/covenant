# Covenant 0.0.79

## Before upgrading

Check the `flags` entries on any custom `regex` filters. Covenant validates
them when it loads the endpoint configuration. Use a flag name such as
`MULTILINE`, a list such as `[I, MULTILINE]`, or an integer mask made from
supported flags. Invalid names, unknown bits and malformed values cause a
startup error. Omitting `flags` uses the default.

The YAML selects the method for `builtintypes`. If a custom endpoint uses
`format` or `format_map`, the source string controls the format fields and
output widths. Use these methods with trusted format strings. The supplied
Apache template uses `count` to count worker states.

Covenant requires HTTPdis 0.6.39 or later. This update keeps exception details
out of client-facing HTTP errors while preserving the status and headers.
Update any lower HTTPdis dependency pin before installing.

Install `covenant==0.0.79` or use `decryptus/covenant:0.0.79`.
