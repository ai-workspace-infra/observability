# Observability

监控服务端与主机探针的独立安装入口。部署实现统一复用 [ai-workspace-infra/playbooks](https://github.com/ai-workspace-infra/playbooks)，本仓库仅维护安装脚本、使用文档与安装器验证。

## 一键安装

在目标主机以 root 运行，支持 Debian 12+ / Ubuntu 24.04+（Python 3.11+）。安装前由 Vault 向当前 Shell 注入凭据，详见[部署说明](docs/zh/deployment.md)。

服务端：

```bash
export OBSERVABILITY_DOMAIN="observability.svc.plus"
# 已导出 VAULT_ADDR、VAULT_TOKEN、GRAFANA_ADMIN_PASSWORD
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-server.sh | bash
```

主机探针：

```bash
export OBSERVABILITY_NODE_NAME="$(hostname -f)"
export OBSERVABILITY_ENDPOINT="https://observability.svc.plus"
export DEPLOY_ENV="production"
# 已导出 VAULT_ADDR、VAULT_TOKEN
curl -fsSL https://raw.githubusercontent.com/ai-workspace-infra/observability.svc.plus/main/setup-observability-agent.sh | bash
```

两个脚本支持 `--help`。探针采集监控数据；XConnect 节点注册仍由 [xconnect-edge-agent](https://github.com/ai-workspace-xstream/xconnect-edge-agent) 管理。

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
