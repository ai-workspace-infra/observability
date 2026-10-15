package plugin

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend/resource/httpadapter"
)

type searchRequest struct {
	Email     string `json:"email"`
	ProxyUUID string `json:"proxyUuid"`
	Start     string `json:"start"`
	End       string `json:"end"`
	Limit     int    `json:"limit"`
}
type identityResult struct {
	Found            bool   `json:"found"`
	ProxyIdentityRef string `json:"proxyIdentityRef"`
}
type integrationSettings struct {
	AccountsURL string `json:"accountsUrl"`
	TracesURL   string `json:"tracesUrl"`
}
type jaegerResponse struct {
	Data []jaegerTrace `json:"data"`
}
type jaegerTrace struct {
	TraceID string       `json:"traceID"`
	Spans   []jaegerSpan `json:"spans"`
}
type jaegerSpan struct {
	OperationName string `json:"operationName"`
	StartTime     int64  `json:"startTime"`
	Duration      int64  `json:"duration"`
}
type safeSpan struct {
	Name       string  `json:"name"`
	StartedAt  string  `json:"startedAt"`
	DurationMs float64 `json:"durationMs"`
}
type safeTrace struct {
	TraceID    string     `json:"traceId"`
	StartedAt  string     `json:"startedAt"`
	DurationMs float64    `json:"durationMs"`
	Spans      []safeSpan `json:"spans"`
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Pragma", "no-cache")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

func (a *App) handleConnectionSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	pluginContext := httpadapter.PluginConfigFromContext(r.Context())
	if pluginContext.User == nil || pluginContext.User.Role != "Admin" {
		writeError(w, http.StatusForbidden, "forbidden")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 8<<10)
	var input searchRequest
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil || ((strings.TrimSpace(input.Email) == "") == (strings.TrimSpace(input.ProxyUUID) == "")) {
		writeError(w, http.StatusBadRequest, "provide exactly one email or proxyUuid")
		return
	}
	start, err := time.Parse(time.RFC3339, input.Start)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid time range")
		return
	}
	end, err := time.Parse(time.RFC3339, input.End)
	if err != nil || !end.After(start) || end.Sub(start) > 24*time.Hour || end.After(time.Now().Add(time.Minute)) {
		writeError(w, http.StatusBadRequest, "time range must be within the last 24 hours")
		return
	}
	if input.Limit <= 0 || input.Limit > 50 {
		input.Limit = 50
	}
	settings := pluginContext.AppInstanceSettings
	var integration integrationSettings
	if err := json.Unmarshal(settings.JSONData, &integration); err != nil {
		writeError(w, http.StatusServiceUnavailable, "diagnostics integration is not configured")
		return
	}
	accountsURL := strings.TrimRight(integration.AccountsURL, "/")
	tracesURL := strings.TrimRight(integration.TracesURL, "/")
	token := settings.DecryptedSecureJSONData["identityLookupToken"]
	if accountsURL == "" || tracesURL == "" || token == "" {
		writeError(w, http.StatusServiceUnavailable, "diagnostics integration is not configured")
		return
	}
	identity, status, err := lookupIdentity(r.Context(), accountsURL, token, input)
	if err != nil {
		writeError(w, status, "identity lookup unavailable")
		return
	}
	if !identity.Found || identity.ProxyIdentityRef == "" {
		writeJSON(w, http.StatusOK, map[string]any{"found": false, "traces": []safeTrace{}})
		return
	}
	traces, err := searchTraces(r.Context(), tracesURL, identity.ProxyIdentityRef, start, end, input.Limit)
	if err != nil {
		writeError(w, http.StatusBadGateway, "trace search unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"found": true, "traces": traces})
}

func lookupIdentity(ctx context.Context, baseURL, token string, input searchRequest) (identityResult, int, error) {
	body, err := json.Marshal(map[string]string{"email": input.Email, "proxyUuid": input.ProxyUUID})
	if err != nil {
		return identityResult{}, http.StatusBadGateway, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/api/observability/internal/xconnect/identity", strings.NewReader(string(body)))
	if err != nil {
		return identityResult{}, http.StatusBadGateway, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-XConnect-Observability-Token", token)
	resp, err := (&http.Client{Timeout: 5 * time.Second}).Do(req)
	if err != nil {
		return identityResult{}, http.StatusBadGateway, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return identityResult{}, http.StatusBadGateway, io.ErrUnexpectedEOF
	}
	var out identityResult
	err = json.NewDecoder(io.LimitReader(resp.Body, 16<<10)).Decode(&out)
	return out, http.StatusBadGateway, err
}

func searchTraces(ctx context.Context, baseURL, identityRef string, start, end time.Time, limit int) ([]safeTrace, error) {
	query := url.Values{}
	query.Set("service", "xray")
	tags, _ := json.Marshal(map[string]string{"xconnect.proxy_identity_ref": identityRef})
	query.Set("tags", string(tags))
	query.Set("start", strconv.FormatInt(start.UnixMicro(), 10))
	query.Set("end", strconv.FormatInt(end.UnixMicro(), 10))
	query.Set("limit", strconv.Itoa(limit))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+"/select/jaeger/api/traces?"+query.Encode(), nil)
	if err != nil {
		return nil, err
	}
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, io.ErrUnexpectedEOF
	}
	var data jaegerResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, 4<<20)).Decode(&data); err != nil {
		return nil, err
	}
	result := make([]safeTrace, 0, len(data.Data))
	for _, trace := range data.Data {
		item := safeTrace{TraceID: trace.TraceID, Spans: []safeSpan{}}
		var minStart, maxEnd int64
		for _, span := range trace.Spans {
			started := span.StartTime * 1000 // Jaeger API startTime and duration use microseconds.
			ended := started + span.Duration*1000
			if minStart == 0 || started < minStart {
				minStart = started
			}
			if ended > maxEnd {
				maxEnd = ended
			}
			item.Spans = append(item.Spans, safeSpan{Name: span.OperationName, StartedAt: time.UnixMicro(span.StartTime).UTC().Format(time.RFC3339Nano), DurationMs: float64(span.Duration) / 1000})
		}
		if minStart != 0 {
			item.StartedAt = time.Unix(0, minStart).UTC().Format(time.RFC3339Nano)
			item.DurationMs = float64(maxEnd-minStart) / 1e6
		}
		result = append(result, item)
	}
	return result, nil
}

func (a *App) registerRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/connections/search", a.handleConnectionSearch)
}
