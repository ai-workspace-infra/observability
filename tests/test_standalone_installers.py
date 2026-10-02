import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install', ROOT / 'scripts/observability_install.py')
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class InstallerTests(unittest.TestCase):
    def test_agent_plan_is_local_and_has_no_accounts_requirement(self):
        inventory, variables, name = install.plan('agent', {'OBSERVABILITY_NODE_NAME': 'node.example.test'})
        hosts = inventory['all']['children']['observability_local']['hosts']
        self.assertEqual(list(hosts), ['node.example.test'])
        self.assertEqual(hosts['node.example.test']['ansible_connection'], 'local')
        self.assertEqual(name, 'deploy_observability_agent.yml')
        self.assertTrue(variables['vector_tls_verify'])
        self.assertTrue(variables['vector_system_journald_enabled'])
        self.assertNotIn('INTERNAL_SERVICE_TOKEN', json.dumps(variables))

    def test_server_requires_runtime_password_and_valid_domain(self):
        with self.assertRaises(ValueError):
            install.plan('server', {})
        with self.assertRaises(ValueError):
            install.plan('server', {'GRAFANA_ADMIN_PASSWORD': 'test-only', 'OBSERVABILITY_DOMAIN': 'bad { domain'})
        _, variables, name = install.plan('server', {'GRAFANA_ADMIN_PASSWORD': 'test-only',
                                                    'OBSERVABILITY_DOMAIN': 'metrics.example.test'})
        self.assertEqual(name, 'deploy_observability_server.yml')
        self.assertEqual(variables['observability_public_domain'], 'metrics.example.test')
        self.assertNotIn('test-only', json.dumps(variables))

    def test_patterns_and_plaintext_endpoints_are_rejected(self):
        for env in ({'OBSERVABILITY_NODE_NAME': 'all:prod'}, {'OBSERVABILITY_ENDPOINT': 'http://example.test'}):
            with self.assertRaises(ValueError):
                install.plan('agent', env)

    def test_shell_help_is_read_only(self):
        for mode in ('server', 'agent'):
            result = subprocess.run(['bash', str(ROOT / f'setup-observability-{mode}.sh'), '--help'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('Standalone observability', result.stdout)

    def test_command_failure_propagates_and_secrets_are_redacted(self):
        with patch('builtins.print') as output:
            with self.assertRaises(RuntimeError):
                install.run(['bash', '-c', 'echo "$VECTOR_AUTH_PASSWORD"; exit 7'],
                            dict(os.environ, VECTOR_AUTH_PASSWORD='test-only-secret'))
        self.assertIn('<redacted>', str(output.call_args_list))
        self.assertNotIn('test-only-secret', str(output.call_args_list))

    def test_server_overlay_removes_default_password_and_authenticates_ingest(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            role = repo / 'roles/docker/observability-server'
            (role / 'templates').mkdir(parents=True)
            (role / 'tasks').mkdir()
            (role / 'templates/docker-compose.yml.j2').write_text('- GF_SECURITY_ADMIN_PASSWORD=admin\n- GF_SERVER_DOMAIN=observability.svc.plus\n- GF_SERVER_ROOT_URL=https://observability.svc.plus/grafana/\n')
            (role / 'templates/observability.caddy.j2').write_text('observability.svc.plus {\n    # 自动走 certificates\n}\n')
            (role / 'tasks/main.yml').write_text(yaml.safe_dump([
                {'name': 'Template Docker Compose and configs', 'ansible.builtin.template': {'mode': '0644'}},
                {'name': 'Template Caddy configuration for observability'}]))
            install.overlay_server(repo)
            compose = (role / 'templates/docker-compose.yml.j2').read_text()
            self.assertNotIn('GF_SECURITY_ADMIN_PASSWORD=admin', compose)
            self.assertIn('GRAFANA_ADMIN_PASSWORD', compose)
            self.assertIn('basic_auth @ingest', (role / 'templates/observability.caddy.j2').read_text())
            tasks = yaml.safe_load((role / 'tasks/main.yml').read_text())
            self.assertTrue(tasks[0]['no_log'])
            self.assertEqual(tasks[0]['ansible.builtin.template']['mode'], '0600')
            self.assertTrue(tasks[1]['no_log'])
            self.assertIn('stdin', tasks[1]['ansible.builtin.command'])


if __name__ == '__main__':
    unittest.main()
