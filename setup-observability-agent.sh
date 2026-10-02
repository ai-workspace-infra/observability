#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "${1:-}" = --help ] || [ "${1:-}" = -h ]; then
    cat <<'HELP'
Standalone observability agent installer (root, Debian/Ubuntu, Python >= 3.11).
Export VECTOR_AUTH_USER/VECTOR_AUTH_PASSWORD or VAULT_ADDR/VAULT_TOKEN.
Server additionally requires GRAFANA_ADMIN_PASSWORD; OBSERVABILITY_DOMAIN is optional.
Agent accepts OBSERVABILITY_NODE_NAME, OBSERVABILITY_ENDPOINT and DEPLOY_ENV.
Optional: OBSERVABILITY_INSTALLER_REF and OBSERVABILITY_PLAYBOOKS_REF (full commit SHA).
Run without arguments. Configurations are backed up; data volumes are retained.
HELP
    exit 0
fi
[ "$#" -eq 0 ] || { echo 'Use exported runtime variables; see --help.' >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo 'Run as root on the target host.' >&2; exit 1; }
. /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) echo 'Debian or Ubuntu is required.' >&2; exit 1;; esac
if ! command -v python3 >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends python3 ca-certificates
fi
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python >= 3.11 required (Debian 12+/Ubuntu 24.04+)"'
ref="${OBSERVABILITY_INSTALLER_REF:-main}"
if [ "$ref" != main ] && [[ ! "$ref" =~ ^[a-f0-9]{40}$ ]]; then
    echo 'OBSERVABILITY_INSTALLER_REF must be main or a full commit SHA.' >&2; exit 1
fi
tmp="$(mktemp -d /tmp/observability-bootstrap.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 3 --connect-timeout 10 \
    "https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/${ref}/scripts/observability_install.py" \
    -o "$tmp/install.py"
python3 "$tmp/install.py" agent
