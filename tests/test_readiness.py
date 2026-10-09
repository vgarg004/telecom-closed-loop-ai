import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.api.app import create_app


class ReadinessTests(unittest.TestCase):
    def test_readiness_reports_database_and_evidence_failures(self):
        with TemporaryDirectory() as directory:
            app = create_app(database_path=Path(directory) / 'state.db')
            with TestClient(app) as client:
                self.assertEqual(client.get('/health/ready').status_code, 200)
                with patch.object(app.state.incidents, 'check_health', side_effect=OSError('private detail')):
                    response = client.get('/health/ready')
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn('private detail', response.text)
                    self.assertEqual(client.get('/health').status_code, 200)
            app = create_app(data_dir=directory, database_path=Path(directory) / 'state.db')
            with TestClient(app) as client:
                self.assertEqual(client.get('/health/ready').status_code, 503)

    def test_weak_and_ambiguous_evidence_cannot_authorize_actions(self):
        with TemporaryDirectory() as directory:
            app = create_app(data_dir='tests/fixtures/rca_safety',
                             database_path=Path(directory) / 'state.db',
                             audit_path=Path(directory) / 'audit.jsonl', api_key='test-key')
            with TestClient(app) as client:
                for cell in ('weak_latency', 'weak_radio', 'weak_config', 'weak_congestion',
                             'ambiguous', 'contradictory_alarm', 'contradictory_causes'):
                    with self.subTest(cell=cell):
                        response = client.post('/api/incidents', headers={'X-API-Key': 'test-key'}, json={
                            'cell_id': cell, 'start_time': '2026-08-01 10:00:00',
                            'end_time': '2026-08-01 11:00:00'})
                        self.assertEqual(response.status_code, 200)
                        incident = response.json()['incident_id']
                        self.assertEqual(client.post(f'/api/incidents/{incident}/actions',
                                         headers={'X-API-Key': 'test-key'}).status_code, 409)
                        self.assertEqual(app.state.incidents.list_actions(incident), [])
