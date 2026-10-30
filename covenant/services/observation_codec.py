"""Version-one closed observation wire schema; stdlib only, no source I/O.

Keep this file identical in Covenant and Atraxis. Unknown source keys are never
exported. Values, nulls, list order and integer precision survive a round trip.
"""

import hashlib
import json
import math

VERSION = 1
MAX_ROWS = 10000
MAX_TEXT = 4096
MAX_ITEMS = 10000
MAX_BYTES = 4 * 1024 * 1024
EXACT_INTEGER = 2**53
LEAF = "scalar"


def fields(names):
    return dict.fromkeys(names.split(), LEAF)


FILESYSTEM = fields(
    "group path disk_usage disk_available disk_total disk_percent "
    "inode_usage inode_available inode_total inode_percent "
    "fs_mode fs_readable fs_writable fs_executable"
)
CONTAINER = fields(
    "id name status health mem_usage mem_limit mem_percent cpu_percent "
    "io_read io_write net_rx net_tx pids_percent maintenance_until pid "
    "oom_events starts_recent pids_current pids_limit event_window_seconds "
    "event_window_end restart_attempts restart_limit event_history_complete "
    "manual_actions_protected maintenance_active"
)
CONTAINER["filesystems"] = [FILESYSTEM]
MONIT = fields(
    "api_version ready running last_cycle_success cycles_total errors_total "
    "age_seconds last_success_at last_cycle_finished_at last_error_code"
)
MONIT["actions"] = fields("executed cooldown pending restart-limit maintenance dry-run")
MONIT["containers"] = [CONTAINER]
CERTIFICATE = fields(
    "certificate_id version status origin renewal_owner pending_action "
    "material_state not_before not_after not_after_timestamp_seconds "
    "fingerprint_sha256 issuance_retry_count last_issuance_retry_at observed_at"
)
CERTIFICATE["domains"] = [LEAF]
CERTIFICATE["verification"] = fields(
    "status checked_at error_code expected_fingerprint_sha256 "
    "observed_fingerprint_sha256 target_sha256"
)
CERTLORD = fields("schema_version started_at completed_at completed_timestamp_seconds")
CERTLORD["certificates"] = [CERTIFICATE]
SCHEMAS = {"monit": MONIT, "certlord": CERTLORD}


class InvalidObservation(ValueError):
    def __init__(self):
        super().__init__("invalid_observation")


def check(condition):
    if not condition:
        raise InvalidObservation()


def project(value, schema):
    if value is None:
        return None
    if type(schema) is dict:
        check(type(value) is dict)
        return {key: project(value.get(key), child) for key, child in schema.items()}
    if type(schema) is list:
        check(type(value) is list and len(value) <= MAX_ITEMS)
        return [project(item, schema[0]) for item in value]
    check(type(value) in (str, int, float, bool))
    if type(value) is str:
        check(
            len(value) <= MAX_TEXT
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        )
    elif type(value) in (int, float):
        try:
            check(math.isfinite(value))
        except OverflowError:
            raise InvalidObservation() from None
    return value


def digest(value):
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode()
    check(len(raw) <= MAX_BYTES)
    return hashlib.sha256(raw).hexdigest()


def encode(payload, kind):
    check(kind in SCHEMAS)
    document = project(payload, SCHEMAS[kind])
    rows = []

    def walk(value, path):
        check(len(rows) < MAX_ROWS)
        typ, text, number = "null", "", 1
        if type(value) is dict:
            typ = "object"
        elif type(value) is list:
            typ, number = "list", len(value)
        elif type(value) is str:
            typ, text = "text", value
        elif type(value) is bool:
            typ, number = "bool", int(value)
        elif type(value) is int:
            typ, number = "int", value
            if abs(value) > EXACT_INTEGER:
                typ, text, number = "integer_text", str(value), 1
        elif type(value) is float:
            typ, number = "float", value
        rows.append((path, typ, text, number))
        if type(value) is dict:
            for key, item in value.items():
                walk(item, path + "." + key)
        elif type(value) is list:
            for index, item in enumerate(value):
                walk(item, path + "." + str(index))

    walk(document, "root")
    return rows, digest(document)


def decode(rows, kind, expected_digest):
    check(kind in SCHEMAS and type(rows) is list and 1 <= len(rows) <= MAX_ROWS)
    remaining = {}
    for path, typ, text, value in rows:
        check(type(path) is str and path not in remaining)
        check(type(text) is str and len(text) <= MAX_TEXT)
        check(type(value) in (int, float) and math.isfinite(value))
        remaining[path] = (typ, text, value)

    def walk(schema, path):
        check(path in remaining)
        typ, text, value = remaining.pop(path)
        if typ == "null":
            check(value == 1 and not text)
            return None
        if type(schema) is dict:
            check(typ == "object" and value == 1 and not text)
            return {key: walk(child, path + "." + key) for key, child in schema.items()}
        if type(schema) is list:
            check(
                typ == "list"
                and not text
                and 0 <= value <= MAX_ITEMS
                and value == int(value)
            )
            return [walk(schema[0], path + "." + str(i)) for i in range(int(value))]
        if typ == "text":
            check(value == 1)
            return text
        if typ == "integer_text":
            check(value == 1 and 1 <= len(text) <= 310)
            try:
                result = int(text)
            except ValueError:
                raise InvalidObservation() from None
            check(str(result) == text and abs(result) > EXACT_INTEGER)
            return result
        check(not text)
        if typ == "bool":
            check(value in (0, 1))
            return bool(value)
        if typ == "int":
            check(abs(value) <= EXACT_INTEGER and value == int(value))
            return int(value)
        check(typ == "float")
        return float(value)

    result = walk(SCHEMAS[kind], "root")
    check(not remaining)
    result = project(result, SCHEMAS[kind])
    check(digest(result) == expected_digest)
    return result
