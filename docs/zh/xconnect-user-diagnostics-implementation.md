# XConnect 用户连接诊断实现

本目录的 `grafana/plugins/xconnect-user-diagnostics-app` 是 Grafana App 查询入口；Dashboard JSON 和服务器安装配置位于 `ai-workspace-infra/playbooks` 的 observability-server role。

## 查询链路

1. 页面仅对 Grafana 管理员开放。用户在本页输入 email 或 Proxy UUID，选择不超过 24 小时的时间窗后发送一次 POST。表单关闭自动补全，提交结束后清空身份字段。
2. Grafana 后端用 Vault 注入的 `IDENTITY_LOOKUP_TOKEN` 调用 Accounts `/api/observability/internal/xconnect/identity`。此 token 只允许访问该解析路由，与通用 `INTERNAL_SERVICE_TOKEN` 分开。
3. Accounts 以当前 Proxy UUID 派生版本化 HMAC 引用。email 与 Proxy UUID 对同一用户返回相同引用，原始身份不返回给 Grafana。
4. 后端使用 VictoriaTraces Jaeger API 的 `service=xray` 与 `xconnect.proxy_identity_ref` 标签查找 trace；页面仅接收 Trace ID、Span 名称、起始时间和持续时间白名单字段。

原始 email/UUID 不进入 URL、Dashboard 变量、localStorage、插件查询结果或错误消息。Accounts token 只保存在 Grafana plugin `secureJsonData`，通过 Vault 在运行时读取。插件不输出请求 body。日志后端、OTel collector 与 trace 标签使用匿名引用关联身份。

## 打包与安装

在插件目录运行 Grafana 官方插件脚手架定义的构建：

```sh
npm install
npm run typecheck
npm run build
go test ./...
mage -v buildAll
```

仓库 release workflow 从 `v*` 标签构建并发布 plugin zip。playbooks 使用不可变版本和必填 SHA-256 下载，不通过 `latest` 或在线安装插件。启用时设置：

- `observability_xconnect_diagnostics_enabled: true`
- `observability_xconnect_diagnostics_plugin_version` 与对应 `observability_xconnect_diagnostics_plugin_sha256`
- Vault `kv/data/observability/xconnect-user-diagnostics` 中的 `IDENTITY_LOOKUP_TOKEN`
- Accounts HTTPS URL（如环境地址不同，覆盖默认值）

Accounts 运行环境也必须把同一份至少 32 字符的随机 token 注入 `XCONNECT_OBSERVABILITY_SEARCH_TOKEN`（Cloud Run Secret Manager 名称为 `xconnect-observability-search-token`，Compose 部署则通过 Ansible Vault 环境变量提供）。Grafana Vault 键与 Accounts runtime secret 的值必须相同；此凭据只授权这条 identity resolver 路由。

关闭此功能时，Grafana App 配置会从 provisioning 中移除；已有 Dashboard JSON 保留，可以用于说明入口和证据边界。插件未签名，因此 playbooks 只把该插件 ID 加入 Grafana unsigned plugin allowlist，其他插件验证策略不变。

## 当前能力边界

此交付提供身份到 trace 的查找与独立 Dashboard 入口。它会显示查询到的 Xray trace/span 实际耗时。客户端真实 DNS/TCP/TLS、Caddy `/split` 与 Unix socket、Agent 重启、目标首响应、节点指标等阶段只有在各自埋点/事件已经随同一连接关联并进入存储后才能显示；未采集字段不得补零，也不能将时间接近的连接合并。当前 Accounts resolver 只解析用户当前 Proxy UUID，凭据轮换历史尚未覆盖。

上线前仍需部署 Accounts 和 Xray PR、发布插件版本、在 playbooks 配置 Vault token 与 checksum，并在 UAT 验证同一 email/UUID 得到同一 trace、非管理员被拒绝、输入不落 URL/日志以及各阶段证据的关联完整度。本次代码提交不代表线上已部署或运行验收通过。
