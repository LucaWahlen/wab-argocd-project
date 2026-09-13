package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"wab-argocd/shipping-cost-api/internal/config"
	"wab-argocd/shipping-cost-api/internal/quote"
)

func testConfig() config.Config {
	return config.Config{
		AppVersion:   "test",
		RulesVersion: "rules-test",
	}
}

func serve(t *testing.T, cfg config.Config) (*httptest.Server, *Server) {
	t.Helper()
	s := New(cfg, quote.NewService(cfg), "test-pod")
	ts := httptest.NewServer(s.Handler())
	t.Cleanup(ts.Close)
	return ts, s
}

func getJSON(t *testing.T, url string) (int, http.Header, map[string]any) {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("GET %s: %v", url, err)
	}
	defer resp.Body.Close()
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decoding body: %v", err)
	}
	return resp.StatusCode, resp.Header, body
}

func TestIndexReturnsVersionsAndPod(t *testing.T) {
	ts, _ := serve(t, testConfig())
	status, header, body := getJSON(t, ts.URL+"/")
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if header.Get("X-Application-Version") != "test" || header.Get("X-Rules-Version") != "rules-test" {
		t.Errorf("version headers = %q/%q, want test/rules-test", header.Get("X-Application-Version"), header.Get("X-Rules-Version"))
	}
	if body["pod"] != "test-pod" {
		t.Errorf("pod = %v, want test-pod", body["pod"])
	}
}

func TestLiveAlwaysReadyEndpoint(t *testing.T) {
	ts, _ := serve(t, testConfig())
	status, _, body := getJSON(t, ts.URL+"/health/live")
	if status != http.StatusOK || body["status"] != "ok" {
		t.Errorf("live = %d %v, want 200 ok", status, body)
	}
}

func TestReadyRespectsStartDelay(t *testing.T) {
	cfg := testConfig()
	cfg.StartDelay = 150 * time.Millisecond
	ts, _ := serve(t, cfg)
	status, _, _ := getJSON(t, ts.URL+"/health/ready")
	if status != http.StatusServiceUnavailable {
		t.Errorf("before start delay: status = %d, want 503", status)
	}
	time.Sleep(200 * time.Millisecond)
	status, _, _ = getJSON(t, ts.URL+"/health/ready")
	if status != http.StatusOK {
		t.Errorf("after start delay: status = %d, want 200", status)
	}
}

func TestReadyFailureModeUnready(t *testing.T) {
	cfg := testConfig()
	cfg.FailureMode = config.FailureUnready
	ts, _ := serve(t, cfg)
	status, _, body := getJSON(t, ts.URL+"/health/ready")
	if status != http.StatusServiceUnavailable || body["status"] != "not-ready" {
		t.Errorf("unready failure mode: = %d %v, want 503 not-ready", status, body)
	}
}

func TestSetNotReadyDropsReadiness(t *testing.T) {
	ts, s := serve(t, testConfig())
	status, _, _ := getJSON(t, ts.URL+"/health/ready")
	if status != http.StatusOK {
		t.Fatalf("initial readiness: status = %d, want 200", status)
	}
	s.SetNotReady()
	status, _, body := getJSON(t, ts.URL+"/health/ready")
	if status != http.StatusServiceUnavailable || body["status"] != "not-ready" {
		t.Errorf("after SetNotReady: = %d %v, want 503 not-ready", status, body)
	}
}

func TestQuoteEndpoint(t *testing.T) {
	ts, _ := serve(t, testConfig())
	resp, err := http.Post(ts.URL+"/v1/quotes", "application/json",
		strings.NewReader(`{"weightKg":4.5,"lengthCm":40,"widthCm":30,"heightCm":20,"destinationZone":"EU","service":"express"}`))
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	if resp.Header.Get("X-Rules-Version") != "rules-test" {
		t.Errorf("X-Rules-Version = %q, want rules-test", resp.Header.Get("X-Rules-Version"))
	}
	var body struct {
		ShippingClass string `json:"shippingClass"`
		PriceCents    int    `json:"priceCents"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decoding: %v", err)
	}
	if body.ShippingClass != quote.ClassM || body.PriceCents != 1948 {
		t.Errorf("body = %+v, want parcel-m/1948", body)
	}
}

func TestQuoteEndpointRejectsBadInput(t *testing.T) {
	ts, _ := serve(t, testConfig())

	resp, err := http.Post(ts.URL+"/v1/quotes", "application/json", strings.NewReader("not json"))
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("malformed json: status = %d, want 400", resp.StatusCode)
	}

	resp, err = http.Get(ts.URL + "/v1/quotes")
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("GET /v1/quotes: status = %d, want 405", resp.StatusCode)
	}
}
