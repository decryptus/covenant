"""Synthetic TLS observations: UTC, SAN-only identities and verified peers."""
import calendar
from datetime import datetime, timedelta, timezone
import os
import socket
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from covenant.plugins.pssl import CovenantSslPlugin


class TLSObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.start = datetime(2026, 1, 1)
        cls.end = datetime(2027, 1, 1)

    def certificate(self, name=True):
        subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'example.test')]) if name else x509.Name([])
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(self.key.public_key()).serial_number(1)
                .not_valid_before(self.start).not_valid_after(self.end)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('example.test')]), critical=False)
                .sign(self.key, hashes.SHA256()).public_bytes(serialization.Encoding.DER))

    def test_certificate_timestamps_do_not_depend_on_process_timezone(self):
        old = os.environ.get('TZ')
        try:
            for zone in ('UTC', 'Asia/Makassar', 'America/Los_Angeles'):
                os.environ['TZ'] = zone
                time.tzset()
                result = CovenantSslPlugin._load_cert(self.certificate())[1]
                self.assertEqual(result['cert_not_before'], calendar.timegm(self.start.utctimetuple()), zone)
                self.assertEqual(result['cert_not_after'], calendar.timegm(self.end.utctimetuple()), zone)
        finally:
            if old is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = old
            time.tzset()

    def test_san_only_certificate_is_observable_without_inventing_common_name(self):
        cert, result = CovenantSslPlugin._load_cert(self.certificate(False))
        self.assertTrue(result['connect_success'])
        self.assertIsNone(result['cert_cn'])
        self.assertIsNone(result['cert_issuer_cn'])
        plugin = CovenantSslPlugin('san-only')
        result, names = plugin._subject_alt_name(cert, result, {'subject': [], 'subjectAltName': []})
        self.assertTrue(plugin._valid_hostname(names, 'example.test'))

    def _peer_result(self, second_hostname):
        # The inspection and validation handshakes may reach different peers.
        ca_name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'Synthetic CA')])
        now = datetime.now(timezone.utc)
        ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
              .public_key(self.key.public_key()).serial_number(10)
              .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
              .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
              .sign(self.key, hashes.SHA256()))
        errors, rows = [], []
        with tempfile.TemporaryDirectory() as directory:
            key_path = os.path.join(directory, 'key.pem')
            with open(key_path, 'wb') as stream:
                stream.write(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            contexts = []
            for serial, hostname in enumerate(('example.test', second_hostname), 11):
                name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, hostname)])
                cert = (x509.CertificateBuilder().subject_name(name).issuer_name(ca_name)
                        .public_key(self.key.public_key()).serial_number(serial)
                        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
                        .sign(self.key, hashes.SHA256()))
                filename = os.path.join(directory, str(serial) + '.pem')
                with open(filename, 'wb') as stream:
                    stream.write(cert.public_bytes(serialization.Encoding.PEM))
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(filename, key_path)
                contexts.append(context)
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            listener.listen(2)
            listener.settimeout(5)
            port = listener.getsockname()[1]

            def serve():
                try:
                    for context in contexts:
                        raw, _ = listener.accept()
                        raw.settimeout(5)
                        try:
                            with context.wrap_socket(raw, server_side=True) as conn:
                                conn.recv(1)
                        except OSError:
                            raw.close()  # Expected rejection of the second peer.
                except Exception as error:
                    errors.append(type(error).__name__)
                finally:
                    listener.close()

            worker = threading.Thread(target=serve)
            worker.start()
            original_context = ssl.create_default_context

            def trusted_context():
                return original_context(cadata=ca.public_bytes(serialization.Encoding.PEM).decode('ascii'))

            class Target:
                name = 'synthetic'
                config = {'uri': 'https://127.0.0.1:' + str(port), 'common_name': 'example.test', 'timeout': 2}
                def __call__(self, data):
                    rows.append(data)

            class Request:
                def get_params(self):
                    return {}

            try:
                with patch('covenant.plugins.pssl.ssl.create_default_context', side_effect=trusted_context):
                    CovenantSslPlugin('peer-change')._do_call(Request(), targets=[Target()])
            finally:
                worker.join(6)
                listener.close()
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(rows), 1)
            return rows[0]

    def test_verified_connection_rejects_different_trusted_hostname(self):
        result = self._peer_result('other.test')
        self.assertFalse(result['cert_secure'])
        self.assertFalse(result['metric_success'])

    def test_verified_connection_accepts_current_trusted_hostname(self):
        result = self._peer_result('example.test')
        self.assertTrue(result['cert_secure'])
        self.assertTrue(result['metric_success'])

    def test_failed_handshake_closes_owned_socket(self):
        conn = Mock()
        conn.connect.side_effect = ssl.SSLError('synthetic handshake failure')
        context = Mock()
        context.wrap_socket.return_value = conn
        with patch('covenant.plugins.pssl.socket.socket'):
            with self.assertRaises(ssl.SSLError):
                CovenantSslPlugin._connect(context, '127.0.0.1', 443, 'example.test', socket.AF_INET, 1)
        conn.close.assert_called_once_with()

    def test_failed_shutdown_still_closes_owned_socket(self):
        conn = Mock()
        conn.shutdown.side_effect = OSError('synthetic disconnected peer')
        CovenantSslPlugin._close(conn)
        conn.close.assert_called_once_with()
