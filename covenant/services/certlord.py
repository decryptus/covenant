# -*- coding: utf-8 -*-
# Copyright (C) 2026 Adrien Delle Cave
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate a complete CertLord metrics snapshot without retaining old samples."""
import math
import uuid

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.parser import text_string_to_metric_families

PREFIX = 'certlord_'
SCHEMA = {
    'observation_completed_timestamp_seconds': (),
    'certificates_observed': (),
    'certificate_info': ('certificate_id', 'origin', 'renewal_owner', 'status',
                         'pending_action', 'material_state'),
    'certificate_not_after_timestamp_seconds': ('certificate_id',),
    'certificate_issuance_retry_count': ('certificate_id',),
    'certificate_tls_verification': ('certificate_id', 'status'),
    'certificate_tls_verified_at_timestamp_seconds': ('certificate_id',),
}
LABEL_VALUES = {
    'origin': ('external', 'acme', 'provider-managed', 'unknown'),
    'renewal_owner': ('external', 'acme', 'provider-managed', 'unknown'),
    'material_state': ('readable', 'missing', 'invalid'),
    'pending_action': ('create', 'exists', 'invalid-dns', 'delete', 'renew',
                       'processing', 'generated', 'deployed', 'none', 'unknown'),
    'status': ('create', 'exists', 'invalid-dns', 'delete', 'renew',
               'processing', 'generated', 'deployed', 'unknown'),
}
TLS_STATES = ('verified', 'failed', 'not_checked')
MAX_BYTES = 4 * 1024 * 1024


class InvalidObservation(ValueError):
    """An incomplete or unsupported observation must not appear healthy."""


def snapshot_metrics(text):
    """Return sanitized gauges; never forward arbitrary HELP, labels or metrics."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        raise InvalidObservation('Invalid observation size')
    samples = {}
    families = []
    seen_families = set()
    for family in text_string_to_metric_families(text):
        key = family.name[len(PREFIX):] if family.name.startswith(PREFIX) else None
        if key not in SCHEMA:
            continue
        if key in seen_families or family.type != 'gauge':
            raise InvalidObservation('Invalid metric family')
        seen_families.add(key)
        output = GaugeMetricFamily(PREFIX + key, 'CertLord lifecycle observation.',
                                   labels=SCHEMA[key])
        rows = samples.setdefault(key, {})
        for sample in family.samples:
            labels = sample.labels
            if (sample.name != PREFIX + key or set(labels) != set(SCHEMA[key])
                    or sample.timestamp is not None or not math.isfinite(sample.value)):
                raise InvalidObservation('Invalid metric sample')
            identity = labels.get('certificate_id', '')
            if 'certificate_id' in labels and str(uuid.UUID(identity)) != identity:
                raise InvalidObservation('Invalid certificate identity')
            if identity in rows:
                raise InvalidObservation('Duplicate certificate sample')
            for name, value in labels.items():
                allowed = TLS_STATES if key == 'certificate_tls_verification' and name == 'status' else LABEL_VALUES.get(name)
                if allowed is not None and value not in allowed:
                    raise InvalidObservation('Invalid lifecycle label')
            if key in ('certificate_info', 'certificate_tls_verification') and sample.value != 1:
                raise InvalidObservation('Invalid information gauge')
            if key in ('certificates_observed', 'certificate_issuance_retry_count') and (
                    sample.value < 0 or not sample.value.is_integer()):
                raise InvalidObservation('Invalid count')
            rows[identity] = (labels, sample.value)
            output.add_metric([labels[name] for name in SCHEMA[key]], sample.value)
        families.append(output)
    for key in ('observation_completed_timestamp_seconds', 'certificates_observed'):
        if set(samples.get(key, {})) != {''}:
            raise InvalidObservation('Missing collection metadata')
    info = samples.get('certificate_info', {})
    if samples['certificates_observed'][''][1] != len(info):
        raise InvalidObservation('Incomplete certificate inventory')
    for key, rows in samples.items():
        if SCHEMA[key] and not set(rows).issubset(info):
            raise InvalidObservation('Unknown certificate reference')
    readable = {identity for identity, (labels, _) in info.items()
                if labels['material_state'] == 'readable'}
    if set(samples.get('certificate_not_after_timestamp_seconds', {})) != readable:
        raise InvalidObservation('Incomplete expiry observations')
    retry = {identity for identity, (labels, _) in info.items()
             if labels['renewal_owner'] == 'acme' and labels['pending_action'] in ('create', 'renew')}
    if set(samples.get('certificate_issuance_retry_count', {})) != retry:
        raise InvalidObservation('Incomplete retry observations')
    if set(samples.get('certificate_tls_verification', {})) != set(info):
        raise InvalidObservation('Incomplete TLS observations')
    verified = {identity for identity, (labels, _) in samples.get('certificate_tls_verification', {}).items()
                if labels['status'] == 'verified'}
    if set(samples.get('certificate_tls_verified_at_timestamp_seconds', {})) != verified:
        raise InvalidObservation('Incomplete TLS verification times')
    registry = CollectorRegistry()
    class Snapshot:
        def collect(self):
            return iter(families)
    registry.register(Snapshot())
    return generate_latest(registry)
