# XConnect User Diagnostics Grafana App

Admin-only Grafana App for searching XConnect traces by email or Proxy UUID. The form sends the identifier in a POST body to the plugin backend. The backend resolves it through Accounts using a dedicated service token, searches VictoriaTraces by the returned `xconnect.proxy_identity_ref`, and returns only trace IDs and safe span timing fields.

The plugin never stores identifiers in dashboard variables, URL state, local storage, trace output, or error messages. The backend rejects non-admin requests, time windows longer than 24 hours, and requests over 50 traces. Accounts and VictoriaTraces URLs are provisioned as non-secret settings; `identityLookupToken` is provisioned under Grafana `secureJsonData`.

## Development

```sh
npm install
npm run typecheck
npm run build
go test ./...
mage -v buildAll
```

The GitHub release workflow builds an immutable plugin ZIP from `v*` tags. The playbooks role installs a pinned release with a required SHA-256 checksum and enables only this plugin in Grafana's unsigned-plugin allowlist.

This first implementation searches the authenticated Xray trace and displays spans actually returned by VictoriaTraces. It does not infer missing client, Caddy, Agent, host, or restart phases; those require their own correlation spans/events.
