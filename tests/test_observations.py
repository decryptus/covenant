"""Complete observation codec and new optional collectors; synthetic only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from prometheus_client.parser import text_string_to_metric_families
from covenant.services.observation_codec import encode, decode, MAX_ROWS
from covenant.services.observations import snapshot_metrics
from covenant.plugins.observations import CovenantMonitObservationPlugin, CovenantCertlordObservationPlugin
from covenant.classes.plugins import EPTS_SYNC
from test_certlord import request


def payload(kind):
    if kind=='monit':
        return dict(api_version=1,ready=True,running=True,last_cycle_success=True,cycles_total=2**54+1,
            errors_total=0,age_seconds=1,last_success_at=100,last_cycle_finished_at=100,
            containers=[dict(id='a'*64,name='fixture',status='running',health='none',cpu_percent=0.0,
                filesystems=[dict(group='data',path='/data',fs_readable=0,fs_writable=1)])])
    return dict(schema_version=1,started_at='2026-10-01T00:00:00+00:00',completed_at='2026-10-01T00:00:01+00:00',
        completed_timestamp_seconds=1790812801,certificates=[dict(certificate_id='12345678-1234-4234-8234-123456789abc',
            domains=['example.test','*.example.test'],version=2**54+1,fingerprint_sha256='a'*64,
            verification=dict(status='failed',checked_at='2026-10-01T00:00:00+00:00',error_code='timeout'),
            observed_at='2026-10-01T00:00:00+00:00')])


class ObservationTests(unittest.TestCase):
    def setUp(self):
        previous=EPTS_SYNC.copy()
        self.addCleanup(lambda:(EPTS_SYNC.clear(),EPTS_SYNC.update(previous)))

    def test_actual_prometheus_serialization_round_trip_and_types(self):
        for kind in ('monit','certlord'):
            raw=payload(kind);expected,sha=encode(raw,kind)
            output=snapshot_metrics(json.dumps(raw),kind,101,.5).decode()
            rows=[];manifest=None
            for family in text_string_to_metric_families(output):
                for sample in family.samples:
                    if sample.name.endswith('_value'):
                        rows.append((sample.labels['path'],sample.labels['type'],sample.labels['text'],sample.value))
                    if sample.name.endswith('_manifest'):manifest=sample.labels['sha256']
            self.assertEqual(encode(decode(rows,kind,manifest),kind),(expected,sha))

    def test_allowlist_never_exports_unknown_fields_material_or_credentials(self):
        for kind in ('monit','certlord'):
            raw=payload(kind);raw['private']='secret'
            raw['containers' if kind=='monit' else 'certificates'][0].update(cert='PRIVATE PEM',password='secret')
            output=snapshot_metrics(json.dumps(raw),kind,101,0)
            self.assertNotIn(b'secret',output);self.assertNotIn(b'PRIVATE PEM',output)

    def test_duplicate_json_keys_nonfinite_and_bounded_data_fail(self):
        for text in ('{"containers":[],"containers":[]}','{"api_version":NaN}', 'x'*(4*1024*1024+1)):
            with self.assertRaises(ValueError):snapshot_metrics(text,'monit',101,0)
        raw=payload('monit');raw['containers']*=500
        with self.assertRaises(ValueError):encode(raw,'monit')

    def test_digest_detects_omissions_duplicates_and_value_corruption(self):
        rows,sha=encode(payload('monit'),'monit')
        for bad in (rows[:-1],rows+[rows[-1]],rows[:-1]+[(rows[-1][0],rows[-1][1],rows[-1][2],7)]):
            with self.assertRaises(ValueError):decode(bad,'monit',sha)

    def test_optional_plugins_fixed_get_failure_and_recovery(self):
        for kind,cls in (('monit',CovenantMonitObservationPlugin),('certlord',CovenantCertlordObservationPlugin)):
            collector=cls(kind+'-test');collector.init(dict(general=dict(result_timeout=30,server_id='test'),
                covenant=dict(config_dir='/tmp'),metrics=[dict(name=kind,config=dict(url='http://127.0.0.1:9876/observations',timeout=1),collects=[])]));collector.safe_init()
            with patch('covenant.plugins.certlord.requests.Session') as factory:
                session=factory.return_value.__enter__.return_value
                response=session.get.return_value.__enter__.return_value
                response.status_code=200;response.iter_content.return_value=[json.dumps(payload(kind)).encode()]
                self.assertIn(b'_observation_up 1',collector._do_call(request()))
                self.assertEqual(session.get.call_args.kwargs['headers']['Accept'],'application/json')
                self.assertFalse(session.trust_env);self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
                for status in (302,401,403,503):
                    response.status_code=status;output=collector._do_call(request())
                    self.assertIn(b'_observation_up 0',output);self.assertNotIn(b'_observation_value',output)
                response.status_code=200
                self.assertIn(b'_observation_up 1',collector._do_call(request()))

    def test_real_yaml_workers_and_httpdis_for_both_plugins(self):
        import covenant
        env=dict(os.environ,PYTHONPATH=str(Path(covenant.__file__).resolve().parents[1]))
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('observations_runtime.py'))],capture_output=True,text=True,timeout=25,env=env)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Complete observations runtime integration OK',result.stdout)
