"""XYS configuration structure checks, without loading or initializing services."""
from sonicprobe.libs import xys
from covenant.classes.exceptions import CovenantConfigurationError


xys.add_callback('covenant.config.mapping', lambda value: isinstance(value, dict))
MAPPING = '!~~callback(covenant.config.mapping) null'
MAPPING_SCHEMA = xys.load(MAPPING)


def validate_fields(data, schema):
    # Unknown fields belong to extensions. Never use a wildcard that could consume
    # known optional fields before their XYS validators run.
    if not isinstance(data, dict) or not xys.validate(
            {key: value for key, value in data.items() if key in schema}, schema):
        raise CovenantConfigurationError('Invalid configuration structure')
    return data



CONFIG_SCHEMA = xys.load('''
general: %s
endpoints*: %s
modules*: %s
''' % (MAPPING, MAPPING, MAPPING))
ENDPOINT_SCHEMA = xys.load('''
plugin![1,]: !!str
vars?: %s
metrics?: [ !!any ]
probes?: [ !!any ]
import_vars*: !!str
import_metrics*: !!str
import_probes*: !!str
''' % MAPPING)
COMPONENT_SCHEMAS = {'vars': MAPPING_SCHEMA,
                     'metrics': xys.load('[ !!any ]'),
                     'probes': xys.load('[ !!any ]')}


def validate_configuration(conf):
    validate_fields(conf, CONFIG_SCHEMA)
    for definition in (conf.get('endpoints') or {}).values():
        validate_fields(definition, ENDPOINT_SCHEMA)
    return conf


def validate_component(data, kind):
    if not xys.validate(data, COMPONENT_SCHEMAS[kind]):
        raise CovenantConfigurationError('Invalid imported endpoint component')
    return data
