package plugin

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestLookupIdentityUsesScopedTokenAndDoesNotEchoInput(t *testing.T) {
	const rawEmail = "person@example.test"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/observability/internal/xconnect/identity" {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL)
		}
		if r.Header.Get("X-XConnect-Observability-Token") != "scoped-test-token" {
			t.Fatal("scoped token missing")
		}
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["email"] != rawEmail || body["proxyUuid"] != "" {
			t.Fatalf("unexpected resolver request shape: %#v", body)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"found":true,"proxyIdentityRef":"opaque-ref"}`))
	}))
	defer server.Close()
	identity, _, err := lookupIdentity(context.Background(), server.URL, "scoped-test-token", searchRequest{Email: rawEmail})
	if err != nil || !identity.Found || identity.ProxyIdentityRef != "opaque-ref" {
		t.Fatalf("lookup result=%+v err=%v", identity, err)
	}
	encoded, _ := json.Marshal(identity)
	if strings.Contains(string(encoded), rawEmail) {
		t.Fatal("raw email leaked in resolver result")
	}
}

func TestSearchTracesFiltersByOpaqueIdentityAndReturnsSafeSpanFields(t *testing.T) {
	const ref = "opaque-pseudonymous-reference"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/select/jaeger/api/traces" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("service") != "xray" {
			t.Fatalf("service filter missing: %s", r.URL.RawQuery)
		}
		var tags map[string]string
		if err := json.Unmarshal([]byte(r.URL.Query().Get("tags")), &tags); err != nil {
			t.Fatal(err)
		}
		if tags["xconnect.proxy_identity_ref"] != ref {
			t.Fatalf("unexpected identity filter: %#v", tags)
		}
		if r.URL.Query().Get("start") == "" || r.URL.Query().Get("end") == "" || r.URL.Query().Get("limit") != "10" {
			t.Fatalf("time/limit filters missing: %s", r.URL.RawQuery)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[{"traceID":"abc123","spans":[{"operationName":"xconnect.server.vless.authenticated","startTime":1780000000000000,"duration":2500,"tags":[{"key":"email","value":"person@example.test"}]}]}]}`))
	}))
	defer server.Close()
	start := time.Unix(1780000000, 0)
	traces, err := searchTraces(context.Background(), server.URL, ref, start, start.Add(time.Minute), 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(traces) != 1 || traces[0].TraceID != "abc123" || len(traces[0].Spans) != 1 {
		t.Fatalf("unexpected traces: %+v", traces)
	}
	encoded, _ := json.Marshal(traces)
	if strings.Contains(string(encoded), "person@example.test") || strings.Contains(string(encoded), ref) {
		t.Fatal("identity material leaked in trace response")
	}
	if traces[0].Spans[0].DurationMs != 2.5 {
		t.Fatalf("duration conversion mismatch: %+v", traces[0].Spans[0])
	}
}
