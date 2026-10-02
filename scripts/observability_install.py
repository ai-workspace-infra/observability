#!/usr/bin/env python3
"""Standalone local installers backed by the canonical platform playbooks."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request

PLAYBOOKS_REF = '4a35679825b778d401eb9041face098c938ae449'


def truth(value):
    return str(value).lower() in ('1', 'true', 'yes', 'on')


def credentials(env):
    if env.get('VECTOR_AUTH_USER') and env.get('VECTOR_AUTH_PASSWORD'):
        return
    address, token = env.get('VAULT_ADDR', '').rstrip('/'), env.get('VAULT_TOKEN', '')
    path = env.get('VAULT_OBSERVABILITY_SECRET_PATH', 'kv/data/CICD/observability').strip('/')
    if not address.startswith('https://') or not token or '/data/' not in path:
        raise ValueError('Export monitoring credentials or HTTPS VAULT_ADDR, VAULT_TOKEN and a KV v2 path.')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = urllib.request.Request(address + '/v1/' + path, headers={'X-Vault-Token': token})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            data = json.load(response)['data']['data']
        env['VECTOR_AUTH_USER'], env['VECTOR_AUTH_PASSWORD'] = data['user'], data['password']
    except (urllib.error.URLError, KeyError, ValueError, TypeError):
        raise ValueError('Unable to read monitoring user/password from Vault.') from None


def plan(mode, env):
    node = env.get('OBSERVABILITY_NODE_NAME') or socket.gethostname()
    endpoint = env.get('OBSERVABILITY_ENDPOINT', 'https://observability.svc.plus').rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', node):
        raise ValueError('OBSERVABILITY_NODE_NAME must be a hostname without inventory pattern characters.')
    if not endpoint.startswith('https://'):
        raise ValueError('OBSERVABILITY_ENDPOINT must use HTTPS.')
    inventory = {'all': {'children': {'observability_local': {'hosts': {
        node: {'ansible_connection': 'local', 'ansible_python_interpreter': '/usr/bin/python3'}
    }}}}}
    common = {'vector_observability_endpoint': endpoint, 'vector_tls_verify': True,
              'vector_system_journald_enabled': True,
              'vector_observability_environment': env.get('DEPLOY_ENV', 'production'),
              'vector_observability_service_domain': node,
              'vector_local_observability_enabled': False}
    if mode == 'agent':
        # The generic host probe does not require or enroll an XConnect Agent.
        common.update(observability_agent_hosts='observability_local',
                      xray_exporter_hosts='observability_xray_disabled',
                      vector_xray_exporter_enabled=truth(env.get('OBSERVABILITY_XRAY_ENABLED', str(Path('/usr/local/bin/xray-exporter').exists()))),
                      vector_billing_ingest_enabled=truth(env.get('VECTOR_BILLING_INGEST_ENABLED', 'false')))
        return inventory, common, 'deploy_observability_agent.yml'
    domain = env.get('OBSERVABILITY_DOMAIN', 'observability.svc.plus')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}', domain):
        raise ValueError('OBSERVABILITY_DOMAIN must be a DNS name.')
    if not env.get('GRAFANA_ADMIN_PASSWORD'):
        raise ValueError('Export GRAFANA_ADMIN_PASSWORD from Vault before server deployment.')
    common.update(observability_server_hosts='observability_local',
                  observability_public_domain=domain, observability_mcp_enabled=False,
                  observability_exporters=[], observability_dir='/opt/observability-server',
                  observability_blackbox_host_port='9116')
    return inventory, common, 'deploy_observability_server.yml'


def overlay_server(repo):
    """Keep the pinned canonical stack; supply standalone domain and secrets."""
    import yaml
    role = repo / 'roles/docker/observability-server'
    compose = role / 'templates/docker-compose.yml.j2'
    text = compose.read_text()
    old = '- GF_SECURITY_ADMIN_PASSWORD=admin'
    if text.count(old) != 1:
        raise ValueError('Unsupported upstream Grafana template; refusing to use a default password.')
    text = text.replace(old, "- {{ ('GF_SECURITY_ADMIN_PASSWORD=' ~ lookup('ansible.builtin.env', 'GRAFANA_ADMIN_PASSWORD')) | to_json }}")
    text = text.replace('GF_SERVER_DOMAIN=observability.svc.plus', 'GF_SERVER_DOMAIN={{ observability_public_domain }}')
    text = text.replace('https://observability.svc.plus/grafana/', 'https://{{ observability_public_domain }}/grafana/')
    compose.write_text(text)
    caddy = role / 'templates/observability.caddy.j2'
    text = caddy.read_text().replace('observability.svc.plus {', '{{ observability_public_domain }} {', 1)
    text = text.replace('    # 自动走', '''    @ingest path /ingest/* /api/v1/write* /api/v1/import/* /insert/* /v1/metrics* /v1/logs* /v1/traces* /otlp/*
    basic_auth @ingest {
        {{ lookup('ansible.builtin.env', 'VECTOR_AUTH_USER') | to_json }} {{ standalone_ingest_password_hash }}
    }
    # 自动走''', 1)
    caddy.write_text(text)
    tasks = role / 'tasks/main.yml'
    data = yaml.safe_load(tasks.read_text())
    for task in data:
        if task.get('name') == 'Template Docker Compose and configs':
            task['ansible.builtin.template']['mode'] = '0600'
            task['no_log'] = True
    index = next(i for i, task in enumerate(data) if task.get('name') == 'Template Caddy configuration for observability')
    data[index:index] = [
        {'name': 'Hash standalone ingest credentials without command-line secrets',
         'ansible.builtin.command': {'argv': ['caddy', 'hash-password'],
                                    'stdin': "{{ lookup('ansible.builtin.env', 'VECTOR_AUTH_PASSWORD') }}"},
         'register': 'standalone_ingest_hash', 'changed_when': False, 'no_log': True},
        {'name': 'Resolve standalone ingest credential hash',
         'ansible.builtin.set_fact': {'standalone_ingest_password_hash': '{{ standalone_ingest_hash.stdout | trim }}'},
         'no_log': True}]
    tasks.write_text(yaml.safe_dump(data, sort_keys=False))


def run(argv, env):
    secrets = [env.get(k, '') for k in ('VAULT_TOKEN', 'VAULT_SERVER_ROOT_ACCESS_TOKEN',
                                      'VECTOR_AUTH_USER', 'VECTOR_AUTH_PASSWORD', 'GRAFANA_ADMIN_PASSWORD', 'INTERNAL_SERVICE_TOKEN')]
    process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        for secret in secrets:
            if secret:
                line = line.replace(secret, '<redacted>')
        print(line, end='', flush=True)
    process.stdout.close()
    if process.wait():
        raise RuntimeError('Deployment command failed: ' + argv[0])


def backup(mode):
    root = Path('/root/observability-backups') / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True, mode=0o700)
    root.parent.chmod(0o700)
    paths = ['/etc/vector', '/etc/default/vector'] if mode == 'agent' else [
        '/etc/caddy', '/opt/observability-server/docker-compose.yml', '/opt/observability-server/.env',
        '/opt/observability-server/grafana/provisioning']
    for name in paths:
        source, target = Path(name), root / name.lstrip('/')
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
    print('Configuration backup: ' + str(root), flush=True)


def verify(mode, env):
    if mode == 'agent':
        for service in ('node-exporter', 'process-exporter', 'blackbox', 'vector'):
            run(['systemctl', 'is-active', '--quiet', service], env)
        for port in (9100, 9256):
            run(['curl', '-fsS', '--max-time', '10', '-o', '/dev/null', f'http://127.0.0.1:{port}/metrics'], env)
        auth = base64.b64encode((env['VECTOR_AUTH_USER'] + ':' + env['VECTOR_AUTH_PASSWORD']).encode()).decode()
        endpoint = env.get('OBSERVABILITY_ENDPOINT', 'https://observability.svc.plus').rstrip('/')
        request = urllib.request.Request(endpoint + '/ingest/logs/insert/jsonline?_msg_field=message&_stream_fields=instance',
            data=(json.dumps({'message': 'observability standalone agent installation check',
                              'instance': env.get('OBSERVABILITY_NODE_NAME') or socket.gethostname()}) + '\n').encode(),
            headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/x-ndjson'}, method='POST')
        with urllib.request.urlopen(request, timeout=20):
            print('Authenticated log ingest accepted. Verify fresh node metrics/logs in the backend.')
    else:
        run(['caddy', 'validate', '--config', '/etc/caddy/Caddyfile'], env)
        # Canonical handler ignores reload errors, so explicitly require success.
        run(['systemctl', 'reload', 'caddy'], env)
        for url in ('http://127.0.0.1:3030/api/health', 'http://127.0.0.1:9090/health',
                    'http://127.0.0.1:9428/health', 'http://127.0.0.1:10428/health'):
            run(['curl', '-fsS', '--max-time', '15', '-o', '/dev/null', url], env)
        print('Core server health checks passed. Verify public DNS/TLS and external agent ingestion.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('server', 'agent'))
    args = parser.parse_args()
    env = dict(os.environ)
    inventory, variables, playbook = plan(args.mode, env)
    credentials(env)
    if truth(env.get('VECTOR_BILLING_INGEST_ENABLED', 'false')) and not (env.get('VECTOR_BILLING_INGEST_URL') and env.get('INTERNAL_SERVICE_TOKEN')):
        raise ValueError('Billing snapshots require VECTOR_BILLING_INGEST_URL and INTERNAL_SERVICE_TOKEN.')
    user, password = env['VECTOR_AUTH_USER'], env['VECTOR_AUTH_PASSWORD']
    if not all(isinstance(v, str) and v and '\n' not in v and '\r' not in v for v in (user, password)) or ':' in user:
        raise ValueError('Invalid monitoring user/password fields.')
    ref = env.get('OBSERVABILITY_PLAYBOOKS_REF', PLAYBOOKS_REF)
    if not re.fullmatch(r'[a-f0-9]{40}', ref):
        raise ValueError('OBSERVABILITY_PLAYBOOKS_REF must be an immutable full commit SHA.')
    if not shutil.which('ansible-playbook'):
        run(['apt-get', 'update'], env)
        run(['apt-get', 'install', '-y', '--no-install-recommends', 'ansible-core'], env)
    backup(args.mode)
    with tempfile.TemporaryDirectory(prefix='observability-install-') as tmp:
        root = Path(tmp)
        archive = root / 'playbooks.tar.gz'
        urllib.request.urlretrieve('https://github.com/ai-workspace-infra/playbooks/archive/' + ref + '.tar.gz', archive)
        repo = root / 'playbooks'
        repo.mkdir()
        with tarfile.open(archive) as bundle:
            if hasattr(tarfile, 'data_filter'):
                bundle.extractall(repo, filter='data')
            else:
                # Python 3.11 before the security backport: allow regular
                # files/directories only, and validate every destination.
                for member in bundle.getmembers():
                    target = (repo / member.name).resolve()
                    if repo.resolve() not in target.parents or not (member.isfile() or member.isdir()):
                        raise ValueError('Unsafe repository archive member.')
                bundle.extractall(repo)
        repo = next(p for p in repo.iterdir() if p.is_dir())
        if args.mode == 'server':
            overlay_server(repo)
        (root / 'inventory.json').write_text(json.dumps(inventory))
        (root / 'vars.json').write_text(json.dumps(variables))
        cfg = root / 'ansible.cfg'
        cfg.write_text('[defaults]\nroles_path=' + str(repo / 'roles') + '\nstdout_callback=default\nretry_files_enabled=False\n')
        env['ANSIBLE_CONFIG'] = str(cfg)
        run(['ansible-playbook', str(repo / playbook), '-i', str(root / 'inventory.json'),
             '--limit', next(iter(inventory['all']['children']['observability_local']['hosts'])),
             '--extra-vars', '@' + str(root / 'vars.json')], env)
    verify(args.mode, env)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, urllib.error.URLError):
        # Upstream exceptions can contain credential-bearing response data.
        print('Installation failed. Check required runtime variables, Vault access, deployment checks and configuration backup.', flush=True)
        raise SystemExit(1)
