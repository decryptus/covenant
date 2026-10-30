# SPDX-License-Identifier: GPL-3.0-or-later
"""Export a bounded, allowlisted JSON observation without cached values."""
import json
import math
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from covenant.services.observation_codec import MAX_BYTES, VERSION, check, encode


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        check(key not in result)
        result[key] = value
    return result


def snapshot_metrics(text, kind, collected_at, elapsed):
    check(type(text) is str and len(text.encode('utf-8')) <= MAX_BYTES)
    check(all(type(x) in (int, float) and math.isfinite(x) and x >= 0
              for x in (collected_at, elapsed)))
    payload = json.loads(text, object_pairs_hook=_unique_object)
    rows, digest = encode(payload, kind)
    prefix = 'covenant_' + kind + '_observation_'
    values = GaugeMetricFamily(prefix + 'value', 'Typed observation field.', labels=('path', 'type', 'text'))
    for path, typ, label, value in rows:
        values.add_metric((path, typ, label), value)
    manifest = GaugeMetricFamily(prefix + 'manifest', 'Complete schema-one observation.', labels=('sha256', 'version'))
    manifest.add_metric((digest, str(VERSION)), len(rows))
    families = (values, manifest,
                GaugeMetricFamily(prefix + 'collected_at_seconds', 'Collection completion time.', value=collected_at),
                GaugeMetricFamily(prefix + 'collection_elapsed_seconds', 'Source read duration.', value=elapsed))
    class Snapshot:
        def collect(self):
            return iter(families)
    registry = CollectorRegistry()
    registry.register(Snapshot())
    output = generate_latest(registry)
    check(len(output) <= MAX_BYTES)
    return output
