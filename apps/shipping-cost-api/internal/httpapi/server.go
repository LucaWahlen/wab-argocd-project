package httpapi

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"sync/atomic"
	"time"

	"wab-argocd/shipping-cost-api/internal/config"
	"wab-argocd/shipping-cost-api/internal/quote"
)

type Server struct {
	service      *quote.Service
	appVersion   string
	rulesVersion string
	startDelay   time.Duration
	failureMode  string
	startedAt    time.Time
	shutdownNow  atomic.Bool
	podName      string
}

func New(cfg config.Config, service *quote.Service, podName string) *Server {
	return &Server{
		service:      service,
		appVersion:   cfg.AppVersion,
		rulesVersion: cfg.RulesVersion,
		startDelay:   cfg.StartDelay,
		failureMode:  cfg.FailureMode,
		startedAt:    time.Now(),
		podName:      podName,
	}
}

func (s *Server) SetNotReady() { s.shutdownNow.Store(true) }

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /{$}", s.handleIndex)
	mux.HandleFunc("GET /health/live", s.handleLive)
	mux.HandleFunc("GET /health/ready", s.handleReady)
	mux.HandleFunc("POST /v1/quotes", s.handleQuote)
	return s.versionHeaders(mux)
}

func (s *Server) versionHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Application-Version", s.appVersion)
		w.Header().Set("X-Rules-Version", s.rulesVersion)
		next.ServeHTTP(w, r)
	})
}

func (s *Server) ready() bool {
	if s.shutdownNow.Load() {
		return false
	}
	if s.failureMode == config.FailureUnready {
		return false
	}
	return time.Since(s.startedAt) >= s.startDelay
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		slog.Error("writing response", "error", err)
	}
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}
