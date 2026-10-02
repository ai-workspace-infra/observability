# Observability

监控服务端与主机探针的独立安装入口。部署实现统一复用 [ai-workspace-infra/playbooks](https://github.com/ai-workspace-infra/playbooks)，本仓库仅维护安装脚本、使用文档与安装器验证。

## 一键安装

在目标主机以 root 运行，支持 Debian 12+ / Ubuntu 24.04+（Python 3.11+）。安装前先由 Vault Agent 或受控 Shell 环境注入并 `export` `VAULT_ADDR`（HTTPS）与 `VAULT_TOKEN`。Vault Token 需要读取监控 KV v2 秘密的权限。不要把 token 写入命令参数、脚本或仓库。

可安全确认当前 Shell 是否已传入变量，只打印“已设置/未设置”，不打印值：

```bash
for name in VAULT_ADDR VAULT_TOKEN; do
  if [[ -n "${!name:-}" ]]; then printf '%s: 已设置\n' "$name"; else printf '%s: 未设置\n' "$name"; fi
done
```

**服务端：** 还需提供 `GRAFANA_ADMIN_PASSWORD`。通过 Vault Agent 注入，或在当前 Shell 中隐藏输入：

```bash
read -rsp "Grafana admin password: " GRAFANA_ADMIN_PASSWORD
printf '\n'
export GRAFANA_ADMIN_PASSWORD
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-server.sh | bash
unset GRAFANA_ADMIN_PASSWORD VAULT_TOKEN
```

**探针端：** 安装器从 `kv/data/CICD/observability` 读取 `user`、`password`，并用 HTTP Basic Auth 向中心端写入指标和日志。也可直接注入 `VECTOR_AUTH_USER`、`VECTOR_AUTH_PASSWORD` 代替这组 Vault 字段。

```bash
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-agent.sh | bash
unset VAULT_TOKEN
```

这两个入口也可先查看帮助：

```bash
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-server.sh | bash -s -- --help
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-agent.sh | bash -s -- --help
```

**Grafana 的 Auth Token 说明：** 当前 Grafana 的 VictoriaMetrics 数据源走容器内网地址 `http://victoria-metrics:8428`，数据源设置为 `No Authentication`，因此 Grafana 查询监控数据不需要单独的 Auth Token。探针写入凭据是上面 Vault 中的监控用户名和密码，不是 Grafana Token。只有启用 Grafana MCP 时才使用 Grafana Service Account Token：存放在 Vault KV v2 `kv/data/observability/mcp` 的 `GRAFANA_SERVICE_ACCOUNT_TOKEN` 字段；当前独立安装入口默认关闭 MCP，该 Token 不参与探针安装或数据写入。

探针采集监控数据；XConnect 节点注册仍由 [xconnect-edge-agent](https://github.com/ai-workspace-xstream/xconnect-edge-agent) 管理。

## 仓库范围

- `setup-observability-{server,agent}.sh`：独立部署入口。
- `scripts/observability_install.py`：下载固定版本 playbooks，生成当前主机参数、备份配置、执行部署与健康检查。
- `docs/`：架构及部署说明。
- `tests/`、`.github/workflows/`：安装器契约验证与凭据扫描。
- `LICENSE`、`NOTICE`：许可证与历史来源声明。

[架构说明](docs/zh/architecture.md) · [部署说明](docs/zh/deployment.md)

本地目录名为 `observability`；GitHub 仓库仍为 `ai-workspace-infra/observability.svc.plus`，以上下载地址保持有效。本仓库不再维护旧 Pigsty roles、库存、应用模板、Terraform/Vagrant 或旧全栈初始化器。多主机编排请使用 playbooks 的正式 inventory 和 `deploy_observability_server.yml` / `deploy_observability_agent.yml`。

## 验证

```bash
bash -n setup-observability-server.sh setup-observability-agent.sh
python3 -m unittest discover -s tests -p test_standalone_installers.py -v
```

测试环境需安装 PyYAML。静态测试通过不代表目标主机已经部署或完成中心端数据验收。
