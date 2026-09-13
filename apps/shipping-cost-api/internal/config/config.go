package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

const (
	FailureNone      = ""
	FailureQuotes500 = "quotes_500"
	FailureUnready   = "unready"
)

type Config struct {
	AppVersion    string
	RulesVersion  string
	StartDelay    time.Duration
	ShutdownDelay time.Duration
	FailureMode   string
}

func FromEnv() (Config, error) {
	startDelay, err := envSeconds("APP_START_DELAY_SECONDS")
	if err != nil {
		return Config{}, err
	}
	shutdownDelay, err := envSeconds("APP_SHUTDOWN_DELAY_SECONDS")
	if err != nil {
		return Config{}, err
	}
	return Config{
		AppVersion:    envOr("APP_VERSION", "dev"),
		RulesVersion:  envOr("RULES_VERSION", "2026.09"),
		StartDelay:    startDelay,
		ShutdownDelay: shutdownDelay,
		FailureMode:   envOr("APP_FAILURE_MODE", FailureNone),
	}, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envSeconds(key string) (time.Duration, error) {
	raw := os.Getenv(key)
	if raw == "" {
		return 0, nil
	}
	seconds, err := strconv.ParseFloat(raw, 64)
	if err != nil || seconds < 0 {
		return 0, fmt.Errorf("invalid %s: %q", key, raw)
	}
	return time.Duration(seconds * float64(time.Second)), nil
}
