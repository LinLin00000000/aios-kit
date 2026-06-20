package installer

import (
	"strings"
	"testing"
)

func TestCommandPlanRedactsSubscriptionURL(t *testing.T) {
	opts := DefaultOptions()
	opts.ProxySubscriptionURL = "https://example.com/sub?placeholder=PRIVATE-VALUE&user=lin"
	plan, err := NewCommandPlan("./install.sh", opts)
	if err != nil {
		t.Fatalf("NewCommandPlan returned error: %v", err)
	}
	if !strings.Contains(plan.Preview, "PRIVATE-VALUE") {
		t.Fatalf("preview should contain real value for explicit full preview: %s", plan.Preview)
	}
	if strings.Contains(plan.RedactedPreview, "PRIVATE-VALUE") {
		t.Fatalf("redacted preview leaked secret: %s", plan.RedactedPreview)
	}
	if !strings.Contains(plan.RedactedPreview, Redacted) {
		t.Fatalf("redacted preview missing placeholder: %s", plan.RedactedPreview)
	}
}

func TestShellQuote(t *testing.T) {
	tests := map[string]string{
		"simple":              "simple",
		"/tmp/aios":           "/tmp/aios",
		"/tmp/aios kit":       "'/tmp/aios kit'",
		"https://x?a=1&b=two": "'https://x?a=1&b=two'",
		"it's":                "'it'\\''s'",
		"":                    "''",
	}
	for input, want := range tests {
		if got := ShellQuote(input); got != want {
			t.Fatalf("ShellQuote(%q) = %q, want %q", input, got, want)
		}
	}
}
