# Observability.svc.plus

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-green.svg)](LICENSE)
[![Status: Stable](https://img.shields.io/badge/Status-Stable-blue)](https://svc.plus)

**Observability.svc.plus** is an observability solution strictly following the Apache 2.0 license.

> **Focus**: Monitoring & Observability (监控/可观测). Integrating OpenTelemetry (OTel), VictoriaMetrics, and DeepFlow-based network observability without long-term raw-flow lock-in.

[Website](https://svc.plus/) | [Public Demo](https://svc.plus/services) | [Blog](https://svc.plus/blogs) | [Support](https://www.svc.plus/support)

[![banner](files/img/observability-banner.jpg)](https://observability.svc.plus)

## 1) 概述

Observability.svc.plus provides a monitoring-focused stack for infrastructure and applications, centered on metrics, logs, and traces. It is designed for self-hosted, cloud-neutral operations with minimal vendor lock-in.

## 2) 架构图

```mermaid
flowchart LR
  A["Client Nodes<br/>node_exporter / process_exporter / vector"] --> B["OTel / Ingest Gateway"]
  B --> C["Metrics Store<br/>VictoriaMetrics"]
  B --> D["Logs Store<br/>Loki-compatible pipeline"]
  B --> E["Traces / OTel pipeline"]
  C --> F["Grafana"]
  D --> F
  E --> F
  F --> G["Dashboard & Alerting"]
```

## 3) Start

当前推荐按“混合部署到已有主机”的方式执行。

1. 先更新 DNS，把 `observability.svc.plus` 指到 `us-xhttp.svc.plus`
2. 在 `us-xhttp.svc.plus` 上执行下面的 Server side 示例，部署中心端
3. 再到其他已有主机执行下面的 Client side 示例，把采集数据回传到 `observability.svc.plus`

当前接入主机：

- `us-xhttp.svc.plus`：继续承载现有服务，同时承载 `observability.svc.plus`
- `openclaw.svc.plus`：部署 agent，采集后上报到中心端
- `jp-xhttp.svc.plus`：部署 agent，采集后上报到中心端

### 独立一键部署入口

以下两个入口只部署当前主机，适用于 **Debian 12+ / Ubuntu 24.04+（Python 3.11+）**，以 root 运行。它们复用固定 commit 的 [平台 playbooks](https://github.com/ai-workspace-infra/playbooks)，不运行旧的全栈初始化流程，也不修改 DNS。

先由 Vault 在当前 Shell 注入并导出 `VAULT_ADDR`、`VAULT_TOKEN`，或直接注入 `VECTOR_AUTH_USER`、`VECTOR_AUTH_PASSWORD`。脚本默认从 `kv/data/CICD/observability` 的 `user`、`password` 字段读取监控凭据；可用 `VAULT_OBSERVABILITY_SECRET_PATH` 覆盖 KV v2 路径。真实凭据不要写入脚本、命令行参数或仓库。

**服务端：** 在专用监控主机上运行，先将域名 DNS 指向该主机，并由 Vault 注入 `GRAFANA_ADMIN_PASSWORD`。

```bash
export OBSERVABILITY_DOMAIN="observability.svc.plus"
# VAULT_ADDR、VAULT_TOKEN、GRAFANA_ADMIN_PASSWORD 已由 Vault 注入并导出
curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/setup-observability-server.sh | bash
```

安装 Caddy、Docker、Grafana、VictoriaMetrics、VictoriaLogs、VictoriaTraces、OTel 和 Blackbox。写入入口开启 Basic Auth；Grafana 初始管理员密码使用运行时变量，已有 Grafana 用户密码仍以持久化数据库为准。默认关闭可选 MCP。配置先备份到 `/root/observability-backups/`，重跑保留 Compose 数据卷，不包含删除、重置或数据库迁移。

**探针：** 在每台被监控主机上运行，无需 Accounts 或 XConnect 节点 token。

```bash
export OBSERVABILITY_NODE_NAME="$(hostname -f)"
export OBSERVABILITY_ENDPOINT="https://observability.svc.plus"
export DEPLOY_ENV="production"
# VAULT_ADDR、VAULT_TOKEN 已由 Vault 注入并导出
curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/setup-observability-agent.sh | bash
```

安装 Node Exporter、Process Exporter、Blackbox 和 Vector，开启 TLS 校验及 systemd 日志采集，通过节点标签向中心端推送数据。它不安装或注册 XConnect Agent；已有 Xray Exporter 时保留其指标采集，可用 `OBSERVABILITY_XRAY_ENABLED=true/false` 覆盖。已有 Billing 快照链路需要继续提供 `VECTOR_BILLING_INGEST_ENABLED=true`、`VECTOR_BILLING_INGEST_URL` 和 `INTERNAL_SERVICE_TOKEN`，默认只安装监控。

两个脚本均支持 `--help`。服务端检查 Caddy 配置及核心服务健康，探针检查服务、本地指标和认证日志写入；失败返回非零。安装后仍需在中心端按 `instance` 验证新指标和日志，并验证服务端公网 DNS/TLS。完成后清理 Shell 中的凭据变量：

```bash
unset VAULT_TOKEN VECTOR_AUTH_USER VECTOR_AUTH_PASSWORD GRAFANA_ADMIN_PASSWORD INTERNAL_SERVICE_TOKEN
```

可用 `OBSERVABILITY_INSTALLER_REF` 固定本仓库完整 commit SHA，`OBSERVABILITY_PLAYBOOKS_REF` 固定平台 playbooks 完整 commit SHA。默认安装器跟随 main，平台 playbooks 固定在已验证的 `4a35679825b778d401eb9041face098c938ae449`；服务端的域名和凭据适配只作用于临时下载副本。

### Ansible (Recommended)

#### Server side

先导出 Cloudflare Token，然后在 `us-xhttp.svc.plus` 上执行服务端部署。`deploy_observability_service.yml` 会先把 Cloudflare 上的 `observability.svc.plus` 更新成指向 `us-xhttp.svc.plus` 的非代理记录，再等待公共 DNS 生效后继续部署，这样更容易保证 Caddy 首次自动签名成功。

```bash
export CLOUDFLARE_API_TOKEN=...
ansible-playbook -i <your-inventory> deploy_observability_service.yml -l us-xhttp.svc.plus
```

如果希望给 `/ingest/*` 增加一层基础认证，可以在服务端部署时一起打开：

```bash
export CLOUDFLARE_API_TOKEN=...
ansible-playbook -i <your-inventory> deploy_observability_service.yml -l us-xhttp.svc.plus \
  -e observability_ingest_basic_auth_enabled=true \
  -e observability_ingest_basic_auth_user=ingest \
  -e observability_ingest_basic_auth_password='<strong-password>'
```

#### Client side (agent)

再到采集端主机执行 `node.yml` 的 push mode：

```bash
ansible-playbook -i <your-inventory> node.yml \
  -l openclaw.svc.plus,jp-xhttp.svc.plus \
  -e node_monitor_mode=push \
  -e observability_endpoint=https://observability.svc.plus/
```

如果服务端已开启 ingest 基本认证，采集端也要带上同一组凭据：

```bash
ansible-playbook -i <your-inventory> node.yml \
  -l openclaw.svc.plus,jp-xhttp.svc.plus \
  -e node_monitor_mode=push \
  -e observability_endpoint=https://observability.svc.plus/ \
  -e observability_ingest_basic_auth_enabled=true \
  -e observability_ingest_basic_auth_user=ingest \
  -e observability_ingest_basic_auth_password='<strong-password>'
```

> `node_monitor_mode=push` 会在远端主机上部署 `node_exporter + process_exporter + vector`，并把 metrics / logs 主动汇总到 `observability.svc.plus`。`vector` 固定归到采集端任务，服务端 `infra.yml` 不再默认部署它。
>
> 如果采集端与 Victoria 服务端同机，playbook 会自动把 metrics / logs 改走本机 `127.0.0.1` ingest；跨主机时默认走 `https://observability.svc.plus/` 并自动补全 `/ingest/metrics/api/v1/write` 和 `/ingest/logs/insert`。
>
> `observability_ingest_basic_auth_*` 只保护 `/ingest/*` 写入入口，不影响 Caddy 暴露的其他站点页面；服务端和采集端必须使用同一组认证信息。

### Script Installers

### Server side

```bash
curl -fsSL "https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/scripts/setup-observability-all-in-one.sh?$(date +%s)" | bash -s -- observability.svc.plus
```

### Client side (agent)

```bash
# bash -s -- --endpoint <YOUR_ENDPOINT>
curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/scripts/agent-install.sh \
  | bash -s -- --endpoint https://observability.svc.plus/ingest/otlp
```

> **Note**
> - `--endpoint` supports both:
>   - `https://observability.svc.plus`
>   - `https://observability.svc.plus/ingest/otlp`
> - The installer auto-derives:
>   - metrics endpoint: `/ingest/metrics/api/v1/write`
>   - logs endpoint: `/ingest/logs/insert`
> - The script automatically verifies installation after setup.

macOS is supported as a user-level installation. It uses `launchd` and writes
under `~/Library/Application Support/observability`, so `sudo` is not needed:

```bash
curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/scripts/agent-install.sh \
  | bash -s -- --endpoint https://observability.svc.plus/ingest/otlp -y
```

The macOS installer collects Node Exporter and Process Exporter metrics plus
`/var/log` files, and sends them to the hosted VictoriaMetrics/VictoriaLogs
ingest endpoints. DeepFlow remains Linux/Kubernetes-only.

### Optional: DeepFlow Agent on Client

If you have deployed DeepFlow with `deepflow.yml`, you can install `deepflow-agent` on client nodes via the same script:

```bash
# example: endpoint exposed by caddy grpc ingress (deepflow_grpc_domain:443)
curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/scripts/agent-install.sh \
  | bash -s -- \
    --endpoint https://observability.svc.plus/ingest/otlp \
    --deepflow-agent \
    --deepflow-grpc-endpoint deepflow-agent.svc.plus:443 \
    --deepflow-agent-download-url https://example.com/path/to/deepflow-agent
```

> If `deepflow-agent` binary already exists on host, replace `--deepflow-agent-download-url` with `--deepflow-agent-bin /path/to/deepflow-agent`.

## 🚀 DeepFlow Deployment (Server Side)

This repo now provides dedicated DeepFlow roles:

- `deepflow_mysql`
- `deepflow_clickhouse_s3`
- `deepflow_server`
- `deepflow_connector`
- `deepflow_agent`

Quick start:

```bash
./configure -c deepflow/deepflow
vi pigsty.yml                  # adjust domain/password/ports
./deploy.yml
./docker.yml
./deepflow.yml
./infra.yml -t caddy           # apply deepflow_grpc_domain ingress
```

Default inventory template: `conf/deepflow/deepflow.yml`

### Lightweight Topology

- `deepflow-server` stays containerized with Docker Compose
- ClickHouse is kept as short-retention local storage
- MinIO/S3 is optional in lightweight mode
- `deepflow_connector` exports selected DeepFlow L4/L7 metrics to VictoriaMetrics
- `deepflow_agent` supports `binary/systemd`, `docker`, and rendered `k8s` manifests
- default `deepflow_agent_profile=lite` keeps `pcap` enabled and disables built-in `vector`

### Remote client example (openclaw.svc.plus)

```bash
ssh root@openclaw.svc.plus \
  'curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/scripts/agent-install.sh \
    | bash -s -- --endpoint https://observability.svc.plus/ingest/otlp'
```

### Remote client example (jp-xhttp.svc.plus)

```bash
ssh root@jp-xhttp.svc.plus \
  'curl -fsSL https://raw.githubusercontent.com/cloud-neutral-toolkit/observability.svc.plus/main/scripts/agent-install.sh \
    | bash -s -- --endpoint https://observability.svc.plus/ingest/otlp'
```

### Optional SSH manager env example

```bash
SSH_SERVER_CLAWBOT_HOST=openclaw.svc.plus
SSH_SERVER_CLAWBOT_USER=root
SSH_SERVER_CLAWBOT_KEYPATH=~/.ssh/id_rsa
SSH_SERVER_CLAWBOT_PORT=22
SSH_SERVER_CLAWBOT_DESCRIPTION=openclaw_server
```

## 4) Features

- **Observability First**: SOTA monitoring for PG / Infra / Node based on VictoriaMetrics, Grafana, and OpenTelemetry.
- **OTel Integration**: Native support for OpenTelemetry, facilitating unified trace, metric, and log ingestion.
- **DeepFlow Ready**: Lightweight DeepFlow server/agent deployment with short-lived flow storage and VictoriaMetrics archiving for high-value protocol metrics.
- **Reliable Base**: Robust self-healing HA clusters, PITR, and secure infrastructure.
- **Maintainable**: One-Cmd Deploy, IaC support, and easy customization.
- **Controllable**: Self-sufficient Cloud Neutral FOSS. Run on bare Linux.

## 5) License & Upstream

- **License**: [Apache-2.0](LICENSE)
- **Upstream references**:
  - [Pigsty](https://github.com/pgsty/pigsty)
  - [OpenTelemetry](https://opentelemetry.io/)
  - [VictoriaMetrics](https://victoriametrics.com/)
  - [Grafana](https://grafana.com/)

## 6) 致谢

感谢开源社区与所有贡献者，特别是 observability、database、DevOps 相关项目维护者与实践者。
