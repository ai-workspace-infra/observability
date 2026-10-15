import React, { useState } from 'react';
import { Alert, Button, Field, Input, Stack, Text } from '@grafana/ui';
import { getBackendSrv } from '@grafana/runtime';

const pluginId = 'aiworkspace-xconnectuserdiagnostics-app';
type Trace = { traceId: string; startedAt: string; durationMs: number; spans: Array<{ name: string; startedAt: string; durationMs: number }> };
type SearchResponse = { found: boolean; traces: Trace[] };

export default function App() {
  const [kind, setKind] = useState<'email' | 'proxyUuid'>('email');
  const [identity, setIdentity] = useState('');
  const [from, setFrom] = useState(() => new Date(Date.now() - 15 * 60_000).toISOString().slice(0, 16));
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 16));
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function search(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setResult(null);
    try {
      const payload = await getBackendSrv().post(`/api/plugins/${pluginId}/resources/connections/search`, {
        [kind]: identity.trim(), start: new Date(from).toISOString(), end: new Date(to).toISOString(), limit: 50,
      }) as SearchResponse;
      setResult(payload);
    } catch {
      setError('查询失败。请检查权限、Accounts 身份解析服务和 VictoriaTraces 可用性后重试。');
    } finally { setIdentity(''); setBusy(false); }
  }

  return <main style={{ padding: 24, maxWidth: 1100 }}>
    <Stack direction="column" gap={2}>
      <Text variant="h3">XConnect 用户慢连接诊断</Text>
      <Text color="secondary">查询使用一次性 POST；原始身份不会写入 URL、浏览器存储或结果响应。默认时间窗 15 分钟，最大 24 小时。</Text>
      {error && <Alert title="无法完成查询" severity="error">{error}</Alert>}
      <form onSubmit={search} autoComplete="off">
        <Stack direction="row" gap={2} alignItems="end" wrap="wrap">
          <Field label="身份类型"><select style={{ minWidth: 180, height: 32 }} value={kind} onChange={(e) => setKind(e.currentTarget.value as 'email' | 'proxyUuid')}><option value="email">Email</option><option value="proxyUuid">Proxy UUID</option></select></Field>
          <Field label={kind === 'email' ? 'Email' : 'Proxy UUID'}><Input width={36} type="password" autoComplete="off" value={identity} onChange={(e) => setIdentity(e.currentTarget.value)} /></Field>
          <Field label="开始时间"><Input width={24} type="datetime-local" value={from} onChange={(e) => setFrom(e.currentTarget.value)} /></Field>
          <Field label="结束时间"><Input width={24} type="datetime-local" value={to} onChange={(e) => setTo(e.currentTarget.value)} /></Field>
          <Button type="submit" disabled={busy || !identity.trim()}>{busy ? '查询中…' : '查询慢连接'}</Button>
        </Stack>
      </form>
      {result && <Alert title={result.found ? `找到 ${result.traces.length} 条相关 trace` : '未找到身份'} severity={result.found ? 'info' : 'warning'}>
        Trace 列表按匿名身份引用查询。某阶段未采集时会显示缺失，不能据此判定为 0 ms。
      </Alert>}
      {result?.traces.map((trace) => <section key={trace.traceId} style={{ marginTop: 16, padding: 16, border: '1px solid #343a46' }}>
        <Text variant="h5">{trace.traceId}</Text>
        <Text color="secondary">开始时间 {trace.startedAt} · Trace 总耗时 {trace.durationMs} ms</Text>
        <ol>{trace.spans.map((span, i) => <li key={`${span.name}-${i}`}>{span.name} — {span.startedAt} — {span.durationMs} ms</li>)}</ol>
        <Text color="secondary">阶段列表仅展示 trace 中的可核验 span；客户端建立、出口建立、首响应和重启证据需要相应埋点进入同一 trace。</Text>
      </section>)}
    </Stack>
  </main>;
}
