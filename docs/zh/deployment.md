# 部署与验证

## 准备

在目标主机以 root 执行，要求 Debian 12+ / Ubuntu 24.04+ 与 Python 3.11+，并能访问 GitHub、系统软件源和监控端点。安装器按需安装 Python、Ansible 及部署依赖。服务端应先完成公网 DNS 指向与 TLS 所需网络条件。

安装前由 Vault Agent 或受控 Shell 环境注入 `VAULT_TOKEN`，并在当前 Shell 导出 Vault 地址与监控秘密路径。Vault Token 需要读取监控 KV v2 秘密的权限。默认从 `kv/data/CICD/observability` 读取 `user`、`password` 作为探针写入凭据；可用 `VAULT_OBSERVABILITY_SECRET_PATH` 指定其他 KV v2 `/data/` 路径。也可直接注入 `VECTOR_AUTH_USER` 和 `VECTOR_AUTH_PASSWORD`。探针通过 HTTP Basic Auth 写入监控数据。

```bash
export VAULT_ADDR="https://<vault-host>"
export VAULT_OBSERVABILITY_SECRET_PATH="kv/data/CICD/observability"
# VAULT_TOKEN 由 Vault Agent 安全注入到当前 Shell；不要用 env/set 回显秘密值
```

`VAULT_TLS_SECRET_PATH` 可供同一 Shell 中的代理 Vault Agent 读取 TLS 证书秘密；它与监控用户名密码的 Vault 路径用途不同，独立监控安装器不使用该变量。

只核对当前 Shell 是否已传入变量时，可查看状态而不暴露值：

```bash
for name in VAULT_ADDR VAULT_TOKEN; do
  if [[ -n "${!name:-}" ]]; then printf '%s: 已设置\n' "$name"; else printf '%s: 未设置\n' "$name"; fi
done
```

服务端还需注入 `GRAFANA_ADMIN_PASSWORD`，可由 Vault Agent 提供，或用 `read -rsp` 隐藏输入。该值控制 Grafana 首次初始化；已有 Grafana 管理员密码以持久化数据库为准。若 `VAULT_ADDR`、`VAULT_TOKEN`、`VAULT_TLS_SECRET_PATH` 均未设置，服务端会生成随机 Basic Auth 用户名和密码，并仅在部署与健康检查成功后于终端显示一次；不会写入服务器文件或 Ansible 日志，请当场安全保存。若 Vault 变量只提供了一部分则会报错。两端安装命令及帮助命令见[根 README](../../README.md)。

Grafana 当前 VictoriaMetrics 数据源查询地址为容器内网 `http://victoria-metrics:8428`，认证方式是 `No Authentication`，查询监控数据不需要额外 Auth Token。Caddy 写入入口保护探针上报路径。安装器有 Vault 配置时通过当前 Shell 安全读取 `kv/data/CICD/observability` 中 `user`、`password` 并用于 HTTP Basic Auth，不会将这组 Vault 凭据打印到终端或 Ansible 日志。无 Vault 配置时服务端仅在部署成功后输出一次随机生成的凭据；探针端必须读取 Vault 中同一组凭据，或安全输入这组凭据，不能独立生成。探针本地 Vector 配置需要保留认证配置才能持续运行，请确保目标主机配置仅 root 可读。

Grafana Service Account Token 仅供 Grafana MCP 使用，Vault 路径为 `kv/data/observability/mcp`，字段为 `GRAFANA_SERVICE_ACCOUNT_TOKEN`；独立安装入口默认关闭 MCP，因此这不是探针接入凭据。

## 参数

| 变量 | 用途 / 默认值 |
| --- | --- |
| `OBSERVABILITY_DOMAIN` | 服务端域名，默认 `observability.svc.plus` |
| `OBSERVABILITY_NODE_NAME` | 探针节点名，默认主机名 |
| `OBSERVABILITY_ENDPOINT` | HTTPS 中心端地址，默认 `https://observability.svc.plus` |
| `DEPLOY_ENV` | 环境标签，默认 `production` |
| `OBSERVABILITY_XRAY_ENABLED` | 覆盖已有 Xray Exporter 指标采集开关；不安装 Xray |
| `OBSERVABILITY_INSTALLER_REF` | 安装器版本，默认 `main`，可固定完整 commit SHA |
| `OBSERVABILITY_PLAYBOOKS_REF` | playbooks 完整 commit SHA，默认值见架构说明 |

Billing 快照默认关闭。需要继续已有链路时，提供 `VECTOR_BILLING_INGEST_ENABLED=true`、`VECTOR_BILLING_INGEST_URL` 与运行时 `INTERNAL_SERVICE_TOKEN`。

服务端默认关闭可选 MCP，配置目录为 `/opt/observability-server`，Blackbox 主机端口为 `9116`。探针开启 TLS 校验、systemd 日志采集，并使用节点及环境标签上报。

## 验证与恢复

安装器在 `/root/observability-backups/` 备份已有配置，不删除或重置数据库卷。服务端验证 Caddy 配置及本机 Grafana、指标、日志、追踪服务健康；探针验证服务、本机指标和认证日志写入。失败返回非零。

安装后还需检查公网 DNS/TLS，在中心端按节点 `instance` 验证新指标及日志，确认采集时间持续更新。服务启动或写入成功不能单独证明中心端数据验收完成。

失败时保留配置备份，检查目标主机日志，按需恢复相应配置。安装器没有自动数据回滚；迁移、数据库备份及 DNS 切换需单独安排。

运行结束后清理当前 Shell 中的凭据：

```bash
unset VAULT_TOKEN VECTOR_AUTH_USER VECTOR_AUTH_PASSWORD GRAFANA_ADMIN_PASSWORD INTERNAL_SERVICE_TOKEN
```
