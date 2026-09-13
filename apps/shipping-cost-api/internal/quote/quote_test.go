package quote

import (
	"net/http"
	"testing"

	"wab-argocd/shipping-cost-api/internal/config"
)

func testService() *Service {
	return NewService(config.Config{AppVersion: "test", RulesVersion: "rules-test"})
}

func validRequest() Request {
	return Request{
		WeightKg:        4.5,
		LengthCm:        40,
		WidthCm:         30,
		HeightCm:        20,
		DestinationZone: "EU",
		Service:         "express",
	}
}

func TestQuoteComputesClassPriceDays(t *testing.T) {
	tests := []struct {
		name      string
		request   Request
		wantClass string
		wantPrice int
		wantDays  int
	}{
		{"DE standard parcel-s", Request{WeightKg: 2, LengthCm: 30, WidthCm: 20, HeightCm: 10, DestinationZone: "DE", Service: "standard"}, ClassS, 499, 1},
		{"DE standard parcel-m", Request{WeightKg: 2.1, LengthCm: 30, WidthCm: 20, HeightCm: 10, DestinationZone: "DE", Service: "standard"}, ClassM, 699, 1},
		{"DE express clamps to one day", Request{WeightKg: 2, LengthCm: 30, WidthCm: 20, HeightCm: 10, DestinationZone: "DE", Service: "express"}, ClassS, 499 * 150 / 100, 1},
		{"EU express parcel-s", Request{WeightKg: 2, LengthCm: 30, WidthCm: 20, HeightCm: 10, DestinationZone: "EU", Service: "express"}, ClassS, 899 * 150 / 100, 2},
		{"EU express parcel-m", Request{WeightKg: 4.5, LengthCm: 40, WidthCm: 30, HeightCm: 20, DestinationZone: "EU", Service: "express"}, ClassM, 1299 * 150 / 100, 2},
		{"WORLD economy parcel-l adds oversize day", Request{WeightKg: 31.5, LengthCm: 120, WidthCm: 120, HeightCm: 120, DestinationZone: "WORLD", Service: "economy"}, ClassL, 3299 * 80 / 100, 9},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, qErr := testService().Quote(tt.request)
			if qErr != nil {
				t.Fatalf("Quote() error = %v, want nil", qErr)
			}
			if got.ShippingClass != tt.wantClass {
				t.Errorf("ShippingClass = %q, want %q", got.ShippingClass, tt.wantClass)
			}
			if got.PriceCents != tt.wantPrice {
				t.Errorf("PriceCents = %d, want %d", got.PriceCents, tt.wantPrice)
			}
			if got.EstimatedDays != tt.wantDays {
				t.Errorf("EstimatedDays = %d, want %d", got.EstimatedDays, tt.wantDays)
			}
			if got.ApplicationVersion != "test" || got.RulesVersion != "rules-test" {
				t.Errorf("versions = %q/%q, want test/rules-test", got.ApplicationVersion, got.RulesVersion)
			}
		})
	}
}

func TestQuoteWeightBoundaries(t *testing.T) {
	tests := []struct {
		weightKg float64
		wantErr  bool
	}{
		{0.01, false},
		{31.5, false},
		{0, true},
		{31.6, true},
	}
	for _, tt := range tests {
		r := validRequest()
		r.WeightKg = tt.weightKg
		_, qErr := testService().Quote(r)
		if (qErr != nil) != tt.wantErr {
			t.Errorf("weight %v: error = %v, wantErr %v", tt.weightKg, qErr, tt.wantErr)
		}
		if qErr != nil && qErr.Code != "WEIGHT_OUT_OF_RANGE" {
			t.Errorf("weight %v: code = %q, want WEIGHT_OUT_OF_RANGE", tt.weightKg, qErr.Code)
		}
	}
}

func TestQuoteDimensionBoundaries(t *testing.T) {
	r := validRequest()
	r.HeightCm = 120.1
	_, qErr := testService().Quote(r)
	if qErr == nil || qErr.Code != "DIMENSION_OUT_OF_RANGE" {
		t.Errorf("HeightCm 120.1: error = %v, want DIMENSION_OUT_OF_RANGE", qErr)
	}
}

func TestQuoteUnknownZoneAndService(t *testing.T) {
	r := validRequest()
	r.DestinationZone = "MARS"
	_, qErr := testService().Quote(r)
	if qErr == nil || qErr.Status != http.StatusBadRequest || qErr.Code != "ZONE_UNKNOWN" {
		t.Errorf("unknown zone: error = %+v, want 400 ZONE_UNKNOWN", qErr)
	}
	r = validRequest()
	r.Service = "drone"
	_, qErr = testService().Quote(r)
	if qErr == nil || qErr.Status != http.StatusBadRequest || qErr.Code != "SERVICE_UNKNOWN" {
		t.Errorf("unknown service: error = %+v, want 400 SERVICE_UNKNOWN", qErr)
	}
}

func TestQuoteMissingRequiredFields(t *testing.T) {
	r := validRequest()
	r.DestinationZone = ""
	_, qErr := testService().Quote(r)
	if qErr == nil || qErr.Code != "ZONE_REQUIRED" {
		t.Errorf("empty zone: error = %+v, want ZONE_REQUIRED", qErr)
	}
	r = validRequest()
	r.Service = ""
	_, qErr = testService().Quote(r)
	if qErr == nil || qErr.Code != "SERVICE_REQUIRED" {
		t.Errorf("empty service: error = %+v, want SERVICE_REQUIRED", qErr)
	}
}

func TestQuoteFailureModeReturns500BeforeValidation(t *testing.T) {
	s := NewService(config.Config{FailureMode: config.FailureQuotes500})
	_, qErr := s.Quote(Request{})
	if qErr == nil || qErr.Status != http.StatusInternalServerError || qErr.Code != "FAILURE_MODE_ACTIVE" {
		t.Fatalf("failure mode quotes_500: error = %+v, want 500 FAILURE_MODE_ACTIVE", qErr)
	}
}
