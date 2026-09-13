package httpapi

import (
	"encoding/json"
	"net/http"

	"wab-argocd/shipping-cost-api/internal/quote"
)

func (s *Server) handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "use GET")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"applicationVersion": s.appVersion,
		"rulesVersion":       s.rulesVersion,
		"pod":                s.podName,
	})
}

func (s *Server) handleLive(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "use GET")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "use GET")
		return
	}
	if !s.ready() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not-ready"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleQuote(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "use POST")
		return
	}
	var req quote.Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "MALFORMED_JSON", "request body is not a valid quote request")
		return
	}
	result, qErr := s.service.Quote(req)
	if qErr != nil {
		writeError(w, qErr.Status, qErr.Code, qErr.Detail)
		return
	}
	writeJSON(w, http.StatusOK, result)
}
