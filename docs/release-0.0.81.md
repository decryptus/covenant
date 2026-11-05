# Covenant 0.0.81

## Before upgrading custom filters

Check `func` on each `'@filter': builtintypes` task in your YAML and imported
templates. Covenant now rejects an unlisted method when loading the endpoint.
The shipped Apache template uses `count` and requires no changes.

For `format` and `format_map`, verify who controls the **collected string**.
A format string can traverse attributes of its arguments and request large output
widths. If the template comes from a trusted source, opt in on that specific
task with a YAML boolean:

```yaml
value_tasks:
  - '@filter': builtintypes
    func: format
    allow_format: true
    args: [42]
```

A source string of `{0:04d}` yields `0042`. If the source can supply arbitrary
text, extract the intended field directly, for example with a configured
`jmespath` expression on a JSON response.

## Supported method names

Each method also requires support on the installed Python version and a
compatible input. The list covers these operations:

| Operation | Methods |
| --- | --- |
| Lookups and collections | `copy`, `count`, `difference`, `fromkeys`, `get`, `has_key`, `index`, `indices`, `intersection`, `isdisjoint`, `issubset`, `issuperset`, `items`, `iteritems`, `iterkeys`, `itervalues`, `keys`, `symmetric_difference`, `union`, `values`, `viewitems`, `viewkeys`, `viewvalues` |
| Text and bytes | `capitalize`, `casefold`, `center`, `decode`, `encode`, `endswith`, `expandtabs`, `find`, `isalnum`, `isalpha`, `isascii`, `isdecimal`, `isdigit`, `isidentifier`, `islower`, `isnumeric`, `isprintable`, `isspace`, `istitle`, `isupper`, `join`, `ljust`, `lower`, `lstrip`, `maketrans`, `partition`, `removeprefix`, `removesuffix`, `replace`, `rfind`, `rindex`, `rjust`, `rpartition`, `rsplit`, `rstrip`, `split`, `splitlines`, `startswith`, `strip`, `swapcase`, `title`, `translate`, `upper`, `zfill` |
| Numeric and binary conversions | `as_integer_ratio`, `bit_count`, `bit_length`, `conjugate`, `from_bytes`, `fromhex`, `hex`, `is_integer`, `to_bytes` |
| Trusted formatting with `allow_format: true` | `format`, `format_map` |

If a custom metric uses `pop` to read a dictionary entry, use `get` and check
the desired fallback for a missing key. For a list or tuple, `get` supports
an index or a start and end index. Configurations using other in-place
operations such as `clear`, `update` or `sort` need an explicit transformation
before upgrading. For a sorted copy, the separate `builtins` filter supports
`func: sorted`.
