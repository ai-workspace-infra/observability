# 架构与维护边界

主机探针通过 Node Exporter、Process Exporter、Blackbox Exporter 和 Vector 采集主机指标与 systemd 日志，使用 HTTPS 向中心端推送。已有 Xray Exporter 可纳入采集。中心端由 Caddy 提供 TLS 与写入认证，Grafana 展示 VictoriaMetrics、VictoriaLogs、VictoriaTraces 与 OTel 链路的数据。

## 唯一部署来源

[playbooks](https://github.com/ai-workspace-infra/playbooks) 管理 Ansible roles、服务模板与多主机编排：

- `deploy_observability_server.yml`：中心服务。
- `deploy_observability_agent.yml`：主机探针。

本仓库的安装器下载固定 commit 的 playbooks，在私有临时目录生成当前主机 inventory 并运行相应入口。默认版本为 `4a35679825b778d401eb9041face098c938ae449`。角色、服务模板和 inventory 不在本仓库复制维护。

服务端安装器对临时副本进行域名、Grafana 初始密码、写入认证与配置权限适配；不会修改 playbooks 仓库。升级固定版本时需验证这些适配仍兼容上游模板，否则安装器会拒绝继续。

## 凭据与数据

监控账号来自运行时变量或 Vault KV v2；真实凭据不能写入脚本或仓库。部署前备份已有配置，重跑保留 Compose 数据卷。备份配置不等于数据库备份或迁移完成。安装器不修改 DNS，也不注册 XConnect 节点。

## 修改与验证

服务角色或模板调整应提交到 playbooks；安装入口与使用说明调整提交到本仓库。修改安装器后运行根 README 中的语法与契约测试，升级 playbooks 时额外进行 Ansible 语法与模板渲染验证。生产验收须在目标主机及中心端检查运行状态、TLS、指标与日志新鲜度。
