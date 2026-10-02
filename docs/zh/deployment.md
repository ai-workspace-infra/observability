# 部署与接入指南

本文按两个操作区域组织：先部署 Observability 中心服务，再把主机探针接入中心端。

## 部署 Observability

### 环境要求

在中心服务主机以 root 执行，支持 Debian 12+ / Ubuntu 24.04+ 与 Python 3.11+。主机需能访问 GitHub、系统软件源和所需监控服务端点；部署前准备公网 DNS 与 Caddy 获取 TLS 证书所需的网络条件。

### Vault 与认证

Vault 配置通过当前 Shell 环境提供：

```bash
export VAULT_ADDR="https://<vault-host>"
export VAULT_OBSERVABILITY_SECRET_PATH="kv/data/CICD/observability"
# VAULT_TOKEN 由 Vault Agent 或受控运行环境安全注入
```

监控账号默认为 KV v2 `kv/data/CICD/observability` 中的 `user`、`password`。这组值用于 Caddy 写入入口的 HTTP Basic Auth；也可使用 `VAULT_OBSERVABILITY_SECRET_PATH` 指向另一 KV v2 `/data/` 路径。不要用 `env` 或 `set` 回显秘密值，也不要把 Vault Token 写入命令参数、脚本或仓库。

若 `VAULT_ADDR`、`VAULT_TOKEN`、`VAULT_TLS_SECRET_PATH` 均未设置，且未直接提供 `VECTOR_AUTH_USER`、`VECTOR_AUTH_PASSWORD`，Server 安装器会生成随机监控账号，仅在部署和健康检查成功后于终端显示一次。它不会把生成的明文账号写入中心端文件或 Ansible 日志；请当场安全保存。Vault 变量只配置一部分时安装器会报错，不会自动创建另一套账号。`VAULT_TLS_SECRET_PATH` 用于代理 TLS 证书秘密，不替代监控账号路径。

服务端另需 `GRAFANA_ADMIN_PASSWORD`，可由 Vault Agent 注入，也可在 Shell 中隐藏输入。此值用于首次初始化 Grafana；已有 Grafana 管理员密码保存在持久化数据库中，不会因重跑安装器而自动变更。

### 安装中心服务

```bash
read -rsp "Grafana admin password: " GRAFANA_ADMIN_PASSWORD
printf '\n'
export GRAFANA_ADMIN_PASSWORD
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-server.sh | bash
unset GRAFANA_ADMIN_PASSWORD VAULT_TOKEN
```

域名默认是 `observability.svc.plus`，可用 `OBSERVABILITY_DOMAIN` 覆盖。服务端安装器备份现有配置、部署后验证 Caddy 与 Grafana、指标、日志和追踪服务健康；不修改 DNS，也不删除 Compose 数据卷。服务启动成功之后，还需从公网检查 DNS/TLS，并确认外部探针数据到达中心端。

## 接入 Observability Agent

### 认证与运行参数

探针通过 HTTPS 向 Caddy 上报指标和日志。它必须使用中心端相同的 `user`、`password`：默认从 Vault 同一路径读取，也可由当前 Shell 直接注入 `VECTOR_AUTH_USER`、`VECTOR_AUTH_PASSWORD`。若中心端用了自动生成的账号，需从服务端部署终端取出这组值，并在探针部署时安全输入；Agent 不会自行生成另一组凭据。

Vector 运行时需要在探针本机配置中保留 Basic Auth 凭据，请将配置权限限制为 root 可读。探针数据使用标签区分节点与部署环境：

| 变量 | 用途 / 默认值 |
| --- | --- |
| `OBSERVABILITY_NODE_NAME` | 节点名，默认系统主机名 |
| `OBSERVABILITY_ENDPOINT` | 中心端 HTTPS 地址，默认 `https://observability.svc.plus` |
| `DEPLOY_ENV` | 环境标签，默认 `production` |
| `OBSERVABILITY_XRAY_ENABLED` | 覆盖已有 Xray Exporter 采集开关；不安装 Xray |
| `OBSERVABILITY_INSTALLER_REF` | 安装器版本，默认 `main`，可指定完整 commit SHA |
| `OBSERVABILITY_PLAYBOOKS_REF` | Playbooks 完整 commit SHA；使用经验证的默认版本 |

Billing 快照默认关闭。若需保留既有 Billing 快照链路，还需提供 `VECTOR_BILLING_INGEST_ENABLED=true`、`VECTOR_BILLING_INGEST_URL` 和运行时 `INTERNAL_SERVICE_TOKEN`。

### 安装探针

已通过 Vault 注入凭据时：

```bash
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-agent.sh | bash
unset VAULT_TOKEN
```

若中心服务使用自动生成的凭据，可在当前 Shell 隐藏输入后部署：

```bash
read -rp "Caddy Basic Auth user: " VECTOR_AUTH_USER
read -rsp "Caddy Basic Auth password: " VECTOR_AUTH_PASSWORD
printf '\n'
export VECTOR_AUTH_USER VECTOR_AUTH_PASSWORD
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-agent.sh | bash
unset VECTOR_AUTH_USER VECTOR_AUTH_PASSWORD VAULT_TOKEN
```

安装器验证 Node Exporter、Process Exporter、Blackbox、Vector 服务、本机指标及认证日志写入。安装后还要在 Grafana 按节点检查指标和日志是否持续更新；本地服务健康不等于中心端完成接收验收。

## 安装帮助

```bash
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-server.sh | bash -s -- --help
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-agent.sh | bash -s -- --help
```

## Grafana 认证说明

Grafana 当前 VictoriaMetrics 数据源通过 Docker 内网地址 `http://victoria-metrics:8428` 查询，认证方式是 `No Authentication`，因此查询指标不需要额外 Auth Token。探针写入 Caddy 使用上述 HTTP Basic Auth 凭据。Grafana Service Account Token 仅供可选 Grafana MCP 使用，路径为 Vault KV v2 `kv/data/observability/mcp`，字段为 `GRAFANA_SERVICE_ACCOUNT_TOKEN`；独立安装入口默认关闭 MCP。

## 验证与恢复

安装器在 `/root/observability-backups/` 备份已有配置，不删除或重置数据库卷。若部署失败，保留该备份并检查目标主机服务日志；安装器不会自动回滚数据库或完成数据迁移。正式验收需分别确认服务进程、TLS、指标数据与日志新鲜度。
