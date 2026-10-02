# 部署与验证

## 准备

在目标主机以 root 执行，要求 Debian 12+ / Ubuntu 24.04+ 与 Python 3.11+，并能访问 GitHub、系统软件源和监控端点。安装器按需安装 Python、Ansible 及部署依赖。服务端应先完成公网 DNS 指向与 TLS 所需网络条件。

由 Vault 向当前 Shell 注入并导出 `VAULT_ADDR`（HTTPS）、`VAULT_TOKEN`。默认从 `kv/data/CICD/observability` 读取 `user`、`password`；可用 `VAULT_OBSERVABILITY_SECRET_PATH` 指定其他 KV v2 `/data/` 路径。也可直接注入 `VECTOR_AUTH_USER` 和 `VECTOR_AUTH_PASSWORD`。凭据仅在运行时提供，不使用命令行参数或仓库文件存储。

服务端还需注入 `GRAFANA_ADMIN_PASSWORD`。该值控制初次初始化；已有 Grafana 管理员密码以持久化数据库为准。安装命令见[根 README](../../README.md)。

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
