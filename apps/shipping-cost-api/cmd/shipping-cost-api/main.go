package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"wab-argocd/shipping-cost-api/internal/config"
	"wab-argocd/shipping-cost-api/internal/httpapi"
	"wab-argocd/shipping-cost-api/internal/quote"
)

const listenAddr = ":8080"

func main() {
	cfg, err := config.FromEnv()
	if err != nil {
		slog.Error("invalid configuration", "error", err)
		os.Exit(1)
	}

	podName, err := os.Hostname()
	if err != nil {
		podName = "unknown"
	}

	service := quote.NewService(cfg)
	api := httpapi.New(cfg, service, podName)

	httpServer := &http.Server{Addr: listenAddr, Handler: api.Handler()}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		slog.Info("listening",
			"addr", listenAddr,
			"applicationVersion", cfg.AppVersion,
			"rulesVersion", cfg.RulesVersion,
			"startDelay", cfg.StartDelay.String(),
			"shutdownDelay", cfg.ShutdownDelay.String(),
			"failureMode", cfg.FailureMode,
		)
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("server failed", "error", err)
			os.Exit(1)
		}
	}()

	<-stop
	slog.Info("shutdown signal received", "shutdownDelay", cfg.ShutdownDelay.String())
	api.SetNotReady()
	if cfg.ShutdownDelay > 0 {
		time.Sleep(cfg.ShutdownDelay)
	}
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
	}
	slog.Info("stopped")
}
