package quote

import (
	"fmt"
	"net/http"

	"wab-argocd/shipping-cost-api/internal/config"
)

const (
	maxWeightKg     = 31.5
	maxSideCm       = 120.0
	weightClassS    = 2.0
	weightClassM    = 10.0
	oversizeDaysAdd = 1

	ClassS = "parcel-s"
	ClassM = "parcel-m"
	ClassL = "parcel-l"
)

var zoneBasePrices = map[string]map[string]int{
	"DE":    {ClassS: 499, ClassM: 699, ClassL: 999},
	"EU":    {ClassS: 899, ClassM: 1299, ClassL: 1899},
	"WORLD": {ClassS: 1699, ClassM: 2299, ClassL: 3299},
}

var zoneBaseDays = map[string]int{"DE": 1, "EU": 3, "WORLD": 6}

var serviceMultipliers = map[string]int{"standard": 100, "express": 150, "economy": 80}

var serviceDayDeltas = map[string]int{"standard": 0, "express": -1, "economy": 2}

type Request struct {
	WeightKg        float64 `json:"weightKg"`
	LengthCm        float64 `json:"lengthCm"`
	WidthCm         float64 `json:"widthCm"`
	HeightCm        float64 `json:"heightCm"`
	DestinationZone string  `json:"destinationZone"`
	Service         string  `json:"service"`
}

type Response struct {
	ShippingClass      string `json:"shippingClass"`
	PriceCents         int    `json:"priceCents"`
	EstimatedDays      int    `json:"estimatedDays"`
	ApplicationVersion string `json:"applicationVersion"`
	RulesVersion       string `json:"rulesVersion"`
}

type Error struct {
	Status int
	Code   string
	Detail string
}

func (e *Error) Error() string { return e.Code + ": " + e.Detail }

func validationError(code, detail string) *Error {
	return &Error{Status: http.StatusBadRequest, Code: code, Detail: detail}
}

type Service struct {
	appVersion   string
	rulesVersion string
	failureMode  string
}

func NewService(cfg config.Config) *Service {
	return &Service{
		appVersion:   cfg.AppVersion,
		rulesVersion: cfg.RulesVersion,
		failureMode:  cfg.FailureMode,
	}
}

func (s *Service) Quote(r Request) (Response, *Error) {
	if s.failureMode == config.FailureQuotes500 {
		return Response{}, &Error{
			Status: http.StatusInternalServerError,
			Code:   "FAILURE_MODE_ACTIVE",
			Detail: "controlled failure mode active",
		}
	}
	if err := validate(r); err != nil {
		return Response{}, err
	}
	class := shippingClass(r.WeightKg)
	base, ok := zoneBasePrices[r.DestinationZone]
	if !ok {
		return Response{}, validationError("ZONE_UNKNOWN",
			fmt.Sprintf("unknown destinationZone %q", r.DestinationZone))
	}
	multiplier, ok := serviceMultipliers[r.Service]
	if !ok {
		return Response{}, validationError("SERVICE_UNKNOWN",
			fmt.Sprintf("unknown service %q", r.Service))
	}
	days, ok := zoneBaseDays[r.DestinationZone]
	if !ok {
		return Response{}, validationError("ZONE_UNKNOWN",
			fmt.Sprintf("unknown destinationZone %q", r.DestinationZone))
	}
	days += serviceDayDeltas[r.Service]
	if class == ClassL {
		days += oversizeDaysAdd
	}
	if days < 1 {
		days = 1
	}
	return Response{
		ShippingClass:      class,
		PriceCents:         base[class] * multiplier / 100,
		EstimatedDays:      days,
		ApplicationVersion: s.appVersion,
		RulesVersion:       s.rulesVersion,
	}, nil
}

func shippingClass(weightKg float64) string {
	switch {
	case weightKg <= weightClassS:
		return ClassS
	case weightKg <= weightClassM:
		return ClassM
	default:
		return ClassL
	}
}

func validate(r Request) *Error {
	switch {
	case r.WeightKg <= 0 || r.WeightKg > maxWeightKg:
		return validationError("WEIGHT_OUT_OF_RANGE",
			fmt.Sprintf("weightKg must be within (0, %v]", maxWeightKg))
	case r.LengthCm <= 0 || r.LengthCm > maxSideCm ||
		r.WidthCm <= 0 || r.WidthCm > maxSideCm ||
		r.HeightCm <= 0 || r.HeightCm > maxSideCm:
		return validationError("DIMENSION_OUT_OF_RANGE",
			fmt.Sprintf("lengthCm, widthCm and heightCm must be within (0, %v]", maxSideCm))
	case r.DestinationZone == "":
		return validationError("ZONE_REQUIRED", "destinationZone is required")
	case r.Service == "":
		return validationError("SERVICE_REQUIRED", "service is required")
	}
	return nil
}
